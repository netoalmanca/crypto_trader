# trading_agent/urls.py
from django.urls import path
from . import views

app_name = 'trading_agent'

urlpatterns = [
    path('dashboard/', views.agent_dashboard_view, name='dashboard'),
    path('reports/', views.agent_reports_view, name='reports'),
    # (ADICIONADO) Rota para a nova página de backtesting
    path('backtest/', views.backtest_view, name='backtest'),
]
