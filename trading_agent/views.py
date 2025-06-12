# trading_agent/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.contrib import messages
from django.http import JsonResponse
from .models import TradingSignal, BacktestReport
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
    user_profile = request.user.profile
    agent_transactions = Transaction.objects.filter(user_profile=user_profile, signal__is_executed=True).order_by('cryptocurrency', 'transaction_date')
    performance_by_crypto = {}

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

    for symbol, data in performance_by_crypto.items():
        profit_loss = data['total_revenue'] - data['total_cost']
        data['profit_loss'] = profit_loss
        total_profit_loss += profit_loss
        
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
    """
    View de API que retorna o estado de um relatório de backtest específico.
    """
    try:
        # Garante que um utilizador só pode verificar os seus próprios relatórios.
        report = BacktestReport.objects.get(id=report_id, user_profile=request.user.profile)
        return JsonResponse({'status': report.status})
    except BacktestReport.DoesNotExist:
        return JsonResponse({'status': 'NOT_FOUND'}, status=404)

