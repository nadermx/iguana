#!/usr/bin/env python3
"""One campaign for one dated show, with a hard stop.

    scripts/meta-show-campaign.py --show improvincia plan
    scripts/meta-show-campaign.py --show improvincia apply --live
    scripts/meta-show-campaign.py --show improvincia status

One entry in SHOWS per dated show. `--show` is required, so a re-run can never touch the wrong show's campaign.
`preflight` checks the live page and the ad against the paid-show rules; `apply` runs it first and refuses to
spend on a FAIL.

The open mic campaigns run forever and point at /open-mic/, which never goes stale. A guest headliner is the
opposite: one night, one landing page, and an ad that must stop before the doors do. So this uses a LIFETIME
budget with a start and an end, which is what makes Meta pace the spend across the window instead of resetting
a daily figure every midnight and overshooting on the last day.

🚨 `end_time` is deliberate here, and it is the opposite of the rule for the open mic ad sets. On those an
end_time is a trap: 31 of them on this account read ACTIVE with a schedule that expired months ago, so the UI
looks busy while nothing spends. Here the expiry IS the feature, because an ad for Friday's show running on
Saturday is worse than no ad. `status` reads it back so a finished campaign is obvious rather than fossilised.

Reuses the open mic builder for the parts that are hard to get right: the rate-limit backoff, the creative
enhancement opt-outs, and the video upload that waits for Meta to finish processing.
"""

import argparse
import datetime as dt
import importlib.util
import json
import pathlib
import sys
import urllib.parse
import urllib.request

ORIGINAL_ARGV = sys.argv[1:]

ROOT = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('openmic', ROOT / 'meta-openmic-campaigns.py')
openmic = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0], 'plan']          # the module parses argv at import
spec.loader.exec_module(openmic)

CANCUN = dt.timezone(dt.timedelta(hours=-5))

SHOWS = {}
SHOWS['privilegio'] = {
    'slug': 'privilegio-fredy-el-regio',
    'name': 'Privilegio · Fredy El Regio',
    'link': f'{openmic.SITE}/es/eventos/privilegio-fredy-el-regio/',
    # Doors are 9pm Friday. The ad stops an hour before, because a ticket bought at 8:55 for a 9pm show in a
    # town people drive to is a refund waiting to happen.
    'ends': dt.datetime(2026, 9, 25, 20, 0, tzinfo=CANCUN),
    # Total for the whole run, not per day: Meta paces a lifetime budget across the window.
    # Raised from 1,200 on 2026-09-24 with 27.7 hours and 40 seats to go; see CLAUDE.md.
    'lifetime_budget': 240000,            # centavos: 2,400.00 MXN
    # A named act pulls from further than a Tuesday open mic does. 40km reaches Tulum and Puerto Morelos;
    # Cancún is its own entry because it is 68km away and worth its own radius.
    'geo': {
        'cities': [{'key': openmic.PLAYA, 'radius': 40, 'distance_unit': 'kilometer'},
                   {'key': 1508006, 'radius': 25, 'distance_unit': 'kilometer'}],   # Cancún, checked against the geo search
        'location_types': ['home', 'recent'],
    },
    'videos': ['fredy-9x16-short.mp4', 'fredy-9x16-long.mp4'],
    'image': 'fredy-flyer-4x5.jpg',
    'story_image': 'fredy-flyer-9x16-safe.jpg',
    'copy': {
        'message': ('Fredy El Regio trae Privilegio a Playa del Carmen, el viernes 25 de septiembre.\n\n'
                    'Una sola función, 80 lugares, en Iguana Comedy en el centro. Boletos 300 MXN y los '
                    'compras aquí en menos de un minuto.'),
        'title': 'Fredy El Regio en Playa del Carmen',
        'description': 'Viernes 25 de septiembre · 9:00 pm · Iguana Comedy',
    },
}

