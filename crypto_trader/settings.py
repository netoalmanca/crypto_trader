from pathlib import Path
import os
# Certifique-se de que python-dotenv está instalado: pip install python-dotenv
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Carrega variáveis de ambiente do arquivo .env na raiz do projeto
load_dotenv(os.path.join(Path(__file__).resolve().parent.parent, '.env'))

# Configuração para django-fernet-fields
DJANGO_FERNET_KEY_FROM_ENV = os.environ.get('DJANGO_FIELD_ENCRYPTION_KEY')
if not DJANGO_FERNET_KEY_FROM_ENV:
    # Em desenvolvimento, você pode permitir uma chave padrão se não estiver no .env,
    # mas é altamente recomendável definir no .env.
    # Para produção, esta chave DEVE ser definida e ser única.
    print("AVISO: DJANGO_FERNET_KEY não encontrada no .env. Gere uma e adicione.")
    # Se você quiser que o sistema quebre se não encontrar a chave (mais seguro para produção):
    # raise ImproperlyConfigured("DJANGO_FERNET_KEY não está configurada no ambiente.")
    # Para um fallback de desenvolvimento (NÃO USE EM PRODUÇÃO):
    # DJANGO_FERNET_KEY_FROM_ENV = 'fallback_development_key_generate_a_real_one'

FERNET_KEYS = [
    DJANGO_FERNET_KEY_FROM_ENV,
    # Você pode adicionar chaves antigas aqui se precisar rotacionar chaves,
    # a primeira da lista é usada para criptografar.
]

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-fallback-secret-key-for-dev-only')
# NUNCA use a chave de fallback em produção.

# DEBUG deve ser 'False' em produção. Carregue de variável de ambiente.
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
    #'django_cryptography',
    # Adicione aqui outras apps que instalar, como 'crispy_forms' se decidir usar.
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

# Configuração de Banco de Dados: SQLite para desenvolvimento.
# Para produção, considere PostgreSQL ou MySQL.
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
USE_L10N = True # Importante para formatação de números e datas
USE_TZ = True

STATIC_URL = 'static/'
# Para produção, você precisará configurar STATIC_ROOT:
# STATIC_ROOT = BASE_DIR / 'staticfiles'
# E talvez STATICFILES_DIRS se tiver estáticos fora das apps:
# STATICFILES_DIRS = [BASE_DIR / "static_global"]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Configurações da API da Binance (carregadas do .env)
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY')
BINANCE_API_SECRET = os.environ.get('BINANCE_API_SECRET')
# Default para False (produção/mainnet) é mais seguro. Mude para True no .env para testar.
BINANCE_TESTNET_STR = os.environ.get('BINANCE_TESTNET', 'False')
BINANCE_TESTNET = BINANCE_TESTNET_STR.lower() in ['true', '1', 't']

# Configurações de Autenticação
LOGIN_URL = 'core:login' # Usando o namespace da URL
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'core:index'

# Configuração de Email (Exemplo para console, configure para produção)
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# Para produção, use algo como:
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.example.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
# DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL')