# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
# Importa o Paginator e as exceções relacionadas
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .forms import (
    CustomUserCreationForm, CustomAuthenticationForm, UserProfileAPIForm,
    TransactionForm, LimitBuyForm, LimitSellForm, MarketBuyForm, MarketSellForm
)
from .models import (
    Cryptocurrency, UserProfile, Holding, Transaction, 
    ExchangeRate, PortfolioSnapshot, BASE_RATE_CURRENCY
)
from decimal import Decimal, ROUND_DOWN
from binance.client import Client 
from binance.exceptions import BinanceAPIException
from django.db import transaction as db_transaction
from django.db.models import Sum
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
    if not all((api_key, secret)) or 'DECRYPTION_FAILED' in (api_key, secret): return None
    return Client(api_key, secret, tld='com', testnet=user_profile.use_testnet)

@db_transaction.atomic
def recalculate_holdings(user_profile):
    Holding.objects.filter(user_profile=user_profile).delete()
    transacted_cryptos = Cryptocurrency.objects.filter(transactions__user_profile=user_profile).distinct()
    
    print(f"\n--- INICIANDO RECÁLCULO DE PORTFÓLIO PARA {user_profile.user.username} ---")
    print(f"Criptomoedas transacionadas encontradas: {[c.symbol for c in transacted_cryptos]}")

    for crypto in transacted_cryptos:
        print(f"\nProcessando {crypto.symbol}...")
        buys = Transaction.objects.filter(user_profile=user_profile, cryptocurrency=crypto, transaction_type='BUY').aggregate(
            total_qty=Sum('quantity_crypto', default=Decimal('0.0')),
            total_cost=Sum('total_value', default=Decimal('0.0'))
        )
        sells = Transaction.objects.filter(user_profile=user_profile, cryptocurrency=crypto, transaction_type='SELL').aggregate(
            total_qty=Sum('quantity_crypto', default=Decimal('0.0'))
        )

        total_qty_bought = buys.get('total_qty') or Decimal('0.0')
        total_cost_of_buys = buys.get('total_cost') or Decimal('0.0')
        total_qty_sold = sells.get('total_qty') or Decimal('0.0')
        
        print(f"  Total Comprado: Qtd={total_qty_bought}, Custo={total_cost_of_buys}")
        print(f"  Total Vendido:  Qtd={total_qty_sold}")

        final_quantity = total_qty_bought - total_qty_sold
        print(f"  => Saldo Final Calculado: {final_quantity}")

        if final_quantity > Decimal('0.00000001'):
            avg_price = (total_cost_of_buys / total_qty_bought) if total_qty_bought > 0 else Decimal('0.0')
            print(f"  DECISÃO: Criar Holding com Qtd={final_quantity}, Preço Médio={avg_price}")
            Holding.objects.create(
                user_profile=user_profile, cryptocurrency=crypto,
                quantity=final_quantity, average_buy_price=avg_price
            )
        else:
            print(f"  DECISÃO: Não criar holding para {crypto.symbol} (saldo zerado ou negativo).")
    print("--- FIM DO RECÁLCULO DE PORTFÓLIO ---\n")

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
    recalculate_holdings(user_profile)

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
    exchange_rates_list = list(ExchangeRate.objects.filter(from_currency=BASE_RATE_CURRENCY))
    
    exchange_rates = {rate.to_currency: rate.rate for rate in exchange_rates_list}
    exchange_rates[BASE_RATE_CURRENCY] = Decimal('1.0')
    rate_to_pref_currency = exchange_rates.get(pref_currency)
    
    enriched_holdings = []
    pie_chart_data = {'labels': [], 'data': []}
    total_portfolio_value = Decimal('0.0')

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
            enriched_holdings.append({
                'holding': holding, 'average_buy_price_display': avg_buy_price_pref,
                'current_price_display': current_price_pref, 'current_value_display': current_value_pref,
                'profit_loss_display': profit_loss_pref, 'profit_loss_percent_display': profit_loss_percent,
                'display_currency': pref_currency
            })
            if current_value_pref > 0:
                pie_chart_data['labels'].append(holding.cryptocurrency.symbol)
                pie_chart_data['data'].append(float(current_value_pref))
    else:
        messages.warning(request, f"Não foi possível encontrar a taxa de câmbio para sua moeda preferida ({pref_currency}).")

    line_chart_data = {'labels': [], 'data': []}
    for snapshot in snapshots_list[-30:]:
        line_chart_data['labels'].append(snapshot.date.strftime('%d/%m'))
        line_chart_data['data'].append(float(snapshot.total_value))

    context = {
        'page_title': 'Meu Dashboard', 'holdings': enriched_holdings,
        'total_portfolio_value': total_portfolio_value, 'portfolio_currency': pref_currency,
        'pie_chart_data_json': json.dumps(pie_chart_data),
        'line_chart_data_json': json.dumps(line_chart_data)
    }
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
@db_transaction.atomic
def reset_portfolio_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    Transaction.objects.filter(user_profile=user_profile).delete()
    Holding.objects.filter(user_profile=user_profile).delete()
    PortfolioSnapshot.objects.filter(user_profile=user_profile).delete()
    messages.success(request, 'Seus dados de portfólio local (transações, posses, snapshots) foram zerados. Sincronize com a Binance para recriar seus dados.')
    return redirect('core:dashboard')