SHOWS['improvincia'] = {
    'slug': 'improvincia',
    'name': 'Improvincia',
    'link': f'{openmic.SITE}/es/eventos/improvincia/',
    # Friday 2 October, doors 8, show 9. Stops at doors, the same rule as Privilegio.
    'ends': dt.datetime(2026, 10, 2, 20, 0, tzinfo=CANCUN),
    # Cut on 2026-09-29 to about 100 MXN a day for the last 3.2 days (owner: "not selling"). The figure is the
    # whole run across both ad sets: 271.26 spent by the retired one + 739.83 on the current one, so a re-run of
    # `apply` keeps the cut instead of restoring the original 2,400.
    'lifetime_budget': 101109,            # centavos: 1,011.09 MXN
    'geo': SHOWS['privilegio']['geo'],
    # An improv troupe, not a stand-up: stand-up alone bought 5,888 impressions and no real order in the first
    # day (owner, 2026-09-28). Meta ORs everything inside one interests list, so this WIDENS the audience; stand-up
    # stays because it is the only interest this account has ever sold on.
    'interests': [
        openmic.STANDUP_INTEREST,
        # Meta folded "Improvisational theatre", "Whose Line Is It Anyway?" and "Comedy Central (Latin America)"
        # into these three on 2026-09-28; the old ids still SEARCH but are refused on an ad set.
        {'id': '6002957026250', 'name': 'Theatre'},
        {'id': '6003319728736', 'name': 'Television comedy'},
        {'id': '6777890774833', 'name': 'Comedy TV Channels'},
        {'id': '6003584475638', 'name': 'Comedy club'},
        {'id': '6003417378239', 'name': 'Obras de teatro (artes escénicas)'},
    ],
    'videos': ['improvincia-9x16-a.mp4', 'improvincia-9x16-b.mp4'],
    # The square flyer: Meta shows 1:1 whole in the feed. The Story version is the same flyer inside the band
    # Instagram does not cover (scripts/fit-story.py).
    'image': 'improvincia-flyer-1x1.jpg',
    'story_image': 'improvincia-flyer-9x16-safe.jpg',
    'copy': {
        # The price in the FIRST line: the feed cuts the rest behind "... más". Before 2026-09-28 it sat in the
        # second paragraph: 345 clicks, 6 people started the checkout, 1 bought. Tickets are paid online only
        # (owner, 2026-09-28: "pay on site, we don't want them paying at the door").
        'message': ('Improvincia, viernes 2 de octubre: boletos $200, cómpralos aquí en un minuto.\n\n'
                    'Comedia 100% improvisada, un show interactivo que nunca se repite. Una sola función en Iguana '
                    'Comedy, en el centro de Playa del Carmen.'),
        'title': 'Improvincia · boletos $200',
        'description': 'Viernes 2 oct · 9:00 pm · Iguana Comedy',
    },
    # What a person checked on the flyer, because no script can read one. See preflight().
    # The promoter's flyer printed "RESERVAS: 9988447132"; on 2026-09-28 it was erased and relettered as
    # "BOLETOS: IGUANACOMEDY.COM" in the flyer's own teal, so the ad no longer sends bookings to a WhatsApp.
    'flyer': {'date': '2 de octubre', 'price': '$200'},
}


