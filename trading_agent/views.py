# trading_agent/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import TradingSignal, BacktestReport, StrategyLog
from .forms import BacktestForm
from .tasks import run_backtest_task
from core.models import Transaction
from decimal import Decimal

@login_required
def agent_dashboard_view(request):
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
    (CORRIGIDO) Calcula e exibe a performance financeira das operações
    executadas pelo agente de IA.
    """
    user_profile = request.user.profile
    # Filtra transações que foram originadas por um sinal do agente
    agent_transactions = Transaction.objects.filter(user_profile=user_profile, signal__is_executed=True).order_by('cryptocurrency', 'transaction_date')
    
    performance_by_crypto = {}

    # Calcula o custo e a receita por cada criptoativo
    for tx in agent_transactions:
        symbol = tx.cryptocurrency.symbol
        if symbol not in performance_by_crypto:
            performance_by_crypto[symbol] = {
                'total_cost': Decimal('0.0'),
                'total_revenue': Decimal('0.0'),
            }

        if tx.transaction_type == 'BUY':
            performance_by_crypto[symbol]['total_cost'] += tx.total_value
        elif tx.transaction_type == 'SELL':
            performance_by_crypto[symbol]['total_revenue'] += tx.total_value

    total_profit_loss = Decimal('0.0')
    total_trades = 0
    total_wins = 0

    # Calcula o P/L e as métricas de vitória para cada ativo
    for symbol, data in performance_by_crypto.items():
        profit_loss = data['total_revenue'] - data['total_cost']
        data['profit_loss'] = profit_loss
        total_profit_loss += profit_loss
        
        # Considera um "trade" como o conjunto de operações em um ativo
        total_trades += 1
        if profit_loss > 0:
            data['is_win'] = True
            total_wins += 1
        else:
            data['is_win'] = False
        
    win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0

    # Define o dicionário de contexto para o template
    context = {
        'page_title': 'Performance do Agente IA',
        'performance_data': performance_by_crypto,
        'total_profit_loss': total_profit_loss,
        'win_rate': win_rate,
        'total_trades': total_trades,
    }
    return render(request, 'trading_agent/agent_reports.html', context)


@login_required
def backtest_view(request):
    form = BacktestForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            report = BacktestReport.objects.create(
                user_profile=request.user.profile,
                symbol=form.cleaned_data['symbol'].symbol,
                start_date=form.cleaned_data['start_date'],
                initial_capital=form.cleaned_data['initial_capital']
            )
            run_backtest_task.delay(report.id)
            messages.success(request, f"Simulação para {report.symbol} iniciada. O relatório aparecerá abaixo quando concluído.")
            return redirect('trading_agent:backtest')

    reports = BacktestReport.objects.filter(user_profile=request.user.profile)
    context = {
        'page_title': 'Backtesting de Estratégia',
        'form': form,
        'reports': reports
    }
    return render(request, 'trading_agent/backtest.html', context)

@login_required
def backtest_status_view(request, report_id):
    report = get_object_or_404(BacktestReport, id=report_id, user_profile=request.user.profile)
    return JsonResponse({'status': report.status})


@login_required
def strategy_log_view(request):
    """
    Exibe o histórico de reflexões da IA (Strategy Logs) e a estratégia ativa.
    """
    user_profile = request.user.profile
    strategy_logs = StrategyLog.objects.filter(user_profile=user_profile).order_by('-created_at')
    
    context = {
        'page_title': 'Gestor de Estratégia do Agente',
        'strategy_logs': strategy_logs,
        'active_strategy_prompt': user_profile.agent_strategy_prompt
    }
    return render(request, 'trading_agent/strategy_manager.html', context)


@login_required
@require_POST
def apply_strategy_suggestion_view(request, log_id):
    """
    Aplica a sugestão de um StrategyLog ao perfil do usuário.
    """
    user_profile = request.user.profile
    log_entry = get_object_or_404(StrategyLog, id=log_id, user_profile=user_profile)
    
    if log_entry.suggested_modifications:
        user_profile.agent_strategy_prompt = log_entry.suggested_modifications
        user_profile.save()
        messages.success(request, "Nova sugestão de estratégia foi aplicada ao seu agente!")
    else:
        messages.warning(request, "Esta reflexão não continha uma sugestão de estratégia para aplicar.")
        
    return redirect('trading_agent:strategy_manager')
