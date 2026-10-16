"""What the club is spending and what it is getting, on one page that keeps itself current.

The question it exists to answer is the one asked several times a day: what does a reservation cost us right
now, free against paid. Everything here is built from two sources that disagree by nature, so the page is
explicit about which is which.

Bookings, seats and money taken are OUR rows, counted live at the moment of the request. Spend is Meta's, read
from the `AdSpend` snapshot a cron writes every quarter of an hour, never fetched in the request. Cost per seat
is therefore their numerator over our denominator, which is the honest way round: Meta's own purchase count
has run both above and below the orders we hold, so it appears on the page as a comparison and is never used
to divide by.

A part-day number is not a day. Spend accrues steadily from midnight while bookings arrive in the evening, so
today's cost per seat reads high all afternoon and settles by night. The page says so rather than letting
somebody act on 14:00 as though it were a result.
"""

from collections import Counter
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from django.utils import timezone
from django.utils.timesince import timesince

from crm.ad_spend import FREQUENCY_TARGET, campaign_rows, last_fetch, spend_between
from crm.models import AdSpend
from sales.i18n import lang_from_request
from sales.models import Order

from .revenue_views import can_see_the_money

CANCUN = ZoneInfo('America/Cancun')
STALE_AFTER = timedelta(minutes=45)


def _bookings(first_day, last_day):
    """Our own rows: (free, paid) each with bookings, seats and money actually taken."""
    start = timezone.make_aware(timezone.datetime.combine(first_day, timezone.datetime.min.time()), CANCUN)
    end = timezone.make_aware(timezone.datetime.combine(last_day + timedelta(days=1), timezone.datetime.min.time()), CANCUN)
    free = {'bookings': 0, 'seats': 0, 'money': Counter()}
    paid = {'bookings': 0, 'seats': 0, 'money': Counter()}
    orders = (Order.objects.filter(status=Order.COMPLETED, created_at__gte=start, created_at__lt=end)
              .prefetch_related('tickets'))
    for order in orders:
        if (order.customer_email or '').startswith('e2e-'):
            continue  # our own end-to-end probes, which would otherwise flatter every rate on this page
        charged = max(order.total_amount_cents - order.pay_at_door_cents, 0)
        side = paid if charged > 0 else free
        side['bookings'] += 1
        side['seats'] += order.tickets.count()
        if charged:
            side['money'][(order.currency or 'mxn').upper()] += charged
    return free, paid


def _row(label, spend_cents, side):
    seats, bookings, money = side['seats'], side['bookings'], side['money']
    earned = [f'{cents / 100:,.2f} {code}' for code, cents in sorted(money.items()) if cents]
    # A ratio across two currencies would be arithmetic on apples and pesos, so it is only offered when one
    # currency took the money. In practice that is MXN; a dollar night selling alongside simply hides the ratio.
    single = money.most_common(1)[0][1] if len(money) == 1 else 0
    return {
        'label': label,
        'spend': spend_cents / 100,
        'bookings': bookings,
        'seats': seats,
        'revenue': ' · '.join(earned),
        'per_seat': (spend_cents / 100 / seats) if seats else None,
        'per_booking': (spend_cents / 100 / bookings) if bookings else None,
        'roas': (single / spend_cents) if spend_cents and single else None,
        'ad_share': (spend_cents / single * 100) if single else None,
    }


def _window(first_day, last_day, label):
    spend = spend_between(first_day, last_day)
    free, paid = _bookings(first_day, last_day)
    free_row = _row('free', spend.get(AdSpend.FREE, 0), free)
    paid_row = _row('paid', spend.get(AdSpend.PAID, 0), paid)
    return {
        'label': label,
        'free': free_row,
        'paid': paid_row,
        'sides': [free_row, paid_row],
        'spend': (spend.get(AdSpend.FREE, 0) + spend.get(AdSpend.PAID, 0)) / 100,
    }


# Which ad an order arrived through, read off the link it landed on. Meta appends fbclid and utm_source fb/ig to
# every click on its own; our TikTok ads carry utm_source=tiktok and TikTok appends ttclid. `fbc` alone is the
# pixel's 90-day memory of an earlier Meta click, so it counts for Meta only when nothing newer says otherwise.
META_SOURCES = {'fb', 'ig', 'facebook', 'instagram', 'meta', 'an', 'msg'}


