# trading_agent/tasks.py
import pandas as pd
import pandas_ta as ta
import requests
import time
import json
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.db.models import F, Sum, Q, Value, CharField
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404

from django.conf import settings
from binance.client import Client
from newsapi import NewsApiClient

from core.models import Cryptocurrency, UserProfile, Holding, Transaction
from .models import TechnicalAnalysis, MarketSentiment, TradingSignal, BacktestReport, StrategyLog
from .services import get_gemini_trade_decision, execute_trade_from_signal, get_gemini_sentiment_analysis, get_gemini_reflection

@shared_task(name="trading_agent.tasks.calculate_technical_indicators_for_all_cryptos")
def calculate_technical_indicators_for_all_cryptos():
    client = Client()
    for crypto in Cryptocurrency.objects.all():
        try:
            klines = client.get_klines(symbol=f"{crypto.symbol}{crypto.price_currency}", interval=Client.KLINE_INTERVAL_1DAY, limit=200)
            if not klines: continue
            
            df = pd.DataFrame(klines, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            df.ta.rsi(length=14, append=True); df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True); df.ta.atr(length=14, append=True)
            
            latest = df.iloc[-1]
            TechnicalAnalysis.objects.update_or_create(
                cryptocurrency=crypto, timeframe='1d', timestamp__date=timezone.now().date(),
                defaults={
                    'rsi': latest.get('RSI_14'), 'macd_line': latest.get('MACD_12_26_9'),
                    'macd_signal': latest.get('MACDs_12_26_9'), 'bollinger_high': latest.get('BBU_20_2.0'),
                    'bollinger_low': latest.get('BBL_20_2.0'), 'atr': latest.get('ATRr_14'),
                    'timestamp': timezone.now()
                }
            )
        except Exception as e:
            print(f"Erro ao calcular indicadores para {crypto.symbol}: {e}")
    return "Análises técnicas concluídas."

@shared_task(name="trading_agent.tasks.analyze_market_sentiment_for_all_cryptos")
def analyze_market_sentiment_for_all_cryptos():
    newsapi = NewsApiClient(api_key=settings.NEWS_API_KEY)
    profiles_with_keys = UserProfile.objects.exclude(Q(_gemini_api_key__isnull=True) | Q(_gemini_api_key__exact=''))
    if not profiles_with_keys.exists():
        return "Nenhum usuário com chave de API Gemini para analisar sentimento."

    profile_for_analysis = profiles_with_keys.first()
    
    cryptos_to_analyze = Cryptocurrency.objects.filter(symbol__in=['BTC', 'ETH']) 
    
    for crypto in cryptos_to_analyze:
        try:
            query = f'"{crypto.name}" OR "{crypto.symbol}" AND (crypto OR cryptocurrency OR blockchain)'
            all_articles = newsapi.get_everything(q=query, language='en', sort_by='relevancy', page_size=20)
            if not all_articles or not all_articles.get('articles'): continue

            headlines = "\n".join([article['title'] for article in all_articles['articles']])
            sentiment_data = get_gemini_sentiment_analysis(profile_for_analysis, crypto, headlines)

            if sentiment_data:
                MarketSentiment.objects.update_or_create(
                    cryptocurrency=crypto, timestamp__date=timezone.now().date(),
                    defaults={
                        'sentiment_score': sentiment_data.get('sentiment_score'),
                        'summary': sentiment_data.get('summary'),
                        'raw_news_data': headlines, 'timestamp': timezone.now()
                    }
                )
                time.sleep(5)
        except Exception as e:
            print(f"Erro ao analisar sentimento para {crypto.symbol}: {e}")
    return f"Análises de sentimento concluídas."

