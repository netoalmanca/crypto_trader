# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import csv
from django.http import HttpResponse, JsonResponse
import requests
import time
import json
import datetime
from django.db import transaction as db_transaction
from django.db.models import Sum, Q
from decimal import Decimal, ROUND_DOWN, InvalidOperation

from .forms import (
    CustomUserCreationForm, CustomAuthenticationForm, UserProfileAPIForm,
    TransactionForm, LimitBuyForm, LimitSellForm, MarketBuyForm, MarketSellForm
)
from .models import (
    Cryptocurrency, UserProfile, Holding, Transaction, 
    ExchangeRate, PortfolioSnapshot, BASE_RATE_CURRENCY
)
from binance.client import Client 
from binance.exceptions import BinanceAPIException

# --- Funções Helper ---

def get_binance_client(user_profile=None):
    """
    Função centralizada para criar um cliente Binance com o tempo sincronizado.
    """
    api_key, api_secret, testnet = None, None, True 

    if user_profile:
        api_key = user_profile.binance_api_key
        api_secret = user_profile.binance_api_secret
        testnet = user_profile.use_testnet
        if not all((api_key, api_secret)) or 'DECRYPTION_FAILED' in (api_key, api_secret):
            return None
    
    if not api_key: api_key = settings.BINANCE_API_KEY
    if not api_secret: api_secret = settings.BINANCE_API_SECRET

    client = Client(api_key, api_secret, tld='com', testnet=testnet)
    
    try:
        server_time = client.get_server_time()
        time_offset = server_time['serverTime'] - int(time.time() * 1000)
        client.timestamp_offset = time_offset
    except requests.exceptions.RequestException as e:
        print(f"Aviso: Não foi possível sincronizar o tempo com a Binance. Erro: {e}")

    return client

def adjust_quantity_to_lot_size(quantity_str, step_size_str):
    quantity, step_size = Decimal(quantity_str), Decimal(step_size_str)
    if step_size <= 0: return quantity.quantize(Decimal('1e-8'), rounding=ROUND_DOWN)
    precision = len(step_size_str.rstrip('0').split('.')[1]) if '.' in step_size_str else 0
    adjusted = (quantity / step_size).to_integral_value(rounding=ROUND_DOWN) * step_size
    return adjusted.quantize(Decimal('1e-' + str(precision)), rounding=ROUND_DOWN)

def adjust_price_to_tick_size(price_str, tick_size_str):
    price, tick_size = Decimal(price_str), Decimal(tick_size_str)
    if tick_size <= 0: return price
    precision = len(tick_size_str.rstrip('0').split('.')[1]) if '.' in tick_size_str else 0
    quotient = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
    return (quotient * tick_size).quantize(Decimal('1e-' + str(precision)))

def _create_todays_snapshot(user_profile):
    """
    Cria ou atualiza o snapshot do portfólio para o dia atual para um usuário específico.
    """
    today = timezone.now().date()
    print(f"A criar/atualizar snapshot para {user_profile.user.username} para a data {today}")

    exchange_rates = {rate.to_currency: rate.rate for rate in ExchangeRate.objects.filter(from_currency=BASE_RATE_CURRENCY)}
    exchange_rates[BASE_RATE_CURRENCY] = Decimal('1.0')
    
    pref_currency = user_profile.preferred_fiat_currency
    rate_to_pref_currency = exchange_rates.get(pref_currency)

    if not rate_to_pref_currency:
        print(f"Aviso: Taxa de câmbio para {pref_currency} não encontrada para o usuário {user_profile.user.username}. Snapshot não criado.")
        return

    total_portfolio_value = Decimal('0.0')
    holdings = Holding.objects.filter(user_profile=user_profile, quantity__gt=0)
    for holding in holdings:
        if holding.current_market_value is not None:
            total_portfolio_value += holding.current_market_value * rate_to_pref_currency
    
    PortfolioSnapshot.objects.update_or_create(
        user_profile=user_profile,
        date=today,
        defaults={
            'total_value': total_portfolio_value,
            'currency': pref_currency,
        }
    )
    print(f"Snapshot salvo para {user_profile.user.username}: {total_portfolio_value} {pref_currency}")


