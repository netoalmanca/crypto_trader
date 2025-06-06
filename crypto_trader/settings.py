# crypto_trader/settings.py
from pathlib import Path
import os
from dotenv import load_dotenv
from celery.schedules import crontab # Para agendamentos mais complexos

load_dotenv(os.path.join(Path(__file__).resolve().parent.parent, '.env'))

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-fallback-secret-key-for-dev-only')
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'
ALLOWED_HOSTS_STRING = os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STRING.split(',') if host.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core.apps.CoreConfig',
    # Adicionar 'django_celery_beat' se for usar o agendador do BD,
    # mas para agendamento simples, a configuração no settings é suficiente.
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'crypto_trader.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'crypto_trader.wsgi.application'
ASGI_APPLICATION = 'crypto_trader.asgi.application' # Adicionado para compatibilidade futura com Celery 5+

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo' # Importante para Celery Beat
USE_I18N = True
USE_L10N = True
USE_TZ = True # Importante para Celery Beat

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY')
BINANCE_API_SECRET = os.environ.get('BINANCE_API_SECRET')
BINANCE_TESTNET_STR = os.environ.get('BINANCE_TESTNET', 'False')
BINANCE_TESTNET = BINANCE_TESTNET_STR.lower() in ['true', '1', 't']

LOGIN_URL = 'core:login' 
LOGIN_REDIRECT_URL = 'core:dashboard' 
LOGOUT_REDIRECT_URL = 'core:index'

# --- Configurações do Celery ---
# URL do Broker (Redis neste caso). Se o Redis estiver rodando localmente na porta padrão:
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
# URL do Backend de Resultados (opcional, mas útil para rastrear o status das tarefas)
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE # Usa o mesmo timezone do Django
CELERY_TASK_TRACK_STARTED = True # Para que as tarefas reportem o estado 'STARTED'
CELERY_TASK_TIME_LIMIT = 30 * 60 # Limite de tempo para tarefas (30 minutos)

# --- Configurações do Celery Beat (Agendador) ---
CELERY_BEAT_SCHEDULE = {
    'update-crypto-prices-every-minute': { # Nome da tarefa alterado para refletir a frequência
        'task': 'core.tasks.update_all_cryptocurrency_prices', # Caminho para a sua tarefa
        'schedule': 60.0,  # Executar a cada 60 segundos (1 minuto)
    },
    'update-exchange-rates-every-minute': { # Nome da tarefa alterado e frequência
        'task': 'core.tasks.update_exchange_rates', # Caminho para a nova tarefa
        'schedule': 60.0,  # Executar a cada 60 segundos (1 minuto)
    },
}
# Se você usar django-celery-beat (para agendamento via Admin), adicione:
# CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