@shared_task(name="trading_agent.tasks.run_trading_cycle_for_all_users")
def run_trading_cycle_for_all_users():
    active_profiles = UserProfile.objects.filter(enable_auto_trading=True).exclude(Q(_gemini_api_key__isnull=True) | Q(_gemini_api_key__exact=''))
    if not active_profiles: return "Nenhum usuário com trading automático e chave de IA ativado."
    
    cryptos_to_analyze = Cryptocurrency.objects.filter(symbol__in=['BTC', 'ETH'])
    
    for crypto in cryptos_to_analyze:
        print(f"--- Iniciando ciclo de análise para {crypto.symbol} ---")
        
        latest_tech_analyses = list(TechnicalAnalysis.objects.filter(cryptocurrency=crypto).order_by('-timestamp')[:3])
        latest_sentiments = list(MarketSentiment.objects.filter(cryptocurrency=crypto).order_by('-timestamp')[:3])
        
        if len(latest_tech_analyses) < 3 or len(latest_sentiments) < 3:
            print(f"Dados históricos insuficientes para {crypto.symbol}. Pulando análise.")
            continue

        for profile in active_profiles:
            current_holding = Holding.objects.filter(user_profile=profile, cryptocurrency=crypto).first()
            
            print(f"Analisando {crypto.symbol} para o usuário {profile.user.username}...")
            get_gemini_trade_decision(
                profile, crypto, latest_tech_analyses, latest_sentiments, current_holding
            )
            time.sleep(2)

    return f"Ciclo de decisão concluído para {cryptos_to_analyze.count()} moeda(s) e {active_profiles.count()} usuário(s)."

@shared_task(name="trading_agent.tasks.process_unexecuted_signals")
def process_unexecuted_signals():
    signals_to_process = TradingSignal.objects.filter(is_executed=False, decision__in=['BUY', 'SELL'])
    if not signals_to_process: return "Nenhum novo sinal para processar."
    
    executable_signals = [s for s in signals_to_process if s.confidence_score >= s.user_profile.agent_confidence_threshold]
    if not executable_signals: return "Nenhum sinal de alta confiança para executar."

    for signal in executable_signals:
        execute_trade_from_signal(signal)
    return f"{len(executable_signals)} sinais processados."

@shared_task(name="trading_agent.tasks.reflect_on_performance")
def reflect_on_performance():
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)
    active_profiles = UserProfile.objects.filter(enable_auto_trading=True).exclude(Q(_gemini_api_key__isnull=True) | Q(_gemini_api_key__exact=''))

    for profile in active_profiles:
        agent_trades = Transaction.objects.filter(user_profile=profile, signal__isnull=False, transaction_date__range=(start_date, end_date)).select_related('cryptocurrency')
        if not agent_trades.exists():
            continue

        trades_by_crypto = {}
        for trade in agent_trades:
            if trade.cryptocurrency.symbol not in trades_by_crypto:
                trades_by_crypto[trade.cryptocurrency.symbol] = []
            trades_by_crypto[trade.cryptocurrency.symbol].append(trade)

        performance_data, total_pl, win_count = [], Decimal('0.0'), 0
        for symbol, trades in trades_by_crypto.items():
            crypto = trades[0].cryptocurrency
            buy_cost = sum(t.total_value for t in trades if t.transaction_type == 'BUY')
            sell_revenue = sum(t.total_value for t in trades if t.transaction_type == 'SELL')
            net_cash_flow = sell_revenue - buy_cost
            current_price = crypto.current_price or Decimal('0')
            buy_qty = sum(t.quantity_crypto for t in trades if t.transaction_type == 'BUY')
            sell_qty = sum(t.quantity_crypto for t in trades if t.transaction_type == 'SELL')
            net_asset_change_qty = buy_qty - sell_qty
            value_of_net_asset_change = net_asset_change_qty * current_price
            period_pl = net_cash_flow + value_of_net_asset_change
            total_pl += period_pl
            if period_pl > 0: win_count += 1
            performance_data.append(f"- Ativo: {symbol}, Resultado: {'Lucro' if period_pl > 0 else 'Prejuízo'} de {period_pl:.2f}")

        win_rate = (win_count / len(trades_by_crypto)) * 100 if trades_by_crypto else 0
        summary_dict = {'total_pl': f"{total_pl:.2f}", 'win_rate': f"{win_rate:.2f}%", 'total_assets_traded': len(trades_by_crypto)}
        performance_str = "\n".join(performance_data)
        full_report_str = f"Resumo Geral: {summary_dict}\n\nTrades Detalhados:\n{performance_str}"
        
        ai_analysis = get_gemini_reflection(profile, full_report_str)
        if ai_analysis:
            StrategyLog.objects.create(user_profile=profile, period_start_date=start_date, period_end_date=end_date, performance_summary=summary_dict, ai_reflection=ai_analysis.get("ai_reflection", "N/A"), suggested_modifications=ai_analysis.get("suggested_modifications", "N/A"))
        time.sleep(10)
    return "Ciclo de reflexão de performance concluído."