SHOWS['manu'] = {
    'slug': 'manu-rejon-playa-del-carmen',
    'name': 'Manu Rejón',
    'link': f'{openmic.SITE}/es/eventos/manu-rejon-playa-del-carmen/',
    # Saturday 17 October, doors 8, show 9. Stops at doors, the same rule as Privilegio.
    'ends': dt.datetime(2026, 10, 17, 20, 0, tzinfo=CANCUN),
    # 75 seats at 250 MXN, eight days out. At the 35 to 49 MXN a paid seat has cost here, a full room is
    # roughly 2,600 to 3,700 MXN of ads, so the run is capped at 3,000 for both ad sets together.
    'lifetime_budget': 300000,            # centavos: 3,000.00 MXN
    'geo': SHOWS['privilegio']['geo'],
    # A stand-up, so stand-up leads; the comedy interests that replaced the retired ones widen it (Meta ORs them).
    'interests': [
        openmic.STANDUP_INTEREST,
        {'id': '6003584475638', 'name': 'Comedy club'},
        {'id': '6003319728736', 'name': 'Television comedy'},
        {'id': '6777890774833', 'name': 'Comedy TV Channels'},
    ],
    # The comedian's own three edits (24s, 19s, 15s), each ending on "click aquí para tus boletos".
    'videos': ['manu-9x16-1.mp4', 'manu-9x16-2.mp4', 'manu-9x16-3.mp4'],
    'image': 'manu-flyer-4x5.jpg',
    'story_image': 'manu-flyer-9x16-safe.jpg',
    'copy': {
        'message': ('Manu Rejón en Playa, sábado 17 de octubre: boletos $250, cómpralos aquí en un minuto.\n\n'
                    'Recién regresado de su gira por Alemania, con invitados especiales desde Mérida. Una sola '
                    'función en Iguana Comedy, en el centro de Playa del Carmen, y el cupo es limitado.'),
        'title': 'Manu Rejón · boletos $250',
        'description': 'Sábado 17 oct · 9:00 pm · Iguana Comedy',
    },
    # Checked by eye 2026-10-09: "SABADO 17 DE OCTUBRE", "ENTRADAS: $250 MXN", the club's address and no phone.
    # The three clips name only Iguana Comedy Club and "click aquí para tus boletos".
    'flyer': {'date': '17 de octubre', 'price': '$250'},
}


SHOWS['halloween'] = {
    'slug': 'halloween-at-iguana-2026',
    'name': 'Halloween en Iguana',
    'link': f'{openmic.SITE}/es/eventos/halloween-at-iguana-2026/',
    # Saturday 31 October, doors 8:30, show 9. The owner asked for the ads to stop at 7pm.
    'ends': dt.datetime(2026, 10, 31, 19, 0, tzinfo=CANCUN),
    # 🔑 FREE since 12:50 Friday 30 Oct (owner: no sales after 11 hours and "i just need people to show up").
    # A free show optimises on checkouts started (as the open mic reservations do), builds a new ad set for
    # the new goal with the unspent budget, and gets fresh creative, because the old copy and flyer said $100.
    'free': True,
    # Built at 01:50 on the Friday, so about 41 hours of run. The owner's ceiling is 20 paid seats; Manu cost
    # 2,945 MXN for 62 seats (47.5 each, and not every seat came from the ads), so 20 x 50 = 1,000 MXN caps it.
    'lifetime_budget': 100000,            # centavos: 1,000.00 MXN
    'geo': SHOWS['privilegio']['geo'],
    'interests': SHOWS['manu']['interests'],
    # A Spanish show, and the owner asked for Spanish speakers. Privilegio and Manu reached them through Spanish
    # copy and a Spanish interest only, with no language filter; this one adds it. 23 Español, 7 Español (España).
    'locales': [23, 7],
    # The owner's 13s clip (3:4, "Click para reservar!", the club's address, no phone) placed inside the Story
    # safe band on a blurred copy of itself; the same file serves feed and Reels.
    # The owner's second cut (9:16, AI voices for the characters, no price on screen) and the flyer relettered
    # "ENTRADA GRATIS RESERVANDO". The paid ad set's $100 video and flyer stay with it, paused.
    'videos': ['halloween-free-9x16.mp4'],
    'image': 'halloween-free-flyer-4x5.jpg',
    'story_image': 'halloween-free-flyer-9x16-safe.jpg',
    'copy': {
        'message': ('Halloween en Iguana, sábado 31 de octubre: entrada GRATIS, reserva tu lugar aquí.\n\n'
                    'Show de stand up temático, concurso de disfraces con premio a los mejores, y después DJ y '
                    'karaoke. En Iguana Comedy, en el centro de Playa del Carmen. ¡Ven disfrazado!'),
        'title': 'Halloween en Iguana · entrada gratis',
        'description': 'Sábado 31 oct · 9:00 pm · reserva gratis',
    },
    # Checked by eye 2026-10-30: "SABADO 31 DE OCTUBRE", "ENTRADA GRATIS RESERVANDO: WWW.IGUANACOMEDY.COM", no phone.
    'flyer': {'date': '31 de octubre', 'price': 'gratis'},
}


