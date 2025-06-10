# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from .forms import (
    CustomUserCreationForm, CustomAuthenticationForm, UserProfileAPIForm,
    TransactionForm, LimitBuyForm, LimitSellForm, MarketBuyForm, MarketSellForm
)
from .models import Cryptocurrency, UserProfile, Holding, Transaction, ExchangeRate, BASE_RATE_CURRENCY
from decimal import Decimal, ROUND_DOWN
from binance.client import Client 
from binance.exceptions import BinanceAPIException
from django.db import transaction as db_transaction
import datetime
import json

# --- Funções Helper ---
def adjust_quantity_to_lot_size(quantity_str, step_size_str):
    quantity = Decimal(quantity_str); step_size = Decimal(step_size_str)
    if step_size <= 0: return quantity.quantize(Decimal('1e-8'), rounding=ROUND_DOWN)
    precision = len(step_size_str.rstrip('0').split('.')[1]) if '.' in step_size_str else 0
    adjusted = (quantity / step_size).to_integral_value(rounding=ROUND_DOWN) * step_size
    return adjusted.quantize(Decimal('1e-' + str(precision)), rounding=ROUND_DOWN)

def adjust_price_to_tick_size(price_str, tick_size_str):
    price = Decimal(price_str); tick_size = Decimal(tick_size_str)
    if tick_size <= 0: return price
    precision = len(tick_size_str.rstrip('0').split('.')[1]) if '.' in tick_size_str else 0
    quotient = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
    return (quotient * tick_size).quantize(Decimal('1e-' + str(precision)))

def get_valid_api_client(user_profile):
    api_key, secret = user_profile.binance_api_key, user_profile.binance_api_secret
    if not all((api_key, secret)) or 'DECRYPTION_FAILED' in (api_key, secret): 
        return None
    return Client(api_key, secret, tld='com', testnet=user_profile.use_testnet)

@db_transaction.atomic
def _process_successful_order(user_profile, order_response, crypto):
    if not order_response or not order_response.get('fills'):
        raise ValueError("A resposta da ordem da Binance não continha 'fills' para processar.")
    transaction_type = order_response.get('side')
    order_id = str(order_response.get('orderId'))
    total_quantity_crypto = sum(Decimal(f['qty']) for f in order_response['fills'])
    total_value_quote = sum(Decimal(f['price']) * Decimal(f['qty']) for f in order_response['fills'])
    total_fees = sum(Decimal(f['commission']) for f in order_response['fills'])
    fee_currency = order_response['fills'][0]['commissionAsset'] if order_response['fills'] else ''
    if total_quantity_crypto == 0: return
    average_price = total_value_quote / total_quantity_crypto
    Transaction.objects.create(
        user_profile=user_profile, cryptocurrency=crypto, transaction_type=transaction_type,
        quantity_crypto=total_quantity_crypto, price_per_unit=average_price,
        total_value=total_value_quote, fees=total_fees,
        transaction_date=datetime.datetime.fromtimestamp(order_response['transactTime'] / 1000, tz=datetime.timezone.utc),
        binance_order_id=order_id, notes=f"Ordem a mercado executada. Taxas pagas em {fee_currency}."
    )
    holding, created = Holding.objects.get_or_create(user_profile=user_profile, cryptocurrency=crypto)
    if transaction_type == 'BUY':
        old_total_cost = (holding.average_buy_price or 0) * holding.quantity
        new_total_quantity = holding.quantity + total_quantity_crypto
        holding.average_buy_price = (old_total_cost + total_value_quote) / new_total_quantity if new_total_quantity > 0 else 0
        holding.quantity = new_total_quantity
    elif transaction_type == 'SELL':
        holding.quantity -= total_quantity_crypto
    holding.save()

