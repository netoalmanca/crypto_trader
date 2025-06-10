# core/tasks.py
from celery import shared_task
from celery.schedules import crontab
from django.conf import settings
from django.utils import timezone
from decimal import Decimal, InvalidOperation

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
import requests.exceptions 

from .models import Cryptocurrency, ExchangeRate, FIAT_CURRENCY_CHOICES, BASE_RATE_CURRENCY, UserProfile, Holding, PortfolioSnapshot

@shared_task(
    bind=True, name="core.tasks.update_all_cryptocurrency_prices",
    autoretry_for=(BinanceRequestException, requests.exceptions.RequestException),
    retry_backoff=True, retry_kwargs={'max_retries': 3}
)
def update_all_cryptocurrency_prices(self):
    print(f"[{timezone.now()}] Iniciando tarefa: update_all_cryptocurrency_prices (Tentativa: {self.request.retries + 1})")
    client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, tld='com', testnet=settings.BINANCE_TESTNET)
    cryptocurrencies = Cryptocurrency.objects.all()
    if not cryptocurrencies.exists(): return "Nenhuma criptomoeda para atualizar."
    updated_count = 0; failed_symbols = []
    for crypto in cryptocurrencies:
        api_symbol_pair = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            ticker_data = client.get_ticker(symbol=api_symbol_pair) 
            if ticker_data and 'lastPrice' in ticker_data:
                new_price = Decimal(ticker_data['lastPrice'])
                if new_price != crypto.current_price or crypto.current_price is None:
                    crypto.current_price = new_price; crypto.last_updated = timezone.now(); crypto.save()
                    updated_count += 1
            else: failed_symbols.append(api_symbol_pair)
        except (BinanceAPIException, InvalidOperation) as e:
            print(f"Erro para {api_symbol_pair}: {e} - Não será tentado novamente.")
            failed_symbols.append(api_symbol_pair)
    result_message = f"Preços finalizados. {updated_count} atualizados. Falhas: {len(failed_symbols)}."
    if failed_symbols: print(f"Símbolos com falha: {', '.join(failed_symbols)}")
    return result_message

@shared_task(
    bind=True, name="core.tasks.update_exchange_rates",
    autoretry_for=(BinanceRequestException, requests.exceptions.RequestException),
    retry_backoff=True, retry_kwargs={'max_retries': 3}
)
def update_exchange_rates(self):
    print(f"[{timezone.now()}] Iniciando tarefa: update_exchange_rates (Tentativa: {self.request.retries + 1})")
    client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, tld='com', testnet=settings.BINANCE_TESTNET)
    target_fiat_currencies = [c[0] for c in FIAT_CURRENCY_CHOICES if c[0] != BASE_RATE_CURRENCY]
    if not target_fiat_currencies: return "Nenhuma moeda fiat alvo."
    updated_count = 0; failed_symbols = []
    for fiat_code in target_fiat_currencies:
        if (BASE_RATE_CURRENCY, fiat_code) in [('USDT', 'USD'), ('USD', 'USDT')]: rate = Decimal('1.0')
        else:
            api_symbol_pair = f"{BASE_RATE_CURRENCY}{fiat_code}"
            try:
                ticker = client.get_symbol_ticker(symbol=api_symbol_pair)
                if ticker and 'price' in ticker: rate = Decimal(ticker['price'])
                else: failed_symbols.append(api_symbol_pair); continue
            except BinanceAPIException as e:
                print(f"Erro API para par de câmbio {api_symbol_pair}: {e.message}")
                failed_symbols.append(api_symbol_pair); continue
        try:
            ExchangeRate.objects.update_or_create(from_currency=BASE_RATE_CURRENCY, to_currency=fiat_code, defaults={'rate': rate})
            updated_count += 1
        except Exception as e:
            print(f"Erro ao salvar taxa {BASE_RATE_CURRENCY}->{fiat_code}: {e}")
            failed_symbols.append(f"{BASE_RATE_CURRENCY}->{fiat_code}")
    result_message = f"Taxas de câmbio finalizadas. {updated_count} atualizadas. Falhas: {len(failed_symbols)}."
    if failed_symbols: print(f"Pares com falha: {', '.join(failed_symbols)}")
    return result_message

# NOVA TAREFA
@shared_task(name="core.tasks.create_daily_portfolio_snapshots")
def create_daily_portfolio_snapshots():
    """
    Cria um snapshot diário do valor total do portfólio para cada usuário.
    Projetado para rodar uma vez ao dia via Celery Beat.
    """
    today = timezone.now().date()
    print(f"[{timezone.now()}] Iniciando tarefa: create_daily_portfolio_snapshots para {today}")
    
    users_with_holdings = UserProfile.objects.filter(holdings__isnull=False).distinct()
    exchange_rates = {rate.to_currency: rate.rate for rate in ExchangeRate.objects.filter(from_currency=BASE_RATE_CURRENCY)}
    exchange_rates[BASE_RATE_CURRENCY] = Decimal('1.0')
    
    created_count = 0
    for profile in users_with_holdings:
        # Evita criar snapshots duplicados se a tarefa rodar mais de uma vez
        if PortfolioSnapshot.objects.filter(user_profile=profile, date=today).exists():
            continue

        total_portfolio_value_pref_currency = Decimal('0.0')
        pref_currency = profile.preferred_fiat_currency
        rate_to_pref_currency = exchange_rates.get(pref_currency)
        
        if not rate_to_pref_currency:
            print(f"Aviso: Taxa de câmbio para {pref_currency} não encontrada para o usuário {profile.user.username}.")
            continue

        holdings = Holding.objects.filter(user_profile=profile, quantity__gt=0).select_related('cryptocurrency')
        for holding in holdings:
            if holding.current_market_value is not None:
                total_portfolio_value_pref_currency += holding.current_market_value * rate_to_pref_currency
        
        PortfolioSnapshot.objects.create(
            user_profile=profile,
            total_value=total_portfolio_value_pref_currency,
            currency=pref_currency,
            date=today
        )
        created_count += 1

    result_message = f"Tarefa de Snapshots finalizada. {created_count} snapshots criados."
    print(f"[{timezone.now()}] {result_message}")
    return result_message