def _chosen_show(argv):
    """`--show <key>` from the command line, taken before argparse because the names below depend on it."""
    if '--show' in argv and argv.index('--show') + 1 < len(argv):
        key = argv[argv.index('--show') + 1]
        if key in SHOWS:
            return key
    sys.exit(f'pass --show with one of: {", ".join(SHOWS)}')


SHOW = SHOWS[_chosen_show(ORIGINAL_ARGV)]
# What a paid show's ad set optimises for: InitiateCheckout with a value above 0 (custom conversion on pixel
# "andrew new pixel"). Plain InitiateCheckout is shared by every night on the pixel, and the cheapest checkout for
# Meta to find is a FREE open mic reservation, so a paid-show ad set steered on it learns to find people who book
# free seats. Improvincia's first day showed it: Meta reported 5 checkouts and 2 purchases, our database held
# zero Improvincia orders. Every InitiateCheckout carries the night's price as `value` (sales/ad_reporting.py),
# which is what makes paid and free separable at all.
PAID_CHECKOUT = '1670646004630204'
# Part of the ad set name, because Meta freezes an ad set's optimisation once published: changing the goal means
# a new ad set, and a new name is what makes this script build one instead of editing the old.
GOAL_TAG = 'pagados'
# A FREE show (SHOW['free']) is a reservation, like an open mic: there is no paid checkout to steer on, so it
# optimises on checkouts started, the event the open mic reservation ad sets use, and says "reserve" not "buy".
if SHOW.get('free'):
    GOAL_TAG = 'reservas'
PROMOTED = ({'pixel_id': openmic.PIXEL_ID, 'custom_event_type': 'INITIATED_CHECKOUT'} if SHOW.get('free')
            else {'custom_conversion_id': PAID_CHECKOUT})
CTA = 'SIGN_UP' if SHOW.get('free') else 'BUY_TICKETS'

CAMPAIGN = f'{SHOW["name"]} · boletos'
ADSET = f'{SHOW["name"]} · Riviera Maya · boletos · {GOAL_TAG}'


def iso(when):
    return when.strftime('%Y-%m-%dT%H:%M:%S%z')


def targeting():
    spec = {
        'geo_locations': SHOW['geo'],
        'age_min': 18,
        'age_max': 65,
        'location_types': ['home', 'recent'],
        'flexible_spec': [{'interests': SHOW.get('interests', [openmic.STANDUP_INTEREST])}],
        'targeting_automation': {'advantage_audience': 0},
    }
    if SHOW.get('locales'):
        spec['locales'] = SHOW['locales']
    return spec


def ensure_campaign(live):
    found = openmic.existing('campaigns', CAMPAIGN)
    spec = {
        'name': CAMPAIGN,
        'objective': 'OUTCOME_SALES',
        'special_ad_categories': [],
        'is_adset_budget_sharing_enabled': False,
        'status': 'ACTIVE' if live else 'PAUSED',
    }
    if found:
        openmic.post(found['id'], name=spec['name'], status=spec['status'])
        print(f'  campaign {found["id"]}  {CAMPAIGN} (updated)')
        return found['id']
    made = openmic.post(f'{openmic.AD_ACCOUNT}/campaigns', **spec)
    openmic.remember('campaigns', {'id': made['id'], 'name': CAMPAIGN})
    print(f'  campaign {made["id"]}  {CAMPAIGN} (created)')
    return made['id']


