"""Run the open mic ads for the three days before each night, unless there is nothing left to sell.

The owner's rule (2026-10-15, replacing "run always" from 2026-09-26): a night's ads run on the show day and the
two days before it, so Sunday, Monday and Tuesday for a Tuesday night, Monday to Wednesday for a Wednesday. Each
campaign stops when its night sells out or one hour before the show starts, and comes back by itself three days
before the following week's night. Paid shows are not governed here: their campaigns start as soon as they are
built (`scripts/meta-show-campaign.py`). A cron calls `sync()` every ten minutes; nothing in a request path
touches Meta.

Why the switch is per LANGUAGE and not per night: the ads point at /open-mic/?night=es or ?night=en, which
always shows the next bookable night of that series, so one campaign per series is the thing that sells every
Tuesday (or every Wednesday) in turn. The night that decides whether it runs is the next one on the calendar.

The switch is the CAMPAIGN status. Which ad sets inside it are live is a builder decision
(`scripts/meta-openmic-campaigns.py` pauses superseded ones and keeps the retired reach campaigns off), so the
only ad set this ever touches is the builder's current one, named `... · checkout`, and its ads, and only inside
the window. Before that (until 2026-10-19) a pause made on the ad set or the ads by hand left the campaign ACTIVE
over nothing that could deliver, and this logged "ACTIVE already" every ten minutes while the Spanish night went
five days and the English one eight without spending a peso.

⚠ Inside the window it overrides a pause made by hand in Ads Manager within ten minutes, and outside it a
resume. To stop
the ads on purpose, set `open_mic_ads_autopilot: false` in group_vars and deploy, then pause them.
"""

import json
import logging
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from catalog.models import Event
from sales.demand import demand

log = logging.getLogger(__name__)

GRAPH = 'https://graph.facebook.com/v21.0'
TIMEOUT = 30

OPEN_MIC_TAG = 'open-mic'
# Names as `scripts/meta-openmic-campaigns.py` builds them (`campaign_name(lang, 'reservations')`).
CAMPAIGNS = {'es': 'Open mic Spanish · reservations', 'en': 'Open mic English · reservations'}
# The owner's number. With the show at 21:00 this is when doors open, which is when a reservation stops being
# worth anything to the person making it.
STOP_BEFORE_SHOW = timedelta(hours=1)
# The show day plus the two before it, counted on the Cancun calendar: a Tuesday night starts on Sunday at 00:00.
RUN_DAYS = 3
# The builder's current ad set in each campaign ends with this (its EVENT_TAG for INITIATED_CHECKOUT).
LIVE_ADSET_SUFFIX = ' · checkout'
# Ads the owner retired by hand: rename the ad to end in this and the autopilot leaves it paused.
RETIRED_SUFFIX = ' · retired'
FALLBACK_SHOW_TIME = time(21, 0)


def _clock(value):
    try:
        hours, minutes = (value or '').split(':')[:2]
        return time(int(hours), int(minutes))
    except (TypeError, ValueError):
        return None


def show_starts(event):
    """The show's start as an aware datetime. `Event.date` is the day; the time lives in `show_time`."""
    day = timezone.localtime(event.date).date()
    clock = _clock(event.show_time) or _clock(event.doors_open) or FALLBACK_SHOW_TIME
    return timezone.make_aware(datetime.combine(day, clock))


def next_night(lang, now=None):
    """The next open mic of this series on the calendar, today included, or None.

    A sold-out or started night is NOT skipped here: it is what makes the answer "off until tomorrow".
    """
    today = timezone.localdate(now or timezone.now())
    start = timezone.make_aware(datetime.combine(today, time.min))
    # SOLD_OUT is still a night (see SoldOutIsStillAShowTests); DRAFT and CANCELLED are not.
    for event in (Event.objects.filter(language=lang, date__gte=start, status__in=(Event.ACTIVE, Event.SOLD_OUT))
                  .order_by('date')):
        if OPEN_MIC_TAG in (event.tags or []):
            return event
    return None


