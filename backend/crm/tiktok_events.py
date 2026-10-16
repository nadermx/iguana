"""Send purchases and checkouts to TikTok server-side, through the Events API. The twin of `crm.meta_capi`.

Same reasoning, same rules: checkout runs in an iframe on api.iguanacomedy.com, so the TikTok pixel on the site
never sees a sale and TikTok learns what an ad was worth only if the backend tells it. The site pixel sends the
page view and ViewContent; the purchase and checkout events come from here and only from here.

Nothing here may break a booking. Every send runs on a daemon thread, every failure is logged and swallowed, and
with no pixel or token configured the module is a no-op that says so once.
"""

import hashlib
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)

URL = 'https://business-api.tiktok.com/open_api/v1.3/event/track/'
TIMEOUT = 10

_warned = {'off': False}


def configured():
    return bool(getattr(settings, 'TIKTOK_PIXEL_ID', '') and getattr(settings, 'TIKTOK_EVENTS_TOKEN', ''))


def _sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def hash_email(value):
    value = str(value or '').strip().lower()
    return _sha(value) if '@' in value else ''


def hash_phone(value):
    """TikTok hashes E.164 WITH the plus (Meta hashes the digits alone). A number with no country code is
    dropped rather than guessed, for the same reason as Meta: a 10-digit MX and US number look identical."""
    raw = str(value or '').strip()
    digits = re.sub(r'\D', '', raw)
    if not raw.startswith('+') or len(digits) < 8:
        return ''
    return _sha('+' + digits)


def user_data(*, email='', phone='', ip='', user_agent='', ttclid='', ttp='', external_id=''):
    hashed = {'email': hash_email(email), 'phone': hash_phone(phone),
              'external_id': _sha(str(external_id)) if external_id else ''}
    data = {key: value for key, value in hashed.items() if value}
    for key, value in (('ip', ip), ('user_agent', user_agent), ('ttclid', ttclid), ('ttp', ttp)):
        if value:
            data[key] = str(value)
    return data


def _post(event):
    body = {
        'event_source': 'web',
        'event_source_id': getattr(settings, 'TIKTOK_PIXEL_ID', ''),
        'data': [event],
    }
    test_code = getattr(settings, 'TIKTOK_TEST_EVENT_CODE', '')
    if test_code:
        body['test_event_code'] = test_code
    request = urllib.request.Request(
        URL, data=json.dumps(body).encode(), method='POST',
        headers={'Access-Token': getattr(settings, 'TIKTOK_EVENTS_TOKEN', ''), 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            result = json.load(response)
        # TikTok answers 200 with a non-zero `code` when it refuses an event, so the status alone proves nothing.
        if result.get('code') == 0:
            log.info('TikTok Events API accepted %s', event['event'])
        else:
            log.warning('TikTok Events API refused %s: %s', event['event'], str(result)[:300])
    except urllib.error.HTTPError as exc:
        log.warning('TikTok Events API %s for %s: %s', exc.code, event['event'], exc.read().decode(errors='replace')[:300])
    except Exception as exc:  # noqa: BLE001 - a booking must never fail because TikTok did
        log.warning('TikTok Events API send failed for %s: %s', event['event'], exc)


def send(event_name, *, event_id, user, properties=None, page_url='', event_time=None):
    """Queue one event. Returns immediately; the HTTP call runs on a daemon thread."""
    if not configured():
        if not _warned['off']:
            log.info('TikTok Events API is off: set TIKTOK_PIXEL_ID and TIKTOK_EVENTS_TOKEN in config.py')
            _warned['off'] = True
        return
    event = {
        'event': event_name,
        'event_time': int(event_time or time.time()),
        'event_id': str(event_id),
        'user': user,
    }
    if properties:
        event['properties'] = properties
    if page_url:
        event['page'] = {'url': page_url}
    threading.Thread(target=_post, args=(event,), daemon=True).start()
