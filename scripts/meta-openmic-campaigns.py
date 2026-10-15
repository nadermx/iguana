#!/usr/bin/env python3
"""Build and run the weekly open mic campaigns on Meta.

Operator tool, run by hand from the dev box, same system-user token as scripts/meta-ads.py. It is idempotent:
it looks for a campaign, ad set, creative or ad it has already made (by name) and updates that rather than
making a second one, so re-running it after changing the copy or the budget is safe.

    scripts/meta-openmic-campaigns.py plan                  print what would be created or changed
    scripts/meta-openmic-campaigns.py apply                 create or update everything, PAUSED
    scripts/meta-openmic-campaigns.py apply --live          the same, and switch the campaigns on
    scripts/meta-openmic-campaigns.py status                what exists now, and what it is spending
    scripts/meta-openmic-campaigns.py pause                 stop all four campaigns

One campaign per night: reservations (OUTCOME_SALES, optimised for INITIATED_CHECKOUT). It chases the 80
bookable seats, it commits people, it captures an email, and it is the only ad set the Conversions API can
teach.

🚨 There used to be a second, `local reach` (OUTCOME_TRAFFIC, landing page views), to fill the walk-in seats (20 of them until 2026-10-06)
cheaply and to seed the pixel. It is off, and `RUN_REACH` below keeps it off. Measured over its whole life:
**71.63 MXN, 183 clicks, 104 landing page views, zero checkouts and zero reservations.** Both of its arguments
had quietly expired. It was written when a seat cost 50 MXN and a conversion ad cost more per head than the
door collected, so buying cheap clicks made sense; the seat is free now and reservations come in at 15 to 26
MXN. And the pixel it was seeding is fed by the conversion campaign anyway. Turning it back on needs a reason
better than the one it was created with.

Why the ads point at /open-mic/ and not at an event page: an event URL carries its date, so a weekly campaign
aimed at one would need rewriting every Tuesday and would keep spending on a dead show in between.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = 'https://graph.facebook.com/v21.0'
AD_ACCOUNT = 'act_178760798664478'
PAGE_ID = '122106930026005410'
INSTAGRAM_ID = '17841461594533193'
PIXEL_ID = '2122037578734069'          # "andrew new pixel"; the backend reports Purchase into it over the CAPI
TOKEN_FILE = os.environ.get('META_TOKEN_FILE', '~/.credentials/meta/iguanacomedy/token')
CREATIVE_DIR = pathlib.Path(os.environ.get('IGUANA_CREATIVE_DIR', '~/iguana-ads/creative')).expanduser()

# Playa del Carmen. The club is in the centre, so the wide radius is for the reservation ads (worth a drive) and
# the tight one for walk-ins, who will not cross the highway for a free show. 17km is Meta's floor for a city
# radius (10 miles); anything smaller is refused outright, so the walk-in ad set cannot be drawn tighter.
PLAYA = 1540930
# 40km on the reservation ads since 2026-09-24, to hold frequency down. At 25km the reachable pool was small
# enough that a week of spend showed the same person the ad 1.7 to 1.8 times; the owner wants 1.3 or under, and
# with the budget fixed the only honest lever is more people. 40 reaches Puerto Aventuras and Akumal, which is
# a drive people here actually make for a night out, and matches what the Privilegio ad set already uses.
WIDE_KM, NEAR_KM = 40, 17
# The interest every campaign this account ever won on used.
STANDUP_INTEREST = {'id': '6003273904571', 'name': 'Comedia stand up (comedia)'}
ENGLISH_LOCALES = [6, 24]              # English (US), English (UK)

# What the reservation ad sets optimise for.
#
# Meta needs roughly 50 conversions per ad set per week to leave the learning phase, and below that it delivers
# erratically at the top of its price range. A night holds 80 reservable seats, so Purchase caps at 80 a week per
# ad set even if we sold out every time, and at 100 MXN a day we will be nowhere near that. Optimising on a
# capped event we cannot feed means paying learning-phase prices indefinitely.
#
# InitiateCheckout fires when someone puts their name and email in, several times for every sale, and the backend
# reports it server-side exactly like Purchase. It is the deepest event this budget can actually supply. Purchase
# is still recorded and still what we judge the campaigns on; it is just not what delivery is steered by yet.
# Move this back to PURCHASE once a reservations ad set is clearing about 50 sales a week on its own.
CONVERSION_EVENT = 'INITIATED_CHECKOUT'
# Meta refuses to edit the pixel, conversion event or optimisation of an ad set once it has been published
# ("no puedes editar ... después de publicarlo"). Changing what we steer on therefore means a NEW ad set, so the
# event is part of the name: a different event produces a different name, the new ad set is built, and the one it
# replaces is paused rather than left running against the old goal.
EVENT_TAG = {'PURCHASE': 'purchase', 'INITIATED_CHECKOUT': 'checkout'}

SITE = 'https://iguanacomedy.com'

# Meta's creative enhancements, opted out one by one. The blanket `standard_enhancements` switch these replaced
# is now refused outright ("quedó obsoleto"), and an unrecognised name is refused too, so this list is only ever
# the names the API actually accepted.
#
# Everything that rewrites the words or repaints the picture is off. The copy states a price and two clock times
# and has to stay true, and the flyers carry the times and the address as artwork, which is why they were padded
# to 4:5 rather than cropped in the first place. What is left on only adds places for the ad to appear:
# adapt_to_placement, site_extensions and profile_card change nothing that is claimed.
OPT_OUT_FEATURES = ['text_optimizations', 'text_generation', 'description_automation', 'enhance_cta',
                    'image_touchups', 'add_text_overlay', 'image_brightness_and_contrast', 'image_templates',
                    'image_background_gen', 'video_auto_crop']

# Set to True only with evidence that a traffic ad set earns its place; see the note at the top of this file.
RUN_REACH = False
KINDS = [('reservations', 'OUTCOME_SALES')] + ([('local reach', 'OUTCOME_TRAFFIC')] if RUN_REACH else [])

NIGHTS = {
    'es': {
        'label': 'Spanish',
        'night': 'Tuesday',
        # ?night= pins the Tuesday Spanish show. A Spanish speaker is not coming to the English night, so
        # the ad must not land on a page that offers it first.
        'link': f'{SITE}/es/open-mic/?night=es',
        'locales': None,               # Playa residents; a language filter would only shrink a local audience
        # Measured 2026-09-21, first day of delivery: 53.06 MXN bought 4 reservations at 13.27 each, on an 8.66%
        # CTR and a 28.90 CPM. The reach ad set spent 29.99 on 57 clicks and produced no checkout at all, so the
        # money moved to where the reservations are. The weekly total per night is unchanged.
        # 2026-10-15: live was 220 (raised outside this script); +25% to 275 when the ads went to three days a
        # week (crm/open_mic_ads.RUN_DAYS), so each night keeps more of its old weekly spend.
        'daily_conversions': 27500,    # centavos: 275.00 MXN
        'daily_reach': 2000,           #           20.00 MXN, just above Meta's minimum, to keep the pixel fed
        'videos': ['openmic-es-long-9x16.mp4', 'openmic-es-short-9x16.mp4'],
        'image': 'openmic-es-flyer-4x5.jpg',
        'story_image': 'openmic-es-flyer-9x16-safe.jpg',
        'copy': {
            'message': ('Stand-up gratis cada martes en Playa del Carmen. Lista a las 8, show a las 9.\n\n'
                        'La sala es de 80 lugares y se llena. Aparta tu lugar gratis en treinta segundos y '
                        'entras seguro.'),
            'title': 'Reserva tu lugar gratis, cada martes',
            'description': 'Iguana Comedy, Calle 6 norte y Av 20, centro',
        },
        'reach_copy': {
            'message': ('Stand-up gratis cada martes en Playa del Carmen. Lista a las 8, show a las 9.\n\n'
                        'Ven a ver, o anótate en la puerta y haz cinco minutos tú. No cuesta nada.'),
            'title': 'Noche de open mic en Playa',
            'description': 'Iguana Comedy, Calle 6 norte y Av 20, centro',
        },
    },
    'en': {
        'label': 'English',
        'night': 'Wednesday',
        'link': f'{SITE}/en/open-mic/?night=en',
        'locales': ENGLISH_LOCALES,
        # Same day: 78.43 MXN bought 3 reservations at 26.14 each. Twice the Spanish cost, on a 45.55 CPM against
        # 28.90, which is the English locale filter shrinking the pool rather than the ad underperforming. Held
        # at 100 rather than cut: 26 MXN a reservation is still well under this account's historic 55 to 220.
        # Plus the 20 the reach ad set gave back when it was retired.
        # 2026-10-15: live was 200; +25% to 250 with the three-day window, as for Spanish.
        'daily_conversions': 25000,
        'daily_reach': 2000,
        'videos': ['openmic-en-long-9x16.mp4'],
        'image': 'openmic-en-flyer-4x5.jpg',
        'story_image': 'openmic-en-flyer-9x16-safe.jpg',
        'copy': {
            'message': ('Free stand-up every Wednesday in Playa del Carmen. Doors at 8, show at 9.\n\n'
                        'The room holds 80 and it fills up. Reserve your spot free in thirty seconds and walk '
                        'straight in.'),
            'title': 'Reserve your free spot, every Wednesday',
            'description': 'Iguana Comedy, Calle 6 Nte and Av 20, centro',
        },
        'reach_copy': {
            'message': ('Free stand-up every Wednesday in Playa del Carmen. Doors at 8, show at 9.\n\n'
                        'Come and watch, or sign up at the door and do five minutes yourself. Nothing to pay.'),
            'title': 'Open mic night in Playa',
            'description': 'Iguana Comedy, Calle 6 Nte and Av 20, centro',
        },
    },
}


# --------------------------------------------------------------------------------------------- Graph plumbing

def token() -> str:
    path = pathlib.Path(TOKEN_FILE).expanduser()
    try:
        value = path.read_text().strip()
    except OSError as exc:
        sys.exit(f'cannot read the Meta token from {path}: {exc}')
    if not value:
        sys.exit(f'{path} is empty; put the system-user token there (chmod 600)')
    return value


class GraphError(Exception):
    """A Graph API refusal. Raised rather than exited so one blocked ad cannot abandon the rest of the build."""


class RateLimited(GraphError):
    pass


# Meta's several ways of saying the same thing. Building four campaigns takes enough calls to hit this, and a
# half-built account is worse than a slow one, so the caller waits rather than gives up.
RATE_LIMIT_CODES = {4, 17, 32, 613}
RATE_LIMIT_SUBCODES = {2446079, 1487742}


def _fail(path, exc):
    body = exc.read().decode(errors='replace')
    try:
        error = json.loads(body)['error']
        message = error.get('error_user_msg') or error.get('message', '')
        detail = error.get('error_user_title', '')
        code, subcode = error.get('code'), error.get('error_subcode')
    except Exception:
        message, detail, code, subcode = body[:400], '', None, None
    text = f'Graph API {exc.code} on {path}: {detail} {message}'.strip()
    if code in RATE_LIMIT_CODES or subcode in RATE_LIMIT_SUBCODES:
        raise RateLimited(text)
    raise GraphError(text)


# Whether this run is allowed to sit and wait out a rate limit. A build sets it: it has to finish, because a
# half-built account has to be completed by hand afterwards. A report leaves it off, because the useful answer
# there is the reason, not a twenty-minute silence. Patience belongs to the command, not to the verb: a LISTING
# read inside a build is as load-bearing as the write that follows it.
PATIENT = False


def with_backoff(call):
    """Retry a rate-limited call, doubling the wait. Meta's ad account limit clears on a rolling window, so the
    only thing that helps is waiting; retrying immediately makes it worse."""
    tries, first_wait = (7, 60) if PATIENT else (2, 20)
    wait = first_wait
    for attempt in range(1, tries + 1):
        try:
            return call()
        except RateLimited as exc:
            if attempt == tries:
                raise
            print(f'  rate limited, waiting {wait}s before retry {attempt} of {tries - 1}')
            time.sleep(wait)
            wait = min(wait * 2, 600)


def get(path, **params):
    def once():
        url = f'{API}/{path}?' + urllib.parse.urlencode(dict(params, access_token=token()))
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            _fail(path, exc)

    return with_backoff(once)


def post(path, **params):
    def once():
        body = dict(params, access_token=token())
        data = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                                       for k, v in body.items()}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(f'{API}/{path}', data=data), timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            _fail(path, exc)

    return with_backoff(once)


def post_file(path, field, file_path, **params):
    """Multipart upload, for /advideos and /adimages. stdlib only, so the body is built by hand."""
    boundary = uuid.uuid4().hex
    params['access_token'] = token()
    body = bytearray()
    for key, value in params.items():
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode()
    kind = mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
             f'filename="{file_path.name}"\r\nContent-Type: {kind}\r\n\r\n').encode()
    body += file_path.read_bytes() + b'\r\n'
    body += f'--{boundary}--\r\n'.encode()
    request = urllib.request.Request(f'{API}/{path}', data=bytes(body),
                                     headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        _fail(path, exc)


def pages(path, **params):
    params.setdefault('limit', 100)
    while True:
        payload = get(path, **params)
        yield from payload.get('data', [])
        paging = payload.get('paging', {})
        after = paging.get('cursors', {}).get('after')
        if not after or 'next' not in paging:
            return
        params['after'] = after


# ------------------------------------------------------------------------------------------------ the shapes

def campaign_name(lang, kind):
    return f'Open mic {NIGHTS[lang]["label"]} · {kind}'


def adset_name(lang, kind):
    name = f'{NIGHTS[lang]["night"]}s · Playa {WIDE_KM if kind == "reservations" else NEAR_KM}km · {kind}'
    return f'{name} · {EVENT_TAG[CONVERSION_EVENT]}' if kind == 'reservations' else name


def targeting(lang, kind):
    night = NIGHTS[lang]
    spec = {
        'geo_locations': {
            'cities': [{'key': PLAYA, 'radius': WIDE_KM if kind == 'reservations' else NEAR_KM,
                        'distance_unit': 'kilometer'}],
            # "home" alone misses every tourist in Playa, who are exactly who the English night is for.
            'location_types': ['home', 'recent'],
        },
        'age_min': 18,
        'age_max': 65,
        'targeting_automation': {'advantage_audience': 1},
    }
    if night['locales']:
        spec['locales'] = night['locales']
    if kind == 'reservations':
        # Narrowed to the interest that every campaign this account ever won on used. The reach ad set stays broad
        # on purpose: it is buying cheap local attention, and an interest filter only makes that dearer.
        spec['flexible_spec'] = [{'interests': [STANDUP_INTEREST]}]
    return spec


def adset_spec(lang, kind, campaign_id):
    night = NIGHTS[lang]
    common = {
        'name': adset_name(lang, kind),
        'campaign_id': campaign_id,
        'billing_event': 'IMPRESSIONS',
        'bid_strategy': 'LOWEST_COST_WITHOUT_CAP',
        'targeting': targeting(lang, kind),
        # No end_time on purpose. An ad set that says ACTIVE while its schedule ended is this account's oldest
        # trap: 31 of them are sitting in here right now, looking busy and spending nothing.
        'status': 'PAUSED',
    }
    if kind == 'reservations':
        return {**common,
                'daily_budget': night['daily_conversions'],
                'optimization_goal': 'OFFSITE_CONVERSIONS',
                'destination_type': 'WEBSITE',
                'promoted_object': {'pixel_id': PIXEL_ID, 'custom_event_type': CONVERSION_EVENT},
                'attribution_spec': [{'event_type': 'CLICK_THROUGH', 'window_days': 7},
                                     {'event_type': 'VIEW_THROUGH', 'window_days': 1}]}
    return {**common,
            'daily_budget': night['daily_reach'],
            'optimization_goal': 'LANDING_PAGE_VIEWS',
            'destination_type': 'WEBSITE'}


# Where a 9:16 asset is used instead of the 4:5 one. Everything else falls through to the catch-all rule below,
# which Meta requires: a placement no rule covers makes the whole creative invalid.
STORY_PLACEMENTS = {
    'publisher_platforms': ['facebook', 'instagram'],
    'facebook_positions': ['story', 'facebook_reels'],
    'instagram_positions': ['story', 'reels'],
}


def flyer_creative_spec(lang, kind, *, feed_hash, story_hash, name):
    """The flyer ad, with a Story-shaped asset for the Story-shaped placements.

    Meta was handed only the 4:5 flyer and zoomed it to fill a 9:16 Story, which cut "Stand Up in Playa!" off
    the top and put "Iguana Comedy Club" under the Registrarte button. The flyer carries the times and the
    address as artwork, so a cropped flyer is not a smaller ad, it is a wrong one.
    """
    night = NIGHTS[lang]
    copy = night['copy'] if kind == 'reservations' else night['reach_copy']
    cta = 'SIGN_UP' if kind == 'reservations' else 'LEARN_MORE'
    return {
        'name': name,
        'object_story_spec': {'page_id': PAGE_ID, 'instagram_user_id': INSTAGRAM_ID},
        'asset_feed_spec': {
            'images': [
                {'hash': feed_hash, 'adlabels': [{'name': f'{name} feed'}]},
                {'hash': story_hash, 'adlabels': [{'name': f'{name} story'}]},
            ],
            'bodies': [{'text': copy['message']}],
            'titles': [{'text': copy['title']}],
            'descriptions': [{'text': copy['description']}],
            'link_urls': [{'website_url': night['link']}],
            'call_to_action_types': [cta],
            'ad_formats': ['SINGLE_IMAGE'],
            'asset_customization_rules': [
                {'customization_spec': STORY_PLACEMENTS, 'image_label': {'name': f'{name} story'}, 'priority': 1},
                # The default rule comes last and its spec must be genuinely EMPTY. Meta refuses the creative
                # outright otherwise ("la regla de personalización de activos predeterminada ... con
                # especificaciones de personalización vacías es obligatoria"), and an age range is not empty.
                {'customization_spec': {}, 'image_label': {'name': f'{name} feed'}, 'priority': 2},
            ],
        },
        'degrees_of_freedom_spec': {'creative_features_spec':
                                    {f: {'enroll_status': 'OPT_OUT'} for f in OPT_OUT_FEATURES}},
    }


def creative_spec(lang, kind, *, video_id=None, thumbnail=None, image_hash=None, name=''):
    night = NIGHTS[lang]
    copy = night['copy'] if kind == 'reservations' else night['reach_copy']
    # The seat costs nothing, so this is a sign-up, not a booking. BOOK_NOW implies a bill.
    cta = {'type': 'SIGN_UP' if kind == 'reservations' else 'LEARN_MORE',
           'value': {'link': night['link']}}
    if video_id:
        story = {'video_data': {'video_id': video_id, 'message': copy['message'], 'title': copy['title'],
                                'link_description': copy['description'], 'call_to_action': cta,
                                'image_url': thumbnail}}
    else:
        story = {'link_data': {'link': night['link'], 'message': copy['message'], 'name': copy['title'],
                               'description': copy['description'], 'image_hash': image_hash,
                               'call_to_action': cta}}
    return {
        'name': name,
        'object_story_spec': {'page_id': PAGE_ID, 'instagram_user_id': INSTAGRAM_ID, **story},
        'degrees_of_freedom_spec': {'creative_features_spec':
                                    {f: {'enroll_status': 'OPT_OUT'} for f in OPT_OUT_FEATURES}},
    }


# ------------------------------------------------------------------------------------------------- the work

# One listing per edge per run. Without this the account is paged once for every lookup, and Meta answers
# "demasiadas llamadas a la API" partway through the build, leaving half the structure made.
_INDEX = {}


def existing(edge, name, fields='id,name,status'):
    if edge not in _INDEX:
        _INDEX[edge] = list(pages(f'{AD_ACCOUNT}/{edge}',
                                  fields='id,name,status,effective_status,objective,daily_budget'))
    return next((row for row in _INDEX[edge] if row.get('name') == name), None)


def remember(edge, row):
    """Keep the cache honest about what this run just created."""
    _INDEX.setdefault(edge, []).append(row)


def upload_video(path):
    """Uploaded once and reused: Meta keeps them on the ad account, keyed by our own name."""
    if 'advideos' not in _INDEX:
        _INDEX['advideos'] = list(pages(f'{AD_ACCOUNT}/advideos', fields='id,title'))
    for row in _INDEX['advideos']:
        if row.get('title') == path.name:
            return row['id']
    print(f'  uploading {path.name} ({path.stat().st_size / 1e6:.1f} MB)')
    video_id = post_file(f'{AD_ACCOUNT}/advideos', 'source', path, title=path.name, name=path.name)['id']
    _INDEX['advideos'].append({'id': video_id, 'title': path.name})
    return video_id


def wait_for_video(video_id, timeout=600):
    """A creative made from a still-encoding video is rejected, so wait for it rather than race it."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = get(video_id, fields='status').get('status', {})
        state = status.get('video_status') or status.get('processing_progress')
        if state == 'ready':
            return
        if state == 'error':
            sys.exit(f'video {video_id} failed to process: {status}')
        time.sleep(10)
    sys.exit(f'video {video_id} was still processing after {timeout}s')