def superseded(campaign_id):
    """Ad sets in this campaign that are not the current one: an older goal, left behind."""
    return [a for a in openmic.pages(f'{campaign_id}/adsets', fields='id,name,status')
            if a['name'] != ADSET]


def spent_by(adset_ids):
    total = 0
    for adset_id in adset_ids:
        for row in openmic.get(f'{adset_id}/insights', fields='spend', date_preset='maximum').get('data', []):
            total += round(float(row.get('spend', 0)) * 100)
    return total


def ensure_adset(campaign_id, live):
    start = dt.datetime.now(CANCUN) + dt.timedelta(minutes=2)
    older = superseded(campaign_id)
    # The show's budget is for the whole run, so a replacement ad set gets what the old one did not spend.
    budget = SHOW['lifetime_budget'] - spent_by([a['id'] for a in older])
    spec = {
        'name': ADSET,
        'campaign_id': campaign_id,
        'lifetime_budget': budget,
        'start_time': iso(start),
        'end_time': iso(SHOW['ends']),
        'billing_event': 'IMPRESSIONS',
        # Without this Meta refuses the ad set outright, asking for a bid amount it does not need.
        'bid_strategy': 'LOWEST_COST_WITHOUT_CAP',
        'optimization_goal': 'OFFSITE_CONVERSIONS',
        'destination_type': 'WEBSITE',
        # A custom conversion is promoted ALONE. Adding its pixel_id or any custom_event_type, even the one it is
        # built on, is refused as "combinación no válida" (checked with validate_only, 2026-09-28).
        'promoted_object': PROMOTED,
        'attribution_spec': [{'event_type': 'CLICK_THROUGH', 'window_days': 1},
                             {'event_type': 'VIEW_THROUGH', 'window_days': 1}],
        'targeting': targeting(),
        'status': 'ACTIVE' if live else 'PAUSED',
    }
    found = openmic.existing('adsets', ADSET)
    if found:
        frozen = {'campaign_id', 'optimization_goal', 'promoted_object', 'destination_type', 'billing_event',
                  'attribution_spec', 'start_time'}
        openmic.post(found['id'], **{k: v for k, v in spec.items() if k not in frozen})
        print(f'  ad set   {found["id"]}  {ADSET} (updated)')
        return found['id'], []
    made = openmic.post(f'{openmic.AD_ACCOUNT}/adsets', **spec)
    openmic.remember('adsets', {'id': made['id'], 'name': ADSET})
    print(f'  ad set   {made["id"]}  {ADSET} (created, {budget / 100:,.2f} MXN)')
    return made['id'], older


def video_creative(video_id, thumbnail, name):
    cta = {'type': CTA, 'value': {'link': SHOW['link']}}
    return {
        'name': name,
        'object_story_spec': {
            'page_id': openmic.PAGE_ID, 'instagram_user_id': openmic.INSTAGRAM_ID,
            'video_data': {'video_id': video_id, 'message': SHOW['copy']['message'],
                           'title': SHOW['copy']['title'], 'link_description': SHOW['copy']['description'],
                           'call_to_action': cta, 'image_url': thumbnail},
        },
        'degrees_of_freedom_spec': {'creative_features_spec':
                                    {f: {'enroll_status': 'OPT_OUT'} for f in openmic.OPT_OUT_FEATURES}},
    }


