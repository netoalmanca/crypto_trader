# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from .forms import CustomUserCreationForm, CustomAuthenticationForm, TransactionForm
from .models import Cryptocurrency, UserProfile, Holding, Transaction
from decimal import Decimal
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from django.db import transaction as db_transaction
import datetime 
import json 

# Create your views here.

def index_view(request):
    """
    View para a página inicial.
    """
    context = {
        'page_title': 'Bem-vindo ao Crypto Trader',
        'message': 'Sua plataforma para negociação de criptomoedas.'
    }
    return render(request, 'core/index.html', context)

def register_view(request):
    """
    View para o registro de novos usuários.
    """
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
    """
    View para o login de usuários.
    """
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
    """
    View para o logout de usuários.
    """
    logout(request)
    messages.info(request, 'Você foi desconectado com sucesso.')
    return redirect('core:index')

@login_required
def dashboard_view(request):
    """
    View para o dashboard do usuário.
    Exibe o valor total do portfólio e as posses de criptomoedas.
    """
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        holdings_qs = Holding.objects.filter(user_profile=user_profile).select_related('cryptocurrency')
    except UserProfile.DoesNotExist:
        messages.error(request, "Perfil de usuário não encontrado. Um novo perfil foi criado, por favor, tente novamente.")
        UserProfile.objects.get_or_create(user=request.user)
        return redirect('core:dashboard') 
    except Exception as e:
        messages.error(request, f"Ocorreu um erro ao carregar o dashboard: {e}")
        return redirect('core:index')

    total_portfolio_value_in_preferred_currency = Decimal('0.0')
    enriched_holdings = []
    
    # Flags para controle de mensagens de aviso no template
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
        # Passa os flags para o template
        'show_conversion_warning': conversion_warning_shown_for_request,
        'show_currency_mismatch_warning': currency_mismatch_warning_shown_for_request,
    }
    return render(request, 'core/dashboard.html', context)

@login_required
def binance_test_view(request):
    """
    View para testar a conexão com a API da Binance e obter informações básicas.
    """
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
    """
    View para listar criptomoedas e atualizar seus preços via API da Binance.
    """
    client = None
    client_initialized_successfully = False
    if settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET:
        try:
            client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, tld='com', testnet=settings.BINANCE_TESTNET)
            client_initialized_successfully = True
        except Exception as e:
            messages.error(request, f"Falha ao inicializar o cliente da Binance para atualização de preços: {e}")
            print(f"Falha ao inicializar o cliente da Binance: {e}") 
    else:
        messages.warning(request, "Chaves API da Binance não configuradas. Os preços não serão atualizados da API.")
        print("Chaves API da Binance não configuradas. Os preços não serão atualizados da API.")

    cryptos_from_db = Cryptocurrency.objects.all()
    updated_cryptos = []
    prices_updated_count = 0

    for crypto in cryptos_from_db:
        if client_initialized_successfully and client: 
            try:
                api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
                
                ticker = client.get_symbol_ticker(symbol=api_symbol)
                
                if ticker and 'price' in ticker:
                    crypto.current_price = Decimal(ticker['price'])
                    crypto.last_updated = timezone.now()
                    crypto.save() 
                    prices_updated_count += 1
                else:
                    pass
            
            except BinanceAPIException as e:
                print(f"API Erro (Símbolo: {api_symbol}): {e.message} (Cod: {e.code})")
            
            except BinanceRequestException as e:
                print(f"Request Erro (Símbolo: {api_symbol}): {e.message}")
                messages.error(request, f"Erro de requisição à Binance ao tentar buscar preços. Tente mais tarde.") 
            
            except Exception as e: 
                print(f"Erro inesperado (Símbolo: {api_symbol}): {str(e)}")
                messages.error(request, f"Ocorreu um erro inesperado ao tentar atualizar os preços.") 
        
        updated_cryptos.append(crypto) 

    if client_initialized_successfully and prices_updated_count > 0 :
        messages.success(request, f"{prices_updated_count} preço(s) de criptomoeda(s) foram atualizados da API da Binance.")
    elif client_initialized_successfully and prices_updated_count == 0 and cryptos_from_db.exists():
         messages.info(request, "Nenhum preço foi atualizado da API. Verifique a configuração dos pares de moedas no admin (ex: BTC com moeda USDT) e os logs do servidor.")


    context = {
        'page_title': 'Lista de Criptomoedas',
        'cryptocurrencies': updated_cryptos, 
    }
    return render(request, 'core/cryptocurrency_list.html', context)

@login_required
def cryptocurrency_detail_view(request, symbol):
    """
    View para exibir detalhes de uma criptomoeda e seu gráfico de histórico de preços.
    """
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
    """
    View para adicionar uma nova transação manual (compra ou venda).
    Atualiza as posses (Holdings) do usuário.
    """
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
    """
    View para exibir o histórico de transações do usuário.
    """
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
