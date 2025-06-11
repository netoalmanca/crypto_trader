# core/urls.py
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Auth & Main
    path('', views.index_view, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    # Profile, Info & Transactions
    path('profile/api-keys/', views.update_api_keys_view, name='update_api_keys'),
    path('profile/reset/', views.reset_portfolio_view, name='reset_portfolio'), 
    path('profile/recalculate/', views.recalculate_holdings_view, name='recalculate_holdings'),
    path('cryptocurrencies/', views.cryptocurrency_list_view, name='cryptocurrency_list'),
    path('cryptocurrency/<str:symbol>/', views.cryptocurrency_detail_view, name='cryptocurrency_detail'),
    path('transactions/history/', views.transaction_history_view, name='transaction_history'),
    path('transactions/add/', views.add_transaction_view, name='add_transaction'),
    path('transactions/sync/', views.sync_binance_trades_view, name='sync_trades'),
    path('transactions/export/', views.export_transactions_csv_view, name='export_transactions_csv'),
    path('open-orders/', views.open_orders_view, name='open_orders'),
    # NOVA ROTA PARA RELATÓRIOS
    path('reports/', views.reports_view, name='reports'),

    # Trading
    path('trade/market-buy/', views.trade_market_buy_view, name='trade_market_buy'),
    path('trade/market-sell/', views.trade_market_sell_view, name='trade_market_sell'),
    path('trade/limit-buy/', views.trade_limit_buy_view, name='trade_limit_buy'),
    path('trade/limit-sell/', views.trade_limit_sell_view, name='trade_limit_sell'),
]