@db_transaction.atomic
def recalculate_holdings(user_profile, request=None):
    """
    (VERSÃO FINAL) Limpa e recalcula as posses.
    1. Usa a API da Binance para obter o SALDO ATUAL (quantidade) de cada ativo.
    2. Usa o HISTÓRICO DE TRADES para calcular o PREÇO MÉDIO de compra.
    """
    print(f"--- INÍCIO DO RECÁLCULO (v5) para {user_profile.user.username} ---")
    
    client = get_binance_client(user_profile)
    if not client:
        if request:
            messages.error(request, "Não foi possível conectar à Binance para recalcular as posses. Verifique suas chaves de API.")
        print("Erro: Cliente Binance não pôde ser criado.")
        return

    Holding.objects.filter(user_profile=user_profile).delete()
    print("Posses antigas eliminadas.")

    try:
        account_info = client.get_account()
        balances = {item['asset']: Decimal(item['free']) for item in account_info.get('balances', []) if Decimal(item['free']) > 0}
        print(f"Saldos obtidos da Binance: {balances}")
    except BinanceAPIException as e:
        if request:
            messages.error(request, f"Erro ao obter saldos da Binance: {e.message}")
        print(f"Erro na API ao obter saldos: {e}")
        return

    crypto_symbols_with_balance = list(balances.keys())
    relevant_cryptos = Cryptocurrency.objects.filter(symbol__in=crypto_symbols_with_balance)

    if not relevant_cryptos.exists():
        print("Nenhuma cripto com saldo positivo encontrada na conta da Binance.")
        print(f"--- FIM DO RECÁLCULO (v5) ---")
        return
        
    print(f"Criptos com saldo na Binance: {[c.symbol for c in relevant_cryptos]}")

    for crypto in relevant_cryptos:
        symbol = crypto.symbol
        current_quantity = balances.get(symbol, Decimal('0.0'))
        
        print(f"\nA processar {symbol}:")
        print(f"  - Saldo atual da API: {current_quantity}")

        buys_data = Transaction.objects.filter(
            user_profile=user_profile, cryptocurrency=crypto, transaction_type='BUY'
        ).aggregate(
            total_qty=Sum('quantity_crypto', default=Decimal('0.0')),
            total_cost=Sum('total_value', default=Decimal('0.0'))
        )
        
        total_qty_bought = buys_data['total_qty']
        total_cost_of_buys = buys_data['total_cost']

        avg_price = (total_cost_of_buys / total_qty_bought) if total_qty_bought > 0 else Decimal('0.0')

        print(f"  - Total histórico de compras: Qtd={total_qty_bought}, Custo={total_cost_of_buys}")
        print(f"  - Preço médio de compra calculado: {avg_price}")
        
        Holding.objects.create(
            user_profile=user_profile,
            cryptocurrency=crypto,
            quantity=current_quantity,
            average_buy_price=avg_price
        )
        print(f"  -> SUCESSO: Nova posse para {crypto.symbol} criada. Qtd={current_quantity}, Preço Médio={avg_price}")
            
    print(f"--- FIM DO RECÁLCULO (v5) ---")

@db_transaction.atomic
def _process_successful_order(user_profile, order_response, crypto, signal=None):
    if not order_response or not order_response.get('fills'):
        raise ValueError("A resposta da ordem da Binance não continha 'fills' para processar.")
    
    order_id = str(order_response.get('orderId'))
    
    for fill in order_response.get('fills', []):
        trade_id = str(fill.get('tradeId'))
        
        Transaction.objects.update_or_create(
            user_profile=user_profile,
            binance_order_id=trade_id,
            defaults={
                'cryptocurrency': crypto,
                'transaction_type': order_response.get('side'),
                'quantity_crypto': Decimal(fill['qty']),
                'price_per_unit': Decimal(fill['price']),
                'total_value': Decimal(fill['qty']) * Decimal(fill['price']),
                'fees': Decimal(fill['commission']),
                'transaction_date': datetime.datetime.fromtimestamp(order_response['transactTime'] / 1000, tz=datetime.timezone.utc),
                'notes': f"Ordem executada via app (OrderID: {order_id}). Taxas pagas em {fill.get('commissionAsset')}.",
                'signal': signal
            }
        )
    
    recalculate_holdings(user_profile)
    _update_crypto_prices_for_profile(user_profile)
    _create_todays_snapshot(user_profile)


