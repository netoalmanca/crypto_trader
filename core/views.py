from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone # Importar timezone
from .forms import CustomUserCreationForm, CustomAuthenticationForm, TransactionForm
from .models import Cryptocurrency, UserProfile, Holding, Transaction
from decimal import Decimal
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from django.db import transaction as db_transaction

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
            # Coletar e exibir mensagens de erro detalhadas
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
        else: # Erros de formulário
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
                if not has_field_errors and not form.non_field_errors(): # Fallback genérico
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
        # Pré-carrega as criptomoedas relacionadas para evitar queries N+1
        holdings_qs = Holding.objects.filter(user_profile=user_profile).select_related('cryptocurrency')
    except UserProfile.DoesNotExist:
        messages.error(request, "Perfil de usuário não encontrado. Um novo perfil foi criado, por favor, tente novamente.")
        # Cria o perfil se não existir (embora o signal deva cuidar disso)
        UserProfile.objects.get_or_create(user=request.user)
        return redirect('core:dashboard') # Tenta recarregar o dashboard
    except Exception as e:
        messages.error(request, f"Ocorreu um erro ao carregar o dashboard: {e}")
        return redirect('core:index')

    total_portfolio_value = Decimal('0.0')
    enriched_holdings = []

    # Calcula o valor de cada posse e o valor total do portfólio
    # Esta lógica assume que Cryptocurrency.current_price já está na moeda preferida do usuário
    # ou em uma moeda base consistente para a qual o usuário fará a conversão mentalmente.
    # Para conversão automática para user_profile.preferred_fiat_currency, seria necessário
    # buscar taxas de câmbio ou garantir que todos os preços estejam nessa moeda.
    for holding_item in holdings_qs:
        current_value = holding_item.current_market_value # Usa a property do modelo
        if current_value is not None:
            # ATENÇÃO: Se Cryptocurrency.price_currency for diferente de user_profile.preferred_fiat_currency,
            # a soma direta pode não ser precisa sem conversão de moeda.
            # Por enquanto, assume-se que as moedas são consistentes ou a conversão é tratada externamente.
            total_portfolio_value += current_value
        enriched_holdings.append({
            'holding': holding_item,
            'current_value': current_value,
            'profit_loss': holding_item.profit_loss,
            'profit_loss_percent': holding_item.profit_loss_percent
        })

    context = {
        'page_title': 'Meu Dashboard',
        'user': request.user,
        'user_profile': user_profile,
        'holdings': enriched_holdings,
        'total_portfolio_value': total_portfolio_value,
        'portfolio_currency': user_profile.preferred_fiat_currency
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
        client = Client(api_key, api_secret, tld='com', testnet=use_testnet) # tld='com' é comum
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
        if e.code == -2015: # Invalid API-key, IP, or permissions for action
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
    NOTA: Atualizar preços em cada requisição pode ser lento e sujeito a limites da API.
    Para produção, uma tarefa de fundo (Celery) é recomendada.
    """
    # Tenta inicializar o cliente da Binance
    client = None
    if settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET:
        try:
            client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET, tld='com', testnet=settings.BINANCE_TESTNET)
        except Exception as e:
            messages.warning(request, f"Não foi possível inicializar o cliente da Binance para atualização de preços: {e}")

    cryptos_from_db = Cryptocurrency.objects.all()
    updated_cryptos = []

    for crypto in cryptos_from_db:
        if client: # Procede com a atualização apenas se o cliente foi inicializado
            try:
                # Monta o par para a API, ex: BTCUSDT, ETHBRL
                # A API da Binance espera os símbolos juntos, ex: "BTCUSDT"
                # crypto.price_currency deve ser a moeda de cotação (ex: USDT, BRL, USD)
                api_symbol = f"{crypto.symbol.upper()}{crypto.price_currency.upper()}"
                
                ticker = client.get_symbol_ticker(symbol=api_symbol)
                
                if ticker and 'price' in ticker:
                    crypto.current_price = Decimal(ticker['price'])
                    crypto.last_updated = timezone.now()
                    crypto.save() # Salva a atualização no banco de dados
                else:
                    # Não loga erro aqui para não poluir, mas pode ser útil para debug
                    # print(f"Ticker não encontrado ou sem preço para {api_symbol}")
                    pass # Mantém o preço antigo se não encontrar

            except BinanceAPIException as e:
                # Se o símbolo não existe na Binance (ex: XYZUSDT), a API retorna um erro.
                # Não é necessariamente um erro crítico para a listagem, apenas não atualiza o preço.
                # messages.warning(request, f"Erro ao buscar preço para {crypto.symbol} ({api_symbol}): {e.message}")
                print(f"Alerta API Binance (ticker para {api_symbol}): {e.message} (Cod: {e.code})")
                pass # Continua para a próxima cripto
            except BinanceRequestException as e:
                messages.error(request, f"Erro de requisição à Binance ao buscar preço para {crypto.symbol}: {e.message}")
            except Exception as e: # Outros erros inesperados
                messages.error(request, f"Erro inesperado ao atualizar preço para {crypto.symbol}: {str(e)}")
        
        updated_cryptos.append(crypto) # Adiciona à lista, mesmo que não atualizado

    context = {
        'page_title': 'Lista de Criptomoedas',
        'cryptocurrencies': updated_cryptos, # Usa a lista que tentamos atualizar
    }
    return render(request, 'core/cryptocurrency_list.html', context)

@login_required
@db_transaction.atomic # Garante que as operações no BD sejam atômicas
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
                # total_value é calculado no save() do modelo Transaction
                transaction.save()

                # Atualiza ou cria o Holding
                holding, created = Holding.objects.get_or_create(
                    user_profile=user_profile,
                    cryptocurrency=transaction.cryptocurrency,
                    # Defaults são usados apenas se 'created' for True
                    defaults={'average_buy_price': Decimal('0.0'), 'quantity': Decimal('0.0')}
                )

                if transaction.transaction_type == 'BUY':
                    # Custo total da transação atual na moeda base da cripto (ex: USD, BRL)
                    current_transaction_cost = transaction.quantity_crypto * transaction.price_per_unit
                    # Custo total antigo das posses (antes desta transação)
                    old_total_cost = holding.quantity * (holding.average_buy_price if holding.average_buy_price is not None else Decimal('0.0'))

                    new_total_quantity = holding.quantity + transaction.quantity_crypto
                    new_total_cost = old_total_cost + current_transaction_cost

                    if new_total_quantity > 0:
                        holding.average_buy_price = new_total_cost / new_total_quantity
                    else: # Caso a quantidade se torne zero (não deveria acontecer em uma compra, mas por segurança)
                        holding.average_buy_price = Decimal('0.0')
                    
                    holding.quantity = new_total_quantity

                elif transaction.transaction_type == 'SELL':
                    holding.quantity -= transaction.quantity_crypto
                    # O preço médio de compra não muda em uma venda simples.
                    # Se a quantidade em holding se tornar zero, o preço médio pode ser mantido ou zerado.
                    # Atualmente, é mantido. Se holding.quantity == 0, o cost_basis será 0.
                    if holding.quantity < 0: # Validação extra, embora o form já deva checar
                        messages.error(request, "Erro: Tentativa de vender mais do que possui.")
                        # Força rollback da transação
                        raise ValueError("Quantidade em holding não pode ser negativa.")
                    if holding.quantity == 0:
                        holding.average_buy_price = Decimal('0.0') # Opcional: zera o preço médio se não houver mais holding

                holding.save()
                messages.success(request, f"Transação de {transaction.get_transaction_type_display()} de {transaction.cryptocurrency.symbol} registrada com sucesso!")
                return redirect('core:transaction_history') # Melhor redirecionar para o histórico
            except ValueError as ve: # Erro de valor (ex: holding negativo)
                 messages.error(request, str(ve))
                 # Não redireciona, permite ao usuário ver o erro no formulário
            except Exception as e:
                messages.error(request, f"Ocorreu um erro ao processar a transação: {e}")
        else: # Formulário inválido
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
        # Ordena por data da transação (mais recente primeiro) e depois por timestamp de criação
        transactions = Transaction.objects.filter(user_profile=user_profile).select_related('cryptocurrency').order_by('-transaction_date', '-timestamp')
        # Implementar paginação se a lista puder ficar muito longa
    except UserProfile.DoesNotExist:
        messages.error(request, "Perfil de usuário não encontrado.")
        return redirect('core:index') # Ou dashboard, se fizer mais sentido

    context = {
        'page_title': 'Histórico de Transações',
        'transactions': transactions,
        'user_profile': user_profile, # Pode ser útil no template
    }
    return render(request, 'core/transaction_history.html', context)