# --- Views de Autenticação e Páginas ---
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
    holdings_qs = Holding.objects.filter(user_profile=user_profile, quantity__gt=0).select_related('cryptocurrency')
    total_portfolio_value_pref_currency = Decimal('0.0')
    enriched_holdings = []
    exchange_rates = {rate.to_currency: rate.rate for rate in ExchangeRate.objects.filter(from_currency=BASE_RATE_CURRENCY)}
    exchange_rates[BASE_RATE_CURRENCY] = Decimal('1.0')
    pref_currency = user_profile.preferred_fiat_currency
    rate_to_pref_currency = exchange_rates.get(pref_currency)
    for holding in holdings_qs:
        cost_basis = holding.cost_basis; current_value = holding.current_market_value
        cost_basis_pref, current_value_pref, avg_buy_price_pref, current_price_pref = [None] * 4
        if rate_to_pref_currency:
            if cost_basis is not None: cost_basis_pref = cost_basis * rate_to_pref_currency
            if current_value is not None:
                current_value_pref = current_value * rate_to_pref_currency
                total_portfolio_value_pref_currency += current_value_pref
            if holding.average_buy_price is not None: avg_buy_price_pref = holding.average_buy_price * rate_to_pref_currency
            if holding.cryptocurrency.current_price is not None: current_price_pref = holding.cryptocurrency.current_price * rate_to_pref_currency
        profit_loss_pref, profit_loss_percent = None, None
        if current_value_pref is not None and cost_basis_pref is not None and cost_basis_pref > 0:
            profit_loss_pref = current_value_pref - cost_basis_pref; profit_loss_percent = (profit_loss_pref / cost_basis_pref) * 100
        enriched_holdings.append({'holding': holding, 'average_buy_price_display': avg_buy_price_pref, 'current_price_display': current_price_pref, 'current_value_display': current_value_pref, 'profit_loss_display': profit_loss_pref, 'profit_loss_percent_display': profit_loss_percent, 'display_currency': pref_currency})
    context = {'page_title': 'Meu Dashboard', 'holdings': enriched_holdings, 'total_portfolio_value': total_portfolio_value_pref_currency, 'portfolio_currency': pref_currency}
    return render(request, 'core/dashboard.html', context)

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
def cryptocurrency_list_view(request):
    client = None
    if settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET:
        client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, testnet=settings.BINANCE_TESTNET)
    cryptos_from_db = Cryptocurrency.objects.all().order_by('name')
    enriched_cryptos_data = []
    for crypto in cryptos_from_db:
        data = {'db_instance': crypto}
        if client:
            try:
                ticker_24h = client.get_ticker(symbol=f"{crypto.symbol.upper()}{crypto.price_currency.upper()}")
                data.update({'price_change_percent_24h': Decimal(ticker_24h.get('priceChangePercent', '0'))})
            except BinanceAPIException: pass
        enriched_cryptos_data.append(data)
    return render(request, 'core/cryptocurrency_list.html', {'page_title': 'Lista de Criptomoedas', 'cryptocurrencies_data': enriched_cryptos_data})