@login_required
def recalculate_holdings_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    recalculate_holdings(user_profile)
    messages.success(request, 'Seu portfólio foi recalculado com sucesso a partir do seu histórico de transações!')
    return redirect('core:dashboard')

@login_required
def cryptocurrency_list_view(request):
    client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, testnet=True)
    cryptos_from_db = Cryptocurrency.objects.all().order_by('name')
    
    enriched_cryptos_data = []
    for crypto in cryptos_from_db:
        data = {'db_instance': crypto}
        try:
            ticker_24h = client.get_ticker(symbol=f"{crypto.symbol.upper()}{crypto.price_currency.upper()}")
            data.update({'price_change_percent_24h': Decimal(ticker_24h.get('priceChangePercent', '0'))})
        except BinanceAPIException:
            # Define explicitamente como None em caso de falha para evitar erros no template
            data.update({'price_change_percent_24h': None})
        enriched_cryptos_data.append(data)

    # Cria o objeto Paginator com a lista enriquecida
    paginator = Paginator(enriched_cryptos_data, 20)  # Mostra 20 criptos por página
    page_number = request.GET.get('page')

    try:
        cryptocurrencies_page = paginator.page(page_number)
    except PageNotAnInteger:
        # Se 'page' não for um inteiro, mostra a primeira página
        cryptocurrencies_page = paginator.page(1)
    except EmptyPage:
        # Se 'page' estiver fora do intervalo, mostra a última página
        cryptocurrencies_page = paginator.page(paginator.num_pages)

    return render(request, 'core/cryptocurrency_list.html', {
        'page_title': 'Lista de Criptomoedas',
        'cryptocurrencies_page': cryptocurrencies_page  # Passa o objeto da página para o template
    })


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
    if not client: messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    if request.method == 'POST':
        order_id = request.POST.get('order_id'); symbol = request.POST.get('symbol')
        if order_id and symbol:
            try:
                client.cancel_order(symbol=symbol, orderId=order_id)
                messages.success(request, f"Ordem {order_id} cancelada.")
            except BinanceAPIException as e: messages.error(request, f"Erro ao cancelar: {e.message}")
        return redirect('core:open_orders')
    processed_orders = []
    try:
        open_orders = client.get_open_orders()
        for order in open_orders:
            order['time_dt'] = datetime.datetime.fromtimestamp(order['time'] / 1000, tz=datetime.timezone.utc)
            order['total_value'] = Decimal(order['price']) * Decimal(order['origQty'])
            processed_orders.append(order)
    except BinanceAPIException as e: messages.error(request, f"Erro ao buscar ordens: {e.message}")
    return render(request, 'core/open_orders.html', {'page_title': 'Minhas Ordens Abertas', 'open_orders': processed_orders})

@login_required
def transaction_history_view(request):
    # Obtém a lista de transações completa e ordenada
    transaction_list = Transaction.objects.filter(user_profile__user=request.user).order_by('-transaction_date')
    
    # Cria um objeto Paginator, com 15 transações por página
    paginator = Paginator(transaction_list, 15) 
    
    # Obtém o número da página da query string da URL (ex: ?page=2)
    page_number = request.GET.get('page')
    
    try:
        # Tenta obter a página solicitada
        transactions_page = paginator.page(page_number)
    except PageNotAnInteger:
        # Se 'page' não for um inteiro, entrega a primeira página.
        transactions_page = paginator.page(1)
    except EmptyPage:
        # Se 'page' estiver fora do intervalo (ex: 9999), entrega a última página de resultados.
        transactions_page = paginator.page(paginator.num_pages)
        
    # Passa o objeto 'page' para o template em vez da lista completa
    return render(request, 'core/transaction_history.html', {
        'transactions_page': transactions_page, 
        'page_title': 'Histórico de Transações'
    })


@login_required
@db_transaction.atomic
def add_transaction_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    form = TransactionForm(request.POST or None, user_profile=user_profile)
    if request.method == 'POST' and form.is_valid():
        tx = form.save(commit=False); tx.user_profile = user_profile; tx.save()
        recalculate_holdings(user_profile)
        messages.success(request, "Transação manual registrada e portfólio recalculado!")
        return redirect('core:dashboard')
    return render(request, 'core/add_transaction.html', {'form': form, 'page_title': 'Adicionar Transação Manual'})

