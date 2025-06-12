# trading_agent/urls.py
from django.urls import path
from . import views

app_name = 'trading_agent'

# Este arquivo define as rotas específicas para a aplicação do agente de trading.
# Cada rota aponta para uma view que lida com a lógica da página.
urlpatterns = [
    # Rota para o dashboard principal do agente de IA.
    path('dashboard/', views.agent_dashboard_view, name='dashboard'),
    path('reports/', views.agent_reports_view, name='reports')
]
