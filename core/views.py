# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from .forms import (
    CustomUserCreationForm, 
    CustomAuthenticationForm, 
    TransactionForm, 
    UserProfileAPIForm,
    TradeForm,
    MarketSellForm 
)
from .models import Cryptocurrency, UserProfile, Holding, Transaction
from decimal import Decimal, ROUND_DOWN, ROUND_UP, InvalidOperation
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from django.db import transaction as db_transaction
import datetime 
import json 

# --- Helper Function para ajustar quantidade ao LOT_SIZE ---
def adjust_quantity_to_lot_size(quantity_str, step_size_str):
    quantity = Decimal(quantity_str)
    step_size = Decimal(step_size_str)
    if step_size <= Decimal(0):
        return quantity.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
    normalized_step_size_str = step_size_str.rstrip('0')
    if '.' in normalized_step_size_str:
        precision = len(normalized_step_size_str.split('.')[1])
    else:
        precision = 0
    adjusted_quantity = (quantity / step_size).to_integral_value(rounding=ROUND_DOWN) * step_size
    return adjusted_quantity.quantize(Decimal('1e-' + str(precision)), rounding=ROUND_DOWN)

# ... (views anteriores) ...
def index_view(request):
    context = {
        'page_title': 'Bem-vindo ao Crypto Trader',
        'message': 'Sua plataforma para negociação de criptomoedas.'
    }
    return render(request, 'core/index.html', context)

def register_view(request):
    if request.user.is_authenticated:
        messages.info(request, "Você já está logado.")
        return redirect('core:dashboard')
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Conta criada com sucesso para {user.username}! Bem-vindo(a)!')
            return redirect('core:dashboard')
        else:
            for field in form:
                for error_list in field.errors.as_data():
                    for error in error_list:
                        messages.error(request, f"{field.label}: {error.message}")
            if form.non_field_errors():
                 for error in form.non_field_errors():
                    messages.error(request, error)
    else:
        form = CustomUserCreationForm()
    context = {'form': form, 'page_title': 'Registrar Nova Conta'}
    return render(request, 'core/register.html', context)


def login_view(request):
    if request.user.is_authenticated:
        messages.info(request, "Você já está logado.")
        return redirect('core:dashboard')
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.info(request, f'Login bem-sucedido! Bem-vindo(a) de volta, {username}.')
                next_page = request.GET.get('next')
                return redirect(next_page or 'core:dashboard')
            else:
                messages.error(request, 'Nome de usuário ou senha inválidos.')
        else: 
            if form.non_field_errors():
                 for error in form.non_field_errors():
                    messages.error(request, error)
            else:
                has_field_errors = False
                for field in form:
                    for error_list in field.errors.as_data():
                        for error in error_list:
                            messages.error(request, f"{field.label}: {error.message}")
                            has_field_errors = True
                if not has_field_errors and not form.non_field_errors(): 
                     messages.error(request, 'Dados de login inválidos. Verifique e tente novamente.')
    else:
        form = CustomAuthenticationForm()
    context = {'form': form, 'page_title': 'Login'}
    return render(request, 'core/login.html', context)

@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'Você foi desconectado com sucesso.')
    return redirect('core:index')