@login_required
@db_transaction.atomic
def sync_binance_trades_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    client = get_valid_api_client(user_profile)
    if not client:
        messages.error(request, "Chaves API inválidas ou não configuradas para sincronizar.")
        return redirect('core:transaction_history')

    existing_trade_ids = set(
        note.split("Trade ID: ")[1] for note in
        Transaction.objects.filter(user_profile=user_profile, notes__icontains="Trade ID:").values_list('notes', flat=True)
        if "Trade ID: " in note
    )
    all_db_cryptos = Cryptocurrency.objects.all()
    new_trades_count = 0
    
    for crypto in all_db_cryptos:
        api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            trades = client.get_my_trades(symbol=api_symbol, limit=500)
            for trade in trades:
                trade_id = str(trade['id'])
                if trade_id not in existing_trade_ids:
                    Transaction.objects.create(
                        user_profile=user_profile, cryptocurrency=crypto,
                        transaction_type='BUY' if trade['isBuyer'] else 'SELL',
                        quantity_crypto=Decimal(trade['qty']), price_per_unit=Decimal(trade['price']),
                        fees=Decimal(trade['commission']), binance_order_id=str(trade['orderId']),
                        transaction_date=datetime.datetime.fromtimestamp(trade['time'] / 1000, tz=datetime.timezone.utc),
                        notes=f"Sincronizado da Binance. Trade ID: {trade_id}"
                    )
                    new_trades_count += 1
        except BinanceAPIException as e:
            if e.code != -1121: messages.warning(request, f"Aviso ao sincronizar {api_symbol}: {e.message}")
        except Exception as e:
            messages.error(request, f"Erro inesperado ao sincronizar {api_symbol}: {e}")
            continue

    if new_trades_count > 0:
        recalculate_holdings(user_profile)
        messages.success(request, f"{new_trades_count} nova(s) transação(ões) foram sincronizadas e o portfólio foi recalculado!")
    else:
        messages.info(request, "Nenhuma nova transação encontrada para sincronizar.")
        
    return redirect('core:transaction_history')

