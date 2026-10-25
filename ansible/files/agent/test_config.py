# The backend's config while iguana-agent-deploy runs the test suite in its build checkout: SQLite, no keys,
# console mail. Nothing in here can reach a customer or a payment processor.
DEBUG = True
SECRET_KEY = 'agent-deploy-tests-only'
ALLOWED_HOSTS = ['*']
BACKEND_URL = 'http://127.0.0.1:8000'
SITE_URLS = ['http://127.0.0.1:4321']
DATABASE = {}
PUBLIC_API_KEYS = ['ipk_test']
SECRET_API_KEYS = ['isk_test']
STRIPE_PUBLISHABLE_KEY = ''
STRIPE_SECRET_KEY = ''
STRIPE_WEBHOOK_SECRET = ''
DEFAULT_FROM_EMAIL = '"Iguana Comedy" <no-reply@iguanacomedy.com>'
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_HOST = 'localhost'
EMAIL_PORT = 25
NOTIFY_EMAILS = ['hello@iguanacomedy.com']
GEOIP_DB = ''
META_PIXEL_ID = ''
TIKTOK_PIXEL_ID = ''
TIKTOK_EVENTS_TOKEN = ''
META_CAPI_TOKEN = ''
META_ADS_TOKEN = ''
META_AD_ACCOUNT = 'act_178760798664478'
META_TEST_EVENT_CODE = ''
MARKETING_REPLY_TO = ''