@login_required
def dashboard_view(request):
    try:
        user_profile, created = UserProfile.objects.get_or_create(user=request.user)
        holdings_qs = Holding.objects.filter(user_profile=user_profile).select_related('cryptocurrency')
    except Exception as e: 
        messages.error(request, f"Ocorreu um erro ao carregar o dashboard: {e}")
        return redirect('core:index')

    total_portfolio_value_in_preferred_currency = Decimal('0.0')
    enriched_holdings = []
    
    conversion_warning_shown_for_request = False
    currency_mismatch_warning_shown_for_request = False
    
    client = None
    if settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET: 
        try:
            client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, tld='com', testnet=settings.BINANCE_TESTNET)
        except Exception:
            client = None 

    for holding_item in holdings_qs:
        current_value_in_crypto_price_currency = holding_item.current_market_value 
        
        value_in_preferred_currency = None
        if current_value_in_crypto_price_currency is not None:
            if holding_item.cryptocurrency.price_currency == user_profile.preferred_fiat_currency:
                value_in_preferred_currency = current_value_in_crypto_price_currency
            elif client: 
                try:
                    conversion_pair = f"{holding_item.cryptocurrency.price_currency.upper()}{user_profile.preferred_fiat_currency.upper()}"
                    if holding_item.cryptocurrency.price_currency.upper() == "USDT" and user_profile.preferred_fiat_currency.upper() == "USD":
                        conversion_rate = Decimal('1.0') 
                    elif conversion_pair == f"{user_profile.preferred_fiat_currency.upper()}{user_profile.preferred_fiat_currency.upper()}":
                         conversion_rate = Decimal('1.0') 
                    else:
                        ticker = client.get_symbol_ticker(symbol=conversion_pair)
                        conversion_rate = Decimal(ticker['price'])
                    
                    value_in_preferred_currency = current_value_in_crypto_price_currency * conversion_rate
                except Exception as e:
                    print(f"Dashboard: Falha ao converter {holding_item.cryptocurrency.price_currency} para {user_profile.preferred_fiat_currency} para {holding_item.cryptocurrency.symbol}. Erro: {e}")
                    value_in_preferred_currency = current_value_in_crypto_price_currency 
                    if not conversion_warning_shown_for_request:
                        messages.warning(request, f"Atenção: Alguns valores podem não estar na sua moeda preferida ({user_profile.preferred_fiat_currency}) devido a falhas na conversão de taxas.")
                        conversion_warning_shown_for_request = True
            else: 
                value_in_preferred_currency = current_value_in_crypto_price_currency
                if holding_item.cryptocurrency.price_currency != user_profile.preferred_fiat_currency:
                    if not currency_mismatch_warning_shown_for_request:
                        messages.warning(request, f"Atenção: O valor total do portfólio pode incluir moedas diferentes de sua preferência ({user_profile.preferred_fiat_currency}) pois o cliente Binance não está disponível para conversão.")
                        currency_mismatch_warning_shown_for_request = True

        if value_in_preferred_currency is not None:
            total_portfolio_value_in_preferred_currency += value_in_preferred_currency
        
        enriched_holdings.append({
            'holding': holding_item,
            'current_value_display': value_in_preferred_currency, 
            'original_currency': holding_item.cryptocurrency.price_currency,
            'profit_loss': holding_item.profit_loss, 
            'profit_loss_percent': holding_item.profit_loss_percent
        })

    context = {
        'page_title': 'Meu Dashboard',
        'user': request.user,
        'user_profile': user_profile,
        'holdings': enriched_holdings,
        'total_portfolio_value': total_portfolio_value_in_preferred_currency,
        'portfolio_currency': user_profile.preferred_fiat_currency,
        'show_conversion_warning': conversion_warning_shown_for_request,
        'show_currency_mismatch_warning': currency_mismatch_warning_shown_for_request,
    }
    return render(request, 'core/dashboard.html', context)

@login_required
def binance_test_view(request):
    context = {'page_title': 'Teste da API Binance'}
    api_key = settings.BINANCE_API_KEY
    api_secret = settings.BINANCE_API_SECRET
    use_testnet = settings.BINANCE_TESTNET

    if not api_key or not api_secret:
        messages.warning(request, "As chaves da API (BINANCE_API_KEY, BINANCE_API_SECRET) não estão configuradas nas variáveis de ambiente.")
        context['error_message'] = "Chaves da API não configuradas."
        return render(request, 'core/binance_test.html', context)
    try:
        client = Client(api_key, api_secret, tld='com', testnet=use_testnet) 
        messages.info(request, f"Conectando à {'Testnet' if use_testnet else 'API Principal'} da Binance...")

        server_time = client.get_server_time()
        context['server_time'] = server_time
        messages.success(request, f"Horário do servidor Binance obtido: {server_time.get('serverTime')}")

        account_info = client.get_account()
        context['account_info'] = {
            'balances': [b for b in account_info.get('balances', []) if Decimal(b['free']) > 0 or Decimal(b['locked']) > 0],
            'canTrade': account_info.get('canTrade'),
            'accountType': account_info.get('accountType'),
        }
        messages.success(request, "Informações da conta obtidas com sucesso!")

    except BinanceAPIException as e:
        error_msg = f"Erro API Binance: {e.message} (Cod: {e.code})"
        if e.code == -2015: 
             error_msg = f"Chave API/Secret inválida ou permissões insuficientes para esta ação. Verifique as permissões da chave na Binance. (Erro: {e.message})"
        messages.error(request, error_msg)
        context['error_message'] = error_msg
    except BinanceRequestException as e:
        error_msg = f"Erro Requisição Binance: {e.message} (Status: {e.status_code})"
        messages.error(request, error_msg)
        context['error_message'] = error_msg
    except Exception as e:
        error_msg = f"Erro inesperado ao conectar com a Binance: {str(e)}"
        messages.error(request, error_msg)
        context['error_message'] = error_msg
    return render(request, 'core/binance_test.html', context)