def video_thumbnail(video_id):
    thumbs = get(f'{video_id}/thumbnails', fields='uri,is_preferred').get('data', [])
    preferred = next((t for t in thumbs if t.get('is_preferred')), None) or (thumbs[0] if thumbs else None)
    if not preferred:
        sys.exit(f'video {video_id} has no thumbnail yet')
    return preferred['uri']


def upload_image(path):
    result = post_file(f'{AD_ACCOUNT}/adimages', 'source', path)
    images = result.get('images', {})
    return images[next(iter(images))]['hash']


def ensure_campaign(lang, kind, objective, live):
    name = campaign_name(lang, kind)
    found = existing('campaigns', name, fields='id,name,status,objective')
    want = 'ACTIVE' if live else 'PAUSED'
    if found:
        if found['status'] != want:
            post(found['id'], status=want)
        print(f'  campaign {found["id"]}  {name}  [{want}]')
        return found['id']
    made = post(f'{AD_ACCOUNT}/campaigns', name=name, objective=objective, status=want,
                special_ad_categories=[], buying_type='AUCTION',
                # The budget lives on the ad set, and each campaign holds exactly one, so there is nothing to
                # share. Meta refuses to create the campaign unless this is stated either way.
                is_adset_budget_sharing_enabled=False)
    remember('campaigns', {'id': made['id'], 'name': name, 'status': want})
    print(f'  campaign {made["id"]}  {name}  [{want}] (created)')
    return made['id']


