# trading_agent/management/commands/runbacktest.py
import pandas as pd
import pandas_ta as ta
import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from binance.client import Client

from core.models import Cryptocurrency, UserProfile
# (CORREÇÃO) Alterado o import de relativo para absoluto
from trading_agent.models import TradingSignal
from trading_agent.services import get_gemini_trade_decision

# Mock de classes para simular objetos do banco de dados em memória
class MockTechAnalysis:
    def __init__(self, rsi, macd_line, macd_signal, bband_high, bband_low):
        self.rsi = rsi
        self.macd_line = macd_line
        self.macd_signal = macd_signal
        self.bollinger_high = bband_high
        self.bollinger_low = bband_low

class MockSentiment:
    def __init__(self, score=0.5, summary="Sentimento neutro para simulação."):
        self.sentiment_score = score
        self.summary = summary

class MockHolding:
    def __init__(self, quantity, avg_price):
        self.quantity = quantity
        self.average_buy_price = avg_price
        
class Command(BaseCommand):
    help = 'Roda uma simulação de backtesting para a estratégia do agente de IA'

    def add_arguments(self, parser):
        parser.add_argument('--symbol', type=str, help='Símbolo da criptomoeda para backtest (ex: BTC)', default='BTC')
        parser.add_argument('--start', type=str, help='Data de início do backtest (ex: "1 year ago")', default='1 year ago')
        parser.add_argument('--capital', type=float, help='Capital inicial para a simulação em USDT', default=1000.0)

    def handle(self, *args, **options):
        symbol = options['symbol']
        start_date = options['start']
        initial_capital = Decimal(options['capital'])

        self.stdout.write(f"Iniciando backtest para {symbol} desde {start_date} com capital inicial de ${initial_capital:.2f}")

        # 1. Obter dados históricos
        try:
            client = Client()
            crypto = Cryptocurrency.objects.get(symbol=symbol)
            klines = client.get_historical_klines(f"{symbol}{crypto.price_currency}", Client.KLINE_INTERVAL_1DAY, start_date)
            
            if not klines:
                self.stdout.write(self.style.ERROR(f"Não foram encontrados dados históricos para {symbol}."))
                return

            df = pd.DataFrame(klines, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            df['close'] = pd.to_numeric(df['close']).astype(str)
            df.set_index('time', inplace=True)
        except Cryptocurrency.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Criptomoeda {symbol} não encontrada no banco de dados."))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erro ao buscar dados históricos: {e}"))
            return

        # 2. Inicializar simulação
        cash = initial_capital
        crypto_holdings = Decimal('0.0')
        avg_buy_price = Decimal('0.0')
        trades = []
        user_profile = UserProfile.objects.first()
        if not user_profile:
            self.stdout.write(self.style.ERROR("Nenhum UserProfile encontrado para a simulação."))
            return
        
        # 3. Loop de simulação
        for index, row in df.iterrows():
            if len(df.loc[:index]) < 50: 
                continue

            current_price = Decimal(row['close'])
            
            past_data = df.loc[:index].copy()
            past_data['close'] = pd.to_numeric(past_data['close'])

            past_data.ta.rsi(length=14, append=True)
            past_data.ta.macd(fast=12, slow=26, signal=9, append=True)
            past_data.ta.bbands(length=20, std=2, append=True)
            latest_indicators = past_data.iloc[-1]
            
            mock_tech = MockTechAnalysis(
                latest_indicators.get('RSI_14'),
                latest_indicators.get('MACD_12_26_9'),
                latest_indicators.get('MACDs_12_26_9'),
                latest_indicators.get('BBU_20_2.0'),
                latest_indicators.get('BBL_20_2.0')
            )
            mock_sentiment = MockSentiment()
            mock_holding = MockHolding(crypto_holdings, avg_buy_price)

            ai_decision_data = get_gemini_trade_decision(
                user_profile, crypto, mock_tech, mock_sentiment, mock_holding, save_signal=False
            )
            
            time.sleep(2)

            if not ai_decision_data:
                self.stdout.write(self.style.WARNING(f"Não foi possível obter a decisão da IA para {index.date()}. Pulando..."))
                continue

            decision = ai_decision_data.get('decision')
            confidence = ai_decision_data.get('confidence_score')

            if decision == 'BUY' and confidence > 0.7 and cash > 10:
                buy_amount = cash * (user_profile.agent_buy_risk_percentage / Decimal('100.0'))
                crypto_bought = buy_amount / current_price
                
                total_cost = (avg_buy_price * crypto_holdings) + buy_amount
                crypto_holdings += crypto_bought
                avg_buy_price = total_cost / crypto_holdings
                
                cash -= buy_amount
                trades.append({'date': index, 'type': 'BUY', 'price': current_price, 'amount': crypto_bought})
                self.stdout.write(f"{index.date()}: COMPRA de {crypto_bought:.6f} {symbol} a ${current_price:.2f}")

            elif decision == 'SELL' and confidence > 0.4 and crypto_holdings > 0:
                sell_amount = crypto_holdings * (user_profile.agent_sell_risk_percentage / Decimal('100.0'))
                cash += sell_amount * current_price
                crypto_holdings -= sell_amount
                
                if crypto_holdings < Decimal('0.00000001'):
                    avg_buy_price = Decimal('0.0')

                trades.append({'date': index, 'type': 'SELL', 'price': current_price, 'amount': sell_amount})
                self.stdout.write(f"{index.date()}: VENDA de {sell_amount:.6f} {symbol} a ${current_price:.2f}")

        # 4. Apresentar resultados
        final_price = Decimal(df.iloc[-1]['close'])
        final_portfolio_value = cash + crypto_holdings * final_price
        profit_loss = final_portfolio_value - initial_capital
        profit_loss_percent = (profit_loss / initial_capital) * 100

        buy_and_hold_value = (initial_capital / Decimal(df.iloc[0]['close'])) * final_price
        buy_and_hold_pl = buy_and_hold_value - initial_capital
        buy_and_hold_pl_percent = (buy_and_hold_pl / initial_capital) * 100

        self.stdout.write("\n" + "="*40)
        self.stdout.write(self.style.SUCCESS("Backtesting Concluído!"))
        self.stdout.write("="*40)
        self.stdout.write(f"Período Analisado: {df.index[0].date()} a {df.index[-1].date()}")
        self.stdout.write(f"Capital Inicial:      ${initial_capital:12,.2f}")
        self.stdout.write(f"Valor Final (Agente): ${final_portfolio_value:12,.2f}")
        self.stdout.write(self.style.SUCCESS(f"Lucro/Prejuízo:       ${profit_loss:12,.2f} ({profit_loss_percent:.2f}%)"))
        self.stdout.write("-"*40)
        self.stdout.write(f"Valor Final (B&H):    ${buy_and_hold_value:12,.2f}")
        self.stdout.write(f"Lucro/Prejuízo (B&H): ${buy_and_hold_pl:12,.2f} ({buy_and_hold_pl_percent:.2f}%)")
        self.stdout.write("-"*40)
        self.stdout.write(f"Total de Trades: {len(trades)}")
        self.stdout.write("="*40)

