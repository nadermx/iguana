from pathlib import Path

import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config.SECRET_KEY
DEBUG = getattr(config, 'DEBUG', False)
ALLOWED_HOSTS = config.ALLOWED_HOSTS

BACKEND_URL = config.BACKEND_URL.rstrip('/')
SITE_URLS = [u.rstrip('/') for u in config.SITE_URLS]
PUBLIC_API_KEYS = config.PUBLIC_API_KEYS
SECRET_API_KEYS = getattr(config, 'SECRET_API_KEYS', [])
STRIPE_PUBLISHABLE_KEY = getattr(config, 'STRIPE_PUBLISHABLE_KEY', '')
STRIPE_SECRET_KEY = getattr(config, 'STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = getattr(config, 'STRIPE_WEBHOOK_SECRET', '')
NOTIFY_EMAILS = getattr(config, 'NOTIFY_EMAILS', [])
# Where a reply to a newsletter should land. Receipts and sign-in codes keep the no-reply From and no Reply-To.
MARKETING_REPLY_TO = getattr(config, 'MARKETING_REPLY_TO', '')
# Meta Conversions API: the only way Meta learns a ticket sold, since checkout is an iframe on this domain and a
# pixel on the marketing site cannot see it. Blank means conversions simply are not reported; see crm/meta_capi.py.
META_PIXEL_ID = getattr(config, 'META_PIXEL_ID', '')
META_CAPI_TOKEN = getattr(config, 'META_CAPI_TOKEN', '')
# Read-only Marketing API access, for the spend half of /stats/. A cron fetches it; no request path calls Meta.
META_ADS_TOKEN = getattr(config, 'META_ADS_TOKEN', '')
META_AD_ACCOUNT = getattr(config, 'META_AD_ACCOUNT', 'act_178760798664478')
# Set only while watching Test Events in Events Manager; it keeps those events out of the real dataset.
META_TEST_EVENT_CODE = getattr(config, 'META_TEST_EVENT_CODE', '')
# TikTok's twin of the above (crm/tiktok_events.py). Blank means TikTok is simply not told.
TIKTOK_PIXEL_ID = getattr(config, 'TIKTOK_PIXEL_ID', '')
TIKTOK_EVENTS_TOKEN = getattr(config, 'TIKTOK_EVENTS_TOKEN', '')
TIKTOK_TEST_EVENT_CODE = getattr(config, 'TIKTOK_TEST_EVENT_CODE', '')

# DB-IP City Lite (.mmdb) for contact and order locations; see crm/geo.py. Blank or missing file = no lookups.
GEOIP_DB = getattr(config, 'GEOIP_DB', '')
# /drop/ (api/drop_views.py): an upload-only page for the owner's business documents. No PIN, no page.
DROP_PIN = getattr(config, 'DROP_PIN', '')
DROP_DIR = getattr(config, 'DROP_DIR', str(BASE_DIR / 'drop'))
# /comic/ (api/comic_views.py): comedians' photos and clips, one folder per submission, never served by nginx.
COMICS_DIR = getattr(config, 'COMICS_DIR', str(BASE_DIR / 'comics'))

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'catalog',
    'crm',
    'sales',
    'api',
    'pos',
]

MIDDLEWARE = [
    'api.middleware.CorsMiddleware',
    'api.middleware.TranslateErrorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'iguana.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'iguana.wsgi.application'

DATABASES = {
    'default': config.DATABASE or {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/Cancun'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Self-hosted fonts for the checkout, order and check-in pages (same files as the site; no Google Fonts).
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_FROM_EMAIL = config.DEFAULT_FROM_EMAIL
SERVER_EMAIL = config.DEFAULT_FROM_EMAIL
EMAIL_BACKEND = getattr(config, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = getattr(config, 'EMAIL_HOST', 'localhost')
EMAIL_PORT = getattr(config, 'EMAIL_PORT', 25)

# Behind nginx with TLS terminated there
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = [BACKEND_URL] + SITE_URLS
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