@login_required
def cryptocurrency_list_view(request):
    client = None
    client_initialized_successfully = False
    if settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET:
        try:
            client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, tld='com', testnet=settings.BINANCE_TESTNET)
            client_initialized_successfully = True
        except Exception as e:
            messages.error(request, f"Falha ao inicializar o cliente da Binance: {e}")
            print(f"Falha ao inicializar o cliente da Binance: {e}") 
    else:
        messages.warning(request, "Chaves API da Binance (sistema) não configuradas. Os dados de mercado não serão atualizados da API.")
        print("Chaves API da Binance (sistema) não configuradas.")

    cryptos_from_db = Cryptocurrency.objects.all()
    enriched_cryptos_data = []
    data_updated_count = 0

    for crypto_instance in cryptos_from_db:
        crypto_data = {
            'db_instance': crypto_instance,
            'symbol': crypto_instance.symbol,
            'name': crypto_instance.name,
            'logo_url': crypto_instance.logo_url,
            'current_price': crypto_instance.current_price, 
            'price_currency': crypto_instance.price_currency,
            'last_updated': crypto_instance.last_updated,
            'price_change_percent_24h': None,
            'volume_24h': None,
            'high_price_24h': None,
            'low_price_24h': None,
        }

        if client_initialized_successfully and client: 
            try:
                api_symbol_pair = f"{crypto_instance.symbol.upper()}{crypto_instance.price_currency.upper()}"
                
                ticker_24h = client.get_ticker(symbol=api_symbol_pair)
                
                if ticker_24h:
                    new_price = Decimal(ticker_24h.get('lastPrice', '0')) 
                    
                    crypto_instance.current_price = new_price
                    crypto_instance.last_updated = timezone.now()
                    crypto_instance.save() 
                    
                    crypto_data['current_price'] = new_price
                    crypto_data['last_updated'] = crypto_instance.last_updated
                    crypto_data['price_change_percent_24h'] = Decimal(ticker_24h.get('priceChangePercent', '0'))
                    crypto_data['volume_24h'] = Decimal(ticker_24h.get('volume', '0')) 
                    crypto_data['high_price_24h'] = Decimal(ticker_24h.get('highPrice', '0'))
                    crypto_data['low_price_24h'] = Decimal(ticker_24h.get('lowPrice', '0'))
                    
                    data_updated_count += 1
                else:
                    print(f"Ticker 24h não encontrado para {api_symbol_pair}")
            
            except BinanceAPIException as e:
                print(f"API Erro ao buscar dados de 24h (Símbolo: {api_symbol_pair}): {e.message} (Cod: {e.code})")
            except (BinanceRequestException, InvalidOperation) as e: 
                print(f"Request/Decimal Erro (Símbolo: {api_symbol_pair}): {e}")
            except Exception as e: 
                print(f"Erro inesperado (Símbolo: {api_symbol_pair}): {str(e)}")
        
        enriched_cryptos_data.append(crypto_data) 

    if client_initialized_successfully and data_updated_count > 0 :
        messages.success(request, f"{data_updated_count} criptomoeda(s) tiveram seus dados de mercado atualizados da API da Binance.")
    elif client_initialized_successfully and data_updated_count == 0 and cryptos_from_db.exists():
         messages.info(request, "Nenhum dado de mercado foi atualizado da API. Verifique a configuração dos pares de moedas no admin (ex: BTC com moeda USDT) e os logs do servidor.")

    context = {
        'page_title': 'Lista de Criptomoedas',
        'cryptocurrencies_data': enriched_cryptos_data, 
    }
    return render(request, 'core/cryptocurrency_list.html', context)

@login_required
def cryptocurrency_detail_view(request, symbol):
    crypto = get_object_or_404(Cryptocurrency, symbol__iexact=symbol) 
    
    klines_data_json = "[]" 
    chart_error_message = None 

    if settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET:
        try:
            client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, tld='com', testnet=settings.BINANCE_TESTNET)
            
            api_symbol_pair = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
            
            end_time = datetime.datetime.now(datetime.timezone.utc) 
            start_time = end_time - datetime.timedelta(days=90) 

            start_ts_ms_str = str(int(start_time.timestamp() * 1000))
            
            klines = client.get_historical_klines(
                api_symbol_pair,
                Client.KLINE_INTERVAL_1DAY, 
                start_str=start_ts_ms_str
            )
            
            chart_labels = []
            chart_data_close = []
            
            if not klines: 
                chart_error_message = f"Nenhum dado histórico encontrado para {api_symbol_pair} no período solicitado."
                messages.warning(request, chart_error_message)
            else:
                for kline_entry in klines:
                    dt_object = datetime.datetime.fromtimestamp(kline_entry[0]/1000, tz=datetime.timezone.utc)
                    chart_labels.append(dt_object.strftime('%Y-%m-%d')) 
                    chart_data_close.append(str(Decimal(kline_entry[4]))) 

                klines_data_for_template = {
                    'labels': chart_labels,
                    'data': chart_data_close,
                    'symbol': crypto.symbol, 
                    'price_currency': crypto.price_currency 
                }
                klines_data_json = json.dumps(klines_data_for_template) 

                messages.success(request, f"Dados históricos para o gráfico de {api_symbol_pair} carregados com sucesso.")

        except BinanceAPIException as e:
            chart_error_message = f"Erro da API Binance ao buscar dados históricos para {crypto.symbol} (par: {api_symbol_pair}): {e.message}. Verifique se o par é válido."
            messages.error(request, chart_error_message)
            print(f"Erro API Binance (histórico para {api_symbol_pair}): {e.message} (Cod: {e.code})")
        except Exception as e: 
            chart_error_message = f"Erro inesperado ao buscar dados históricos para {crypto.symbol}: {str(e)}"
            messages.error(request, chart_error_message)
            print(f"Erro inesperado (histórico para {api_symbol_pair}): {str(e)}")
    else:
        chart_error_message = "Chaves API da Binance não configuradas. Não é possível carregar o gráfico de histórico."
        messages.warning(request, chart_error_message)

    context = {
        'page_title': f"Detalhes de {crypto.name} ({crypto.symbol})",
        'crypto': crypto,
        'klines_data_json': klines_data_json, 
        'chart_error_message': chart_error_message, 
    }
    return render(request, 'core/cryptocurrency_detail.html', context)