# --- Trading Views ---
@login_required
def trade_market_buy_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    client = get_valid_api_client(user_profile)
    if not client:
        messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    form = MarketBuyForm(request.POST or None, user_currency=BASE_RATE_CURRENCY)
    if request.method == 'POST' and form.is_valid():
        crypto = form.cleaned_data['cryptocurrency']
        api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            params = {'symbol': api_symbol}
            if form.cleaned_data['buy_type'] == 'QUANTITY':
                quantity = form.cleaned_data['quantity']
                symbol_info = client.get_symbol_info(api_symbol)
                lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                if lot_size_filter:
                    quantity = adjust_quantity_to_lot_size(str(quantity), lot_size_filter['stepSize'])
                params['quantity'] = f'{quantity:.8f}'.rstrip('0').rstrip('.')
            else:
                params['quoteOrderQty'] = form.cleaned_data['quote_quantity']
            order = client.order_market_buy(**params)
            _process_successful_order(user_profile, order, crypto)
            messages.success(request, f"Ordem de compra a mercado para {api_symbol} executada com sucesso!")
            return redirect('core:dashboard')
        except (BinanceAPIException, ValueError) as e:
            messages.error(request, f"Erro: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_market_buy.html', {'form': form, 'page_title': 'Comprar a Mercado'})

@login_required
def trade_market_sell_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    client = get_valid_api_client(user_profile)
    if not client:
        messages.error(request, "Chaves API inválidas."); return redirect('core:update_api_keys')
    form = MarketSellForm(request.POST or None, user_profile=user_profile, quote_currency=BASE_RATE_CURRENCY)
    if request.method == 'POST' and form.is_valid():
        crypto = form.cleaned_data['cryptocurrency']
        api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            quantity_to_sell = Decimal('0')
            if form.cleaned_data['sell_type'] == 'QUANTITY':
                quantity_to_sell = form.cleaned_data['quantity']
            else:
                ticker = client.get_symbol_ticker(symbol=api_symbol)
                price = Decimal(ticker['price'])
                if price > 0:
                    quantity_to_sell = form.cleaned_data['quote_quantity_to_receive'] / price
                else:
                    raise ValueError("Preço de mercado inválido para calcular a quantidade.")
            holding = Holding.objects.get(user_profile=user_profile, cryptocurrency=crypto)
            if holding.quantity < quantity_to_sell:
                raise ValueError(f"Saldo insuficiente.")
            symbol_info = client.get_symbol_info(api_symbol)
            lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            if lot_size_filter:
                quantity_to_sell = adjust_quantity_to_lot_size(str(quantity_to_sell), lot_size_filter['stepSize'])
            if quantity_to_sell <= 0:
                raise ValueError("Quantidade a vender deve ser maior que zero após ajustes.")
            order = client.order_market_sell(symbol=api_symbol, quantity=f'{quantity_to_sell:.8f}'.rstrip('0').rstrip('.'))
            _process_successful_order(user_profile, order, crypto)
            messages.success(request, f"Ordem de venda para {api_symbol} executada com sucesso!")
            return redirect('core:dashboard')
        except (BinanceAPIException, ValueError, Holding.DoesNotExist) as e:
            messages.error(request, f"Erro: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_market_sell.html', {'form': form, 'page_title': 'Vender a Mercado'})

@login_required
def trade_limit_buy_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    client = get_valid_api_client(user_profile)
    if not client:
        messages.error(request, "Chaves API inválidas ou não configuradas."); return redirect('core:update_api_keys')
    form = LimitBuyForm(request.POST or None, user_currency=user_profile.preferred_fiat_currency)
    if request.method == 'POST' and form.is_valid():
        crypto = form.cleaned_data['cryptocurrency']
        api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            price_in_user_currency = form.cleaned_data['price']
            price_in_base_currency = price_in_user_currency
            if user_profile.preferred_fiat_currency != crypto.price_currency:
                rate_obj = ExchangeRate.objects.get(from_currency=crypto.price_currency, to_currency=user_profile.preferred_fiat_currency)
                price_in_base_currency = price_in_user_currency / rate_obj.rate
            quantity = form.cleaned_data['quantity'] if form.cleaned_data['order_type'] == 'QUANTITY' else form.cleaned_data['total_value'] / price_in_user_currency
            symbol_info = client.get_symbol_info(api_symbol)
            price_in_base_currency = adjust_price_to_tick_size(str(price_in_base_currency), next(f['tickSize'] for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'))
            quantity = adjust_quantity_to_lot_size(str(quantity), next(f['stepSize'] for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'))
            if quantity <= 0: raise ValueError("A quantidade final da ordem deve ser maior que zero.")
            order = client.order_limit_buy(symbol=api_symbol, quantity=f'{quantity:.8f}'.rstrip('0').rstrip('.'), price=f'{price_in_base_currency:.8f}'.rstrip('0').rstrip('.'))
            messages.success(request, f"Ordem limite de COMPRA enviada! ID: {order['orderId']}")
            return redirect('core:open_orders')
        except (BinanceAPIException, ValueError, ExchangeRate.DoesNotExist) as e:
            messages.error(request, f"Erro ao criar ordem: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_limit_buy.html', {'form': form, 'page_title': "Comprar com Ordem Limite"})

@login_required
def trade_limit_sell_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    client = get_valid_api_client(user_profile)
    if not client:
        messages.error(request, "Chaves API inválidas ou não configuradas."); return redirect('core:update_api_keys')
    form = LimitSellForm(request.POST or None, user_profile=user_profile)
    if request.method == 'POST' and form.is_valid():
        crypto = form.cleaned_data['cryptocurrency']
        api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
        try:
            price_in_user_currency = form.cleaned_data['price']
            price_in_base_currency = price_in_user_currency
            if user_profile.preferred_fiat_currency != crypto.price_currency:
                rate_obj = ExchangeRate.objects.get(from_currency=crypto.price_currency, to_currency=user_profile.preferred_fiat_currency)
                price_in_base_currency = price_in_user_currency / rate_obj.rate
            quantity = form.cleaned_data['quantity'] if form.cleaned_data['order_type'] == 'QUANTITY' else form.cleaned_data['total_value'] / price_in_user_currency
            symbol_info = client.get_symbol_info(api_symbol)
            price_in_base_currency = adjust_price_to_tick_size(str(price_in_base_currency), next(f['tickSize'] for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'))
            quantity = adjust_quantity_to_lot_size(str(quantity), next(f['stepSize'] for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'))
            if quantity <= 0: raise ValueError("A quantidade final da ordem deve ser maior que zero.")
            order = client.order_limit_sell(symbol=api_symbol, quantity=f'{quantity:.8f}'.rstrip('0').rstrip('.'), price=f'{price_in_base_currency:.8f}'.rstrip('0').rstrip('.'))
            messages.success(request, f"Ordem limite de VENDA enviada! ID: {order['orderId']}")
            return redirect('core:open_orders')
        except (BinanceAPIException, ValueError, ExchangeRate.DoesNotExist) as e:
            messages.error(request, f"Erro ao criar ordem: {getattr(e, 'message', str(e))}")
    return render(request, 'core/trade_limit_sell.html', {'form': form, 'page_title': "Vender com Ordem Limite"})