def retire_superseded_adsets(campaign_id, keep_name):
    """Pause any other ad set in this campaign. One campaign holds exactly one ad set here, so anything else is a
    previous version left behind when its optimisation event changed, and it would otherwise keep spending
    against the old goal."""
    for adset in pages(f'{campaign_id}/adsets', fields='id,name,status'):
        if adset['name'] != keep_name and adset.get('status') != 'PAUSED':
            post(adset['id'], status='PAUSED')
            print(f'  retired  {adset["id"]}  {adset["name"]} (superseded)')


def ensure_adset(lang, kind, campaign_id, live):
    spec = adset_spec(lang, kind, campaign_id)
    found = existing('adsets', spec['name'], fields='id,name,status,daily_budget')
    spec['status'] = 'ACTIVE' if live else 'PAUSED'
    if found:
        # Never re-send the optimisation fields to a published ad set: Meta rejects the whole call for them, even
        # when the value is unchanged. Budget, targeting and status stay editable.
        frozen = {'campaign_id', 'optimization_goal', 'promoted_object', 'destination_type', 'billing_event',
                  'attribution_spec'}
        post(found['id'], **{k: v for k, v in spec.items() if k not in frozen})
        print(f'  ad set   {found["id"]}  {spec["name"]}  {int(spec["daily_budget"]) / 100:.2f} MXN/day (updated)')
        adset_id = found['id']
    else:
        made = post(f'{AD_ACCOUNT}/adsets', **spec)
        remember('adsets', {'id': made['id'], 'name': spec['name'], 'status': spec['status']})
        print(f'  ad set   {made["id"]}  {spec["name"]}  {int(spec["daily_budget"]) / 100:.2f} MXN/day (created)')
        adset_id = made['id']
    retire_superseded_adsets(campaign_id, spec['name'])
    return adset_id