@login_required
@db_transaction.atomic 
def add_transaction_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    if request.method == 'POST':
        form = TransactionForm(request.POST, user_profile=user_profile)
        if form.is_valid():
            try:
                transaction = form.save(commit=False)
                transaction.user_profile = user_profile
                transaction.save()

                holding, created = Holding.objects.get_or_create(
                    user_profile=user_profile,
                    cryptocurrency=transaction.cryptocurrency,
                    defaults={'average_buy_price': Decimal('0.0'), 'quantity': Decimal('0.0')}
                )

                if transaction.transaction_type == 'BUY':
                    current_transaction_cost = transaction.quantity_crypto * transaction.price_per_unit
                    old_total_cost = holding.quantity * (holding.average_buy_price if holding.average_buy_price is not None else Decimal('0.0'))
                    new_total_quantity = holding.quantity + transaction.quantity_crypto
                    new_total_cost = old_total_cost + current_transaction_cost

                    if new_total_quantity > 0:
                        holding.average_buy_price = new_total_cost / new_total_quantity
                    else: 
                        holding.average_buy_price = Decimal('0.0')
                    holding.quantity = new_total_quantity

                elif transaction.transaction_type == 'SELL':
                    holding.quantity -= transaction.quantity_crypto
                    if holding.quantity < 0: 
                        messages.error(request, "Erro: Tentativa de vender mais do que possui. Transação não registrada.")
                        raise ValueError("Quantidade em holding não pode ser negativa após a venda.") 
                    if holding.quantity == 0:
                        holding.average_buy_price = Decimal('0.0') 

                holding.save()
                messages.success(request, f"Transação de {transaction.get_transaction_type_display()} de {transaction.cryptocurrency.symbol} registrada com sucesso!")
                return redirect('core:transaction_history') 
            except ValueError as ve: 
                 messages.error(request, str(ve))
            except Exception as e:
                messages.error(request, f"Ocorreu um erro grave ao processar a transação: {e}")
        else: 
            for field, errors in form.errors.items():
                for error in errors:
                    field_label = form.fields[field].label if field != '__all__' and field in form.fields else "Erro geral do formulário"
                    messages.error(request, f"{field_label}: {error}")
    else:
        form = TransactionForm(user_profile=user_profile)

    context = {
        'form': form,
        'page_title': 'Adicionar Nova Transação'
    }
    return render(request, 'core/add_transaction.html', context)

