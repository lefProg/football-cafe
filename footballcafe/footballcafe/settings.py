"""
Django settings for the footballcafe project.

Everything that changes between machines comes from environment variables (see .env.example).
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get('DEBUG') == 'True'

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError('Set DJANGO_SECRET_KEY.')

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,0.0.0.0,localhost').split(',')
CSRF_TRUSTED_ORIGINS = [origin for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'health_check',
    'health_check.db',
    'core',
]

REST_FRAMEWORK = {
    # The public API has no accounts: readers are told apart by a signed cookie (see core/services.py).
    # Session authentication is only there so the browsable API works for a logged-in admin.
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.CafePagination',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Football Cafe API',
    'DESCRIPTION': 'Pieces, their claims, the votes on them and the replies readers write back. '
    'No login: a reader is a random id in the signed `fc_visitor` cookie, which the first '
    'vote or reply sets. Send the cookie back to keep the same ticks.',
    'VERSION': '1.0.0',
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
    'SERVE_INCLUDE_SCHEMA': False,
    'ENUM_NAME_OVERRIDES': {
        'VoteChoiceEnum': 'core.enums.VoteChoice',
        'ReplyStatusEnum': 'core.enums.ReplyStatus',
    },
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'footballcafe.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'footballcafe.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DATABASE_NAME', 'footballcafe'),
        'USER': os.getenv('DATABASE_USERNAME', 'footballcafe'),
        'PASSWORD': os.getenv('DATABASE_PASSWORD', 'footballcafe'),
        'HOST': os.getenv('DATABASE_HOST', 'db'),
        'PORT': os.getenv('DATABASE_PORT', 5432),
    }
}

# The reply rate limit counts per address in the cache. A table, so every gunicorn worker sees the same count.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'cafe_cache',
    }
}
if 'test' in sys.argv:
    CACHES['default'] = {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-gb'
TIME_ZONE = 'Europe/Athens'
USE_I18N = False
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': os.environ.get('DJANGO_LOGLEVEL', 'info').upper()},
}

# HTTPS=True when the site sits behind an https address. Cookies are then sent over https only.
# Leave it False on a plain http address (a bare IP and port), or browsers drop the cookies and nobody
# can log in or keep their ticks.
HTTPS = os.environ.get('HTTPS') == 'True'
if HTTPS:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Football Cafe
# Both agents run on Claude's cheapest model unless .env names another one.
CAFE_MODERATOR_MODEL = os.environ.get('CAFE_MODERATOR_MODEL', 'claude-haiku-4-5')
CAFE_NOTETAKER_MODEL = os.environ.get('CAFE_NOTETAKER_MODEL', 'claude-haiku-4-5')
CAFE_VISITOR_COOKIE = 'fc_visitor'
CAFE_VISITOR_COOKIE_AGE = 60 * 60 * 24 * 365
# Replies one visitor (or one address) may post inside the window.
CAFE_REPLY_LIMIT = 3
CAFE_REPLY_LIMIT_PER_IP = 10
CAFE_REPLY_WINDOW_SECONDS = 600
