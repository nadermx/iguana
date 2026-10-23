import logging
from dataclasses import dataclass, field

import stripe
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.utils import formats, timezone, translation

from api.serializers import remaining
from catalog.models import TicketType
from crm.models import Contact
from sales.ad_reporting import report_purchase
from sales.i18n import normalize, tr
from sales.links import order_url
from sales.sharing import is_open_mic, paid_show_offer, share_url
from sales.models import Membership, Order, OrderItem, Ticket


# Django date formats: "Wednesday 23 September 2026" / "miércoles 23 de septiembre de 2026".
DATE_FORMATS = {'en': 'l j F Y', 'es': r'l j \d\e F \d\e Y'}


log = logging.getLogger(__name__)


class CheckoutError(Exception):
    """A checkout refusal shown to the customer. Keeps the English template and its values so views can translate."""

    def __init__(self, message, *params):
        super().__init__(message.format(*params) if params else message)
        self.message = message
        self.params = params

    def translated(self, lang):
        return tr(lang, self.message, *self.params)


def format_money(cents, currency):
    """5000, 'mxn' -> '50 MXN'; 550, 'usd' -> '5.50 USD'."""
    amount = f'{cents / 100:,.2f}'
    if amount.endswith('.00'):
        amount = amount[:-3]
    return f'{amount} {currency.upper()}'


def stripe_enabled():
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PUBLISHABLE_KEY)


def collects_payment(event):
    """Whether this event's checkout will draw a card form at all.

    The page that hosts the checkout has to reserve its height before it exists, and a form that takes a card
    is roughly three times the height of one that does not. Only the server knows which it will be: it depends
    on having Stripe keys and on the ticket types being paid online rather than at the door.
    """
    if not stripe_enabled():
        return False
    seats = sorted((t for t in event.ticket_types.all() if t.active and not t.is_addon),
                   key=lambda t: (t.sort_order, t.price_cents))
    # Same price, several ways to pay: the checkout preselects the first, so what it will draw is that one's.
    if seats and (len(seats) == 1 or len({t.price_cents for t in seats}) == 1):
        return seats[0].price_cents > 0 and not seats[0].pay_at_door
    return any(t.price_cents > 0 and not t.pay_at_door for t in seats)


def wallets_available():
    """Whether Apple Pay and Google Pay can appear at all.

    They are enabled on the Stripe account and `api.iguanacomedy.com` is a registered payment method domain, so
    from here it comes down to having keys: the Express Checkout Element does the rest, and hides itself on a
    browser with no wallet. This used to be hardcoded `False`, which told the site a wallet was impossible while
    the checkout was perfectly able to take one.
    """
    on = stripe_enabled()
    return {'apple': on, 'google': on}


def stripe_client():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def current_membership(contact):
    if contact is None:
        return None
    for m in contact.memberships.select_related('plan').filter(status=Membership.ACTIVE):
        if m.is_current:
            return m
    return None


def clean_email(value):
    """One address as a string, lowercased, or '' when it is not one. A probe on 2026-10-23 sent a JSON object, a
    list, a comma-separated pair and a CRLF `bcc:` here; `str()` turned the first two into contacts and the rest
    reached send_mail, which refused them with a 500."""
    if not isinstance(value, str):
        return ''
    email = value.strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return ''
    return email if len(email) <= 254 else ''


def upsert_contact(email, source, first_name='', last_name='', phone=''):
    email = email.strip().lower()
    contact, created = Contact.objects.get_or_create(
        email=email, defaults={'source': source, 'first_name': first_name, 'last_name': last_name, 'phone': phone}
    )
    if not created:
        changed = False
        for attr, value in (('first_name', first_name), ('last_name', last_name), ('phone', phone)):
            if value and not getattr(contact, attr):
                setattr(contact, attr, value)
                changed = True
        if changed:
            contact.save()
    return contact


def member_unit_price(ticket_type, membership):
    if membership and ticket_type.member_price_cents is not None:
        return ticket_type.member_price_cents
    return ticket_type.price_cents


