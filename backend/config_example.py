# Copy to config.py (gitignored) and fill in real values.
DEBUG = False
SECRET_KEY = 'change-me'
ALLOWED_HOSTS = ['api.iguanacomedy.com']

# Public origin of this backend (used for embed/checkout/ticket URLs).
BACKEND_URL = 'https://api.iguanacomedy.com'
# Public origin of the Astro site (CORS + magic-link redirect allowlist).
SITE_URLS = ['https://iguanacomedy.com']

# Leave DATABASE empty for SQLite in the backend directory.
DATABASE = {
    # 'ENGINE': 'django.db.backends.postgresql',
    # 'NAME': 'iguana', 'USER': 'iguana', 'PASSWORD': '', 'HOST': 'localhost', 'PORT': '5432',
}

# Keys the Astro site sends as `Authorization: Bearer ...` (PUBLIC_KINTANA_API_KEY).
PUBLIC_API_KEYS = ['ipk_live_change_me']
SECRET_API_KEYS = ['isk_live_change_me']

STRIPE_PUBLISHABLE_KEY = ''
STRIPE_SECRET_KEY = ''
STRIPE_WEBHOOK_SECRET = ''

DEFAULT_FROM_EMAIL = '"Iguana Comedy" <no-reply@iguanacomedy.com>'
EMAIL_HOST = 'localhost'
EMAIL_PORT = 25
NOTIFY_EMAILS = ['hello@iguanacomedy.com']
# Path to a DB-IP City Lite .mmdb for contact/order locations (ansible puts it at /var/lib/iguana/). Blank = off.
GEOIP_DB = ''

# Meta Conversions API (server-side Purchase and InitiateCheckout). Blank locally: nothing is reported.
META_PIXEL_ID = ''
TIKTOK_PIXEL_ID = ''
TIKTOK_EVENTS_TOKEN = ''
META_CAPI_TOKEN = ''
META_ADS_TOKEN = ''          # system-user token with ads_read, for /stats/
META_AD_ACCOUNT = 'act_178760798664478'
META_TEST_EVENT_CODE = ''

# A human address replies to the newsletter land on; blank means no Reply-To.
MARKETING_REPLY_TO = ''