def flyer_creative(feed_hash, story_hash, name):
    return {
        'name': name,
        'object_story_spec': {'page_id': openmic.PAGE_ID, 'instagram_user_id': openmic.INSTAGRAM_ID},
        'asset_feed_spec': {
            'images': [{'hash': feed_hash, 'adlabels': [{'name': f'{name} feed'}]},
                       {'hash': story_hash, 'adlabels': [{'name': f'{name} story'}]}],
            'bodies': [{'text': SHOW['copy']['message']}],
            'titles': [{'text': SHOW['copy']['title']}],
            'descriptions': [{'text': SHOW['copy']['description']}],
            'link_urls': [{'website_url': SHOW['link']}],
            'call_to_action_types': [CTA],
            'ad_formats': ['SINGLE_IMAGE'],
            'asset_customization_rules': [
                {'customization_spec': openmic.STORY_PLACEMENTS, 'image_label': {'name': f'{name} story'},
                 'priority': 1},
                {'customization_spec': {}, 'image_label': {'name': f'{name} feed'}, 'priority': 2},
            ],
        },
        'degrees_of_freedom_spec': {'creative_features_spec':
                                    {f: {'enroll_status': 'OPT_OUT'} for f in openmic.OPT_OUT_FEATURES}},
    }


# ------------------------------------------------------------------ preflight
#
# The rules every PAID show's ads are checked against before a peso is spent (owner, 2026-09-28: "set rules to
# always check for these things on paid events"). Each one is a thing that went wrong on Improvincia:
#   - a date on the page that disagreed with the flyer (3 vs 2 October),
#   - a pay-at-the-door option: tickets for paid shows are paid ON THE SITE (owner, 2026-09-28), never at the door,
#   - the price in the ad's second paragraph, behind "... más",
#   - a flyer that sends bookings to a WhatsApp number instead of the page,
#   - a thin page: no Spanish description, no clip of the act.
# FAIL stops `apply`; WARN is printed and allowed.

SOCIAL_SPEC = importlib.util.spec_from_file_location('social', ROOT / 'meta-social.py')
social = importlib.util.module_from_spec(SOCIAL_SPEC)
SOCIAL_SPEC.loader.exec_module(social)


def live_event(locale='es'):
    key = social.public_api_key(None)
    url = f'{social.EVENTS_API}/{urllib.parse.quote(SHOW["slug"])}?locale={locale}'
    request = urllib.request.Request(url, headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)['event']


def preflight():
    """[(level, message)] for this show. Levels: FAIL, WARN, OK."""
    out = []
    add = lambda ok, level, msg: out.append(('OK' if ok else level, msg))
    try:
        ev = live_event('es')
    except Exception as exc:  # noqa: BLE001 - any failure to read the page is itself a FAIL
        return [('FAIL', f'cannot read the event from the API: {exc}')]
    add(ev.get('status') == 'on-sale', 'FAIL', f'event is on sale (status: {ev.get("status")})')
    add(ev.get('date') == SHOW['ends'].date().isoformat(), 'FAIL',
        f'event date {ev.get("date")} matches the ad window ending {SHOW["ends"]:%Y-%m-%d}')
    first_line = SHOW['copy']['message'].split('\n')[0].lower()
    if SHOW.get('free'):
        add(ev.get('priceFrom') == 0, 'FAIL', f'the page sells free seats (priceFrom {ev.get("priceFrom")})')
        add('gratis' in first_line and '$' not in SHOW['copy']['message'], 'FAIL',
            'the ad\'s FIRST line says it is free, and the ad names no price')
    else:
        add(not ev.get('payAtDoor'), 'FAIL', 'tickets are paid on the site, with no pay-at-the-door option')
        add(('$' in first_line or 'mxn' in first_line), 'FAIL', 'the ad\'s FIRST line states the price')
        add('puerta' not in first_line, 'FAIL', 'the ad does not promise paying at the door')
        add('$' in (SHOW['copy']['title'] + SHOW['copy']['description']), 'WARN', 'the headline or link line carries the price')
    description = (ev.get('description') or '') + ' ' + (ev.get('longDescription') or '')
    add(len(description.strip()) >= 60, 'FAIL', f'the Spanish page says what the show is ({len(description.strip())} chars)')
    add(bool(ev.get('imageUrl')), 'FAIL', 'the page has a poster')
    reels = [r for entry in ev.get('lineup') or [] for r in (entry.get('reels') or [])]
    add(bool(reels), 'WARN', 'the page has a clip of the act (lineup reel)')
    flyer = SHOW.get('flyer') or {}
    add(bool(flyer.get('date')) and bool(flyer.get('price')), 'FAIL',
        'somebody checked the flyer\'s date and price (SHOW["flyer"])')
    if flyer.get('booking_phone'):
        add(flyer.get('accept_booking_phone', False), 'FAIL',
            f'the flyer sends bookings to {flyer["booking_phone"]} instead of the page' +
            (' (accepted for this run)' if flyer.get('accept_booking_phone') else ''))
    interests = [i['name'] for i in SHOW.get('interests', [openmic.STANDUP_INTEREST])]
    add(len(interests) > 1, 'WARN', f'targeting is wider than stand-up alone ({len(interests)} interest(s))')
    missing = [f for f in [*SHOW['videos'], SHOW['image'], SHOW['story_image']] if not (openmic.CREATIVE_DIR / f).exists()]
    add(not missing, 'FAIL', 'creative files present' + (f' (missing {", ".join(missing)})' if missing else ''))
    return out


