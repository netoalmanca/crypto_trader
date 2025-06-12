# crypto_trader/settings.py
from pathlib import Path
import os
from dotenv import load_dotenv
from celery.schedules import crontab
from decimal import Decimal # (Adicionado) Importar Decimal

load_dotenv(os.path.join(Path(__file__).resolve().parent.parent, '.env'))

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-fallback-secret-key-for-dev-only')
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'
ALLOWED_HOSTS_STRING = os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STRING.split(',') if host.strip()]

FIELD_ENCRYPTION_KEY = os.environ.get('DJANGO_FIELD_ENCRYPTION_KEY')
if not FIELD_ENCRYPTION_KEY and not DEBUG:
    raise ValueError("A variável de ambiente DJANGO_FIELD_ENCRYPTION_KEY deve ser definida em produção.")

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'core.apps.CoreConfig',
    'trading_agent.apps.TradingAgentConfig', # Adicionado anteriormente
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
ASGI_APPLICATION = 'crypto_trader.asgi.application'

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
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- API Keys ---
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY')
BINANCE_API_SECRET = os.environ.get('BINANCE_API_SECRET')
BINANCE_TESTNET_STR = os.environ.get('BINANCE_TESTNET', 'False')
BINANCE_TESTNET = BINANCE_TESTNET_STR.lower() in ['true', '1', 't']
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')


LOGIN_URL = 'core:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'core:index'

# --- Configurações do Celery ---
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

CELERY_BROKER_TRANSPORT_OPTIONS = {
    'visibility_timeout': 43200,  # 12 horas
    'health_check_interval': 30, # Verifica a conexão a cada 30 segundos
}

# (ATUALIZADO) Desabilita o pool de conexões do broker para o PRODUCER (Django).
# Isto força uma nova conexão a cada tarefa enviada a partir da aplicação web,
# evitando o erro "Connection reset by peer" com conexões inativas.
# O worker do Celery ainda usará o seu próprio pool interno de forma eficiente.
CELERY_BROKER_POOL_LIMIT = 0 


CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 3600 # Aumentado para 1 hora para backtests longos

# --- Configurações do Celery Beat (Agendador) ---
CELERY_BEAT_SCHEDULE = {
    'update-crypto-prices-every-minute': {
        'task': 'core.tasks.update_all_cryptocurrency_prices',
        'schedule': 60.0,
    },
    'update-exchange-rates-every-minute': {
        'task': 'core.tasks.update_exchange_rates',
        'schedule': 60.0,
    },
    'create-daily-snapshots': {
        'task': 'core.tasks.create_daily_portfolio_snapshots',
        'schedule': crontab(hour=23, minute=55),
    },
    'calculate-indicators-every-4-hours': {
        'task': 'trading_agent.tasks.calculate_technical_indicators_for_all_cryptos',
        'schedule': crontab(minute=0, hour='*/4'),
    },
    'analyze-sentiment-every-4-hours': {
        'task': 'trading_agent.tasks.analyze_market_sentiment_for_all_cryptos',
        'schedule': crontab(minute=15, hour='*/4'),
    },
    'run-trading-cycle-every-hour': {
        'task': 'trading_agent.tasks.run_trading_cycle_for_all_users',
        'schedule': crontab(minute=30, hour='*'),
    },
    'process-signals-every-hour': {
        'task': 'trading_agent.tasks.process_unexecuted_signals',
        'schedule': crontab(minute=35, hour='*'),
    },
}

# --- Configurações do Agente de Trading ---
AGENT_BUY_RISK_PERCENTAGE = Decimal('0.05')
AGENT_SELL_RISK_PERCENTAGE = Decimal('1.0')
