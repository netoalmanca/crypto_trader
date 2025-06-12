# trading_agent/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from .models import TradingSignal
from core.models import Transaction, Cryptocurrency
from decimal import Decimal

@login_required
def agent_dashboard_view(request):
    """
    Esta view busca e organiza todos os dados necessários para exibir
    no dashboard do Agente de IA.
    """
    user_profile = request.user.profile
    signals_list = TradingSignal.objects.filter(user_profile=user_profile).order_by('-timestamp')
    
    paginator = Paginator(signals_list, 10)
    page_number = request.GET.get('page')
    signals_page = paginator.get_page(page_number)
    
    stats = signals_list.aggregate(
        total_signals=Count('id'),
        buy_signals=Count('id', filter=Q(decision='BUY')),
        sell_signals=Count('id', filter=Q(decision='SELL')),
        executed_signals=Count('id', filter=Q(is_executed=True))
    )
    
    execution_rate = 0
    if stats['total_signals'] > 0:
        executable_signals = stats['buy_signals'] + stats['sell_signals']
        if executable_signals > 0:
            execution_rate = (stats['executed_signals'] / executable_signals) * 100

    context = {
        'page_title': 'Dashboard do Agente de IA',
        'signals_page': signals_page,
        'agent_status': user_profile.enable_auto_trading,
        'stats': stats,
        'execution_rate': execution_rate
    }
    return render(request, 'trading_agent/agent_dashboard.html', context)

@login_required
def agent_reports_view(request):
    """
    Calcula e exibe as métricas de performance para as operações
    executadas pelo Agente de IA.
    """
    user_profile = request.user.profile
    
    # Filtra transações que foram originadas por um sinal de IA executado
    agent_transactions = Transaction.objects.filter(
        user_profile=user_profile,
        signal__is_executed=True
    ).order_by('cryptocurrency', 'transaction_date')

    # Dicionário para armazenar o resultado por cripto
    performance_by_crypto = {}

    for tx in agent_transactions:
        symbol = tx.cryptocurrency.symbol
        if symbol not in performance_by_crypto:
            performance_by_crypto[symbol] = {
                'total_cost': Decimal('0.0'),
                'total_revenue': Decimal('0.0'),
                'total_qty_bought': Decimal('0.0'),
                'total_qty_sold': Decimal('0.0'),
                'win_trades': 0,
                'loss_trades': 0,
            }

        if tx.transaction_type == 'BUY':
            performance_by_crypto[symbol]['total_cost'] += tx.total_value
            performance_by_crypto[symbol]['total_qty_bought'] += tx.quantity_crypto
        elif tx.transaction_type == 'SELL':
            performance_by_crypto[symbol]['total_revenue'] += tx.total_value
            performance_by_crypto[symbol]['total_qty_sold'] += tx.quantity_crypto

    # Pós-processamento para calcular P/L e Win Rate
    total_profit_loss = Decimal('0.0')
    total_trades = 0
    total_wins = 0

    for symbol, data in performance_by_crypto.items():
        profit_loss = data['total_revenue'] - data['total_cost']
        data['profit_loss'] = profit_loss
        total_profit_loss += profit_loss
        
        # Simplificação de Win Rate: considera o P/L geral por ativo
        if profit_loss > 0:
            data['is_win'] = True
            total_wins +=1
        else:
            data['is_win'] = False
        total_trades += 1
        
    win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0

    context = {
        'page_title': 'Performance do Agente IA',
        'performance_data': performance_by_crypto,
        'total_profit_loss': total_profit_loss,
        'win_rate': win_rate,
        'total_trades': total_trades,
    }
    return render(request, 'trading_agent/agent_reports.html', context)