def decide(lang, now=None):
    """(should_run, reason, event). Pure apart from reading the database, so the tests can drive it."""
    now = now or timezone.now()
    event = next_night(lang, now)
    if event is None:
        return False, 'no upcoming night to sell', None
    if event.status == Event.SOLD_OUT:
        return False, 'next night is marked sold out', event
    room = demand(event)
    if room is not None and room['left'] <= 0:
        return False, f'next night is full ({room["taken"]} of {room["capacity"]})', event
    starts = show_starts(event)
    first_day = timezone.localtime(starts).date() - timedelta(days=RUN_DAYS - 1)
    if timezone.localdate(now) < first_day:
        return False, f'ads start {first_day:%a %Y-%m-%d}, {RUN_DAYS} days before the night', event
    if now >= starts - STOP_BEFORE_SHOW:
        return False, f'show starts {timezone.localtime(starts):%H:%M}, less than an hour away', event
    return True, 'next night is within three days, has seats and is more than an hour out', event


def _graph(method, path, **params):
    params['access_token'] = settings.META_ADS_TOKEN
    data = urllib.parse.urlencode(params)
    if method == 'GET':
        request = urllib.request.Request(f'{GRAPH}/{path}?{data}')
    else:
        request = urllib.request.Request(f'{GRAPH}/{path}', data=data.encode(), method='POST')
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def refusal(exc):
    """Meta's own words from a refused Graph call: the message the Ads Manager would show, else the raw body."""
    try:
        body = exc.read().decode(errors='replace')
    except Exception:  # noqa: BLE001 - an unreadable body still has a status code
        return f'HTTP {exc.code}'
    try:
        error = json.loads(body).get('error') or {}
    except ValueError:
        return f'HTTP {exc.code}: {body[:300]}'
    parts = [error.get('error_user_title'), error.get('error_user_msg') or error.get('message')]
    return f'HTTP {exc.code}: ' + ' / '.join(p for p in parts if p)


def _campaigns():
    """{name: {'id', 'status'}} for the account, one read per run (the rate limit clears only by waiting)."""
    found, after = {}, None
    while True:
        params = {'fields': 'id,name,status', 'limit': 200}
        if after:
            params['after'] = after
        page = _graph('GET', f'{settings.META_AD_ACCOUNT}/campaigns', **params)
        for row in page.get('data', []):
            found[row['name']] = row
        paging = page.get('paging') or {}
        after = paging.get('cursors', {}).get('after') if paging.get('next') else None
        if not after:
            return found


def sync(apply=False, now=None):
    """Set each open mic campaign to what `decide()` says. Returns one line per series, for the log."""
    if not settings.META_ADS_TOKEN:
        return ['no META_ADS_TOKEN, nothing done']
    campaigns = _campaigns()
    lines = []
    refused = {}
    for lang, name in CAMPAIGNS.items():
        run, reason, event = decide(lang, now)
        want = 'ACTIVE' if run else 'PAUSED'
        night = timezone.localtime(event.date).date().isoformat() if event else '-'
        found = campaigns.get(name)
        if not found:
            lines.append(f'{lang}: campaign "{name}" not found on the account')
            log.warning('open mic campaign %s not found', name)
            continue
        if found['status'] == want:
            lines.append(f'{lang}: {want} already ({reason}; night {night})')
        else:
            if apply:
                try:
                    _graph('POST', found['id'], status=want)
                except urllib.error.HTTPError as exc:
                    # Say WHY, and carry on with the other series. 2026-11-09/10: the account sat in "Payment
                    # required" for 36 hours, every switch-on was refused, and the log said only "400 Bad Request".
                    why = refusal(exc)
                    lines.append(f'{lang}: REFUSED {found["status"]} -> {want}: {why} (night {night})')
                    log.error('Meta refused %s -> %s on %s: %s', found['status'], want, name, why)
                    refused[lang] = {'why': why, 'want': want, 'night': night}
                    continue
            lines.append(f'{lang}: {found["status"]} -> {want}{"" if apply else " (dry run)"} ({reason}; night {night})')
        if run:
            lines += [f'{lang}: {line}' for line in _resume_inside(found['id'], apply)]
    if apply:
        lines += alert_owner(refused, now)
    return lines


# ------------------------------------------------------------------ telling the owner
#
# Owner, 2026-11-10: "send me an email when it fails, apart from the notifications that meta does". One mail when
# Meta starts refusing a campaign (or refuses for a new reason), a reminder every REMIND_EVERY while it goes on, and
# one when it works again. The state lives in a small file so the every-ten-minutes cron does not mail every run.

REMIND_EVERY = timedelta(hours=12)
ADS_MANAGER = 'https://adsmanager.facebook.com/adsmanager/manage/campaigns?act=178760798664478'
BILLING = 'https://business.facebook.com/billing_hub/accounts/details?asset_id=178760798664478'