def _update_crypto_prices_for_profile(user_profile):
    client = get_binance_client()
    if not client:
        print("Não foi possível criar um cliente Binance genérico para atualizar os preços.")
        return

    held_cryptos = Cryptocurrency.objects.filter(held_by_users__user_profile=user_profile).distinct()
    
    if not held_cryptos.exists():
        print("Nenhuma posse encontrada para atualizar preços.")
        return

    print(f"Atualizando preços para {held_cryptos.count()} criptos de {user_profile.user.username}...")
    for crypto in held_cryptos:
        api_symbol_pair = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            ticker_data = client.get_ticker(symbol=api_symbol_pair)
            if ticker_data and 'lastPrice' in ticker_data:
                crypto.current_price = Decimal(ticker_data['lastPrice'])
                crypto.last_updated = timezone.now()
                crypto.save(update_fields=['current_price', 'last_updated'])
        except (BinanceAPIException, InvalidOperation) as e:
            print(f"Erro ao atualizar o preço para {api_symbol_pair}: {e}")


# --- Views ---
def index_view(request):
    return render(request, 'core/index.html', {'page_title': "Bem-vindo ao Crypto Trader Pro"})

def register_view(request):
    if request.user.is_authenticated: return redirect('core:dashboard')
    form = CustomUserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(); login(request, user)
        messages.success(request, 'Conta criada com sucesso!')
        return redirect('core:dashboard')
    return render(request, 'core/register.html', {'form': form, 'page_title': 'Criar Nova Conta'})

def login_view(request):
    if request.user.is_authenticated: return redirect('core:dashboard')
    form = CustomAuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user(); login(request, user)
        return redirect(request.GET.get('next') or 'core:dashboard')
    return render(request, 'core/login.html', {'form': form, 'page_title': 'Acessar Conta'})

@login_required
def logout_view(request):
    logout(request); messages.info(request, 'Você foi desconectado.')
    return redirect('core:index')

@login_required
def dashboard_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    holdings_list = list(Holding.objects.filter(user_profile=user_profile, quantity__gt=0).select_related('cryptocurrency'))
    pref_currency = user_profile.preferred_fiat_currency
    snapshots_list = list(PortfolioSnapshot.objects.filter(user_profile=user_profile, currency=pref_currency).order_by('date'))
    exchange_rates = {rate.to_currency: rate.rate for rate in ExchangeRate.objects.filter(from_currency=BASE_RATE_CURRENCY)}
    exchange_rates[BASE_RATE_CURRENCY] = Decimal('1.0')
    rate_to_pref_currency = exchange_rates.get(pref_currency)
    enriched_holdings, pie_chart_data, total_portfolio_value = [], {'labels': [], 'data': []}, Decimal('0.0')
    if rate_to_pref_currency:
        for holding in holdings_list:
            current_value_pref = (holding.current_market_value or 0) * rate_to_pref_currency
            total_portfolio_value += current_value_pref
            cost_basis_pref = (holding.cost_basis or 0) * rate_to_pref_currency
            avg_buy_price_pref = (holding.average_buy_price or 0) * rate_to_pref_currency
            current_price_pref = (holding.cryptocurrency.current_price or 0) * rate_to_pref_currency
            profit_loss_pref, profit_loss_percent = None, None
            if current_value_pref > 0 and cost_basis_pref > 0:
                profit_loss_pref = current_value_pref - cost_basis_pref
                profit_loss_percent = (profit_loss_pref / cost_basis_pref) * 100
            enriched_holdings.append({'holding': holding, 'average_buy_price_display': avg_buy_price_pref, 'current_price_display': current_price_pref, 'current_value_display': current_value_pref, 'profit_loss_display': profit_loss_pref, 'profit_loss_percent_display': profit_loss_percent, 'display_currency': pref_currency})
            if current_value_pref > 0:
                pie_chart_data['labels'].append(holding.cryptocurrency.symbol)
                pie_chart_data['data'].append(float(current_value_pref))
    else:
        messages.warning(request, f"Não foi possível encontrar a taxa de câmbio para sua moeda preferida ({pref_currency}).")
    line_chart_data = {'labels': [s.date.strftime('%d/%m') for s in snapshots_list[-30:]], 'data': [float(s.total_value) for s in snapshots_list[-30:]]}
    context = {'page_title': 'Meu Dashboard', 'holdings': enriched_holdings, 'total_portfolio_value': total_portfolio_value, 'portfolio_currency': pref_currency, 'pie_chart_data_json': json.dumps(pie_chart_data), 'line_chart_data_json': json.dumps(line_chart_data)}
    return render(request, 'core/dashboard.html', context)

