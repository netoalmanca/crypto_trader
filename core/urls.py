# core/urls.py
from django.urls import path
from . import views

app_name = 'core' # Define o namespace da aplicação

urlpatterns = [
    path('', views.index_view, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('binance-test/', views.binance_test_view, name='binance_test'),
    path('cryptocurrencies/', views.cryptocurrency_list_view, name='cryptocurrency_list'),
    path('cryptocurrency/<str:symbol>/', views.cryptocurrency_detail_view, name='cryptocurrency_detail'),
    path('transactions/add/', views.add_transaction_view, name='add_transaction'),
    path('transactions/history/', views.transaction_history_view, name='transaction_history'),
    path('profile/api-keys/', views.update_api_keys_view, name='update_api_keys'),
    path('trade/market-buy/', views.trade_market_buy_view, name='trade_market_buy'),
    # Nova rota para realizar venda a mercado
    path('trade/market-sell/', views.trade_market_sell_view, name='trade_market_sell'),
]
