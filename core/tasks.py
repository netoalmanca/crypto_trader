# core/tasks.py
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from decimal import Decimal, InvalidOperation

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

# Importa os modelos necessários
from .models import Cryptocurrency, ExchangeRate, FIAT_CURRENCY_CHOICES, BASE_RATE_CURRENCY

@shared_task(bind=True, name="core.tasks.update_all_cryptocurrency_prices")
def update_all_cryptocurrency_prices(self):
    """
    Tarefa Celery para buscar e atualizar os preços de todas as criptomoedas
    cadastradas no banco de dados usando a API da Binance.
    """
    print(f"[{timezone.now()}] Iniciando tarefa: update_all_cryptocurrency_prices")
    
    client = None
    if settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET:
        try:
            client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, tld='com', testnet=settings.BINANCE_TESTNET)
        except Exception as e:
            print(f"Falha ao inicializar o cliente da Binance na tarefa Celery (preços): {e}")
            return f"Falha ao inicializar cliente Binance (preços): {e}"
    else:
        print("Chaves API da Binance (sistema) não configuradas para a tarefa Celery (preços).")
        return "Chaves API (preços) não configuradas."

    cryptocurrencies = Cryptocurrency.objects.all()
    if not cryptocurrencies.exists():
        print("Nenhuma criptomoeda cadastrada para atualizar preços.")
        return "Nenhuma criptomoeda para atualizar preços."

    updated_count = 0
    failed_count = 0

    for crypto in cryptocurrencies:
        try:
            api_symbol_pair = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
            ticker_data = client.get_ticker(symbol=api_symbol_pair) 

            if ticker_data and 'lastPrice' in ticker_data:
                new_price = Decimal(ticker_data['lastPrice'])
                
                if new_price != crypto.current_price or crypto.current_price is None:
                    crypto.current_price = new_price
                    crypto.last_updated = timezone.now()
                    crypto.save()
                    updated_count += 1
                    print(f"Preço de {api_symbol_pair} atualizado para {new_price}")
            else:
                print(f"Dados do ticker não encontrados para {api_symbol_pair}")
                failed_count += 1
        
        except BinanceAPIException as e:
            print(f"Erro API Binance para {api_symbol_pair} na tarefa (preços): {e.message} (Cod: {e.code})")
            failed_count += 1
        except (BinanceRequestException, InvalidOperation) as e:
            print(f"Erro de Requisição/Decimal para {api_symbol_pair} na tarefa (preços): {e}")
            failed_count += 1
        except Exception as e:
            print(f"Erro inesperado para {api_symbol_pair} na tarefa (preços): {str(e)}")
            failed_count += 1
    
    result_message = f"Tarefa de preços finalizada. {updated_count} preços atualizados, {failed_count} falhas."
    print(f"[{timezone.now()}] {result_message}")
    return result_message

@shared_task(bind=True, name="core.tasks.update_exchange_rates")
def update_exchange_rates(self):
    """
    Tarefa Celery para buscar e atualizar as taxas de câmbio de FIAT_CURRENCY_CHOICES
    em relação à BASE_RATE_CURRENCY (ex: USDT) usando a API da Binance.
    """
    print(f"[{timezone.now()}] Iniciando tarefa: update_exchange_rates")

    client = None
    if settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET:
        try:
            client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, tld='com', testnet=settings.BINANCE_TESTNET) # Pode usar mainnet para taxas de câmbio
        except Exception as e:
            print(f"Falha ao inicializar o cliente da Binance na tarefa Celery (câmbio): {e}")
            return f"Falha ao inicializar cliente Binance (câmbio): {e}"
    else:
        print("Chaves API da Binance (sistema) não configuradas para a tarefa Celery (câmbio).")
        return "Chaves API (câmbio) não configuradas."

    # Moedas fiat para as quais queremos a taxa em relação à BASE_RATE_CURRENCY
    # Exclui a própria BASE_RATE_CURRENCY da lista de 'to_currencies'
    target_fiat_currencies = [choice[0] for choice in FIAT_CURRENCY_CHOICES if choice[0] != BASE_RATE_CURRENCY]
    
    if not target_fiat_currencies:
        print("Nenhuma moeda fiat alvo definida para buscar taxas de câmbio.")
        return "Nenhuma moeda fiat alvo."

    updated_count = 0
    failed_count = 0

    for fiat_code in target_fiat_currencies:
        # Precisamos do par BASE_RATE_CURRENCY + fiat_code.
        # Ex: Se BASE_RATE_CURRENCY é USDT e fiat_code é BRL, buscamos USDTBRL.
        # A API retorna quantos 'fiat_code' valem 1 BASE_RATE_CURRENCY.
        # Se fiat_code for USD e BASE_RATE_CURRENCY for USDT, assumimos 1:1 ou buscamos um par estável se existir.
        
        if BASE_RATE_CURRENCY == fiat_code: # Não precisamos de taxa para a mesma moeda
            continue

        # Caso especial: USDT para USD (ou vice-versa). Frequentemente tratados como 1:1 ou pode não haver par direto.
        if (BASE_RATE_CURRENCY == 'USDT' and fiat_code == 'USD') or \
           (BASE_RATE_CURRENCY == 'USD' and fiat_code == 'USDT'):
            rate = Decimal('1.0')
            api_symbol_pair = f"{BASE_RATE_CURRENCY}{fiat_code} (Assumido 1:1)"
        else:
            # Forma o par, ex: USDTBRL (para obter quantos BRL valem 1 USDT)
            api_symbol_pair = f"{BASE_RATE_CURRENCY}{fiat_code}"
            try:
                # Para taxas de câmbio, é melhor usar a API principal, mesmo que o resto seja Testnet,
                # pois a Testnet pode não ter todos os pares fiat.
                # Considere ter chaves API separadas ou usar um cliente diferente para isso.
                # Por agora, usaremos o mesmo cliente.
                ticker = client.get_symbol_ticker(symbol=api_symbol_pair)
                if ticker and 'price' in ticker:
                    rate = Decimal(ticker['price'])
                else:
                    print(f"Ticker não encontrado para o par de câmbio {api_symbol_pair}")
                    failed_count +=1
                    continue
            except BinanceAPIException as e:
                print(f"Erro API Binance para par de câmbio {api_symbol_pair}: {e.message} (Cod: {e.code})")
                # Tentar o par inverso? Ex: se USDTBRL falhar, tentar BRLUSDT e calcular 1/rate?
                # Por simplicidade, vamos apenas logar e continuar.
                failed_count += 1
                continue
            except Exception as e:
                print(f"Erro inesperado ao buscar taxa para {api_symbol_pair}: {str(e)}")
                failed_count += 1
                continue
        
        # Salva ou atualiza a taxa no banco de dados
        try:
            exchange_rate_obj, created = ExchangeRate.objects.update_or_create(
                from_currency=BASE_RATE_CURRENCY,
                to_currency=fiat_code,
                defaults={'rate': rate}
            )
            if created:
                print(f"Taxa de câmbio para {BASE_RATE_CURRENCY} -> {fiat_code} criada: {rate}")
            else:
                print(f"Taxa de câmbio para {BASE_RATE_CURRENCY} -> {fiat_code} atualizada: {rate}")
            updated_count += 1
        except Exception as e:
            print(f"Erro ao salvar taxa de câmbio para {BASE_RATE_CURRENCY} -> {fiat_code}: {e}")
            failed_count +=1

    result_message = f"Tarefa de taxas de câmbio finalizada. {updated_count} taxas atualizadas/criadas, {failed_count} falhas."
    print(f"[{timezone.now()}] {result_message}")
    return result_message
