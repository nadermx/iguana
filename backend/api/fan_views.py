import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import JsonResponse
from django.utils import timezone

from catalog.models import Event
from crm.geo import LOOPBACK, client_ip, remember_locale
from crm.models import Contact
from sales.i18n import locale_from_request, normalize, tr
from sales.models import CreditTransfer, LoginToken, Membership, MembershipPlan, Order, RedeemCode
from sales.demand import demand
from sales.services import (clean_email, current_membership, member_unit_price, stripe_client, stripe_enabled,
                            upsert_contact, wallets_available)

from .auth import api_view, error, fan_contact, fan_required, issue_fan_token
from .public_views import _by_id_or_slug, public_events
from .serializers import event_day, iso, media, membership_json, order_ticket_json, plan_json, remaining


def _allowed_redirect(url):
    parsed = urlparse(url or '')
    origin = f'{parsed.scheme}://{parsed.netloc}'
    return parsed.scheme in ('http', 'https') and origin in settings.SITE_URLS


@api_view()
def config(request):
    return JsonResponse({
        'workspace': {'slug': 'iguana-comedy', 'name': 'Iguana Comedy'},
        'membershipsEnabled': MembershipPlan.objects.filter(active=True).exists(),
        'memberPortalEnabled': True,
        'wallets': wallets_available(),
    })


@api_view(methods=('POST',))
def auth_request(request):
    email = clean_email(request.json.get('email'))
    redirect_url = str(request.json.get('redirectUrl', '')).strip()
    if not email:
        return error('Enter a valid email address')
    if not _allowed_redirect(redirect_url):
        return error('redirectUrl is not an allowed site URL')
    now = timezone.now()
    recent = LoginToken.objects.filter(email=email, created_at__gte=now - timedelta(minutes=10)).count()
    # Per address alone, one connection could mail every address it liked from our domain (41 in 25 minutes on
    # 2026-10-23), so the connection is counted too.
    ip = client_ip(request) or None
    from_ip = LoginToken.objects.filter(ip=ip, created_at__gte=now - timedelta(hours=1)).count() if ip not in LOOPBACK else 0
    if recent >= 5 or from_ip >= 10:
        return error('Too many sign-in emails. Try again in a few minutes.', 429)
    login = LoginToken.objects.create(email=email, code=f'{secrets.randbelow(10**6):06d}', ip=ip)
    link = f'{redirect_url}{"&" if "?" in redirect_url else "?"}{urlencode({"token": login.token})}'
    # The link goes back to /en/... or /es/..., which is the language the person is using the site in.
    lang = normalize(urlparse(redirect_url).path.strip('/').split('/')[0])
    # Worth writing down on a contact we already have. Not worth creating one for: anyone can ask for a sign-in
    # email, and a contact row should mean somebody actually did something.
    remember_locale(Contact.objects.filter(email=email).first(), lang)
    body = '\n\n'.join([
        tr(lang, 'Sign in to Iguana Comedy:'), link, tr(lang, 'Or enter this code: {0}', login.code),
        tr(lang, 'The link and code expire in 30 minutes. If you did not ask for this, ignore this email.'),
        'Iguana Comedy\niguanacomedy.com',
    ])
    send_mail(tr(lang, 'Your Iguana Comedy sign-in code: {0}', login.code), body, settings.DEFAULT_FROM_EMAIL, [email])
    return JsonResponse({'success': True})


@api_view(methods=('POST',))
def auth_verify(request):
    token = str(request.json.get('token', '')).strip()
    code = str(request.json.get('code', '')).strip()
    email = str(request.json.get('email', '')).strip().lower()
    now = timezone.now()
    with transaction.atomic():
        if token:
            login = LoginToken.objects.select_for_update().filter(token=token).first()
        elif code and email:
            # Five tries per code, and asking for a new code every few minutes would otherwise reset the count. Ten
            # wrong guesses across the address's live codes shut the code door until they expire; the link still works.
            pending = LoginToken.objects.filter(email=email, used_at__isnull=True, expires_at__gte=now)
            if (pending.aggregate(n=Sum('attempts'))['n'] or 0) >= 10:
                return error('That sign-in link or code is invalid or has expired.', 401)
            login = LoginToken.objects.select_for_update().filter(email=email, used_at__isnull=True).order_by('-created_at').first()
            if login:
                login.attempts += 1
                login.save(update_fields=['attempts'])
                if login.attempts > 5 or not secrets.compare_digest(login.code, code):
                    login = None
        else:
            return error('Provide the link token, or your email and code')
        # A just-used link may be verified again briefly: React effects and double-clicks send it twice.
        replay_ok = login is not None and login.used_at and (now - login.used_at).total_seconds() < 60
        if login is None or (login.used_at and not replay_ok) or login.expires_at < now:
            return error('That sign-in link or code is invalid or has expired.', 401)
        if not login.used_at:
            login.used_at = now
            login.save(update_fields=['used_at'])
    upsert_contact(login.email, 'SIGN_IN')
    access_token, expires = issue_fan_token(login.email)
    return JsonResponse({'success': True, 'accessToken': access_token, 'expiresAt': iso(expires), 'email': login.email})