@dataclass
class PricedCart:
    lines: list = field(default_factory=list)  # (ticket_type, quantity, unit_price_cents)
    subtotal_cents: int = 0
    discount_cents: int = 0
    free_tickets: int = 0

    @property
    def total_cents(self):
        return max(0, self.subtotal_cents - self.discount_cents)


def price_cart(event, requested, contact, lang='en'):
    """requested: {ticket_type_id: quantity}. Server-side source of truth for every checkout total."""
    membership = current_membership(contact)
    cart = PricedCart()
    types = {t.id: t for t in event.ticket_types.filter(active=True)}
    for type_id, qty in requested.items():
        ticket_type = types.get(type_id)
        if ticket_type is None:
            raise CheckoutError('That ticket type is no longer available.')
        if not isinstance(qty, int) or qty < 0 or qty > 20:
            raise CheckoutError('Choose between 0 and 20 tickets.')
        if qty == 0:
            continue
        limit = ticket_type.max_per_order or 20
        if qty > limit:
            raise CheckoutError('You can book up to {0} {1} per order.', limit, ticket_type.label(lang))
        if ticket_type.member_access == 'MEMBERS_ONLY' and not membership:
            raise CheckoutError('{0} is for members only.', ticket_type.label(lang))
        if ticket_type.member_access == 'NON_MEMBERS' and membership:
            raise CheckoutError('{0} is not available to members.', ticket_type.label(lang))
        left = remaining(ticket_type)
        if left is not None and qty > left:
            raise (CheckoutError('Only {0} {1} tickets left.', left, ticket_type.label(lang)) if left
                   else CheckoutError('{0} is sold out.', ticket_type.label(lang)))
        cart.lines.append((ticket_type, qty, member_unit_price(ticket_type, membership)))
    if not cart.lines:
        raise CheckoutError('Choose at least one ticket.')
    cart.subtotal_cents = sum(qty * unit for _, qty, unit in cart.lines)

    if membership and event.members_eligible:
        plan = membership.plan
        # Free tickets go to the priciest seats first, then the guest discount applies to the rest.
        units = sorted((unit for _, qty, unit in cart.lines for _ in range(qty)), reverse=True)
        free = units[: plan.free_tickets_per_order]
        rest = units[plan.free_tickets_per_order:]
        cart.free_tickets = len(free)
        cart.discount_cents = sum(free) + round(sum(rest) * plan.guest_discount_percent / 100)
    return cart


@transaction.atomic
def create_order(event, cart, *, name, email, phone, contact, attribution=None, locale='en'):
    lang = normalize(locale)
    email = email.strip().lower()
    # Nothing paid up front means nothing stops one person taking the room. Sixty free seats and no limit is an
    # invitation; the same guard already covers pay-at-the-door bookings for exactly this reason.
    if cart.total_cents == 0 and Order.objects.filter(
            event=event, customer_email=email, status=Order.COMPLETED).exists():
        raise CheckoutError('You already have a reservation for this night. Check your email for your seats.')
    first, _, last = name.strip().partition(' ')
    contact = contact or upsert_contact(email, 'ORDER', first, last, phone)
    order = Order.objects.create(
        event=event,
        event_name=event.label(lang),
        contact=contact,
        customer_name=name.strip(),
        customer_email=email,
        customer_phone=phone.strip(),
        currency=event.currency,
        total_amount_cents=cart.total_cents,
        discount_amount_cents=cart.discount_cents,
        attribution=attribution or {},
        locale=lang,
    )
    for ticket_type, qty, unit in cart.lines:
        # Snapshot the name in the customer's language: tickets, the order page and the email all show it.
        OrderItem.objects.create(order=order, ticket_type=ticket_type, name=ticket_type.label(lang), quantity=qty,
                                 unit_price_cents=unit, is_addon=ticket_type.is_addon)
    return order