def ensure_ad(lang, kind, adset_id, creative, ad_name, live):
    found = existing('ads', ad_name, fields='id,name,status')
    made = post(f'{AD_ACCOUNT}/adcreatives', **creative)
    status = 'ACTIVE' if live else 'PAUSED'
    if found:
        post(found['id'], creative={'creative_id': made['id']}, status=status)
        print(f'  ad       {found["id"]}  {ad_name} (new creative {made["id"]})')
        return found['id']
    ad = post(f'{AD_ACCOUNT}/ads', name=ad_name, adset_id=adset_id, creative={'creative_id': made['id']},
              status=status)
    remember('ads', {'id': ad['id'], 'name': ad_name, 'status': status})
    print(f'  ad       {ad["id"]}  {ad_name} (created)')
    return ad['id']


def try_ad(blocked, lang, kind, adset_id, creative, ad_name, live):
    try:
        ensure_ad(lang, kind, adset_id, creative, ad_name, live)
    except GraphError as exc:
        print(f'  ad       BLOCKED  {ad_name}')
        blocked.append((ad_name, str(exc)))


def cmd_apply(args):
    global PATIENT
    PATIENT = True
    missing = [f for lang in NIGHTS
               for f in [*NIGHTS[lang]['videos'], NIGHTS[lang]['image'], NIGHTS[lang]['story_image']]
               if not (CREATIVE_DIR / f).exists()]
    if missing:
        sys.exit(f'creative missing from {CREATIVE_DIR}: {", ".join(missing)}')
    blocked = []

    for lang, night in NIGHTS.items():
        print(f'\n{night["label"]} night ({night["night"]}s) -> {night["link"]}')
        for kind, objective in KINDS:
            campaign_id = ensure_campaign(lang, kind, objective, args.live)
            adset_id = ensure_adset(lang, kind, campaign_id, args.live)

            for index, filename in enumerate(night['videos'], start=1):
                video_id = upload_video(CREATIVE_DIR / filename)
                wait_for_video(video_id)
                creative = creative_spec(lang, kind, video_id=video_id, thumbnail=video_thumbnail(video_id),
                                         name=f'{campaign_name(lang, kind)} · video {index}')
                try_ad(blocked, lang, kind, adset_id, creative, f'{adset_name(lang, kind)} · video {index}', args.live)

            if kind == 'reservations':
                # The flyer carries the times and the address in the artwork, which a video cannot do at a glance.
                image_hash = upload_image(CREATIVE_DIR / night['image'])
                story_hash = upload_image(CREATIVE_DIR / night['story_image'])
                creative = flyer_creative_spec(lang, kind, feed_hash=image_hash, story_hash=story_hash,
                                               name=f'{campaign_name(lang, kind)} · flyer')
                try_ad(blocked, lang, kind, adset_id, creative, f'{adset_name(lang, kind)} · flyer', args.live)

    if blocked:
        print(f'\n{len(blocked)} ad(s) could not be created. Campaigns and ad sets are in place and will pick the '
              'ads up as soon as the cause is cleared; re-run this command then.')
        for name, reason in blocked:
            print(f'  {name}\n    {reason}')
        if any('modo de desarrollo' in reason or 'development mode' in reason for _, reason in blocked):
            print('\n  That one is the Meta app, not the ads. App "Iguana 2026" (1616667029816710) is in\n'
                  '  Development mode, and Meta refuses to build an ad creative from a development app.\n'
                  '  Switch it to Live at developers.facebook.com/apps/1616667029816710/settings/basic/\n'
                  f'  (it wants a privacy policy URL first: {SITE}/en/legal/privacy-policy/).')
        sys.exit(1)
    print('\nlive' if args.live else '\npaused: re-run with --live to switch them on')