def profile_json(contact):
    return {'email': contact.email, 'firstName': contact.first_name or None, 'lastName': contact.last_name or None, 'phone': contact.phone or None}


@api_view(methods=('GET', 'PATCH'))
@fan_required
def account_profile(request):
    contact = request.contact
    if request.method == 'PATCH':
        for key, attr, size in (('firstName', 'first_name', 120), ('lastName', 'last_name', 120), ('phone', 'phone', 40)):
            if key in request.json:
                setattr(contact, attr, str(request.json[key] or '').strip()[:size])
        contact.save()
    return JsonResponse({'profile': profile_json(contact)})


@api_view()
def membership_plans(request):
    lang = locale_from_request(request)
    return JsonResponse({'plans': [plan_json(p, lang) for p in MembershipPlan.objects.filter(active=True)]})


def _pending_received(contact):
    return sum(t.amount_cents for t in CreditTransfer.objects.filter(to_email=contact.email, status='PENDING'))


@api_view()
@fan_required
def membership_status(request):
    contact = request.contact
    memberships = list(contact.memberships.select_related('plan').exclude(status=Membership.PENDING))
    return JsonResponse({
        'signedIn': True,
        'email': contact.email,
        'membershipsEnabled': MembershipPlan.objects.filter(active=True).exists(),
        'memberPortalEnabled': True,
        'pendingReceivedCents': _pending_received(contact),
        'walletCreditBalanceCents': contact.wallet_credit_cents,
        'memberships': [membership_json(m) for m in memberships if m.status in (Membership.ACTIVE, Membership.PAST_DUE) or m.is_current],
        'billing': {
            'hasRecurringSubscription': any(m.stripe_subscription_id and m.status == Membership.ACTIVE for m in memberships),
            'manageInBrowser': True,
        },
    })


@api_view(methods=('POST',))
@fan_required
def redeem_code(request):
    raw = str(request.json.get('code', '')).strip().upper()
    contact = request.contact
    now = timezone.now()
    with transaction.atomic():
        code = RedeemCode.objects.select_for_update().filter(code__iexact=raw).first()
        if code is None or code.uses >= code.max_uses or (code.expires_at and code.expires_at < now):
            return error('That code is invalid or has already been used.', 404)
        code.uses = F('uses') + 1
        code.save(update_fields=['uses'])
        if code.kind == RedeemCode.CREDITS:
            contact.wallet_credit_cents += code.amount_cents or 0
            contact.save()
            return JsonResponse({'kind': 'credits', 'amountCents': code.amount_cents or 0,
                                 'newBalanceCents': contact.wallet_credit_cents, 'currency': code.currency})
        existing = contact.memberships.filter(plan=code.plan, status=Membership.ACTIVE).first()
        days = timedelta(days=code.days or 30)
        if existing and existing.is_current:
            existing.ends_at = (existing.ends_at or now) + days if existing.ends_at else None
            existing.save()
            membership, extended = existing, True
        else:
            membership = Membership.objects.create(contact=contact, plan=code.plan, status=Membership.ACTIVE, source='CODE',
                                                   starts_at=now, ends_at=now + days)
            extended = False
    return JsonResponse({'kind': 'membership', 'extended': extended, 'membership': {
        'id': membership.id, 'planId': membership.plan_id, 'planName': membership.plan.name, 'endsAt': iso(membership.ends_at)}})


@api_view(methods=('POST',))
@fan_required
def credits_transfer(request):
    contact = request.contact
    to_email = str(request.json.get('toEmail', '')).strip().lower()
    try:
        amount = int(request.json.get('amountCents'))
    except (TypeError, ValueError):
        return error('amountCents must be a whole number')
    if amount <= 0 or '@' not in to_email or to_email == contact.email:
        return error('Enter an amount and a different recipient email')
    with transaction.atomic():
        source = None
        membership_id = request.json.get('fromMembershipId')
        if membership_id:
            source = Membership.objects.select_for_update().filter(pk=membership_id, contact=contact).first()
        balance_holder = source or Contact.objects.select_for_update().get(pk=contact.pk)
        balance_attr = 'credit_balance_cents' if source else 'wallet_credit_cents'
        if getattr(balance_holder, balance_attr) < amount:
            return error('Not enough credit for that transfer')
        setattr(balance_holder, balance_attr, getattr(balance_holder, balance_attr) - amount)
        balance_holder.save()
        recipient = Contact.objects.select_for_update().filter(email=to_email).first()
        currency = source.plan.currency if source else 'mxn'
        transfer = CreditTransfer.objects.create(sender=contact, from_membership=source, to_email=to_email, recipient=recipient,
                                                 amount_cents=amount, currency=currency,
                                                 status='COMPLETED' if recipient else 'PENDING',
                                                 claimed_at=timezone.now() if recipient else None)
        if recipient:
            recipient.wallet_credit_cents += amount
            recipient.save()
    return JsonResponse({'transfer': {'id': transfer.id, 'status': transfer.status, 'amountCents': amount,
                                      'currency': currency, 'toEmail': to_email}})