def platform_of(attribution):
    a = attribution if isinstance(attribution, dict) else {}
    source = str(a.get('source', '')).lower()
    if a.get('ttclid') or source == 'tiktok':
        return 'tiktok'
    if a.get('fbclid') or source in META_SOURCES or a.get('fbc'):
        return 'meta'
    return 'other'


def _platforms(first_day, last_day):
    """Bookings and seats per ad platform, against that platform's own spend, so the two can be compared."""
    start = timezone.make_aware(timezone.datetime.combine(first_day, timezone.datetime.min.time()), CANCUN)
    end = timezone.make_aware(timezone.datetime.combine(last_day + timedelta(days=1), timezone.datetime.min.time()), CANCUN)
    rows = {key: {'key': key, 'bookings': 0, 'seats': 0, 'free_seats': 0, 'paid_seats': 0, 'money': Counter()}
            for key in ('meta', 'tiktok', 'other')}
    for order in (Order.objects.filter(status=Order.COMPLETED, created_at__gte=start, created_at__lt=end)
                  .prefetch_related('tickets')):
        if (order.customer_email or '').startswith('e2e-'):
            continue
        row = rows[platform_of(order.attribution)]
        seats = order.tickets.count()
        charged = max(order.total_amount_cents - order.pay_at_door_cents, 0)
        row['bookings'] += 1
        row['seats'] += seats
        row['paid_seats' if charged else 'free_seats'] += seats
        if charged:
            row['money'][(order.currency or 'mxn').upper()] += charged
    spend = spend_between(first_day, last_day)
    # AdSpend holds Meta only so far; TikTok's spend has no snapshot yet, so its cost is unknown, not zero.
    spend_cents = {'meta': spend.get(AdSpend.FREE, 0) + spend.get(AdSpend.PAID, 0), 'tiktok': None, 'other': None}
    out = []
    for key in ('meta', 'tiktok', 'other'):
        row = rows[key]
        cents = spend_cents[key]
        row['spend'] = None if cents is None else cents / 100
        row['per_seat'] = (cents / 100 / row['seats']) if cents and row['seats'] else None
        row['revenue'] = ' · '.join(f'{c / 100:,.2f} {code}' for code, c in sorted(row['money'].items()) if c)
        out.append(row)
    return out


def _upcoming_nights(limit=6):
    """Every night still to come: how many of the room we have sold, and how many are left.

    The question this answers is the one asked walking into the office: are we full on Tuesday. `demand_for`
    does it in two queries for the whole set and already counts seats sold elsewhere by a guest promoter, so a
    night somebody else is also selling does not read as empty here.
    """
    from catalog.models import Event
    from sales.demand import demand_for

    today = timezone.now().astimezone(CANCUN).date()
    # A sold-out night is the one you most want on this page, so `status=ACTIVE` was exactly the wrong filter:
    # marking Privilegio sold out dropped the busiest night of the week off the dashboard entirely.
    events = list(Event.objects.filter(status__in=(Event.ACTIVE, Event.SOLD_OUT), date__date__gte=today)
                  .order_by('date')[:limit])
    pressure = demand_for(events)
    nights = []
    for event in events:
        row = pressure.get(event.id) or {}
        capacity, taken = row.get('capacity') or 0, row.get('taken') or 0
        when = event.date.astimezone(CANCUN)
        nights.append({
            'id': event.id,
            'name': event.label('en'),
            'when': when,
            'tonight': when.date() == today,
            'taken': taken,
            'capacity': capacity,
            'left': max(capacity - taken, 0) if capacity else None,
            'percent': 100 if event.status == Event.SOLD_OUT else (
                round(min(taken / capacity, 1) * 100) if capacity else 0),
            # Our own rows can say 40 of 80 on a night that is genuinely gone, because a guest promoter sells a
            # block we never see. The status is the truth; the counts are what WE can see, and both are shown.
            'sold_out': event.status == Event.SOLD_OUT,
            'show_time': event.show_time,
        })
    return nights


