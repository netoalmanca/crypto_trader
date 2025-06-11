# trading_agent/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from .models import TradingSignal

@login_required
def agent_dashboard_view(request):
    """
    Esta view busca e organiza todos os dados necessários para exibir
    no dashboard do Agente de IA.
    """
    user_profile = request.user.profile
    # Busca todos os sinais de trade gerados para o usuário logado.
    signals_list = TradingSignal.objects.filter(user_profile=user_profile).order_by('-timestamp')
    
    # Configura a paginação para a lista de sinais.
    paginator = Paginator(signals_list, 10) # Mostra 10 sinais por página
    page_number = request.GET.get('page')
    signals_page = paginator.get_page(page_number)
    
    # Calcula estatísticas agregadas para os cards do dashboard.
    stats = signals_list.aggregate(
        total_signals=Count('id'),
        buy_signals=Count('id', filter=Q(decision='BUY')),
        sell_signals=Count('id', filter=Q(decision='SELL')),
        executed_signals=Count('id', filter=Q(is_executed=True))
    )
    
    # Calcula a taxa de execução dos sinais que não são 'HOLD'.
    execution_rate = 0
    if stats['total_signals'] > 0:
        executable_signals = stats['buy_signals'] + stats['sell_signals']
        if executable_signals > 0:
            execution_rate = (stats['executed_signals'] / executable_signals) * 100

    # Monta o contexto a ser enviado para o template.
    context = {
        'page_title': 'Dashboard do Agente de IA',
        'signals_page': signals_page,
        'agent_status': user_profile.enable_auto_trading,
        'stats': stats,
        'execution_rate': execution_rate
    }
    return render(request, 'trading_agent/agent_dashboard.html', context)