@api_view()
@fan_required
def credits_transfers(request):
    contact = request.contact
    rows = CreditTransfer.objects.filter(Q(sender=contact) | Q(to_email=contact.email)).select_related('sender', 'recipient')
    out = []
    for t in rows:
        sent = t.sender_id == contact.id
        other = (t.recipient if sent else t.sender)
        out.append({
            'id': t.id, 'direction': 'sent' if sent else 'received', 'amountCents': t.amount_cents, 'currency': t.currency,
            'status': t.status, 'counterpartyEmail': t.to_email if sent else t.sender.email,
            'counterpartyName': (f'{other.first_name} {other.last_name}'.strip() or None) if other else None,
            'createdAt': iso(t.created_at), 'claimedAt': iso(t.claimed_at),
        })
    return JsonResponse({'transfers': out})


def _orders_for(contact):
    return (Order.objects.filter(Q(contact=contact) | Q(customer_email=contact.email), status=Order.COMPLETED)
            .select_related('event__venue').prefetch_related('items', 'tickets'))


@api_view()
@fan_required
def tickets(request):
    return JsonResponse({'tickets': [order_ticket_json(o) for o in _orders_for(request.contact)]})


@api_view()
@fan_required
def ticket_detail(request, order_id):
    order = _orders_for(request.contact).filter(pk=order_id).first()
    if order is None:
        return error('Not found', 404)
    return JsonResponse({'ticket': order_ticket_json(order)})


def fan_event_json(event, contact, lang='en'):
    membership = current_membership(contact)
    ticket_url = f'{settings.BACKEND_URL}/embed/event/{event.id}'
    venue = event.venue
    types = []
    for t in event.ticket_types.filter(active=True):
        left = remaining(t)
        types.append({
            'id': t.id, 'name': t.label(lang), 'description': t.details(lang) or None, 'priceCents': t.price_cents,
            'currency': event.currency, 'memberAccess': t.member_access, 'memberPriceCents': t.member_price_cents,
            'yourPriceCents': member_unit_price(t, membership) if membership else None,
            'soldOut': left == 0, 'remaining': left,
            'payAtDoor': t.pay_at_door, 'maxPerOrder': t.max_per_order or 20, 'isAddon': t.is_addon,
        })
    data = {
        'id': event.id, 'slug': event.slug, 'name': event.label(lang), 'date': event_day(event),
        'doorsOpen': event.doors_open or None, 'showTime': event.show_time or None, 'endTime': event.end_time or None,
        'description': event.description or None, 'longDescription': event.long_description or None,
        'imageUrl': media(event.image_url), 'imageUrlMobile': media(event.image_url_mobile),
        'status': event.status, 'ticketingType': event.ticketing_type, 'visibility': event.visibility,
        'venue': venue.name if venue else event.venue_label, 'venueAddress': venue.address or None if venue else None,
        'city': venue.city if venue else '', 'country': venue.country if venue else '',
        'venueTimeZone': venue.time_zone if venue else 'America/Cancun', 'currency': event.currency,
        'language': event.language, 'embedUrl': f'{ticket_url}?embedded=1', 'checkoutUrl': ticket_url,
        'ticketTypes': types, 'isMember': membership is not None, 'demand': demand(event),
    }
    if event.ticketing_type == 'EXTERNAL' and event.external_ticket_url:
        data['externalTicketUrl'] = event.external_ticket_url
    return data


@api_view()
def fan_events(request):
    contact = fan_contact(request)
    qs = public_events().filter(date__gte=timezone.now() - timedelta(days=1)).exclude(visibility='UNLISTED')
    if not current_membership(contact):
        qs = qs.exclude(visibility='MEMBERS')
    rows = []
    for e in qs:
        v = e.venue
        rows.append({'id': e.id, 'name': e.name, 'slug': e.slug, 'date': event_day(e), 'doorsOpen': e.doors_open or None,
                     'showTime': e.show_time or None, 'venue': v.name if v else e.venue_label, 'city': v.city if v else '',
                     'country': v.country if v else '', 'citySlug': v.city.lower().replace(' ', '-') if v else '',
                     'countrySlug': v.country.lower().replace(' ', '-') if v else '', 'status': e.status,
                     'ticketingType': e.ticketing_type, 'url': f'{settings.BACKEND_URL}/embed/event/{e.id}',
                     'imageUrl': media(e.image_url), 'venueAddress': v.address or None if v else None,
                     'venueTimeZone': v.time_zone if v else 'America/Cancun'})
    return JsonResponse({'events': rows})


