import logging
from datetime import UTC, datetime, timedelta

import stripe
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from catalog.models import Event
from crm.email_links import remember_click
from crm.geo import LOOPBACK, remember_on_contact, visitor_profile
from crm.models import Contact, TrackedEvent
from crm.optin import confirm as confirm_optin
from crm.optin import email_from_token as email_from_optin_token
from crm.unsubscribe import email_from_token, resume_marketing, stop_marketing
from sales.ad_reporting import report_checkout_engaged, report_payment_info_added
from sales.sharing import is_open_mic, paid_show_offer, share_is_free, share_message, share_url, whatsapp_url
from sales.i18n import lang_from_request, normalize, tr
from sales.links import order_url
from sales.reminders import can_release, release
from sales.models import Membership, MembershipPlan, Order, Ticket
from sales.services import (DATE_FORMATS, CheckoutError, clean_email, collects_payment, complete_order, create_order,
                            current_membership, price_cart, reserve_at_door, stripe_client, stripe_enabled)

from .auth import contact_from_fan_token, error, json_body
from .fan_views import fan_event_json
from .floor import floor_required
from .public_views import _add_to_lists as add_to_lists
from .public_views import _by_id_or_slug, public_events

log = logging.getLogger(__name__)


def tracker_js(request):
    response = render(request, 'embed/k.js', {'backend_url': settings.BACKEND_URL}, content_type='application/javascript')
    response['Cache-Control'] = 'public, max-age=300'
    return response


# Strings the checkout script builds in the browser. The page gets them already translated.
CHECKOUT_JS_STRINGS = ('Sold out', 'pay at the door', 'members only', '{0} left', 'Add one {0}', 'Remove one {0}',
                       'in the last hour', 'in the last few hours', 'in the last day',
                       '{0} people reserved {1}', 'Only {0} seats left of {1}', 'Only {0} seats left for tonight',
                       '{0} of {1} seats reserved',
                       'Over half reserved, worth booking early',
                       'Up to {0} per order', 'Discount',
                       'Reserve 1 seat', 'Reserve {0} seats', 'Pay {0} at the door', 'Free', 'Get 1 ticket',
                       'Get {0} tickets', 'Pay {0}', '1 ticket', '{0} tickets', 'Reserving...', 'Processing...',
                       'Reserve my free spot', 'Reserve {0} free spots', 'Nothing to pay',
                       'Enter your name and email.', 'The total is now {0}. Press the button again to pay it.',
                       'Something went wrong.', 'plus drinks')


@xframe_options_exempt
def event_checkout(request, key):
    event = _by_id_or_slug(public_events(), key)
    lang = normalize(request.GET.get('lang'))
    return render(request, 'embed/checkout.html', {
        'event': event,
        'event_name': event.label(lang),
        'lang': lang,
        'embedded': request.GET.get('embedded') == '1',
        # Lets the card form hold its height from the first paint rather than after the quote round-trip.
        'collects_payment': collects_payment(event),
        # The open mic lander prints the demand line in its own header, above the form rather than below
        # the date pills. Saying it twice on one page reads as a glitch.
        'show_demand': request.GET.get('demand') != '0',
        'bootstrap': {
            'lang': lang,
            'strings': {text: tr(lang, text) for text in CHECKOUT_JS_STRINGS},
            'event': fan_event_json(event, None, lang),
            'apiBase': settings.BACKEND_URL,
            'stripeKey': settings.STRIPE_PUBLISHABLE_KEY if stripe_enabled() else '',
            'devPayments': settings.DEBUG and not stripe_enabled(),
            'siteOrigins': settings.SITE_URLS,
        },
    })


def _body_lang(request):
    body = json_body(request)
    return normalize(body.get('lang')) if isinstance(body, dict) else 'en'


def _cart_payload(request):
    body = json_body(request)
    if body is None:
        raise CheckoutError('Invalid request')
    items = body.get('items') or {}
    if not isinstance(items, dict):
        raise CheckoutError('Invalid ticket selection')
    return body, {str(k): v for k, v in items.items()}, contact_from_fan_token(str(body.get('fanToken') or ''))


