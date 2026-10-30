"""JSON shapes matching @kintana/sdk types, so the Astro site works unchanged."""
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from catalog.models import Event
from sales.models import MembershipPlan, Order, OrderItem
from sales.links import checkin_url, order_url

CANCUN = ZoneInfo('America/Cancun')


def media(value):
    """Image fields hold absolute URLs or `/media/...` paths.

    A relative path is made absolute against the SITE, not the API host: nginx serves the uploads tree under
    iguanacomedy.com as well, so a poster is same-origin with the page showing it. It was on api.iguanacomedy.com
    before, which put a DNS lookup and a TLS handshake in front of the largest image on every show page.
    """
    if not value:
        return None
    if not value.startswith('/'):
        return value
    base = settings.SITE_URLS[0] if settings.SITE_URLS else settings.BACKEND_URL
    return f'{base}{value}'



def iso(dt):
    if dt is None:
        return None
    return dt.astimezone(ZoneInfo('UTC')).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def event_day(event):
    """Date-only string: the site formats `YYYY-MM-DD` without timezone drift."""
    return event.date.astimezone(ZoneInfo(event.venue.time_zone if event.venue else 'America/Cancun')).date().isoformat()


def today_local():
    return timezone.now().astimezone(CANCUN).date()


def venue_json(venue, listed=False):
    if venue is None:
        return None
    data = {
        'id': venue.id,
        'slug': venue.slug,
        'name': venue.name,
        'city': venue.city or None,
        'country': venue.country or None,
        'address': venue.address or None,
        'description': venue.description or None,
        'lat': venue.lat,
        'lng': venue.lng,
        'timeZone': venue.time_zone,
        'wheelchairAccessible': venue.wheelchair_accessible,
    }
    if listed:
        data.update(capacity=venue.capacity, imageUrl=media(venue.image_url))
    return data


def artist_json(artist, locale='en'):
    bio = artist.bio_es if locale == 'es' and artist.bio_es else artist.bio
    return {
        'id': artist.id,
        'slug': artist.slug,
        'name': artist.name,
        'bio': bio or None,
        'imageUrl': media(artist.image_url),
        'website': artist.website or None,
        'stageName': artist.stage_name or None,
        'homeCity': artist.home_city or None,
        'residency': artist.residency or None,
        'socials': artist.socials or {},
        'reels': artist.reels or [],
    }


def sold_quantity(ticket_type):
    return (
        OrderItem.objects.filter(ticket_type=ticket_type, order__status=Order.COMPLETED).aggregate(n=Sum('quantity'))['n'] or 0
    )


def remaining(ticket_type):
    """Seats this checkout may still sell.

    `sold_elsewhere` is subtracted because a guest promoter selling the same night on their own site is selling
    the same eighty chairs. Without it our checkout happily sells the room twice and the second person to
    arrive is turned away at the door having paid.
    """
    if ticket_type.capacity is None:
        return None
    return max(0, ticket_type.capacity - sold_quantity(ticket_type) - (ticket_type.sold_elsewhere or 0))


def listing_status(event, ticket_types=None):
    if event.status == Event.CANCELLED:
        return 'cancelled'
    if event.status == Event.POSTPONED:
        return 'postponed'
    if event.date.astimezone(CANCUN).date() < today_local():
        return 'past'
    if event.status == Event.SOLD_OUT:
        return 'sold-out'
    types = ticket_types if ticket_types is not None else [t for t in event.ticket_types.all() if t.active]
    if event.ticketing_type == 'INTERNAL' and types and all(remaining(t) == 0 for t in types):
        return 'sold-out'
    return 'on-sale'


def lineup_entry_json(entry, lang='en'):
    """A name and a face for the list, plus enough for a show page to introduce its headliner.

    The bio and the clip ride along because an event page selling a named act has to be about that act: the
    poster says who is on and nothing on the page said a word about them. Everyone on the bill carries them,
    not just the headliner, so a two-hander does not have to be a special case.
    """
    artist = entry.artist
    reels = [{'title': r.get('title', ''), 'url': media(r.get('url')), 'posterUrl': media(r.get('posterUrl'))}
             for r in (artist.reels or []) if r.get('url')]
    return {
        'id': artist.id,
        'slug': artist.slug,
        'name': artist.stage_name or artist.name,
        'role': entry.role or None,
        'sortOrder': entry.sort_order,
        'imageUrl': media(artist.image_url),
        'headliner': entry.headliner,
        'bio': (artist.bio_es if lang == 'es' and artist.bio_es else artist.bio) or '',
        'reels': reels,
    }