def cmd_status(args):
    today = time.strftime('%Y-%m-%d')
    for lang, night in NIGHTS.items():
        for kind in ('reservations', 'local reach'):
            found = existing('campaigns', campaign_name(lang, kind), fields='id,name,status,effective_status')
            if not found:
                print(f'{campaign_name(lang, kind):42} not created')
                continue
            spend = get(f'{found["id"]}/insights', date_preset='last_30d',
                        fields='spend,impressions,clicks,actions,cost_per_action_type').get('data', [])
            row = spend[0] if spend else {}
            actions = {a['action_type']: int(float(a['value'])) for a in row.get('actions', [])}
            purchases = actions.get('purchase') or actions.get('offsite_conversion.fb_pixel_purchase') or 0
            print(f'{found["name"]:42} {found["effective_status"]:22} '
                  f'spend {float(row.get("spend", 0)):8,.2f}  clicks {int(row.get("clicks", 0)):5}  '
                  f'purchases {purchases}')
            for adset in pages(f'{found["id"]}/adsets', fields='id,name,effective_status,end_time,daily_budget'):
                end = (adset.get('end_time') or '')[:10]
                flag = '  SCHEDULE ENDED, SPENDS NOTHING' if end and end < today else ''
                print(f'    {adset["id"]}  {adset["name"][:46]:46} {adset["effective_status"]:12} '
                      f'{int(adset.get("daily_budget") or 0) / 100:6.2f}/day{flag}')