@csrf_exempt
def unsubscribe(request, token):
    """The link at the foot of every bulk email. GET shows where the address stands, POST changes it.

    Gmail's one-click button POSTs here without a CSRF token and without a session, so the view is exempt: the
    signed token in the URL is the only thing that proves who is asking, and it only ever names one address.
    """
    email = email_from_token(token)
    lang = lang_from_request(request)
    contact = Contact.objects.filter(email=email).first() if email else None

    if request.method == 'POST' and contact:
        if request.POST.get('action') == 'resubscribe':
            resume_marketing(contact)
        else:
            stop_marketing(contact)

    return render(request, 'embed/unsubscribe.html', {
        'lang': lang,
        'email': email,
        # An address we have never seen counts as unsubscribed: there is nothing to send it either way.
        'subscribed': bool(contact and contact.subscribed),
        'site_url': settings.SITE_URLS[0] if settings.SITE_URLS else settings.BACKEND_URL,
    })


@csrf_exempt
@require_POST
def checkout_quote(request, event_id):
    event = get_object_or_404(public_events(), pk=event_id)
    lang = _body_lang(request)
    try:
        _, items, contact = _cart_payload(request)
        cart = price_cart(event, items, contact, lang)
    except CheckoutError as exc:
        return error(exc.translated(lang))
    return JsonResponse({'subtotalCents': cart.subtotal_cents, 'discountCents': cart.discount_cents,
                         'freeTickets': cart.free_tickets, 'totalCents': cart.total_cents, 'currency': event.currency,
                         'isMember': current_membership(contact) is not None,
                         'payAtDoor': any(ticket_type.pay_at_door for ticket_type, _, _ in cart.lines)})


@csrf_exempt
@require_POST
def checkout_engaged(request, event_id):
    """Fired once when somebody starts filling the checkout in, from the widget itself.

    This is the mid-funnel event the reservation ad sets optimise on, so it has to mean what Meta means by it:
    entering a checkout, not completing one. It was previously reported at submit time, which made it nearly as
    rare as a purchase and left the campaigns with nothing to learn from.

    Answers 204 whatever happens. It is a beacon on the path to a sale and must never be able to interrupt one.
    """
    event = public_events().filter(pk=event_id).first()
    if event is None:
        return HttpResponse(status=204)
    body = json_body(request) or {}
    lang = normalize(body.get('lang'))
    # Kept here as well as sent to Meta, so /revenue can show what happened after the click. Meta reports a cost
    # per reservation and nothing about the step before it, which is where a funnel is actually lost.
    try:
        TrackedEvent.objects.create(kind='checkout', name='checkout_engaged',
                                    visitor_key=str(body.get('key', ''))[:100],
                                    url=str((body.get('attribution') or {}).get('pageUrl', ''))[:1000],
                                    properties={'event': event.id, 'lang': lang})
    except Exception:
        pass
    attribution = body.get('attribution') if isinstance(body.get('attribution'), dict) else {}
    client = body.get('client') if isinstance(body.get('client'), dict) else {}
    try:
        report_checkout_engaged(
            event=event,
            attribution={k: str(v)[:200] for k, v in attribution.items() if k != 'visitor'},
            visitor=visitor_profile(request, locale=lang, browser_language=client.get('browserLanguage', ''),
                                    time_zone=client.get('timeZone', '')),
            user_agent=request.headers.get('User-Agent', '')[:500],
            value_cents=int(body.get('valueCents') or 0),
            currency=event.currency,
            # The widget sends one key per mounted checkout, so a person who types, deletes and types again is
            # one InitiateCheckout rather than three.
            key=str(body.get('key') or '')[:60] or event.id,
        )
    except Exception:  # noqa: BLE001
        log.warning('could not report checkout engagement for %s', event_id, exc_info=True)
    return HttpResponse(status=204)


