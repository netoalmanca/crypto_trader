# crypto_trader/celery.py
import os
from celery import Celery

# Define a variável de ambiente padrão do Django settings para o 'celery'.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crypto_trader.settings')

# Cria a instância do Celery
# 'crypto_trader' é o nome do seu projeto Django
app = Celery('crypto_trader')

# Usando uma string aqui significa que o worker não precisa serializar
# o objeto de configuração para processos filhos.
# - namespace='CELERY' significa que todas as chaves de configuração do Celery
#   devem ter um prefixo `CELERY_` (ex: CELERY_BROKER_URL).
app.config_from_object('django.conf:settings', namespace='CELERY')

# Carrega módulos de tasks de todas as apps registradas no Django.
# O Celery procurará por um arquivo chamado 'tasks.py' em cada app.
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
    