@login_required
def transaction_history_view(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        transactions = Transaction.objects.filter(user_profile=user_profile).select_related('cryptocurrency').order_by('-transaction_date', '-timestamp')
    except UserProfile.DoesNotExist:
        messages.error(request, "Perfil de usuário não encontrado.")
        return redirect('core:index') 

    context = {
        'page_title': 'Histórico de Transações',
        'transactions': transactions,
        'user_profile': user_profile, 
    }
    return render(request, 'core/transaction_history.html', context)

@login_required
def update_api_keys_view(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = UserProfileAPIForm(request.POST, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Suas configurações de API e preferências foram atualizadas com sucesso!')
            return redirect('core:dashboard') 
        else:
            messages.error(request, 'Por favor, corrija os erros abaixo.')
    else:
        form = UserProfileAPIForm(instance=user_profile)

    context = {
        'form': form,
        'page_title': 'Configurar Chaves API e Preferências'
    }
    return render(request, 'core/profile_api_keys.html', context)

@login_required
def trade_market_buy_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)

    if not user_profile.binance_api_key or not user_profile.binance_api_secret:
        messages.error(request, "Suas chaves API da Binance não estão configuradas. Por favor, configure-as em seu perfil antes de negociar.")
        return redirect('core:update_api_keys')

    if request.method == 'POST':
        form = TradeForm(request.POST)
        if form.is_valid():
            crypto_to_buy = form.cleaned_data['cryptocurrency']
            buy_type = form.cleaned_data['buy_type']
            quantity_base_input = form.cleaned_data.get('quantity') 
            quantity_quote_input = form.cleaned_data.get('quote_quantity')
            
            api_symbol_pair = f"{crypto_to_buy.symbol.upper()}{crypto_to_buy.price_currency.upper()}"

            try:
                client = Client(user_profile.binance_api_key, user_profile.binance_api_secret, tld='com', testnet=True)
                
                symbol_info = client.get_symbol_info(api_symbol_pair)
                lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                min_notional_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), None)
                
                step_size_str = "0.00000001" 
                min_qty_str = "0"
                if lot_size_filter:
                    step_size_str = lot_size_filter['stepSize']
                    min_qty_str = lot_size_filter['minQty']

                min_notional_str = "0"
                if min_notional_filter:
                    min_notional_str = min_notional_filter['minNotional']

                order_params = {'symbol': api_symbol_pair}
                log_msg_qty_type = ""

                if buy_type == 'QUANTITY' and quantity_base_input:
                    adjusted_quantity = adjust_quantity_to_lot_size(str(quantity_base_input), step_size_str)
                    if adjusted_quantity < Decimal(min_qty_str):
                        messages.error(request, f"A quantidade ajustada ({adjusted_quantity} {crypto_to_buy.symbol}) é menor que a quantidade mínima permitida ({min_qty_str}) para {api_symbol_pair}.")
                        raise ValueError(f"Quantidade ajustada {adjusted_quantity} abaixo da mínima {min_qty_str}")

                    order_params['quantity'] = f"{adjusted_quantity}" 
                    log_msg_qty_type = f"{adjusted_quantity} {crypto_to_buy.symbol}"

                elif buy_type == 'QUOTE_QUANTITY' and quantity_quote_input:
                    if quantity_quote_input < Decimal(min_notional_str):
                        messages.error(request, f"O valor da ordem ({quantity_quote_input} {crypto_to_buy.price_currency}) é menor que o valor nocional mínimo permitido ({min_notional_str}) para {api_symbol_pair}.")
                        raise ValueError(f"Valor da ordem {quantity_quote_input} abaixo do nocional mínimo {min_notional_str}")
                    order_params['quoteOrderQty'] = quantity_quote_input
                    log_msg_qty_type = f"{quantity_quote_input} {crypto_to_buy.price_currency} de"
                else:
                    messages.error(request, "Tipo de compra ou quantidade inválida.")
                    return redirect('core:trade_market_buy')

                messages.info(request, f"Tentando executar ordem de COMPRA A MERCADO: {log_msg_qty_type} {crypto_to_buy.symbol} ({api_symbol_pair}) na Testnet...")
                
                order_response = client.order_market_buy(**order_params)

                messages.success(request, f"Ordem de COMPRA para {api_symbol_pair} enviada com sucesso! ID da Ordem: {order_response.get('orderId')}")
                
                executed_qty_total = Decimal('0')
                cummulative_quote_qty_total = Decimal('0')
                
                if buy_type == 'QUOTE_QUANTITY':
                    executed_qty_total = Decimal(order_response.get('executedQty', '0'))
                    cummulative_quote_qty_total = Decimal(order_response.get('cummulativeQuoteQty', '0'))
                elif order_response.get('fills'): 
                    for fill in order_response['fills']:
                        price = Decimal(fill['price'])
                        qty = Decimal(fill['qty'])
                        executed_qty_total += qty
                        cummulative_quote_qty_total += price * qty
                        
                if executed_qty_total > 0:
                    average_price = (cummulative_quote_qty_total / executed_qty_total)
                    
                    with db_transaction.atomic():
                        local_tx = Transaction.objects.create(
                            user_profile=user_profile,
                            cryptocurrency=crypto_to_buy,
                            transaction_type='BUY',
                            quantity_crypto=executed_qty_total,
                            price_per_unit=average_price, 
                            transaction_date=timezone.now(), 
                            binance_order_id=str(order_response.get('orderId')),
                            notes=f"Compra a mercado via API. Qtd: {executed_qty_total:.8f}, Preço Médio: {average_price:.8f} {crypto_to_buy.price_currency}. Quote Gasto: {cummulative_quote_qty_total:.2f} {crypto_to_buy.price_currency}."
                        )
                        
                        holding, created = Holding.objects.get_or_create(
                            user_profile=user_profile,
                            cryptocurrency=crypto_to_buy,
                            defaults={'average_buy_price': Decimal('0.0'), 'quantity': Decimal('0.0')}
                        )
                        current_transaction_cost = local_tx.quantity_crypto * local_tx.price_per_unit
                        old_total_cost = holding.quantity * (holding.average_buy_price if holding.average_buy_price is not None else Decimal('0.0'))
                        new_total_quantity = holding.quantity + local_tx.quantity_crypto
                        new_total_cost = old_total_cost + current_transaction_cost

                        if new_total_quantity > 0:
                            holding.average_buy_price = (new_total_cost / new_total_quantity)
                        else: 
                            holding.average_buy_price = Decimal('0.0')
                        holding.quantity = new_total_quantity
                        holding.save()

                    messages.success(request, f"Transação local registrada para compra de {executed_qty_total:.8f} {crypto_to_buy.symbol} a ~{average_price:.2f} {crypto_to_buy.price_currency}.")
                else: 
                    messages.warning(request, f"A ordem foi enviada (ID: {order_response.get('orderId')}), mas não houve execuções reportadas ou a quantidade executada foi zero. Verifique o status na Binance.")

                return redirect('core:transaction_history')

            except BinanceAPIException as e:
                error_message = f"Erro da API Binance: {e.message} (Cod: {e.code})"
                if e.code == -1013: # Filter failure
                    if "LOT_SIZE" in e.message.upper():
                        error_message = f"Erro de Quantidade (LOT_SIZE): A quantidade especificada não atende aos requisitos de tamanho do lote ({step_size_str}) ou quantidade mínima ({min_qty_str}) da Binance para {api_symbol_pair}. (Detalhe: {e.message})"
                    elif "MIN_NOTIONAL" in e.message.upper():
                         error_message = f"Erro de Valor Mínimo (MIN_NOTIONAL): O valor total da ordem não atinge o mínimo exigido ({min_notional_str} {crypto_to_buy.price_currency}) pela Binance para {api_symbol_pair}. Tente um valor maior. (Detalhe: {e.message})"
                elif e.code == -2010: 
                    error_message = f"Ordem Rejeitada pela Binance: {e.message}. Verifique seu saldo na Testnet ou os limites do par."

                messages.error(request, error_message)
                print(f"Erro API Binance (COMPRA {api_symbol_pair}): {e.message} (Cod: {e.code})")
            except ValueError as ve: 
                messages.error(request, str(ve))
            except BinanceRequestException as e:
                messages.error(request, f"Erro de requisição à Binance: {e.message}")
            except Exception as e:
                messages.error(request, f"Erro inesperado: {str(e)}")
        else: 
            messages.error(request, "Por favor, corrija os erros no formulário.")
    else:
        form = TradeForm()

    context = {
        'form': form,
        'page_title': 'Comprar Criptomoeda (Ordem a Mercado - Testnet)'
    }
    return render(request, 'core/trade_form.html', context)

