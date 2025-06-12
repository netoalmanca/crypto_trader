# trading_agent/services.py
import requests
import json
from decimal import Decimal
from django.conf import settings
from .models import TradingSignal
from binance.client import Client
from binance.exceptions import BinanceAPIException
# (ATUALIZADO) Garante que a importação usa o nome correto da nova função.
from core.views import get_binance_client, _process_successful_order, adjust_quantity_to_lot_size
from core.models import Holding

def get_gemini_trade_decision(profile, crypto, tech_data, sentiment_data, holding_data, save_signal=True):
    """
    Monta o prompt, consulta a API Gemini e, opcionalmente, salva o sinal de trading.
    """
    prompt = f"""
    Você é um experiente analista quantitativo e trader de criptomoedas. Sua tarefa é analisar os dados fornecidos e gerar um sinal de trade (compra, venda ou manter) para o ativo {crypto.symbol} para um usuário com perfil de risco moderado.

    **Contexto do Portfólio do Usuário:**
    - Moeda Preferida: {profile.preferred_fiat_currency}
    - Possui {holding_data.quantity if holding_data else '0'} de {crypto.symbol}.
    - Preço médio de compra: {holding_data.average_buy_price if holding_data else 'N/A'}.

    **Análise Técnica (Timeframe Diário):**
    - RSI: {tech_data.rsi} (Valores < 30 indicam sobrevenda, > 70 sobrecompra)
    - Linha MACD: {tech_data.macd_line}
    - Sinal MACD: {tech_data.macd_signal} (Cruzamento do MACD acima da linha de sinal é otimista)
    - Banda de Bollinger Superior: {tech_data.bollinger_high}
    - Banda de Bollinger Inferior: {tech_data.bollinger_low}
    - Preço Atual: {crypto.current_price}

    **Análise de Sentimento:**
    - Pontuação de Sentimento: {sentiment_data.sentiment_score} (de -1.0 a +1.0)
    - Resumo das Notícias: "{sentiment_data.summary}"

    **Instruções:**
    Baseado em TODOS os dados acima, aplique uma estratégia de **Swing Trading**. Considere a confluência de indicadores. Um RSI baixo junto com um cruzamento otimista do MACD e um sentimento positivo é um forte sinal de compra. O oposto é um sinal de venda. Se os sinais forem mistos ou fracos, a decisão deve ser 'HOLD'.

    Responda **APENAS** com um objeto JSON contendo as seguintes chaves:
    - "decision": uma string, "BUY", "SELL", ou "HOLD".
    - "confidence_score": um float de 0.0 a 1.0.
    - "stop_loss_price": um float, representando o preço de stop-loss sugerido.
    - "take_profit_price": um float, representando o preço para realização de lucro.
    - "justification": uma string com a sua explicação concisa em português.
    """

    gemini_api_key = settings.GEMINI_API_KEY
    if not gemini_api_key:
        print("Chave da API do Gemini não configurada.")
        return None

    api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={gemini_api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        full_response_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        json_text = full_response_text.strip().replace("```json", "").replace("```", "").strip()
        
        ai_data = json.loads(json_text)

        if save_signal:
            signal = TradingSignal.objects.create(
                user_profile=profile,
                cryptocurrency=crypto,
                decision=ai_data.get('decision', 'HOLD').upper(),
                confidence_score=Decimal(ai_data.get('confidence_score', 0.0)),
                stop_loss_price=Decimal(ai_data.get('stop_loss_price', 0.0)),
                take_profit_price=Decimal(ai_data.get('take_profit_price', 0.0)),
                justification=ai_data.get('justification', 'Nenhuma justificativa fornecida.')
            )
            return signal
        else:
            return ai_data

    except (requests.exceptions.RequestException, KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Erro ao comunicar com a API Gemini ou ao processar a resposta: {e}")
        return None


def execute_trade_from_signal(signal):
    """
    Executa uma ordem na Binance baseada em um TradingSignal.
    """
    user_profile = signal.user_profile
    # (ATUALIZADO) Usa a nova função para obter o cliente
    client = get_binance_client(user_profile=user_profile)

    if not client:
        print(f"Cliente Binance inválido para o usuário {user_profile.user.username}.")
        return

    crypto = signal.cryptocurrency
    api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
    
    try:
        if signal.decision == 'BUY':
            quote_currency = crypto.price_currency
            balance = client.get_asset_balance(asset=quote_currency)
            available_balance = Decimal(balance['free'])
            
            buy_risk = user_profile.agent_buy_risk_percentage / Decimal('100.0')
            order_value = available_balance * buy_risk
            
            if order_value < 10:
                print(f"Valor da ordem ({order_value:.2f}) abaixo do mínimo para {user_profile.user.username}.")
                return

            print(f"Executando ordem de COMPRA a mercado para {api_symbol} no valor de {order_value:.2f}")
            order_response = client.order_market_buy(symbol=api_symbol, quoteOrderQty=f"{order_value:.2f}")

        elif signal.decision == 'SELL':
            holding = Holding.objects.get(user_profile=user_profile, cryptocurrency=crypto)
            
            sell_risk = user_profile.agent_sell_risk_percentage / Decimal('100.0')
            quantity_to_sell = holding.quantity * sell_risk

            symbol_info = client.get_symbol_info(api_symbol)
            lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            if lot_size_filter:
                quantity_to_sell = adjust_quantity_to_lot_size(str(quantity_to_sell), lot_size_filter['stepSize'])

            if quantity_to_sell <= 0:
                print(f"Quantidade a vender para {api_symbol} é zero ou negativa após ajustes.")
                return

            print(f"Executando ordem de VENDA a mercado para {api_symbol} na quantidade de {quantity_to_sell}")
            order_response = client.order_market_sell(symbol=api_symbol, quantity=f'{quantity_to_sell:.8f}'.rstrip('0').rstrip('.'))

        else:
            return

        _process_successful_order(user_profile, order_response, crypto, signal=signal)
        
        signal.is_executed = True
        signal.save()
        print(f"Ordem para {api_symbol} executada e registrada com sucesso.")

    except Holding.DoesNotExist:
        print(f"Sinal de VENDA para {user_profile.user.username}, mas ele não possui {crypto.symbol}.")
    except BinanceAPIException as e:
        print(f"Erro da API Binance ao executar ordem para {user_profile.user.username} no par {api_symbol}: {e}")
    except Exception as e:
        print(f"Erro inesperado ao executar sinal de trade {signal.id}: {e}")