@csrf_exempt
@require_POST
def checkout_start(request, event_id):
    event = get_object_or_404(public_events(), pk=event_id)
    lang = _body_lang(request)
    if event.ticketing_type != 'INTERNAL' or event.status in (Event.CANCELLED, Event.POSTPONED, Event.SOLD_OUT):
        return error(tr(lang, 'Tickets are not on sale for this show.'))
    try:
        body, items, contact = _cart_payload(request)
        name, phone = (body.get(k).strip() if isinstance(body.get(k), str) else '' for k in ('name', 'phone'))
        email = clean_email(body.get('email'))
        if not name or not email:
            raise CheckoutError('Enter your name and email.')
        if contact and contact.email != email.lower():
            contact = None  # member pricing only applies to the signed-in member's own email
        cart = price_cart(event, items, contact, lang)
    except CheckoutError as exc:
        return error(exc.translated(lang))

    attribution = body.get('attribution') if isinstance(body.get('attribution'), dict) else {}
    attribution = {k: str(v)[:200] for k, v in attribution.items() if k != 'visitor'}
    client = body.get('client') if isinstance(body.get('client'), dict) else {}
    attribution['visitor'] = visitor_profile(request, locale=lang, browser_language=client.get('browserLanguage', ''),
                                             time_zone=client.get('timeZone', ''))
    # Meta matches a server-side conversion on the browser that made it. The fan is in this iframe, so the header
    # is theirs; `_fbp` and `_fbc` belong to the site origin and arrive in attribution from k.js.
    attribution['userAgent'] = request.headers.get('User-Agent', '')[:500]

    # One email per night stops one person taking a free room, but not one connection with a box of throwaway
    # addresses: a probe on 2026-10-23 held 39 seats across 23 nights, 8 of them on the next Tuesday. A group books
    # several seats in one order, so a handful of free bookings per connection is plenty.
    ip = attribution['visitor'].get('ip')
    if ip and ip not in LOOPBACK and (cart.total_cents == 0 or any(t.pay_at_door for t, _, _ in cart.lines)):
        free = Order.objects.filter(status=Order.COMPLETED, stripe_payment_intent_id='', attribution__visitor__ip=ip)
        if (free.filter(event=event).count() >= 4
                or free.filter(created_at__gte=timezone.now() - timedelta(days=1)).count() >= 12):
            return error(tr(lang, 'Too many reservations from this connection. Write to hello@iguanacomedy.com and we will hold your seats.'))

    if any(ticket_type.pay_at_door for ticket_type, _, _ in cart.lines):
        try:
            order = reserve_at_door(event, cart, name=name, email=email, phone=phone, contact=contact,
                                    attribution=attribution, locale=lang)
        except CheckoutError as exc:
            return error(exc.translated(lang))
        remember_on_contact(order.contact, attribution['visitor'])
        return JsonResponse({'orderId': order.id, 'complete': True,
                             'successUrl': order_url(order)})

    try:
        order = create_order(event, cart, name=name, email=email, phone=phone, contact=contact,
                             attribution=attribution, locale=lang)
    except CheckoutError as exc:
        # create_order refuses a second free reservation for the same email. Before this was caught the refusal
        # reached the customer as a 500 with no message at all.
        return error(exc.translated(lang))
    remember_on_contact(order.contact, attribution['visitor'])
    report_payment_info_added(order)
    success_url = order_url(order)

    if cart.total_cents == 0:
        complete_order(order)
        return JsonResponse({'orderId': order.id, 'complete': True, 'successUrl': success_url})
    if not stripe_enabled():
        if settings.DEBUG:
            return JsonResponse({'orderId': order.id, 'complete': False, 'devPayment': True, 'successUrl': success_url,
                                 'totalCents': cart.total_cents})
        return error(tr(lang, 'Online payment is not available yet. Please contact us to book.'))

    intent = stripe_client().PaymentIntent.create(
        amount=cart.total_cents, currency=event.currency, receipt_email=order.customer_email,
        # Card only (Apple Pay and Google Pay are cards too). Automatic methods switched on Stripe Link, whose
        # "save my info" box doubled the height of the form on a phone (owner, 2026-09-28: remove it). Must match
        # `paymentMethodTypes` in checkout.html or confirmation is refused.
        payment_method_types=['card'],
        metadata={'purpose': 'tickets', 'order_id': order.id, 'event_id': event.id},
        description=f'{event.name} tickets',
    )
    order.stripe_payment_intent_id = intent.id
    order.save(update_fields=['stripe_payment_intent_id'])
    return JsonResponse({'orderId': order.id, 'complete': False, 'clientSecret': intent.client_secret,
                         'successUrl': success_url, 'totalCents': cart.total_cents})