def active_plan():
    return MembershipPlan.objects.filter(active=True).first()


def event_urls(event):
    embed = f'{settings.BACKEND_URL}/embed/event/{event.id}'
    if event.ticketing_type == 'EXTERNAL' and event.external_ticket_url:
        return event.external_ticket_url, embed
    return embed, f'{embed}?embedded=1'


def _wallets():
    # Imported here, not at module level: sales.services imports this module back.
    from sales.services import wallets_available

    return wallets_available()


def _collects_payment(event):
    from sales.services import collects_payment

    return collects_payment(event)


def _demand(event):
    # Imported here: sales imports catalog, so a module-level import the other way is a cycle.
    from sales.demand import demand

    return demand(event)


def past_summary(event, status, room):
    """What happened, for a show that is over: whether it sold out and how many seats went.

    None while the show is still to come. `soldOut` trusts the owner's mark as well as the count, because a guest
    promoter can sell a block we never see; `seats` is only what we can count, so it is never inflated to match.
    """
    if status != 'past':
        return None
    if room is not None:
        seats, capacity = room['taken'], room['capacity']
    else:
        from sales.models import Order, OrderItem

        seats = sum(OrderItem.objects.filter(order__event=event, order__status=Order.COMPLETED)
                    .exclude(ticket_type__is_addon=True).values_list('quantity', flat=True))
        seats += sum(t.sold_elsewhere or 0 for t in event.ticket_types.all())
        capacity = None
    return {
        'soldOut': event.status == Event.SOLD_OUT or bool(capacity and seats >= capacity),
        'seats': seats,
        'capacity': capacity,
    }


def gallery_json(event, lang='en'):
    """The event page's photos, alt text in the reader's language. `section` says whether a photo goes above
    the description or below it; anything else counts as above."""
    out = []
    for item in event.gallery or []:
        if not isinstance(item, dict) or not item.get('url'):
            continue
        alt = (item.get('alt_es') if lang == 'es' else None) or item.get('alt') or ''
        out.append({'url': media(item['url']), 'alt': alt,
                    'section': 'after' if item.get('section') == 'after' else 'before',
                    'width': item.get('width'), 'height': item.get('height')})
    return out


def event_json(event, plan=None, lang='en', demand=None):
    """`demand` is passed in by listing views, which compute it for the whole page at once; a single event
    works it out for itself."""
    types = [t for t in event.ticket_types.all() if t.active]
    lineup = list(event.lineup.all())
    headliner = next((e for e in lineup if e.headliner), None)
    ticket_url, embed_url = event_urls(event)
    venue = venue_json(event.venue)
    if venue is None and event.venue_label:
        venue = {'id': None, 'slug': None, 'name': event.venue_label, 'city': None, 'country': None, 'address': None,
                 'description': None, 'lat': None, 'lng': None, 'timeZone': 'America/Cancun', 'wheelchairAccessible': None}
    room = demand if demand is not None else _demand(event)
    status = listing_status(event, types)
    data = {
        'id': event.id,
        'slug': event.slug,
        'name': event.label(lang),
        'date': event_day(event),
        'city': event.venue.city if event.venue and event.venue.city else None,
        'country': event.venue.country if event.venue and event.venue.country else None,
        'imageUrl': media(event.poster(lang)),
        'imageUrlMobile': media(event.poster_mobile(lang)),
        'ticketUrl': ticket_url,
        'embedUrl': embed_url,
        'demand': room,
        'doorsOpen': event.doors_open or None,
        'showTime': event.show_time or None,
        'endTime': event.end_time or None,
        'description': event.details(lang) or None,
        'longDescription': event.long_details(lang) or None,
        'status': status,
        'past': past_summary(event, status, room),
        'language': event.language or 'en',
        'venue': venue,
        'tour': {'id': event.tour.id, 'slug': event.tour.slug, 'name': event.tour.name, 'imageUrl': media(event.tour.image_url)} if event.tour else None,
        'lineup': [lineup_entry_json(e, lang) for e in lineup],
        'headliner': lineup_entry_json(headliner, lang) if headliner else None,
        'ticketingType': event.ticketing_type,
        # The site reserves the checkout's height before the iframe exists, and a card form is three times the
        # height of a name-and-email one. Without this it has to guess, and a wrong guess is the jump itself.
        'collectsPayment': _collects_payment(event),
        # Whether a seat can be reserved without a card (pay at the door). The paid-show ad preflight insists on it.
        'payAtDoor': any(t.pay_at_door and not t.is_addon for t in types),
        'ticketTypeCount': len(types),
        'ageRestriction': event.age_restriction or None,
        'priceFrom': min((t.price_cents for t in types), default=None),
        'priceCurrency': event.currency.upper() if types else None,
        'tags': event.tags or [],
        'reviews': event.reviews or [],
        'gallery': gallery_json(event, lang),
        'isShared': False,
        'hostWorkspace': {'slug': 'iguana-comedy', 'name': 'Iguana Comedy'},
        'promoter': None,
    }
    if plan and event.members_eligible:
        data['goldMembership'] = {'status': 'eligible', 'planName': plan.name, 'freeTickets': plan.free_tickets_per_order}
    return data


