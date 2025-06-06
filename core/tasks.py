# core/tasks.py
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from decimal import Decimal, InvalidOperation

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

from .models import Cryptocurrency

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
            print(f"Falha ao inicializar o cliente da Binance na tarefa Celery: {e}")
            return f"Falha ao inicializar cliente Binance: {e}"
    else:
        print("Chaves API da Binance (sistema) não configuradas para a tarefa Celery.")
        return "Chaves API não configuradas."

    cryptocurrencies = Cryptocurrency.objects.all()
    if not cryptocurrencies.exists():
        print("Nenhuma criptomoeda cadastrada para atualizar.")
        return "Nenhuma criptomoeda para atualizar."

    updated_count = 0
    failed_count = 0

    for crypto in cryptocurrencies:
        try:
            api_symbol_pair = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
            # Usar get_ticker para dados de 24h, mas só precisamos do preço atual aqui
            ticker_data = client.get_ticker(symbol=api_symbol_pair) 

            if ticker_data and 'lastPrice' in ticker_data:
                new_price = Decimal(ticker_data['lastPrice'])
                
                # Atualiza apenas se o preço mudou ou se nunca foi atualizado
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
            print(f"Erro API Binance para {api_symbol_pair} na tarefa: {e.message} (Cod: {e.code})")
            failed_count += 1
        except (BinanceRequestException, InvalidOperation) as e:
            print(f"Erro de Requisição/Decimal para {api_symbol_pair} na tarefa: {e}")
            failed_count += 1
        except Exception as e:
            print(f"Erro inesperado para {api_symbol_pair} na tarefa: {str(e)}")
            failed_count += 1
    
    result_message = f"Tarefa finalizada. {updated_count} preços atualizados, {failed_count} falhas."
    print(f"[{timezone.now()}] {result_message}")
    return result_message