@login_required
def trade_market_sell_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)

    if not user_profile.binance_api_key or not user_profile.binance_api_secret:
        messages.error(request, "Suas chaves API da Binance não estão configuradas. Por favor, configure-as em seu perfil antes de negociar.")
        return redirect('core:update_api_keys')

    if request.method == 'POST':
        form = MarketSellForm(request.POST, user_profile=user_profile) 
        if form.is_valid():
            crypto_to_sell = form.cleaned_data['cryptocurrency']
            sell_type = form.cleaned_data['sell_type']
            quantity_base_input = form.cleaned_data.get('quantity')
            quote_quantity_to_receive_input = form.cleaned_data.get('quote_quantity_to_receive')
            
            api_symbol_pair = f"{crypto_to_sell.symbol.upper()}{crypto_to_sell.price_currency.upper()}"

            try:
                client = Client(user_profile.binance_api_key, user_profile.binance_api_secret, tld='com', testnet=True)
                
                symbol_info = client.get_symbol_info(api_symbol_pair)
                lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                min_notional_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), None) # Útil para validar quote_quantity_to_receive
                
                step_size_str = "0.00000001" 
                min_qty_str = "0"
                if lot_size_filter:
                    step_size_str = lot_size_filter['stepSize']
                    min_qty_str = lot_size_filter['minQty']
                
                min_notional_str = "0"
                if min_notional_filter: # Valor mínimo da ordem na moeda de cotação
                    min_notional_str = min_notional_filter['minNotional']


                order_params = {'symbol': api_symbol_pair}
                quantity_to_actually_sell = Decimal('0') # Quantidade da cripto base que será vendida

                if sell_type == 'QUANTITY' and quantity_base_input:
                    adjusted_quantity = adjust_quantity_to_lot_size(str(quantity_base_input), step_size_str)
                    if adjusted_quantity < Decimal(min_qty_str):
                         messages.error(request, f"A quantidade ajustada para venda ({adjusted_quantity} {crypto_to_sell.symbol}) é menor que a quantidade mínima permitida ({min_qty_str}) para {api_symbol_pair}.")
                         raise ValueError(f"Quantidade ajustada para venda {adjusted_quantity} abaixo da mínima {min_qty_str}")
                    if adjusted_quantity == Decimal(0):
                        messages.error(request, f"A quantidade ajustada para venda de {crypto_to_sell.symbol} é zero. A ordem não foi enviada.")
                        raise ValueError("Quantidade ajustada para venda é zero.")
                    
                    quantity_to_actually_sell = adjusted_quantity
                    order_params['quantity'] = f"{quantity_to_actually_sell}"
                    log_msg_qty_type = f"{quantity_to_actually_sell} {crypto_to_sell.symbol}"

                elif sell_type == 'QUOTE_RECEIVE' and quote_quantity_to_receive_input:
                    if quote_quantity_to_receive_input < Decimal(min_notional_str):
                        messages.error(request, f"O valor desejado a receber ({quote_quantity_to_receive_input} {crypto_to_sell.price_currency}) é menor que o valor nocional mínimo permitido ({min_notional_str}) para {api_symbol_pair}.")
                        raise ValueError(f"Valor desejado {quote_quantity_to_receive_input} abaixo do nocional mínimo {min_notional_str}")

                    # Para vender por 'quote quantity', precisamos estimar a quantidade da base
                    # A API não suporta 'quoteOrderQty' para venda a mercado diretamente da mesma forma que para compra.
                    # Precisamos vender uma 'quantity' da base.
                    # 1. Obter o preço de mercado atual (ask price, pois queremos vender)
                    # 2. Calcular a quantidade da base: quote_quantity_to_receive_input / ask_price
                    # 3. Ajustar essa quantidade ao LOT_SIZE
                    # 4. Verificar se o usuário tem essa quantidade.
                    
                    # Obter o melhor preço de compra (bid) no livro de ofertas, pois estamos vendendo
                    depth = client.get_order_book(symbol=api_symbol_pair, limit=5)
                    if not depth['bids']:
                        messages.error(request, f"Não foi possível obter o preço de mercado atual para {api_symbol_pair} para calcular a quantidade de venda.")
                        raise ValueError("Livro de ofertas vazio ou indisponível.")
                    
                    current_market_price = Decimal(depth['bids'][0][0]) # Melhor preço de compra (alguém querendo comprar de você)
                    
                    if current_market_price <= 0:
                         messages.error(request, f"Preço de mercado inválido ({current_market_price}) obtido para {api_symbol_pair}.")
                         raise ValueError("Preço de mercado inválido.")

                    estimated_base_qty_to_sell = quote_quantity_to_receive_input / current_market_price
                    adjusted_quantity_to_sell = adjust_quantity_to_lot_size(str(estimated_base_qty_to_sell), step_size_str)

                    if adjusted_quantity_to_sell < Decimal(min_qty_str):
                         messages.error(request, f"A quantidade calculada para venda ({adjusted_quantity_to_sell} {crypto_to_sell.symbol}) para obter ~{quote_quantity_to_receive_input} {crypto_to_sell.price_currency} é menor que a quantidade mínima permitida ({min_qty_str}).")
                         raise ValueError("Quantidade calculada para venda abaixo da mínima.")
                    if adjusted_quantity_to_sell == Decimal(0):
                        messages.error(request, f"A quantidade calculada para venda de {crypto_to_sell.symbol} é zero. Tente um valor maior para receber.")
                        raise ValueError("Quantidade calculada para venda é zero.")

                    # Verificar se o usuário tem essa quantidade calculada
                    user_holding = Holding.objects.get(user_profile=user_profile, cryptocurrency=crypto_to_sell)
                    if user_holding.quantity < adjusted_quantity_to_sell:
                        messages.error(request, f"Saldo insuficiente. Para obter ~{quote_quantity_to_receive_input} {crypto_to_sell.price_currency}, você precisaria vender ~{adjusted_quantity_to_sell:.8f} {crypto_to_sell.symbol}, mas seu saldo é {user_holding.quantity:.8f}.")
                        raise ValueError("Saldo insuficiente para a quantidade calculada.")

                    quantity_to_actually_sell = adjusted_quantity_to_sell
                    order_params['quantity'] = f"{quantity_to_actually_sell}"
                    log_msg_qty_type = f"~{quote_quantity_to_receive_input} {crypto_to_sell.price_currency} de (vendendo {quantity_to_actually_sell} {crypto_to_sell.symbol})"
                else:
                    messages.error(request, "Tipo de venda ou valor inválido.")
                    return redirect('core:trade_market_sell')

                messages.info(request, f"Tentando executar ordem de VENDA A MERCADO: {log_msg_qty_type} ({api_symbol_pair}) na Testnet...")
                
                order_response = client.order_market_sell(**order_params)

                messages.success(request, f"Ordem de VENDA para {api_symbol_pair} enviada com sucesso! ID da Ordem: {order_response.get('orderId')}")
                
                executed_qty_total = Decimal(order_response.get('executedQty', '0'))
                cummulative_quote_qty_total = Decimal(order_response.get('cummulativeQuoteQty', '0'))
                               
                if executed_qty_total > 0:
                    average_price = (cummulative_quote_qty_total / executed_qty_total)
                    
                    with db_transaction.atomic():
                        local_tx = Transaction.objects.create(
                            user_profile=user_profile,
                            cryptocurrency=crypto_to_sell,
                            transaction_type='SELL',
                            quantity_crypto=executed_qty_total,
                            price_per_unit=average_price,
                            transaction_date=timezone.now(), 
                            binance_order_id=str(order_response.get('orderId')),
                            notes=f"Venda a mercado via API. Qtd: {executed_qty_total:.8f}, Preço Médio: {average_price:.8f} {crypto_to_sell.price_currency}. Quote Recebido: {cummulative_quote_qty_total:.2f} {crypto_to_sell.price_currency}."
                        )
                        
                        holding = Holding.objects.get(user_profile=user_profile, cryptocurrency=crypto_to_sell)
                        holding.quantity -= executed_qty_total 
                        if holding.quantity < Decimal('0.000000005'): 
                            holding.quantity = Decimal('0.0')
                        
                        if holding.quantity == Decimal('0.0'):
                            holding.average_buy_price = Decimal('0.0') 
                        
                        holding.save()

                    messages.success(request, f"Transação local registrada para venda de {executed_qty_total:.8f} {crypto_to_sell.symbol} a ~{average_price:.2f} {crypto_to_sell.price_currency}.")
                else:
                     messages.warning(request, f"A ordem de venda foi enviada (ID: {order_response.get('orderId')}), mas não houve execuções reportadas ou a quantidade executada foi zero. Verifique o status na Binance.")

                return redirect('core:transaction_history')

            except BinanceAPIException as e:
                error_message = f"Erro da API Binance: {e.message} (Cod: {e.code})"
                if e.code == -1013: 
                    if "LOT_SIZE" in e.message.upper():
                        error_message = f"Erro de Quantidade (LOT_SIZE): A quantidade para venda não atende aos requisitos de tamanho do lote ({step_size_str}) ou quantidade mínima ({min_qty_str}) da Binance para {api_symbol_pair}. (Detalhe: {e.message})"
                elif e.code == -2010: 
                    error_message = f"Ordem de Venda Rejeitada pela Binance: {e.message}. Verifique seu saldo da criptomoeda na Testnet ou os limites do par."
                messages.error(request, error_message)
                print(f"Erro API Binance (VENDA {api_symbol_pair}): {e.message} (Cod: {e.code})")
            except ValueError as ve: 
                messages.error(request, str(ve)) # Mostra a mensagem de erro customizada de ValueError
            except BinanceRequestException as e:
                messages.error(request, f"Erro de requisição à Binance: {e.message}")
            except Exception as e:
                messages.error(request, f"Erro inesperado ao tentar vender {crypto_to_sell.symbol}: {str(e)}")
        else: 
            messages.error(request, "Por favor, corrija os erros no formulário.")
    else:
        form = MarketSellForm(user_profile=user_profile) 

    context = {
        'form': form,
        'page_title': 'Vender Criptomoeda (Ordem a Mercado - Testnet)'
    }
    return render(request, 'core/trade_sell_form.html', context) 