@transaction.atomic
def reserve_at_door(event, cart, *, name, email, phone, contact, attribution=None, locale='en'):
    lang = normalize(locale)
    """Book pay-at-the-door seats. The order completes now, nothing is charged, and the door collects the total."""
    if not all(ticket_type.pay_at_door for ticket_type, _, _ in cart.lines):
        raise CheckoutError('Reserve pay-at-the-door seats in their own order.')
    # price_cart already checked capacity, but without a lock two people booking at once could both take the last
    # seat. Re-check under a row lock on the ticket types.
    locked = {t.id: t for t in TicketType.objects.select_for_update().filter(pk__in=[t.id for t, _, _ in cart.lines])}
    for ticket_type, qty, _ in cart.lines:
        left = remaining(locked[ticket_type.id])
        if left is not None and qty > left:
            raise (CheckoutError('Only {0} {1} left.', left, ticket_type.label(lang)) if left
                   else CheckoutError('{0} is fully booked.', ticket_type.label(lang)))
    email = email.strip().lower()
    # Nothing is paid up front, so one reservation per email per night stops one person holding every seat.
    if Order.objects.filter(event=event, customer_email=email, status=Order.COMPLETED,
                            items__ticket_type__pay_at_door=True).exists():
        raise CheckoutError('You already have a reservation for this night. Check your email for your seats.')
    order = create_order(event, cart, name=name, email=email, phone=phone, contact=contact, attribution=attribution,
                         locale=lang)
    order.pay_at_door_cents = cart.total_cents
    order.save(update_fields=['pay_at_door_cents'])
    order, _ = complete_order(order)
    return order


@transaction.atomic
def complete_order(order, charge_id=''):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == Order.COMPLETED:
        return order, False
    order.status = Order.COMPLETED
    order.completed_at = timezone.now()
    if charge_id:
        order.stripe_charge_id = charge_id
    order.save()
    # Seats only. A round of drinks ordered ahead is not somebody at the door: issuing a ticket for it gave the
    # customer four QR codes for one person, printed four lines in the confirmation email, and asked the door to
    # scan a beer.
    for item in order.items.exclude(is_addon=True):
        for _ in range(item.quantity):
            Ticket.objects.create(order=order, ticket_type_name=item.name)
    transaction.on_commit(lambda: send_order_confirmation(order))
    transaction.on_commit(lambda: notify_new_reservation(order))
    # Meta only learns an ad sold a seat if we say so: the checkout iframe is on another origin, so no pixel on
    # the marketing pages can see this. Fires after commit, on its own thread, and cannot fail the sale.
    transaction.on_commit(lambda: report_purchase(order))
    return order, True


def notify_new_reservation(order):
    """Tell the club a seat just went. Contact-form enquiries have always alerted hello@; bookings never did,
    so the first two reservations this club ever took online were found by someone querying the database.

    Everything the door needs is in the subject line, because that is all a phone shows.
    """
    if not settings.NOTIFY_EMAILS:
        return 0
    event = order.event
    when = ''
    if event:
        with translation.override('en'):
            when = formats.date_format(timezone.localtime(event.date), 'D j M')
    seats = sum(i.quantity for i in order.items.all() if not (i.ticket_type and i.ticket_type.is_addon))
    extras = [f'{i.quantity} x {i.name}' for i in order.items.all() if i.ticket_type and i.ticket_type.is_addon]
    paid = order.total_amount_cents - order.pay_at_door_cents
    subject = f'{seats} seat{"s" if seats != 1 else ""} reserved for {order.event_name} ({when})'
    if paid:
        subject += f' + {format_money(paid, order.currency)}'
    lines = [
        f'{order.customer_name or "(no name)"} <{order.customer_email}>',
        f'Phone: {order.customer_phone or "-"}',
        '',
        f'Show: {order.event_name}{" on " + when if when else ""}',
        f'Seats: {seats}',
    ]
    if extras:
        lines.append('Also ordered: ' + ', '.join(extras))
    lines += [
        f'Paid online: {format_money(paid, order.currency) if paid else "nothing, the seat is free"}',
        '',
        f'Door check-in and tickets: {order_url(order)}',
        f'Total reserved for this night so far: {_seats_reserved(event)}' if event else '',
    ]
    # fail_silently for the same reason the customer's confirmation is: an alert that cannot be delivered must
    # never undo a booking that already happened.
    return send_mail(subject, '\n'.join(l for l in lines if l is not None),
                     settings.DEFAULT_FROM_EMAIL, settings.NOTIFY_EMAILS, fail_silently=True)