def _alert_state_path():
    return pathlib.Path(getattr(settings, 'OPEN_MIC_ADS_ALERT_STATE', '/var/lib/iguana/open-mic-ads-alert.json'))


def _mail(subject, body):
    recipients = list(getattr(settings, 'NOTIFY_EMAILS', []) or [])
    if not recipients:
        return False
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients)
        return True
    except Exception:  # noqa: BLE001 - a mail failure must not stop the ads being switched
        log.exception('could not mail the open mic ads alert')
        return False


def alert_owner(refused, now=None):
    now = now or timezone.now()
    path = _alert_state_path()
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {}
    lines, changed = [], False
    for lang, info in refused.items():
        name = CAMPAIGNS[lang]
        seen = state.get(lang)
        new = not seen or seen.get('why') != info['why']
        due = seen and now - datetime.fromisoformat(seen['mailed']) >= REMIND_EVERY
        if not (new or due):
            continue
        since = now if new else datetime.fromisoformat(seen['since'])
        verb = 'switch on' if info['want'] == 'ACTIVE' else 'pause'
        subject = (f'Meta ads: "{name}" could not be switched {"on" if info["want"] == "ACTIVE" else "off"}'
                   + ('' if new else ' (still)'))
        body = '\n'.join([
            f'Meta refused to {verb} the campaign "{name}" (night {info["night"]}).',
            '',
            f'Meta says: {info["why"]}',
            '',
            f'This has been going on since {timezone.localtime(since):%a %d %b %H:%M} (Playa time). The server tries '
            'again every 10 minutes and will mail again when it works.',
            '',
            'If it mentions payment ("Pago necesario", "Payment required"), the ad account needs its card or PayPal '
            'checked; nothing will run until then:',
            BILLING,
            '',
            f'Ads Manager: {ADS_MANAGER}',
            '',
            'Iguana Comedy',
        ])
        if _mail(subject, body):
            state[lang] = {'why': info['why'], 'since': since.isoformat(), 'mailed': now.isoformat()}
            changed = True
            lines.append(f'{lang}: owner mailed ({"new refusal" if new else "reminder"})')
    for lang in [lang for lang in state if lang not in refused]:
        name = CAMPAIGNS.get(lang, lang)
        if _mail(f'Meta ads: "{name}" is working again',
                 f'Meta accepted the switch for "{name}" again, so the open mic ads are back on schedule.\n\n'
                 f'Ads Manager: {ADS_MANAGER}\n\nIguana Comedy'):
            lines.append(f'{lang}: owner mailed (working again)')
        del state[lang]
        changed = True
    if changed:
        try:
            path.write_text(json.dumps(state))
        except OSError:
            log.exception('could not save the open mic ads alert state to %s', path)
    return lines


def _resume_inside(campaign_id, apply):
    """Un-pause the builder's ad set and its ads, so an ACTIVE campaign has something that can spend."""
    adsets = _graph('GET', f'{campaign_id}/adsets', fields='id,name,status,ads.limit(50){id,name,status}',
                    limit=50).get('data', [])
    live = [a for a in adsets if a['name'].endswith(LIVE_ADSET_SUFFIX)]
    if not live:
        log.warning('open mic campaign %s has no ad set ending %r, nothing can deliver', campaign_id,
                    LIVE_ADSET_SUFFIX)
        return [f'no ad set ending "{LIVE_ADSET_SUFFIX.strip()}", NOTHING CAN DELIVER']
    lines = []
    for adset in live:
        paused = [adset] if adset['status'] == 'PAUSED' else []
        # An ad renamed to end in RETIRED_SUFFIX was taken out on purpose (2026-11-11: a flyer with the wrong show
        # time) and stays paused; every other pause inside the window is still undone.
        paused += [ad for ad in (adset.get('ads') or {}).get('data', [])
                   if ad['status'] == 'PAUSED' and not ad['name'].endswith(RETIRED_SUFFIX)]
        for row in paused:
            if apply:
                _graph('POST', row['id'], status='ACTIVE')
            log.warning('open mic %s was paused inside its window, %s', row['name'],
                        'resumed' if apply else 'would resume')
            lines.append(f'PAUSED -> ACTIVE{"" if apply else " (dry run)"} {row["name"]}')
    return lines