@login_required
@db_transaction.atomic 
def add_transaction_view(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    if request.method == 'POST':
        form = TransactionForm(request.POST, user_profile=user_profile)
        if form.is_valid():
            try:
                transaction = form.save(commit=False)
                transaction.user_profile = user_profile
                transaction.save()

                holding, created = Holding.objects.get_or_create(
                    user_profile=user_profile,
                    cryptocurrency=transaction.cryptocurrency,
                    defaults={'average_buy_price': Decimal('0.0'), 'quantity': Decimal('0.0')}
                )

                if transaction.transaction_type == 'BUY':
                    current_transaction_cost = transaction.quantity_crypto * transaction.price_per_unit
                    old_total_cost = holding.quantity * (holding.average_buy_price if holding.average_buy_price is not None else Decimal('0.0'))
                    new_total_quantity = holding.quantity + transaction.quantity_crypto
                    new_total_cost = old_total_cost + current_transaction_cost

                    if new_total_quantity > 0:
                        holding.average_buy_price = new_total_cost / new_total_quantity
                    else: 
                        holding.average_buy_price = Decimal('0.0')
                    holding.quantity = new_total_quantity

                elif transaction.transaction_type == 'SELL':
                    holding.quantity -= transaction.quantity_crypto
                    if holding.quantity < 0: 
                        messages.error(request, "Erro: Tentativa de vender mais do que possui. Transação não registrada.")
                        raise ValueError("Quantidade em holding não pode ser negativa após a venda.") 
                    if holding.quantity == 0:
                        holding.average_buy_price = Decimal('0.0') 

                holding.save()
                messages.success(request, f"Transação de {transaction.get_transaction_type_display()} de {transaction.cryptocurrency.symbol} registrada com sucesso!")
                return redirect('core:transaction_history') 
            except ValueError as ve: 
                 messages.error(request, str(ve))
            except Exception as e:
                messages.error(request, f"Ocorreu um erro grave ao processar a transação: {e}")
        else: 
            for field, errors in form.errors.items():
                for error in errors:
                    field_label = form.fields[field].label if field != '__all__' and field in form.fields else "Erro geral do formulário"
                    messages.error(request, f"{field_label}: {error}")
    else:
        form = TransactionForm(user_profile=user_profile)

    context = {
        'form': form,
        'page_title': 'Adicionar Nova Transação'
    }
    return render(request, 'core/add_transaction.html', context)

@login_required
def transaction_history_view(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        transactions = Transaction.objects.filter(user_profile=user_profile).select_related('cryptocurrency').order_by('-transaction_date', '-timestamp')
    except UserProfile.DoesNotExist:
        messages.error(request, "Perfil de usuário não encontrado.")
        return redirect('core:index') 

    context = {
        'page_title': 'Histórico de Transações',
        'transactions': transactions,
        'user_profile': user_profile, 
    }
    return render(request, 'core/transaction_history.html', context)

@login_required
def update_api_keys_view(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = UserProfileAPIForm(request.POST, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Suas configurações de API e preferências foram atualizadas com sucesso!')
            return redirect('core:dashboard') 
        else:
            messages.error(request, 'Por favor, corrija os erros abaixo.')
    else:
        form = UserProfileAPIForm(instance=user_profile)

    context = {
        'form': form,
        'page_title': 'Configurar Chaves API e Preferências'
    }
    return render(request, 'core/profile_api_keys.html', context)