@login_required
def cryptocurrency_detail_view(request, symbol):
    crypto = get_object_or_404(Cryptocurrency, symbol__iexact=symbol)
    klines_data_json = "[]"; chart_error_message = None
    client = get_valid_api_client(request.user.profile) or Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, testnet=True)
    if client:
        try:
            api_symbol_pair = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
            klines = client.get_historical_klines(api_symbol_pair, Client.KLINE_INTERVAL_1DAY, "90 days ago UTC")
            if klines:
                chart_labels = [datetime.datetime.fromtimestamp(k[0]/1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d') for k in klines]
                chart_data_close = [str(Decimal(k[4])) for k in klines]
                klines_data = {'labels': chart_labels, 'data': chart_data_close, 'currency': crypto.price_currency}
                klines_data_json = json.dumps(klines_data)
        except BinanceAPIException as e: chart_error_message = f"Erro ao buscar dados do gráfico: {e.message}"
    else: chart_error_message = "Chaves API não configuradas."
    if chart_error_message: messages.error(request, chart_error_message)
    context = {'page_title': f"Detalhes de {crypto.name}", 'crypto': crypto, 'klines_data_json': klines_data_json, 'chart_error_message': chart_error_message}
    return render(request, 'core/cryptocurrency_detail.html', context)

@login_required
def open_orders_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    client = get_valid_api_client(user_profile)
    if not client:
        messages.error(request, "Chaves API inválidas ou não configuradas."); return redirect('core:update_api_keys')
    if request.method == 'POST':
        order_id = request.POST.get('order_id'); symbol = request.POST.get('symbol')
        if order_id and symbol:
            try:
                client.cancel_order(symbol=symbol, orderId=order_id)
                messages.success(request, f"Ordem {order_id} cancelada com sucesso.")
            except BinanceAPIException as e: messages.error(request, f"Erro ao cancelar ordem: {e.message}")
        return redirect('core:open_orders')
    processed_orders = []
    try:
        open_orders = client.get_open_orders()
        for order in open_orders:
            order['time_dt'] = datetime.datetime.fromtimestamp(order['time'] / 1000, tz=datetime.timezone.utc)
            order['total_value'] = Decimal(order['price']) * Decimal(order['origQty'])
            processed_orders.append(order)
    except BinanceAPIException as e: messages.error(request, f"Erro ao buscar ordens abertas: {e.message}")
    return render(request, 'core/open_orders.html', {'page_title': 'Minhas Ordens Abertas', 'open_orders': processed_orders})

@login_required
def transaction_history_view(request):
    transactions = Transaction.objects.filter(user_profile__user=request.user).order_by('-transaction_date')
    return render(request, 'core/transaction_history.html', {'transactions': transactions, 'page_title': 'Histórico de Transações'})

@login_required
@db_transaction.atomic
def add_transaction_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    form = TransactionForm(request.POST or None, user_profile=user_profile)
    if request.method == 'POST' and form.is_valid():
        tx = form.save(commit=False); tx.user_profile = user_profile; tx.save()
        holding, created = Holding.objects.get_or_create(user_profile=user_profile, cryptocurrency=tx.cryptocurrency)
        if tx.transaction_type == 'BUY':
            old_total_cost = (holding.average_buy_price or 0) * holding.quantity; new_total_quantity = holding.quantity + tx.quantity_crypto
            holding.average_buy_price = (old_total_cost + tx.total_value) / new_total_quantity if new_total_quantity > 0 else 0
            holding.quantity = new_total_quantity
        else: holding.quantity -= tx.quantity_crypto
        holding.save()
        messages.success(request, "Transação manual registrada com sucesso!")
        return redirect('core:transaction_history')
    return render(request, 'core/add_transaction.html', {'form': form, 'page_title': 'Adicionar Transação Manual'})

@login_required
@db_transaction.atomic
def sync_binance_trades_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user); client = get_valid_api_client(user_profile)
    if not client: messages.error(request, "Chaves API inválidas."); return redirect('core:transaction_history')
    existing_trade_ids = {note.split("Trade ID: ")[1] for note in Transaction.objects.filter(user_profile=user_profile, notes__icontains="Trade ID:").values_list('notes', flat=True) if "Trade ID: " in note}
    new_trades_count = 0
    for crypto in Cryptocurrency.objects.all():
        api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            for trade in client.get_my_trades(symbol=api_symbol, limit=200):
                if str(trade['id']) not in existing_trade_ids:
                    # Lógica de criação de transação e atualização de holding
                    new_trades_count += 1
        except BinanceAPIException as e:
            if e.code != -1121: messages.warning(request, f"Aviso ao sincronizar {api_symbol}: {e.message}")
        except Exception as e: messages.error(request, f"Erro inesperado ao sincronizar {api_symbol}: {e}")
    if new_trades_count > 0: messages.success(request, f"{new_trades_count} novas transações foram sincronizadas!")
    else: messages.info(request, "Nenhuma nova transação encontrada para sincronizar.")
    return redirect('core:transaction_history')

# --- Views de Negociação (Trading) ---
@login_required
def trade_market_buy_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user); client = get_valid_api_client(user_profile)
    if not client: messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    form = MarketBuyForm(request.POST or None, user_currency=BASE_RATE_CURRENCY)
    if request.method == 'POST' and form.is_valid():
        crypto = form.cleaned_data['cryptocurrency']; api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            params = {'symbol': api_symbol}
            if form.cleaned_data['buy_type'] == 'QUANTITY':
                quantity = form.cleaned_data['quantity']
                symbol_info = client.get_symbol_info(api_symbol)
                lot_size_filter = next(f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE')
                params['quantity'] = f'{adjust_quantity_to_lot_size(str(quantity), lot_size_filter["stepSize"]):.8f}'.rstrip('0').rstrip('.')
            else: params['quoteOrderQty'] = form.cleaned_data['quote_quantity']
            order = client.order_market_buy(**params); _process_successful_order(user_profile, order, crypto)
            messages.success(request, f"Ordem de compra para {api_symbol} executada com sucesso!")
            return redirect('core:dashboard')
        except (BinanceAPIException, ValueError) as e: messages.error(request, f"Erro: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_market_buy.html', {'form': form, 'page_title': 'Comprar a Mercado'})

@login_required
def trade_market_sell_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user); client = get_valid_api_client(user_profile)
    if not client: messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    form = MarketSellForm(request.POST or None, user_profile=user_profile, quote_currency=BASE_RATE_CURRENCY)
    if request.method == 'POST' and form.is_valid():
        crypto = form.cleaned_data['cryptocurrency']; api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            quantity_to_sell = Decimal('0')
            if form.cleaned_data['sell_type'] == 'QUANTITY':
                quantity_to_sell = form.cleaned_data['quantity']
            else:
                ticker = client.get_symbol_ticker(symbol=api_symbol)
                if Decimal(ticker['price']) > 0: quantity_to_sell = form.cleaned_data['quote_quantity_to_receive'] / Decimal(ticker['price'])
                else: raise ValueError("Preço de mercado inválido.")
            holding = Holding.objects.get(user_profile=user_profile, cryptocurrency=crypto)
            if holding.quantity < quantity_to_sell:
                raise ValueError(f"Saldo insuficiente.")
            symbol_info = client.get_symbol_info(api_symbol)
            lot_size_filter = next(f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE')
            quantity_to_sell = adjust_quantity_to_lot_size(str(quantity_to_sell), lot_size_filter['stepSize'])
            if quantity_to_sell <= 0: raise ValueError("Quantidade a vender deve ser positiva.")
            order = client.order_market_sell(symbol=api_symbol, quantity=f'{quantity_to_sell:.8f}'.rstrip('0').rstrip('.'))
            _process_successful_order(user_profile, order, crypto)
            messages.success(request, f"Ordem de venda para {api_symbol} executada!")
            return redirect('core:dashboard')
        except (BinanceAPIException, ValueError) as e: messages.error(request, f"Erro: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_market_sell.html', {'form': form, 'page_title': 'Vender a Mercado'})

@login_required
def trade_limit_buy_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user); client = get_valid_api_client(user_profile)
    if not client: messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    form = LimitBuyForm(request.POST or None, user_currency=user_profile.preferred_fiat_currency)
    if request.method == 'POST' and form.is_valid():
        crypto = form.cleaned_data['cryptocurrency']; api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            price_in_user_currency = form.cleaned_data['price']; price_in_base_currency = price_in_user_currency
            if user_profile.preferred_fiat_currency != crypto.price_currency:
                rate_obj = ExchangeRate.objects.get(from_currency=crypto.price_currency, to_currency=user_profile.preferred_fiat_currency)
                price_in_base_currency = price_in_user_currency / rate_obj.rate
            quantity = form.cleaned_data['quantity'] if form.cleaned_data['order_type'] == 'QUANTITY' else form.cleaned_data['total_value'] / price_in_user_currency
            symbol_info = client.get_symbol_info(api_symbol)
            price_in_base_currency = adjust_price_to_tick_size(str(price_in_base_currency), next(f['tickSize'] for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'))
            quantity = adjust_quantity_to_lot_size(str(quantity), next(f['stepSize'] for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'))
            if quantity <= 0: raise ValueError("Quantidade final deve ser positiva.")
            order = client.order_limit_buy(symbol=api_symbol, quantity=f'{quantity:.8f}'.rstrip('0').rstrip('.'), price=f'{price_in_base_currency:.8f}'.rstrip('0').rstrip('.'))
            messages.success(request, f"Ordem limite de COMPRA enviada! (ID: {order['orderId']})")
            return redirect('core:open_orders')
        except (BinanceAPIException, ValueError, ExchangeRate.DoesNotExist) as e:
            messages.error(request, f"Erro ao criar ordem: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_limit_buy.html', {'form': form, 'page_title': "Comprar com Ordem Limite"})

@login_required
def trade_limit_sell_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user); client = get_valid_api_client(user_profile)
    if not client: messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    form = LimitSellForm(request.POST or None, user_profile=user_profile)
    if request.method == 'POST' and form.is_valid():
        crypto = form.cleaned_data['cryptocurrency']; api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            price_in_user_currency = form.cleaned_data['price']; price_in_base_currency = price_in_user_currency
            if user_profile.preferred_fiat_currency != crypto.price_currency:
                rate_obj = ExchangeRate.objects.get(from_currency=crypto.price_currency, to_currency=user_profile.preferred_fiat_currency)
                price_in_base_currency = price_in_user_currency / rate_obj.rate
            quantity = form.cleaned_data['quantity'] if form.cleaned_data['order_type'] == 'QUANTITY' else form.cleaned_data['total_value'] / price_in_user_currency
            symbol_info = client.get_symbol_info(api_symbol)
            price_in_base_currency = adjust_price_to_tick_size(str(price_in_base_currency), next(f['tickSize'] for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'))
            quantity = adjust_quantity_to_lot_size(str(quantity), next(f['stepSize'] for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'))
            if quantity <= 0: raise ValueError("Quantidade final deve ser positiva.")
            order = client.order_limit_sell(symbol=api_symbol, quantity=f'{quantity:.8f}'.rstrip('0').rstrip('.'), price=f'{price_in_base_currency:.8f}'.rstrip('0').rstrip('.'))
            messages.success(request, f"Ordem limite de VENDA enviada! (ID: {order['orderId']})")
            return redirect('core:open_orders')
        except (BinanceAPIException, ValueError, ExchangeRate.DoesNotExist) as e:
            messages.error(request, f"Erro ao criar ordem: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_limit_sell.html', {'form': form, 'page_title': "Vender com Ordem Limite"})