def plan_json(plan, lang='en'):
    prices = {}
    if plan.monthly_cents is not None:
        prices['monthly'] = {'amountCents': plan.monthly_cents}
    if plan.annual_cents is not None:
        prices['annual'] = {'amountCents': plan.annual_cents}
    if plan.lifetime_cents is not None:
        prices['lifetime'] = {'amountCents': plan.lifetime_cents}
    if plan.pass_cents is not None and plan.pass_days:
        prices['pass'] = {'amountCents': plan.pass_cents, 'durationDays': plan.pass_days}
    primary = plan.monthly_cents if plan.monthly_cents is not None else (plan.annual_cents or plan.lifetime_cents or plan.pass_cents or 0)
    return {
        'id': plan.id,
        'name': plan.label(lang),
        'description': plan.details(lang) or None,
        'benefits': [{'label': b, 'sortOrder': i} for i, b in enumerate(plan.perks(lang))],
        'currency': plan.currency,
        'prices': prices,
        'priceCents': primary,
        'billingInterval': 'month' if plan.monthly_cents is not None else ('year' if plan.annual_cents is not None else 'one_time'),
        'durationDays': plan.pass_days,
    }


def membership_json(m):
    return {
        'id': m.id,
        'status': m.status,
        'startsAt': iso(m.starts_at),
        'endsAt': iso(m.ends_at),
        'creditBalanceCents': m.credit_balance_cents,
        'plan': {
            'id': m.plan.id,
            'name': m.plan.name,
            'billingInterval': m.billing_interval or 'month',
            'priceCents': (m.plan.annual_cents if m.billing_interval == 'year' else m.plan.monthly_cents) or 0,
            'currency': m.plan.currency,
        },
        'stripeSubscriptionId': m.stripe_subscription_id or None,
    }


def order_ticket_json(order):
    event = order.event
    tz = event.venue.time_zone if event and event.venue else 'America/Cancun'
    return {
        'id': order.id,
        'totalAmount': order.total_amount_cents,
        'currency': order.currency,
        'completedAt': iso(order.completed_at),
        'event': {
            'id': event.id if event else '',
            'name': event.name if event else order.event_name,
            'slug': event.slug if event else '',
            'date': event_day(event) if event else '',
            'doorsOpen': event.doors_open or None if event else None,
            'showTime': event.show_time or None if event else None,
            'venue': (event.venue.name if event.venue else event.venue_label) if event else '',
            'venueAddress': (event.venue.address or None) if event and event.venue else None,
            'venueTimeZone': tz,
            'currency': order.currency,
        },
        'orderItems': [{'name': i.name, 'quantity': i.quantity, 'unitPrice': i.unit_price_cents} for i in order.items.all()],
        'tickets': [
            {
                'id': t.id,
                'ticketTypeName': t.ticket_type_name,
                'checkinUrl': checkin_url(t),
                'checkedInAt': iso(t.checked_in_at),
            }
            for t in order.tickets.all()
        ],
        'ticketsPageUrl': order_url(order),
        'publicViewToken': order.public_view_token,
        'wallets': _wallets(),
    }