@api_view()
def fan_event_detail(request, slug):
    event = _by_id_or_slug(public_events(), slug)
    return JsonResponse({'event': fan_event_json(event, fan_contact(request), normalize(request.GET.get('locale')))})


def _stripe_customer(contact):
    client = stripe_client()
    if not contact.stripe_customer_id:
        customer = client.Customer.create(email=contact.email, name=f'{contact.first_name} {contact.last_name}'.strip() or None)
        contact.stripe_customer_id = customer.id
        contact.save(update_fields=['stripe_customer_id', 'updated_at'])
    return contact.stripe_customer_id


def _stripe_product(plan):
    client = stripe_client()
    if not plan.stripe_product_id:
        plan.stripe_product_id = client.Product.create(name=plan.name).id
        plan.save(update_fields=['stripe_product_id'])
    return plan.stripe_product_id


NOT_CONFIGURED = {'clientSecret': '', 'stripeConnectAccountId': None, 'stripePublishableKey': None}


@api_view(methods=('POST',))
@fan_required
def membership_subscribe(request):
    plan = MembershipPlan.objects.filter(pk=request.json.get('planId'), active=True).first()
    interval = request.json.get('interval')
    if plan is None or interval not in ('month', 'year'):
        return error('Unknown plan or interval')
    amount = plan.monthly_cents if interval == 'month' else plan.annual_cents
    if amount is None:
        return error('That billing interval is not offered for this plan')
    if not stripe_enabled():
        return JsonResponse({'mode': 'elements', **NOT_CONFIGURED})
    client = stripe_client()
    subscription = client.Subscription.create(
        customer=_stripe_customer(request.contact),
        items=[{'price_data': {'currency': plan.currency, 'product': _stripe_product(plan), 'unit_amount': amount,
                               'recurring': {'interval': interval}}}],
        payment_behavior='default_incomplete',
        payment_settings={'save_default_payment_method': 'on_subscription'},
        expand=['latest_invoice.confirmation_secret'],
        metadata={'plan_id': plan.id, 'contact_id': request.contact.id, 'interval': interval},
    )
    Membership.objects.create(contact=request.contact, plan=plan, status=Membership.PENDING, source='RECURRING',
                              billing_interval=interval, auto_renew=True, stripe_subscription_id=subscription.id,
                              stripe_customer_id=request.contact.stripe_customer_id)
    secret = subscription.latest_invoice.confirmation_secret.client_secret
    return JsonResponse({'mode': 'elements', 'clientSecret': secret, 'stripeConnectAccountId': None,
                         'stripePublishableKey': settings.STRIPE_PUBLISHABLE_KEY})


@api_view(methods=('POST',))
@fan_required
def membership_oneoff(request):
    plan = MembershipPlan.objects.filter(pk=request.json.get('planId'), active=True).first()
    kind = request.json.get('kind')
    if plan is None or kind not in ('lifetime', 'pass'):
        return error('Unknown plan or kind')
    amount = plan.lifetime_cents if kind == 'lifetime' else plan.pass_cents
    if amount is None:
        return error('That option is not offered for this plan')
    if not stripe_enabled():
        return JsonResponse(NOT_CONFIGURED)
    intent = stripe_client().PaymentIntent.create(
        amount=amount, currency=plan.currency, customer=_stripe_customer(request.contact),
        automatic_payment_methods={'enabled': True},
        metadata={'purpose': 'membership_oneoff', 'plan_id': plan.id, 'contact_id': request.contact.id, 'kind': kind},
    )
    return JsonResponse({'clientSecret': intent.client_secret, 'stripeConnectAccountId': None,
                         'stripePublishableKey': settings.STRIPE_PUBLISHABLE_KEY})


@api_view(methods=('POST',))
@fan_required
def billing_portal(request):
    return_url = str(request.json.get('returnUrl', ''))
    if not _allowed_redirect(return_url):
        return error('returnUrl is not an allowed site URL')
    if not stripe_enabled() or not request.contact.stripe_customer_id:
        return error('Billing is not available for this account', 404)
    session = stripe_client().billing_portal.Session.create(customer=request.contact.stripe_customer_id, return_url=return_url)
    return JsonResponse({'url': session.url})