@login_required
def reports_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    holdings = Holding.objects.filter(user_profile=user_profile).select_related('cryptocurrency')
    pref_currency = user_profile.preferred_fiat_currency
    exchange_rates = {rate.to_currency: rate.rate for rate in ExchangeRate.objects.filter(from_currency=BASE_RATE_CURRENCY)}
    exchange_rates[BASE_RATE_CURRENCY] = Decimal('1.0')
    rate_to_pref_currency = exchange_rates.get(pref_currency)
    total_current_value, total_cost_basis = Decimal('0.0'), Decimal('0.0')
    if rate_to_pref_currency:
        for holding in holdings:
            if holding.current_market_value is not None: total_current_value += holding.current_market_value * rate_to_pref_currency
            if holding.cost_basis is not None: total_cost_basis += holding.cost_basis * rate_to_pref_currency
    else:
        messages.warning(request, f"Taxa de câmbio para {pref_currency} não encontrada. Os valores podem estar incorretos.")
    total_profit_loss = total_current_value - total_cost_basis
    roi = (total_profit_loss / total_cost_basis) * 100 if total_cost_basis > 0 else None
    context = {'page_title': 'Relatório de Performance', 'total_current_value': total_current_value, 'total_cost_basis': total_cost_basis, 'total_profit_loss': total_profit_loss, 'roi': roi, 'portfolio_currency': pref_currency}
    return render(request, 'core/reports.html', context)

