import pandas as pd
import pandas_ta as ta
import requests
from celery import shared_task
from django.conf import settings
from binance.client import Client

from core.models import Cryptocurrency
from .models import TechnicalAnalysis, MarketSentiment

from core.models import UserProfile, Holding
from .services import get_gemini_trade_decision

from .models import TradingSignal
from .services import execute_trade_from_signal

@shared_task(name="trading_agent.tasks.run_trading_cycle_for_all_users")
def run_trading_cycle_for_all_users():
    """
    Tarefa principal que roda periodicamente para gerar sinais de trading para
    todos os usuários que ativaram o agente.
    """
    active_profiles = UserProfile.objects.filter(enable_auto_trading=True)
    if not active_profiles:
        return "Nenhum usuário com trading automático ativado."

    print(f"Iniciando ciclo de decisão para {active_profiles.count()} usuário(s).")

    # Para este exemplo, vamos focar em apenas uma cripto (BTC)
    # Em um sistema real, você faria um loop ou selecionaria os ativos mais relevantes
    try:
        crypto_to_trade = Cryptocurrency.objects.get(symbol='BTC')
    except Cryptocurrency.DoesNotExist:
        return "BTC não encontrado no banco de dados. Ciclo encerrado."

    # Pega as análises mais recentes
    latest_tech_analysis = TechnicalAnalysis.objects.filter(cryptocurrency=crypto_to_trade).order_by('-timestamp').first()
    latest_sentiment = MarketSentiment.objects.filter(cryptocurrency=crypto_to_trade).order_by('-timestamp').first()

    if not latest_tech_analysis or not latest_sentiment:
        return "Dados de análise técnica ou sentimento não estão disponíveis para o BTC."

    for profile in active_profiles:
        current_holding = Holding.objects.filter(user_profile=profile, cryptocurrency=crypto_to_trade).first()

        print(f"Gerando sinal para o usuário: {profile.user.username}")

        # Chama o serviço para obter a decisão da IA
        get_gemini_trade_decision(
            profile=profile,
            crypto=crypto_to_trade,
            tech_data=latest_tech_analysis,
            sentiment_data=latest_sentiment,
            holding_data=current_holding
        )
    return f"Ciclo de decisão concluído para {active_profiles.count()} usuário(s)."

@shared_task(name="trading_agent.tasks.calculate_technical_indicators_for_all_cryptos")
def calculate_technical_indicators_for_all_cryptos():
    """Calcula e salva indicadores técnicos para todas as criptomoedas no banco."""
    client = Client() # Cliente público para dados de mercado
    for crypto in Cryptocurrency.objects.all():
        try:
            klines = client.get_klines(symbol=f"{crypto.symbol}{crypto.price_currency}", interval=Client.KLINE_INTERVAL_1DAY, limit=200)
            if not klines: continue
            
            df = pd.DataFrame(klines, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            df['close'] = pd.to_numeric(df['close'])
            
            # Usando pandas-ta para calcular indicadores
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            
            latest = df.iloc[-1]
            TechnicalAnalysis.objects.create(
                cryptocurrency=crypto,
                timeframe='1d',
                rsi=latest.get('RSI_14'),
                macd_line=latest.get('MACD_12_26_9'),
                macd_signal=latest.get('MACDs_12_26_9'),
                bollinger_high=latest.get('BBU_20_2.0'),
                bollinger_low=latest.get('BBL_20_2.0'),
            )
        except Exception as e:
            print(f"Erro ao calcular indicadores para {crypto.symbol}: {e}")
    return "Análises técnicas concluídas."


@shared_task(name="trading_agent.tasks.analyze_market_sentiment_for_all_cryptos")
def analyze_market_sentiment_for_all_cryptos():
    """Busca notícias e usa a IA para analisar o sentimento de cada criptomoeda."""
    for crypto in Cryptocurrency.objects.filter(symbol__in=['BTC', 'ETH']): # Exemplo: rodar apenas para BTC e ETH
        # NOTA: Integre uma API de notícias real aqui (ex: NewsAPI, Bing News)
        # Para este exemplo, usaremos dados mockados.
        headlines = f"Notícias sobre {crypto.name}: Investidores otimistas, mas reguladores trazem cautela."
        
        prompt = f"""
        Analise o sentimento das seguintes manchetes de notícias sobre {crypto.name}: "{headlines}".
        Responda em formato JSON com duas chaves:
        1. "sentiment_score": um número de -1.0 (muito negativo) a 1.0 (muito positivo).
        2. "summary": um resumo conciso (1-2 frases) em português explicando o sentimento geral do mercado para este ativo.
        """
        
        try:
            # Reutilize a lógica de chamada da API Gemini de `core/views.py`
            # Esta função `call_gemini_api` precisaria ser criada em um módulo de serviços.
            # ai_json_response = call_gemini_api(prompt) 
            
            # Resposta mockada para o exemplo:
            ai_json_response = {'sentiment_score': 0.65, 'summary': 'O sentimento é majoritariamente positivo devido ao otimismo dos investidores, embora a incerteza regulatória represente um risco.'}

            MarketSentiment.objects.create(
                cryptocurrency=crypto,
                sentiment_score=ai_json_response['sentiment_score'],
                summary=ai_json_response['summary'],
                raw_news_data=headlines
            )
        except Exception as e:
            print(f"Erro ao analisar sentimento para {crypto.symbol}: {e}")
    return "Análises de sentimento concluídas."

@shared_task(name="trading_agent.tasks.process_unexecuted_signals")
def process_unexecuted_signals():
    """
    Busca por sinais de trade não executados que atendam ao critério de confiança
    e os envia para execução.
    """
    # Limiar de confiança importado do settings
    confidence_threshold = settings.AGENT_CONFIDENCE_THRESHOLD

    # Busca todos os sinais de COMPRA ou VENDA não executados com confiança suficiente
    signals_to_process = TradingSignal.objects.filter(
        is_executed=False,
        decision__in=['BUY', 'SELL'],
        confidence_score__gte=confidence_threshold
    ).select_related('user_profile', 'cryptocurrency')

    if not signals_to_process:
        return "Nenhum novo sinal de alta confiança para executar."

    print(f"Encontrados {signals_to_process.count()} sinais de alta confiança para processar.")

    for signal in signals_to_process:
        print(f"Processando sinal {signal.id} ({signal.decision} {signal.cryptocurrency.symbol}) para {signal.user_profile.user.username}")
        execute_trade_from_signal(signal)

    return f"{signals_to_process.count()} sinais processados."