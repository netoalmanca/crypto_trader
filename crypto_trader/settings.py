# crypto_trader/settings.py
from pathlib import Path
import os
from dotenv import load_dotenv
from celery.schedules import crontab
from decimal import Decimal
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(os.path.join(BASE_DIR, '.env'))

env = environ.Env(
    DEBUG=(bool, False)
)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('DJANGO_SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),
        'PORT': env('DB_PORT'),
    }
}

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth',
    'django.contrib.contenttypes', 'django.contrib.sessions',
    'django.contrib.messages', 'django.contrib.staticfiles',
    'django.contrib.humanize', 'core.apps.CoreConfig',
    'trading_agent.apps.TradingAgentConfig',
    'django_celery_beat',
    'rest_framework',
    'django_ratelimit',
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
                'django.template.context_processors.debug', 'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'crypto_trader.wsgi.application'
ASGI_APPLICATION = 'crypto_trader.asgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE, TIME_ZONE, USE_I18N, USE_L10N, USE_TZ = 'pt-br', 'America/Sao_Paulo', True, True, True
STATIC_URL, DEFAULT_AUTO_FIELD = 'static/', 'django.db.models.BigAutoField'
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- API Keys ---
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY')
BINANCE_API_SECRET = os.environ.get('BINANCE_API_SECRET')
BINANCE_TESTNET = os.environ.get('BINANCE_TESTNET', 'False').lower() in ['true', '1', 't']
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

LOGIN_URL, LOGIN_REDIRECT_URL, LOGOUT_REDIRECT_URL = 'core:login', 'core:dashboard', 'core:index'

# --- Celery Settings ---
# (CORRIGIDO) Aponta para 'localhost' em vez de 'redis' para desenvolvimento local.
CELERY_BROKER_URL = env('REDIS_URL')
CELERY_RESULT_BACKEND = env('REDIS_URL')
CELERY_BROKER_POOL_LIMIT = 0 
CELERY_ACCEPT_CONTENT, CELERY_TASK_SERIALIZER, CELERY_RESULT_SERIALIZER = ['json'], 'json', 'json'
CELERY_TIMEZONE, CELERY_TASK_TRACK_STARTED, CELERY_TASK_TIME_LIMIT = TIME_ZONE, True, 3600
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# --- Celery Beat Schedule ---
CELERY_BEAT_SCHEDULE = {
    'update-crypto-prices-every-minute': {
        'task': 'core.tasks.update_all_cryptocurrency_prices', 'schedule': 60.0, },
    'update-exchange-rates-every-minute': {
        'task': 'core.tasks.update_exchange_rates', 'schedule': 60.0, },
    'create-daily-snapshots': {
        'task': 'core.tasks.create_daily_portfolio_snapshots', 'schedule': crontab(hour=23, minute=55), },
    'calculate-indicators-every-hour': {
        'task': 'trading_agent.tasks.calculate_technical_indicators_for_all_cryptos',
        'schedule': crontab(minute=0, hour='*'), 
    },
    'analyze-sentiment-every-hour': {
        'task': 'trading_agent.tasks.analyze_market_sentiment_for_all_cryptos',
        'schedule': crontab(minute=5, hour='*'), 
    },
    'run-trading-cycle-every-15-minutes': {
        'task': 'trading_agent.tasks.run_trading_cycle_for_all_users',
        'schedule': crontab(minute='*/15'), 
    },
    'process-signals-every-15-minutes': {
        'task': 'trading_agent.tasks.process_unexecuted_signals',
        'schedule': crontab(minute='1,16,31,46'),
    },
    'reflect-on-performance-weekly': {
        'task': 'trading_agent.tasks.reflect_on_performance',
        'schedule': crontab(day_of_week='sunday', hour=2, minute=0),
    },
}

# --- Trading Agent Settings ---
AGENT_BUY_RISK_PERCENTAGE = Decimal('0.05')
AGENT_SELL_RISK_PERCENTAGE = Decimal('1.0')

# Segurança
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# Rate Limiting (DRF)
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '100/minute',
    }
}

# CORS
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL'),  # Usa a mesma URL do Redis já definida no .env
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
