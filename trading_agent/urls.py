# trading_agent/urls.py
from django.urls import path
from . import views

app_name = 'trading_agent'

urlpatterns = [
    path('dashboard/', views.agent_dashboard_view, name='dashboard'),
    path('reports/', views.agent_reports_view, name='reports'),
    path('backtest/', views.backtest_view, name='backtest'),
    path('backtest-status/<int:report_id>/', views.backtest_status_view, name='backtest_status'),
    
    # (NOVOS) URLs para o Gestor de Estratégia
    path('strategy-manager/', views.strategy_log_view, name='strategy_manager'),
    path('strategy-manager/apply/<int:log_id>/', views.apply_strategy_suggestion_view, name='apply_suggestion'),
]