def cmd_pause(args):
    for lang in NIGHTS:
        # Both kinds, including the retired one: `pause` is the stop button and must stop everything.
        for kind in ('reservations', 'local reach'):
            found = existing('campaigns', campaign_name(lang, kind))
            if found:
                post(found['id'], status='PAUSED')
                print(f'paused {found["id"]}  {found["name"]}')


def cmd_plan(args):
    for lang, night in NIGHTS.items():
        weekly = (night['daily_conversions'] + (night['daily_reach'] if RUN_REACH else 0)) * 7 / 100
        print(f'\n{night["label"]} night, {night["night"]}s -> {night["link"]}')
        print(f'  {campaign_name(lang, "reservations"):44} OUTCOME_SALES    '
              f'{night["daily_conversions"] / 100:6.2f} MXN/day  optimise {CONVERSION_EVENT} via pixel {PIXEL_ID}')
        if RUN_REACH:
            print(f'  {campaign_name(lang, "local reach"):44} OUTCOME_TRAFFIC  '
                  f'{night["daily_reach"] / 100:6.2f} MXN/day  optimise landing page views')
        else:
            print(f'  {campaign_name(lang, "local reach"):44} OFF                '
                  'retired: no reservation in its whole life, see the note at the top of this file')
        print(f'  targeting  Playa del Carmen {WIDE_KM}km / {NEAR_KM}km, home+recent, 18 to 65'
              + (f', locales {night["locales"]}' if night['locales'] else ''))
        print(f'  creative   {", ".join(night["videos"])}, {night["image"]}')
        print(f'             {night["story_image"]} for Story and Reels, so nothing is cut off by the '
              'account bar or the CTA')
        print(f'  weekly     {weekly:,.2f} MXN')
    total = sum((n['daily_conversions'] + (n['daily_reach'] if RUN_REACH else 0))
                for n in NIGHTS.values()) * 7 / 100
    print(f'\ntotal {total:,.2f} MXN a week across both nights')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('plan', help='print what would be created').set_defaults(func=cmd_plan)
    apply_cmd = sub.add_parser('apply', help='create or update the campaigns')
    apply_cmd.add_argument('--live', action='store_true', help='switch them on rather than leaving them paused')
    apply_cmd.set_defaults(func=cmd_apply)
    sub.add_parser('status', help='what exists and what it spent').set_defaults(func=cmd_status)
    sub.add_parser('pause', help='pause all four campaigns').set_defaults(func=cmd_pause)
    args = parser.parse_args()
    try:
        args.func(args)
    except RateLimited as exc:
        sys.exit(f'{exc}\n\nThe ad account limit clears on a rolling window, so the only fix is to wait a few '
                 'minutes and run it again.')
    except GraphError as exc:
        sys.exit(str(exc))


if __name__ == '__main__':
    main()