def cmd_preflight(_):
    rows = preflight()
    for level, msg in rows:
        print(f'  {level:4}  {msg}')
    failed = [m for lvl, m in rows if lvl == 'FAIL']
    print(f'\n{len(failed)} failure(s)' if failed else '\nready')
    return not failed


def cmd_plan(_):
    left = SHOW['ends'] - dt.datetime.now(CANCUN)
    hours = left.total_seconds() / 3600
    print(f'\n{SHOW["name"]} -> {SHOW["link"]}')
    goal = 'checkouts started (free reservations)' if SHOW.get('free') else f'paid checkouts ({PAID_CHECKOUT})'
    print(f'  {CAMPAIGN:52} OUTCOME_SALES  optimise {goal} via pixel {openmic.PIXEL_ID}')
    print(f'  budget     {SHOW["lifetime_budget"] / 100:,.2f} MXN for the whole run, paced by Meta')
    print(f'  window     now until {SHOW["ends"]:%a %d %b %H:%M} Cancun  ({hours:.1f} hours left)')
    names = ', '.join(i['name'] for i in SHOW.get('interests', [openmic.STANDUP_INTEREST]))
    print(f'  targeting  Playa del Carmen 40km + Cancún 25km, home+recent, 18 to 65, any of: {names}')
    print(f'  creative   {", ".join(SHOW["videos"])}, {SHOW["image"]}')
    print(f'             {SHOW["story_image"]} for Story and Reels')
    if hours <= 0:
        print('\n  the window has already closed; nothing would deliver')