@login_required
def update_api_keys_view(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    form = UserProfileAPIForm(request.POST or None, instance=user_profile)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Configurações salvas com sucesso!')
        if not form.cleaned_data.get('use_testnet'):
            messages.warning(request, 'MODO MAINNET ATIVADO. Tenha cuidado, as próximas operações usarão fundos reais.')
        return redirect('core:dashboard')
    return render(request, 'core/profile_api_keys.html', {'form': form, 'page_title': 'Configurar Chaves API e Ambiente'})

@login_required
@db_transaction.atomic
def reset_portfolio_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    Transaction.objects.filter(user_profile=user_profile).delete()
    Holding.objects.filter(user_profile=user_profile).delete()
    PortfolioSnapshot.objects.filter(user_profile=user_profile).delete()
    messages.success(request, 'Seus dados de portfólio local foram zerados.')
    return redirect('core:dashboard')

@login_required
def recalculate_holdings_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    recalculate_holdings(user_profile, request)
    _update_crypto_prices_for_profile(user_profile)
    _create_todays_snapshot(user_profile)
    messages.success(request, 'Seu portfólio foi recalculado e os preços foram atualizados com sucesso!')
    return redirect('core:dashboard')

@login_required
def cryptocurrency_list_view(request):
    client = get_binance_client()
    cryptos_from_db = Cryptocurrency.objects.all().order_by('name')
    enriched_cryptos_data = []
    if client:
        for crypto in cryptos_from_db:
            data = {'db_instance': crypto}
            try:
                ticker_24h = client.get_ticker(symbol=f"{crypto.symbol.upper()}{crypto.price_currency.upper()}")
                data.update({'price_change_percent_24h': Decimal(ticker_24h.get('priceChangePercent', '0'))})
            except BinanceAPIException:
                data.update({'price_change_percent_24h': None})
            enriched_cryptos_data.append(data)
    else:
         messages.error(request, "Não foi possível conectar à Binance para obter dados de mercado.")

    paginator = Paginator(enriched_cryptos_data, 20)
    page_number = request.GET.get('page')
    cryptocurrencies_page = paginator.get_page(page_number)
    return render(request, 'core/cryptocurrency_list.html', {'page_title': 'Lista de Criptomoedas', 'cryptocurrencies_page': cryptocurrencies_page})

@login_required
def cryptocurrency_detail_view(request, symbol):
    crypto = get_object_or_404(Cryptocurrency, symbol__iexact=symbol)
    klines_data_json, chart_error_message = "[]", None
    client = get_binance_client(user_profile=request.user.profile)
    if client:
        try:
            api_symbol_pair = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
            klines = client.get_historical_klines(api_symbol_pair, Client.KLINE_INTERVAL_1DAY, "90 days ago UTC")
            if klines:
                klines_data = {'labels': [datetime.datetime.fromtimestamp(k[0]/1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d') for k in klines], 'data': [str(Decimal(k[4])) for k in klines], 'currency': crypto.price_currency}
                klines_data_json = json.dumps(klines_data)
        except BinanceAPIException as e:
            chart_error_message = f"Erro ao buscar dados do gráfico: {e.message}"
    else:
        chart_error_message = "Chaves API não configuradas ou inválidas."
    if chart_error_message: messages.error(request, chart_error_message)
    context = {'page_title': f"Detalhes de {crypto.name}", 'crypto': crypto, 'klines_data_json': klines_data_json, 'chart_error_message': chart_error_message}
    return render(request, 'core/cryptocurrency_detail.html', context)

@login_required
def explain_crypto_with_ai_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            crypto_name = data.get('crypto_name')
            if not crypto_name:
                return JsonResponse({'error': 'Nome da criptomoeda não fornecido.'}, status=400)

            gemini_api_key = settings.GEMINI_API_KEY
            if not gemini_api_key or gemini_api_key == "SUA_CHAVE_GEMINI":
                return JsonResponse({'error': 'A chave da API Gemini não está configurada no servidor.'}, status=500)

            prompt = f"Aja como um especialista em criptomoedas. Explique o que é {crypto_name}, qual o seu propósito principal, e um ponto positivo e um negativo sobre o projeto. Seja claro e direto, em um parágrafo."
            
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={gemini_api_key}"
            headers = {'Content-Type': 'application/json'}
            payload = {'contents': [{'parts': [{'text': prompt}]}]}

            response = requests.post(api_url, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            
            result = response.json()
            explanation = result['candidates'][0]['content']['parts'][0]['text']
            
            return JsonResponse({'explanation': explanation})

        except requests.exceptions.RequestException as e:
            return JsonResponse({'error': f'Erro de rede ao contatar a API Gemini: {e}'}, status=502)
        except (KeyError, IndexError) as e:
            return JsonResponse({'error': 'Resposta inesperada da API Gemini. Tente novamente.'}, status=500)
        except Exception as e:
            return JsonResponse({'error': f'Ocorreu um erro inesperado: {e}'}, status=500)

    return JsonResponse({'error': 'Método não permitido'}, status=405)


@login_required
def open_orders_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    client = get_binance_client(user_profile=user_profile)
    if not client:
        messages.error(request, "Chaves API inválidas ou não configuradas.")
        return redirect('core:update_api_keys')
    if request.method == 'POST':
        order_id, symbol = request.POST.get('order_id'), request.POST.get('symbol')
        if order_id and symbol:
            try:
                client.cancel_order(symbol=symbol, orderId=order_id)
                messages.success(request, f"Ordem {order_id} cancelada.")
            except BinanceAPIException as e:
                messages.error(request, f"Erro ao cancelar: {e.message}")
        return redirect('core:open_orders')
    processed_orders = []
    try:
        open_orders = client.get_open_orders()
        for order in open_orders:
            order['time_dt'] = datetime.datetime.fromtimestamp(order['time'] / 1000, tz=datetime.timezone.utc)
            order['total_value'] = Decimal(order['price']) * Decimal(order['origQty'])
            processed_orders.append(order)
    except BinanceAPIException as e:
        messages.error(request, f"Erro ao buscar ordens: {e.message}")
    return render(request, 'core/open_orders.html', {'page_title': 'Minhas Ordens Abertas', 'open_orders': processed_orders})

@login_required
def transaction_history_view(request):
    transaction_list = Transaction.objects.filter(user_profile__user=request.user).order_by('-transaction_date')
    paginator = Paginator(transaction_list, 15) 
    page_number = request.GET.get('page')
    transactions_page = paginator.get_page(page_number)
    return render(request, 'core/transaction_history.html', {'page_title': 'Histórico de Transações', 'transactions_page': transactions_page})

@login_required
def export_transactions_csv_view(request):
    filename = f"historico_transacoes_{request.user.username}_{timezone.now().strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{filename}"'})
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Data Transacao', 'Tipo', 'Simbolo', 'Nome Cripto', 'Quantidade', 'Preco Unitario', 'Moeda Preco', 'Valor Total', 'Taxas', 'Notas'])
    transactions = Transaction.objects.filter(user_profile__user=request.user).select_related('cryptocurrency').order_by('transaction_date')
    for tx in transactions:
        writer.writerow([tx.transaction_date.strftime('%Y-%m-%d %H:%M:%S'), tx.get_transaction_type_display(), tx.cryptocurrency.symbol, tx.cryptocurrency.name, f'{tx.quantity_crypto:.8f}'.replace('.', ','), f'{tx.price_per_unit:.8f}'.replace('.', ','), tx.cryptocurrency.price_currency, f'{tx.total_value:.8f}'.replace('.', ','), f'{tx.fees:.8f}'.replace('.', ','), tx.notes])
    return response

@login_required
@db_transaction.atomic
def add_transaction_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    form = TransactionForm(request.POST or None, user_profile=user_profile)
    if request.method == 'POST' and form.is_valid():
        tx = form.save(commit=False); tx.user_profile = user_profile; tx.save()
        recalculate_holdings(user_profile, request)
        _update_crypto_prices_for_profile(user_profile)
        _create_todays_snapshot(user_profile)
        messages.success(request, "Transação manual registrada e portfólio recalculado!")
        return redirect('core:dashboard')
    return render(request, 'core/add_transaction.html', {'form': form, 'page_title': 'Adicionar Transação Manual'})

@login_required
@db_transaction.atomic
def sync_binance_trades_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    client = get_binance_client(user_profile=user_profile)
    if not client:
        messages.error(request, "Chaves API inválidas ou não configuradas para sincronizar.")
        return redirect('core:transaction_history')

    print("--- INÍCIO DA SINCRONIZAÇÃO COMPLETA COM A BINANCE ---")
    
    existing_trade_ids = set(Transaction.objects.filter(
        user_profile=user_profile, 
        binance_order_id__isnull=False
    ).values_list('binance_order_id', flat=True))
    print(f"Encontrados {len(existing_trade_ids)} IDs de trades já existentes no banco de dados.")

    all_db_cryptos = Cryptocurrency.objects.all()
    total_new_trades_count = 0

    for crypto in all_db_cryptos:
        api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        print(f"\nSincronizando histórico para o par: {api_symbol}")
        
        last_trade_id = 0
        
        while True:
            try:
                trades = client.get_my_trades(symbol=api_symbol, fromId=last_trade_id, limit=1000)

                if not trades:
                    print(f"Nenhum trade novo encontrado para {api_symbol} a partir do ID {last_trade_id}. Fim da sincronização para este par.")
                    break

                new_trades_in_batch = 0
                for trade in trades:
                    trade_id_str = str(trade['id'])
                    
                    if trade_id_str not in existing_trade_ids:
                        Transaction.objects.update_or_create(
                            user_profile=user_profile,
                            binance_order_id=trade_id_str,
                            defaults={
                                'cryptocurrency': crypto, 
                                'transaction_type': 'BUY' if trade['isBuyer'] else 'SELL', 
                                'quantity_crypto': Decimal(trade['qty']), 
                                'price_per_unit': Decimal(trade['price']), 
                                'fees': Decimal(trade['commission']), 
                                'transaction_date': datetime.datetime.fromtimestamp(trade['time'] / 1000, tz=datetime.timezone.utc), 
                                'notes': f"Sincronizado da Binance. Trade ID: {trade_id_str}"
                            }
                        )
                        existing_trade_ids.add(trade_id_str)
                        new_trades_in_batch += 1
                
                if new_trades_in_batch > 0:
                    print(f"  -> {new_trades_in_batch} novas transações salvas neste lote.")
                    total_new_trades_count += new_trades_in_batch

                last_trade_id = trades[-1]['id'] + 1
                
                if len(trades) < 1000:
                    print(f"Fim do histórico para {api_symbol} alcançado.")
                    break
                
                time.sleep(0.5)

            except BinanceAPIException as e:
                if e.code != -1121:
                    messages.warning(request, f"Aviso ao sincronizar {api_symbol}: {e.message}")
                else:
                    print(f"Nenhum histórico de trade encontrado para {api_symbol}.")
                break
            except Exception as e:
                messages.error(request, f"Erro inesperado ao sincronizar {api_symbol}: {e}")
                break

    print(f"\n--- FIM DA SINCRONIZAÇÃO ---")
    
    if total_new_trades_count > 0:
        messages.success(request, f"{total_new_trades_count} nova(s) transação(ões) foram sincronizadas. O portfólio será recalculado.")
    else:
        messages.info(request, "Nenhuma nova transação encontrada. Recalculando portfólio com os dados existentes.")
    
    recalculate_holdings(user_profile, request)
    _update_crypto_prices_for_profile(user_profile)
    _create_todays_snapshot(user_profile)
        
    return redirect('core:transaction_history')


@login_required
def trade_market_buy_view(request):
    user_profile, client = get_object_or_404(UserProfile, user=request.user), get_binance_client(user_profile=request.user.profile)
    if not client: messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    form = MarketBuyForm(request.POST or None, user_currency=BASE_RATE_CURRENCY)
    if request.method == 'POST' and form.is_valid():
        crypto, api_symbol = form.cleaned_data['cryptocurrency'], f"{form.cleaned_data['cryptocurrency'].symbol.upper()}{form.cleaned_data['cryptocurrency'].price_currency.upper()}"
        try:
            params = {'symbol': api_symbol}
            if form.cleaned_data['buy_type'] == 'QUANTITY':
                quantity, symbol_info = form.cleaned_data['quantity'], client.get_symbol_info(api_symbol)
                lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                if lot_size_filter: quantity = adjust_quantity_to_lot_size(str(quantity), lot_size_filter['stepSize'])
                params['quantity'] = f'{quantity:.8f}'.rstrip('0').rstrip('.')
            else: params['quoteOrderQty'] = form.cleaned_data['quote_quantity']
            order = client.order_market_buy(**params)
            _process_successful_order(user_profile, order, crypto)
            messages.success(request, f"Ordem de compra para {api_symbol} executada!")
            return redirect('core:dashboard')
        except (BinanceAPIException, ValueError) as e: messages.error(request, f"Erro: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_market_buy.html', {'form': form, 'page_title': 'Comprar a Mercado'})

@login_required
def trade_market_sell_view(request):
    user_profile, client = get_object_or_404(UserProfile, user=request.user), get_binance_client(user_profile=request.user.profile)
    if not client: messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    form = MarketSellForm(request.POST or None, user_profile=user_profile, quote_currency=BASE_RATE_CURRENCY)
    if request.method == 'POST' and form.is_valid():
        crypto, api_symbol = form.cleaned_data['cryptocurrency'], f"{form.cleaned_data['cryptocurrency'].symbol.upper()}{form.cleaned_data['cryptocurrency'].price_currency.upper()}"
        try:
            quantity_to_sell = Decimal('0')
            if form.cleaned_data['sell_type'] == 'QUANTITY': quantity_to_sell = form.cleaned_data['quantity']
            else:
                ticker, price = client.get_symbol_ticker(symbol=api_symbol), Decimal(client.get_symbol_ticker(symbol=api_symbol)['price'])
                if price > 0: quantity_to_sell = form.cleaned_data['quote_quantity_to_receive'] / price
                else: raise ValueError("Preço de mercado inválido.")
            holding = Holding.objects.get(user_profile=user_profile, cryptocurrency=crypto)
            if holding.quantity < quantity_to_sell: raise ValueError("Saldo insuficiente.")
            symbol_info, lot_size_filter = client.get_symbol_info(api_symbol), next((f for f in client.get_symbol_info(api_symbol)['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            if lot_size_filter: quantity_to_sell = adjust_quantity_to_lot_size(str(quantity_to_sell), lot_size_filter['stepSize'])
            if quantity_to_sell <= 0: raise ValueError("Quantidade a vender deve ser maior que zero.")
            order = client.order_market_sell(symbol=api_symbol, quantity=f'{quantity_to_sell:.8f}'.rstrip('0').rstrip('.'))
            _process_successful_order(user_profile, order, crypto)
            messages.success(request, f"Ordem de venda para {api_symbol} executada!")
            return redirect('core:dashboard')
        except (BinanceAPIException, ValueError, Holding.DoesNotExist) as e: messages.error(request, f"Erro: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_market_sell.html', {'form': form, 'page_title': 'Vender a Mercado'})

@login_required
def trade_limit_buy_view(request):
    user_profile, client = get_object_or_404(UserProfile, user=request.user), get_binance_client(user_profile=request.user.profile)
    if not client: messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    form = LimitBuyForm(request.POST or None, user_currency=user_profile.preferred_fiat_currency)
    if request.method == 'POST' and form.is_valid():
        crypto, api_symbol = form.cleaned_data['cryptocurrency'], f"{form.cleaned_data['cryptocurrency'].symbol.upper()}{form.cleaned_data['cryptocurrency'].price_currency.upper()}"
        try:
            price_in_user_currency, price_in_base_currency = form.cleaned_data['price'], form.cleaned_data['price']
            if user_profile.preferred_fiat_currency != crypto.price_currency:
                rate_obj = ExchangeRate.objects.get(from_currency=crypto.price_currency, to_currency=user_profile.preferred_fiat_currency)
                price_in_base_currency = price_in_user_currency / rate_obj.rate
            quantity = form.cleaned_data['quantity'] if form.cleaned_data['order_type'] == 'QUANTITY' else form.cleaned_data['total_value'] / price_in_user_currency
            symbol_info = client.get_symbol_info(api_symbol)
            price_in_base_currency = adjust_price_to_tick_size(str(price_in_base_currency), next(f['tickSize'] for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'))
            quantity = adjust_quantity_to_lot_size(str(quantity), next(f['stepSize'] for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'))
            if quantity <= 0: raise ValueError("A quantidade final deve ser maior que zero.")
            order = client.order_limit_buy(symbol=api_symbol, quantity=f'{quantity:.8f}'.rstrip('0').rstrip('.'), price=f'{price_in_base_currency:.8f}'.rstrip('0').rstrip('.'))
            messages.success(request, f"Ordem limite de COMPRA enviada! ID: {order['orderId']}")
            return redirect('core:open_orders')
        except (BinanceAPIException, ValueError, ExchangeRate.DoesNotExist) as e: messages.error(request, f"Erro: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_limit_buy.html', {'page_title': "Comprar com Ordem Limite"})

@login_required
def trade_limit_sell_view(request):
    user_profile, client = get_object_or_404(UserProfile, user=request.user), get_binance_client(user_profile=request.user.profile)
    if not client: messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    form = LimitSellForm(request.POST or None, user_profile=user_profile)
    if request.method == 'POST' and form.is_valid():
        crypto, api_symbol = form.cleaned_data['cryptocurrency'], f"{form.cleaned_data['cryptocurrency'].symbol.upper()}{form.cleaned_data['cryptocurrency'].price_currency.upper()}"
        try:
            price_in_user_currency, price_in_base_currency = form.cleaned_data['price'], form.cleaned_data['price']
            if user_profile.preferred_fiat_currency != crypto.price_currency:
                rate_obj = ExchangeRate.objects.get(from_currency=crypto.price_currency, to_currency=user_profile.preferred_fiat_currency)
                price_in_base_currency = price_in_user_currency / rate_obj.rate
            quantity = form.cleaned_data['quantity'] if form.cleaned_data['order_type'] == 'QUANTITY' else form.cleaned_data['total_value'] / price_in_user_currency
            symbol_info = client.get_symbol_info(api_symbol)
            price_in_base_currency = adjust_price_to_tick_size(str(price_in_base_currency), next(f['tickSize'] for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'))
            quantity = adjust_quantity_to_lot_size(str(quantity), next(f['stepSize'] for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'))
            if quantity <= 0: raise ValueError("A quantidade final deve ser maior que zero.")
            order = client.order_limit_sell(symbol=api_symbol, quantity=f'{quantity:.8f}'.rstrip('0').rstrip('.'), price=f'{price_in_base_currency:.8f}'.rstrip('0').rstrip('.'))
            messages.success(request, f"Ordem limite de VENDA enviada! ID: {order['orderId']}")
            return redirect('core:open_orders')
        except (BinanceAPIException, ValueError, ExchangeRate.DoesNotExist) as e: messages.error(request, f"Erro: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_limit_sell.html', {'page_title': "Vender com Ordem Limite"})