def _seats_reserved(event):
    """How full the night is now, which is the thing the club actually wants to know from an alert."""
    rows = OrderItem.objects.filter(order__event=event, order__status=Order.COMPLETED).select_related('ticket_type')
    return sum(i.quantity for i in rows if not (i.ticket_type and i.ticket_type.is_addon))


def send_order_confirmation(order):
    lang = normalize(order.locale)
    link = order_url(order)
    event = order.event
    when = ''
    if event:
        with translation.override(lang):
            when = formats.date_format(timezone.localtime(event.date), DATE_FORMATS[lang])
    lines = [
        tr(lang, 'Hi {0},', order.customer_name) if order.customer_name else tr(lang, 'Hi there,'),
        '',
        tr(lang, 'You are booked for {0} on {1}.', order.event_name, when) if when
        else tr(lang, 'You are booked for {0}.', order.event_name),
    ]
    if event and event.show_time:
        lines.append(tr(lang, 'Doors {0} · Show {1}', event.doors_open, event.show_time) if event.doors_open
                     else tr(lang, 'Show {0}', event.show_time))
    if event and (event.venue or event.venue_label):
        lines.append(tr(lang, 'Venue: {0}', event.venue.name if event.venue else event.venue_label))
    items = list(order.items.select_related('ticket_type'))
    # What the ticket includes and any house rules (a free drink, arrive by doors) live on the ticket type.
    descriptions = sorted({i.ticket_type.details(lang) for i in items if i.ticket_type and i.ticket_type.details(lang)})
    if descriptions:
        lines += [''] + descriptions
    if order.pay_at_door_cents:
        seats = sum(i.quantity for i in items)
        amount = format_money(order.pay_at_door_cents, order.currency)
        lines += ['', tr(lang, 'Pay {0} at the door for your seat. Nothing was charged online.', amount) if seats == 1
                  else tr(lang, 'Pay {0} at the door for your {1} seats. Nothing was charged online.', amount, seats)]
        lines += ['', tr(lang, 'Your seats (show this at the door): {0}', link)]
        subject = tr(lang, 'Your reservation: {0}', order.event_name)
    else:
        lines += ['', tr(lang, 'Your tickets (show this at the door): {0}', link)]
        subject = tr(lang, 'Your tickets: {0}', order.event_name)
    # The invite. In the email as well as on the order page, because the page is seen once and the email is
    # the thing still in their pocket on the night they are deciding who to bring.
    invite = share_url(order)
    if invite:
        lines += ['', tr(lang, 'Bringing someone? Send them this and they can reserve their own free seat:')
                  if is_open_mic(event) else tr(lang, 'Bringing someone? Send them this and they can get their own ticket:'),
                  invite]
    # The next paid show in the open mic's language, one line (owner, 2026-10-09). Tracked by ref=om-email.
    offer = paid_show_offer(order, 'om-email')
    if offer:
        lines += ['', tr(lang, 'Our next headliner: {0}, {1}.', offer['name'], offer['when'])
                  + (' ' + tr(lang, 'Tickets {0}:', offer['price']) if offer['price'] else ''), offer['url']]
    lines += ['', tr(lang, 'See you there,'), 'Iguana Comedy', 'iguanacomedy.com']
    # fail_silently, because this runs on_commit and therefore inside the request: an address the mail server
    # refuses would otherwise raise SMTPRecipientsRefused straight through a checkout that had ALREADY created
    # and completed the order. The customer would see a 500 and still hold a valid ticket, which is the worst
    # of both. Measured on production the night reservations became free, when the refused address happened to
    # be a probe; the next one would have been a typo in a stranger's email, and free bookings mean many more
    # addresses typed by people with nothing at stake.
    sent = send_mail(subject, '\n'.join(lines), settings.DEFAULT_FROM_EMAIL, [order.customer_email],
                     fail_silently=True)
    if not sent:
        log.warning('order %s completed but its confirmation to %s was not accepted', order.id, order.customer_email)
    return sent