def cmd_apply(args):
    print('preflight:')
    if not cmd_preflight(args) and not args.force:
        sys.exit('refusing to spend on a show that fails preflight (fix it, or --force with a reason)')
    openmic.PATIENT = True
    missing = [f for f in [*SHOW['videos'], SHOW['image'], SHOW['story_image']]
               if not (openmic.CREATIVE_DIR / f).exists()]
    if missing:
        sys.exit(f'creative missing from {openmic.CREATIVE_DIR}: {", ".join(missing)}')
    if SHOW['ends'] <= dt.datetime.now(CANCUN):
        sys.exit('the end time has already passed; nothing would deliver')

    print(f'\n{SHOW["name"]} -> {SHOW["link"]}')
    campaign_id = ensure_campaign(args.live)
    adset_id, older = ensure_adset(campaign_id, args.live)
    blocked = []

    # A replacement ad set carries the old one's ads over by creative, so nothing is uploaded twice and the
    # copy people have already seen stays identical. Then the old ad set stops.
    if older and SHOW.get('free'):
        # The old ads say $100, so they are not carried over: the old ad set stops and new ads are built below.
        for old in older:
            if old.get('status') != 'PAUSED':
                openmic.post(old['id'], status='PAUSED')
                print(f'  retired  {old["id"]}  {old["name"]} (paid goal, priced creative)')
    elif older:
        status = 'ACTIVE' if args.live else 'PAUSED'
        for old in older:
            for ad in openmic.pages(f'{old["id"]}/ads', fields='id,name,creative{id}'):
                name = ad['name'].replace(old['name'], ADSET)
                if not openmic.existing('ads', name):
                    made = openmic.post(f'{openmic.AD_ACCOUNT}/ads', name=name, adset_id=adset_id,
                                        creative={'creative_id': ad['creative']['id']}, status=status)
                    openmic.remember('ads', {'id': made['id'], 'name': name})
                    print(f'  ad       {made["id"]}  {name} (carried over)')
            if old.get('status') != 'PAUSED':
                openmic.post(old['id'], status='PAUSED')
                print(f'  retired  {old["id"]}  {old["name"]} (old goal)')
        print('\nlive' if args.live else '\npaused: re-run with --live to start it')
        return

    for index, filename in enumerate(SHOW['videos'], start=1):
        video_id = openmic.upload_video(openmic.CREATIVE_DIR / filename)
        openmic.wait_for_video(video_id)
        creative = video_creative(video_id, openmic.video_thumbnail(video_id), f'{CAMPAIGN} · video {index}')
        openmic.try_ad(blocked, 'es', 'show', adset_id, creative, f'{ADSET} · video {index}', args.live)

    feed = openmic.upload_image(openmic.CREATIVE_DIR / SHOW['image'])
    story = openmic.upload_image(openmic.CREATIVE_DIR / SHOW['story_image'])
    openmic.try_ad(blocked, 'es', 'show', adset_id,
                   flyer_creative(feed, story, f'{CAMPAIGN} · flyer'), f'{ADSET} · flyer', args.live)

    if blocked:
        print(f'\n{len(blocked)} ad(s) could not be created:')
        for name, reason in blocked:
            print(f'  {name}\n    {reason}')
        sys.exit(1)
    print('\nlive' if args.live else '\npaused: re-run with --live to start it')


def cmd_status(_):
    adset = openmic.existing('adsets', ADSET, fields='id,name,status,effective_status')
    if not adset:
        print('not built yet')
        return
    row = openmic.get(adset['id'], fields='name,status,effective_status,lifetime_budget,start_time,end_time,budget_remaining')
    print(f"{row['name']}\n  {row['status']} / {row.get('effective_status')}")
    print(f"  budget {int(row.get('lifetime_budget') or 0) / 100:,.2f} MXN  "
          f"remaining {int(row.get('budget_remaining') or 0) / 100:,.2f}")
    print(f"  {row.get('start_time')} -> {row.get('end_time')}")
    data = openmic.get(f"{adset['id']}/insights", fields='spend,impressions,clicks,ctr,actions').get('data', [])
    for r in data:
        acts = {a['action_type']: a['value'] for a in r.get('actions', [])}
        print(f"  spend {float(r['spend']):.2f}  impressions {r['impressions']}  clicks {r['clicks']}  "
              f"ctr {float(r['ctr']):.2f}%")
        print('  ', {k: v for k, v in acts.items()
                     if k in ('purchase', 'initiate_checkout', 'landing_page_view', 'link_click')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--show', required=True, choices=sorted(SHOWS))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('plan').set_defaults(func=cmd_plan)
    sub.add_parser('preflight').set_defaults(func=cmd_preflight)
    sub.add_parser('status').set_defaults(func=cmd_status)
    apply_cmd = sub.add_parser('apply')
    apply_cmd.add_argument('--live', action='store_true', help='Start it. Without this everything is PAUSED.')
    apply_cmd.add_argument('--force', action='store_true', help='Spend even though preflight failed.')
    apply_cmd.set_defaults(func=cmd_apply)
    args = parser.parse_args(sys.argv[1:])
    args.func(args)


if __name__ == '__main__':
    sys.argv = [sys.argv[0]] + ORIGINAL_ARGV
    main()