@csrf_exempt
@require_POST
def checkout_confirm(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    lang = _body_lang(request)
    if order.status != Order.COMPLETED:
        if order.stripe_payment_intent_id:
            intent = stripe_client().PaymentIntent.retrieve(order.stripe_payment_intent_id)
            if intent.status != 'succeeded':
                return error(tr(lang, 'Payment has not completed yet.'), 409)
            complete_order(order, intent.latest_charge or '')
        elif settings.DEBUG and not stripe_enabled():
            complete_order(order)  # local development: no Stripe keys, simulate a successful payment
        else:
            return error(tr(lang, 'Payment has not completed yet.'), 409)
    return JsonResponse({'ok': True, 'successUrl': order_url(order)})


def order_page(request, token):
    order = get_object_or_404(Order.objects.select_related('event__venue').prefetch_related('items', 'tickets'),
                              public_view_token=token)
    lang = normalize(order.locale)
    site = settings.SITE_URLS[0] if settings.SITE_URLS else ''
    # Unprefixed, the same link the table codes carry, so it works for whichever language they read it in.
    menu_url = f'{site}/menu/' if site and is_open_mic(order.event) else ''
    return render(request, 'embed/order.html', {
        'order': order, 'lang': lang, 'date_format': DATE_FORMATS[lang], 'menu_url': menu_url,
        'status_label': tr(lang, order.get_status_display().lower()),
        'site_url': settings.SITE_URLS[0] if settings.SITE_URLS else '',
        # Somebody who has just reserved is about to tell a friend anyway; this is the moment to make it one tap.
        'share_url': share_url(order),
        'share_is_free': share_is_free(order),
        'whatsapp_url': whatsapp_url(order),
        'share_message': share_message(order),
        # An open mic booker is offered the next paid show in that night's language (owner, 2026-10-09).
        'paid_show': paid_show_offer(order, 'om-thanks') if order.status == Order.COMPLETED else None,
    })


@csrf_exempt
def release_seat(request, token):
    """The link in the open mic reminder. GET asks, POST gives the seat back. The token in the URL is the proof,
    the same one the order page uses, so a forwarded reminder can release the seat it names and nothing else.
    CSRF-exempt for the same reason as the unsubscribe page: it is reached from an email with no session."""
    order = get_object_or_404(Order.objects.select_related('event__venue'), public_view_token=token)
    lang = normalize(order.locale)
    state = None
    if request.method == 'POST':
        state = release(order.id)
        order.refresh_from_db()
    elif order.released_at:
        state = 'already'
    elif not can_release(order):
        state = 'refused'
    seats = sum(i.quantity for i in order.items.all() if not i.is_addon)
    return render(request, 'embed/release.html', {
        'order': order, 'lang': lang, 'state': state, 'seats': seats, 'order_url': order_url(order),
        'site_url': settings.SITE_URLS[0] if settings.SITE_URLS else '',
    })


@floor_required
def checkin(request, token):
    ticket = get_object_or_404(Ticket.objects.select_related('order__event'), checkin_token=token)
    just_checked_in = False
    if request.method == 'POST' and ticket.checked_in_at is None and ticket.order.status == Order.COMPLETED:
        ticket.checked_in_at = timezone.now()
        ticket.save(update_fields=['checked_in_at'])
        just_checked_in = True
    lang = lang_from_request(request)
    return render(request, 'embed/checkin.html', {
        'ticket': ticket, 'just_checked_in': just_checked_in, 'lang': lang,
        'status_label': tr(lang, ticket.order.get_status_display().lower()),
    })


@csrf_exempt
@require_POST
def stripe_webhook(request):
    try:
        event = stripe.Webhook.construct_event(request.body, request.headers.get('Stripe-Signature', ''),
                                               settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponse(status=400)
    # 🚨 `.to_dict()`, not the object. stripe-python stopped being a dict subclass, so `obj.get(...)` raises
    # `AttributeError: 'get' is a dict method, but a PaymentIntent is not a dict` and the whole handler 500s.
    # Every payment_intent.succeeded failed this way. It is a silent class of failure because the browser
    # normally confirms the order itself: the webhook is the backstop for when it does not come back, which is
    # exactly the case where nobody is watching, so a paid order sits PENDING with no ticket and no complaint.
    raw = event['data']['object']
    obj = raw.to_dict() if hasattr(raw, 'to_dict') else dict(raw)
    kind = event['type']

    if kind == 'payment_intent.succeeded':
        meta = obj.get('metadata') or {}
        if meta.get('purpose') == 'tickets':
            order = Order.objects.filter(pk=meta.get('order_id')).first()
            if order:
                complete_order(order, obj.get('latest_charge') or '')
        elif meta.get('purpose') == 'pos':
            from pos.models import Payment as PosPayment
            from pos.views_pay import settle as settle_pos

            payment = PosPayment.objects.filter(pk=meta.get('payment_id')).first()
            if payment:
                settle_pos(payment, obj.get('latest_charge') or '')
        elif meta.get('purpose') == 'table':
            # 🚨 The backstop that matters most here. A table pays, the phone loses signal on the way out of a
            # basement room, and the browser never gets to confirm: without this the card is charged and the
            # board still shows the table owing, so somebody gets chased for money they already paid.
            from sales.models import TablePayment
            from .pay_views import settle
            payment = TablePayment.objects.filter(pk=meta.get('payment_id')).first()
            if payment:
                settle(payment, obj.get('latest_charge') or '')
        elif meta.get('purpose') == 'membership_oneoff':
            plan = MembershipPlan.objects.filter(pk=meta.get('plan_id')).first()
            contact_id = meta.get('contact_id')
            if plan and contact_id and not Membership.objects.filter(notes=f'pi:{obj["id"]}').exists():
                now = timezone.now()
                ends = None if meta.get('kind') == 'lifetime' else now + timedelta(days=plan.pass_days or 1)
                Membership.objects.create(contact_id=contact_id, plan=plan, status=Membership.ACTIVE,
                                          source=meta.get('kind', '').upper(), starts_at=now, ends_at=ends,
                                          notes=f'pi:{obj["id"]}')

    elif kind in ('customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted'):
        membership = Membership.objects.filter(stripe_subscription_id=obj['id']).first()
        if membership:
            status = obj.get('status')
            membership.status = {
                'active': Membership.ACTIVE, 'trialing': Membership.ACTIVE, 'past_due': Membership.PAST_DUE,
                'canceled': Membership.CANCELED, 'unpaid': Membership.PAST_DUE,
                'incomplete': Membership.PENDING, 'incomplete_expired': Membership.EXPIRED,
            }.get(status, membership.status)
            items = (obj.get('items') or {}).get('data') or []
            period_end = obj.get('current_period_end') or (items[0].get('current_period_end') if items else None)
            if period_end:
                membership.ends_at = datetime.fromtimestamp(period_end, tz=UTC)
            membership.auto_renew = not obj.get('cancel_at_period_end') and status != 'canceled'
            membership.save()

    return HttpResponse(status=200)


@csrf_exempt
def ingest(request, kind):
    if request.method != 'POST':
        return HttpResponse(status=405)
    body = json_body(request) or {}
    if str(body.get('token', '')) not in settings.PUBLIC_API_KEYS:
        return HttpResponse(status=204)
    url, visitor_key = str(body.get('url', ''))[:1000], str(body.get('visitorKey', ''))[:100]
    TrackedEvent.objects.create(
        kind=kind[:40],
        name=str(body.get('name', ''))[:80],
        visitor_key=visitor_key,
        url=url,
        referrer=str(body.get('referrer', ''))[:1000],
        properties={k: body[k] for k in ('utm', 'props', 'email', 'traits') if body.get(k)},
    )
    # A click out of the weekly email says which of its two language blocks this person reads. It is the only
    # signal we get from the imported list, most of which has no language on it at all.
    try:
        remember_click(url, visitor_key)
    except Exception:  # noqa: BLE001 - tracking must stay a 204 whatever happens
        log.warning('could not record the language of a click on %s', url[:120], exc_info=True)
    return HttpResponse(status=204)


def newsletter_confirm(request, token):
    """The link in the confirmation email. Clicking it is the only way onto the mailing list.

    Deliberately a GET with no form: a person clicking a link in their own inbox is the proof we wanted, and
    asking them to press a second button loses the ones who assume the click was enough.
    """
    email = email_from_optin_token(token)
    lang = lang_from_request(request)
    contact = Contact.objects.filter(email=email).first() if email else None
    if contact is not None:
        confirm_optin(contact)
        pending = (contact.custom_data or {}).get('pending_lists') or ['Newsletter']
        add_to_lists(contact, names=pending)
    return render(request, 'embed/newsletter_confirmed.html', {
        'lang': lang,
        'email': email or '',
        'confirmed': contact is not None,
        'site_url': settings.SITE_URLS[0] if settings.SITE_URLS else settings.BACKEND_URL,
    })
