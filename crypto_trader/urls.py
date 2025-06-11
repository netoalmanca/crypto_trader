# crypto_trader/urls.py
from django.contrib import admin
from django.urls import path, include

# Este é o arquivo de roteamento principal do projeto.
# Ele delega as rotas para as aplicações específicas.
urlpatterns = [
    # Rota para a interface de administração do Django.
    path('admin/', admin.site.urls),
    
    # Inclui todas as URLs da aplicação 'core' (páginas principais, dashboard, etc.).
    path('', include('core.urls')),
    
    # (ADICIONADO) Inclui as URLs da nova aplicação 'trading_agent'.
    # Qualquer acesso a /agent/... será gerenciado por esta app.
    path('agent/', include('trading_agent.urls')),
]