@shared_task(name="trading_agent.tasks.run_backtest_task")
def run_backtest_task(report_id):
    report = get_object_or_404(BacktestReport, id=report_id)
    try:
        report.status = 'RUNNING'; report.save()
        user_profile, crypto = report.user_profile, Cryptocurrency.objects.get(symbol=report.symbol)

        client = Client()
        klines = client.get_historical_klines(f"{crypto.symbol}{crypto.price_currency}", Client.KLINE_INTERVAL_1DAY, report.start_date)
        
        REQUIRED_KLINES_FOR_INDICATORS = 35 
        if not klines or len(klines) < REQUIRED_KLINES_FOR_INDICATORS:
             raise ValueError(f"Dados históricos insuficientes para o backtest. Necessário no mínimo {REQUIRED_KLINES_FOR_INDICATORS} dias de dados, mas foram obtidos {len(klines) if klines else 0}.")

        df = pd.DataFrame(klines, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        df.set_index(pd.to_datetime(df['time'], unit='ms'), inplace=True)
        for col in ['open', 'high', 'low', 'close']: df[col] = pd.to_numeric(df[col])

        cash, crypto_holdings, trades = report.initial_capital, Decimal('0.0'), 0
        
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        
        df.fillna(0, inplace=True)
        df['MACD_diff'] = df['MACD_12_26_9'] - df['MACDs_12_26_9']
        
        loop_start_index = REQUIRED_KLINES_FOR_INDICATORS
        if len(df) <= loop_start_index:
             raise ValueError(f"Dados históricos insuficientes após o período de warm-up dos indicadores.")

        for i in range(loop_start_index, len(df)):
            current_row = df.iloc[i]
            previous_row = df.iloc[i-1]
            current_price = Decimal(current_row['close'])

            buy_condition = (current_row['MACD_diff'] > 0 and previous_row['MACD_diff'] <= 0 and current_row['RSI_14'] < 70)
            sell_condition = (current_row['MACD_diff'] < 0 and previous_row['MACD_diff'] >= 0 and current_row['RSI_14'] > 30)
            
            if buy_condition and cash > 10:
                buy_amount = cash * (user_profile.agent_buy_risk_percentage / Decimal('100.0'))
                crypto_bought = buy_amount / current_price
                crypto_holdings += crypto_bought; cash -= buy_amount; trades += 1
            elif sell_condition and crypto_holdings > 0:
                sell_amount = crypto_holdings * (user_profile.agent_sell_risk_percentage / Decimal('100.0'))
                cash += sell_amount * current_price; crypto_holdings -= sell_amount; trades += 1

        final_price = Decimal(df.iloc[-1]['close'])
        report.final_value = cash + crypto_holdings * final_price
        
        if report.initial_capital > 0:
            report.profit_loss_percent = ((report.final_value - report.initial_capital) / report.initial_capital) * 100
        else:
            report.profit_loss_percent = Decimal('0.0')

        initial_price = Decimal(df.iloc[0]['close'])
        if initial_price > 0:
            buy_and_hold_value = (report.initial_capital / initial_price) * final_price
            if report.initial_capital > 0:
                report.buy_and_hold_profit_loss_percent = ((buy_and_hold_value - report.initial_capital) / report.initial_capital) * 100
            else:
                report.buy_and_hold_profit_loss_percent = Decimal('0.0')
        else:
            report.buy_and_hold_profit_loss_percent = Decimal('0.0')
            
        report.total_trades = trades
        report.status = 'COMPLETED'
    except ValueError as ve: 
        report.status = 'FAILED'; report.error_message = str(ve)
        print(f"ERRO DE VALIDAÇÃO NO BACKTEST {report.id}: {ve}")
    except Exception as e:
        report.status = 'FAILED'; report.error_message = str(e)
        print(f"ERRO INESPERADO NO BACKTEST {report.id}: {e}")
    finally:
        report.completed_at = timezone.now()
        report.save()

    return f"Backtest {report.id} concluído."