def _funnel(first_day, last_day):
    """Visits, then the ones who touched the form, then the ones who booked.

    `k.js` records a pageview per visit and `checkout_engaged` when somebody actually starts filling the
    checkout in, so the gap between those two is interest and the gap after it is the form itself.
    """
    from crm.models import TrackedEvent

    start = timezone.make_aware(timezone.datetime.combine(first_day, timezone.datetime.min.time()), CANCUN)
    end = timezone.make_aware(timezone.datetime.combine(last_day + timedelta(days=1), timezone.datetime.min.time()), CANCUN)
    seen = TrackedEvent.objects.filter(created_at__gte=start, created_at__lt=end)
    visits = seen.filter(kind='pageview').count()
    engaged = seen.filter(name='checkout_engaged').count()
    booked = (Order.objects.filter(status=Order.COMPLETED, created_at__gte=start, created_at__lt=end)
              .exclude(customer_email__startswith='e2e-').count())
    return {
        'visits': visits,
        'engaged': engaged,
        'booked': booked,
        'engaged_rate': (engaged / visits * 100) if visits else None,
        'booked_rate': (booked / engaged * 100) if engaged else None,
    }


def _open_mic_to_paid():
    """Do open mic bookers come back and pay? (owner, 2026-10-09)

    Counted by PERSON, contact first and email as the fallback, across every booking we hold: somebody who
    reserved a free open mic seat and later completed a paid order counts once, whatever led them there. The
    links on the order page and in the confirmation email are counted separately, by the `ref` k.js saves on
    the order and by the pageviews that arrived carrying it, so the follow-on link's own pull is visible.
    """
    from crm.models import TrackedEvent
    from sales.sharing import CROSS_SELL_REFS, is_open_mic

    first_mic, paid = {}, {}
    via_link = {ref: 0 for ref in CROSS_SELL_REFS}
    orders = (Order.objects.filter(status=Order.COMPLETED, source='').exclude(event__isnull=True)
              .exclude(customer_email__startswith='e2e-').select_related('event').order_by('created_at'))
    for order in orders:
        who = order.contact_id or (order.customer_email or '').lower()
        if is_open_mic(order.event):
            first_mic.setdefault(who, order.created_at)
        elif (order.total_amount_cents or 0) - (order.pay_at_door_cents or 0) > 0:
            paid.setdefault(who, []).append(order.created_at)
            ref = (order.attribution or {}).get('ref', '')
            if ref in via_link:
                via_link[ref] += 1
    crossed = sum(1 for who, at in first_mic.items() if any(when > at for when in paid.get(who, [])))
    clicks = {ref: TrackedEvent.objects.filter(kind='pageview', url__contains=f'ref={ref}').count()
              for ref in CROSS_SELL_REFS}
    return {
        'bookers': len(first_mic),
        'crossed': crossed,
        'rate': (crossed / len(first_mic) * 100) if first_mic else None,
        'clicks_page': clicks['om-thanks'], 'clicks_email': clicks['om-email'],
        'sold_page': via_link['om-thanks'], 'sold_email': via_link['om-email'],
    }


def _bar_nights(limit=8):
    """What the bar sold and collected, per show.

    A round is stamped with the night it was poured on, so this survives the calendar rolling over at midnight
    while the show is still running. `collected` is what has actually been settled; `owed` is what is still on
    a table, which on a night still in progress is most of it.
    """
    from django.db.models import Sum
    from sales.models import TableOrder, TableOrderItem

    rows = {}
    orders = (TableOrder.objects.exclude(status=TableOrder.CANCELLED).exclude(event__isnull=True)
              .select_related('event').order_by('-created_at'))
    for order in orders[:400]:
        key = order.event_id
        row = rows.setdefault(key, {'event': order.event, 'rounds': 0, 'collected': 0, 'owed': 0,
                                    'currency': order.currency or 'mxn', 'drinks': 0})
        row['rounds'] += 1
        if order.status == TableOrder.PAID:
            row['collected'] += order.total_cents
        else:
            row['owed'] += order.total_cents
        if len(rows) > limit:
            break
    drinks = (TableOrderItem.objects.filter(order__event_id__in=list(rows))
              .values('order__event_id').annotate(n=Sum('quantity')))
    for row in drinks:
        if row['order__event_id'] in rows:
            rows[row['order__event_id']]['drinks'] = row['n'] or 0
    # The point of sale's checks (from 2026-09-28), added to the same night. A check's money is collected once
    # it is PAID; an open one is still owed.
    from pos.models import Check, CheckLine

    for cuenta in (Check.objects.exclude(status=Check.CANCELLED).exclude(event__isnull=True)
                   .select_related('event').prefetch_related('lines', 'payments').order_by('-opened_at')[:600]):
        row = rows.setdefault(cuenta.event_id, {'event': cuenta.event, 'rounds': 0, 'collected': 0, 'owed': 0,
                                                'currency': 'mxn', 'drinks': 0})
        row['rounds'] += 1
        row['collected'] += cuenta.paid_cents
        row['owed'] += cuenta.due_cents if cuenta.status == Check.OPEN else 0
        row['drinks'] += sum(l.quantity for l in cuenta.live_lines())
    nights = sorted(rows.values(), key=lambda r: r['event'].date or timezone.now(), reverse=True)[:limit]
    for night in nights:
        night['when'] = night['event'].date.astimezone(CANCUN) if night['event'].date else None
        night['name'] = night['event'].label('en')
        night['collected_money'] = f"{night['collected'] / 100:,.2f} {night['currency'].upper()}"
        night['owed_money'] = f"{night['owed'] / 100:,.2f} {night['currency'].upper()}" if night['owed'] else ''
    return nights


def _room():
    """Everything else worth a glance: the list, and whatever the bar is holding right now."""
    from crm.models import Contact
    from sales.models import TableOrder

    week = timezone.now() - timedelta(days=7)
    from pos.models import Check

    tabs = TableOrder.objects.filter(status=TableOrder.OPEN, created_at__gte=timezone.now() - timedelta(days=2))
    owed = Counter()
    for tab in tabs:
        owed[(tab.currency or 'mxn').upper()] += tab.total_cents
    checks = list(Check.objects.filter(status=Check.OPEN).prefetch_related('lines', 'payments'))
    for cuenta in checks:
        owed['MXN'] += cuenta.due_cents
    return {
        'mailable': Contact.objects.filter(subscribed=True).count(),
        'new_contacts': Contact.objects.filter(created_at__gte=week).count(),
        'open_tabs': tabs.count() + len(checks),
        'owed': ' · '.join(f'{cents / 100:,.2f} {code}' for code, cents in sorted(owed.items())),
    }


@user_passes_test(can_see_the_money, login_url='/admin/login/')
@staff_member_required
def stats(request):
    lang = lang_from_request(request)
    now = timezone.now().astimezone(CANCUN)
    today = now.date()
    fetched = last_fetch()
    windows = [
        _window(today, today, 'today'),
        _window(today - timedelta(days=1), today - timedelta(days=1), 'yesterday'),
        _window(today - timedelta(days=6), today, 'last 7 days'),
    ]
    # Meta's own purchase count for today, shown beside ours rather than instead of it.
    campaigns_today = campaign_rows(today, AdSpend.DAY)
    campaigns_week = campaign_rows(today, AdSpend.WEEK)
    reported = sum(row.reported_purchases for row in AdSpend.objects.filter(day=today, window=AdSpend.DAY))
    ours = windows[0]['free']['bookings'] + windows[0]['paid']['bookings']
    return render(request, 'embed/stats.html', {
        'lang': lang,
        'nights': _upcoming_nights(),
        'funnel_today': _funnel(today, today),
        'funnel_week': _funnel(today - timedelta(days=6), today),
        'mic_to_paid': _open_mic_to_paid(),
        'room': _room(),
        'campaigns_today': campaigns_today,
        'campaigns_week': campaigns_week,
        'saturated_any': any(c['saturated'] for c in campaigns_week),
        'frequency_target': FREQUENCY_TARGET,
        'bar_nights': _bar_nights(),
        'now': now,
        'fetched_ago': timesince(fetched) if fetched else '',
        'windows': windows,
        'platforms': _platforms(today - timedelta(days=6), today),
        'fetched': fetched,
        'stale': (not fetched) or (timezone.now() - fetched) > STALE_AFTER,
        'day_fraction': round(((now.hour * 60 + now.minute) / (24 * 60)) * 100),
        'reported_today': reported,
        'ours_today': ours,
    })
