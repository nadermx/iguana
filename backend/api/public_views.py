import logging
import re
from datetime import date

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Prefetch, Q
from django.http import Http404, JsonResponse

from catalog.spam import rejection_reason
from crm.optin import send_confirmation
from crm.geo import remember_on_contact, visitor_profile
from sales.links import public_base
from sales.demand import demand_for
from sales.i18n import normalize
from crm.models import Contact, ContactList, ContactListMember
from catalog import videos as site_videos
from catalog.models import (Artist, Event, FormEndpoint, FormSubmission, LineupEntry, SiteFile, SiteVideo, StoreCollection,
                            StoreProduct, Venue)
from sales.services import upsert_contact

from .auth import api_view, error
from .serializers import active_plan, artist_json, event_json, media, today_local, venue_json


def _limit(request, default, cap=200):
    try:
        return max(1, min(cap, int(request.GET.get('limit', default))))
    except ValueError:
        return default


def _parse_day(value):
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def public_events():
    return (
        Event.objects.exclude(status=Event.DRAFT)
        .select_related('venue', 'tour')
        .prefetch_related('ticket_types', Prefetch('lineup', queryset=LineupEntry.objects.select_related('artist')))
    )


def _by_id_or_slug(queryset, key):
    obj = queryset.filter(Q(slug=key) | Q(pk=key)).first()
    if obj is None:
        raise Http404
    return obj


@api_view()
def events(request):
    qs = public_events().exclude(visibility='UNLISTED')
    if request.GET.get('tourId'):
        qs = qs.filter(tour_id=request.GET['tourId'])
    if request.GET.get('artistSlug'):
        qs = qs.filter(lineup__artist__slug=request.GET['artistSlug'])
    if request.GET.get('venueSlug'):
        qs = qs.filter(venue__slug=request.GET['venueSlug'])
    today = today_local()
    start, end = _parse_day(request.GET.get('from')), _parse_day(request.GET.get('to'))
    if start:
        qs = qs.filter(date__date__gte=start)
    if end:
        qs = qs.filter(date__date__lte=end)
    status = request.GET.get('status', '')
    if status == 'past':
        qs = qs.filter(date__date__lt=today).order_by('-date')
    elif status == 'cancelled':
        qs = qs.filter(status=Event.CANCELLED)
    elif status == 'postponed':
        qs = qs.filter(status=Event.POSTPONED)
    elif status in ('on-sale', 'sold-out'):
        qs = qs.filter(date__date__gte=today).exclude(status__in=[Event.CANCELLED, Event.POSTPONED])
    plan = active_plan()
    rows_qs = list(qs.distinct())
    # One pass for the page, rather than two queries per row.
    pressure = demand_for(rows_qs)
    lang = normalize(request.GET.get('locale'))
    rows = [event_json(e, plan, lang, demand=pressure.get(e.id)) for e in rows_qs]
    if status in ('on-sale', 'sold-out'):
        rows = [r for r in rows if r['status'] == status]
    return JsonResponse({'events': rows[: _limit(request, 24)]})


@api_view()
def event_detail(request, key):
    return JsonResponse({'event': event_json(_by_id_or_slug(public_events(), key), active_plan(),
                                             normalize(request.GET.get('locale')))})


def _upcoming_for(lang='en', **filters):
    today = today_local()
    plan = active_plan()
    qs = public_events().exclude(visibility='UNLISTED').filter(date__date__gte=today, **filters).exclude(status=Event.CANCELLED)
    rows_qs = list(qs.distinct())
    pressure = demand_for(rows_qs)
    return [event_json(e, plan, lang, demand=pressure.get(e.id)) for e in rows_qs]


@api_view()
def artists(request):
    locale = request.GET.get('locale', 'en')
    qs = Artist.objects.filter(listed=True)[: _limit(request, 50)]
    return JsonResponse({'artists': [artist_json(a, locale) for a in qs]})


@api_view()
def artist_detail(request, key):
    artist = _by_id_or_slug(Artist.objects.all(), key)
    data = artist_json(artist, request.GET.get('locale', 'en'))
    data['upcomingEvents'] = _upcoming_for(normalize(request.GET.get('locale')), lineup__artist=artist)
    return JsonResponse({'artist': data})


@api_view()
def videos(request):
    """The videos the owner ticked "Show on the site" on /videos/, in their order, titled in the reader's language.
    Paths are site-relative: nginx serves /site-videos/ on the main domain."""
    lang = normalize(request.GET.get('locale'))
    rows = SiteVideo.objects.filter(published=True, status=SiteVideo.READY).exclude(web_file='')
    return JsonResponse({'videos': [
        {'id': v.id, 'title': v.label(lang), 'url': site_videos.url(v.web_file),
         'poster': site_videos.url(v.poster_file) or None, 'duration': v.duration}
        for v in rows
    ]})


@api_view()
def venues(request):
    return JsonResponse({'venues': [venue_json(v, listed=True) for v in Venue.objects.filter(listed=True)]})


@api_view()
def venue_detail(request, key):
    venue = _by_id_or_slug(Venue.objects.all(), key)
    data = venue_json(venue, listed=True)
    data['upcomingEvents'] = _upcoming_for(normalize(request.GET.get('locale')), venue=venue)
    return JsonResponse({'venue': data})


log = logging.getLogger(__name__)

@api_view()
def endpoints(request):
    rows = FormEndpoint.objects.filter(active=True)
    return JsonResponse({'endpoints': [{'slug': e.slug, 'intent': e.intent, 'title': e.title or None} for e in rows]})


@api_view(methods=('POST',))
def endpoint_submit(request, slug):
    endpoint = FormEndpoint.objects.filter(slug=slug, active=True).first()
    if endpoint is None:
        return error('Unknown form', 404)
    body = request.json
    email = str(body.get('email', '')).strip().lower()
    if '@' not in email or len(email) > 254:
        return error('A valid email is required')
    fields = {str(k)[:80]: str(v)[:5000] for k, v in (body.get('fields') or {}).items()} if isinstance(body.get('fields'), dict) else {}
    context = {str(k)[:80]: str(v)[:2000] for k, v in (body.get('context') or {}).items()} if isinstance(body.get('context'), dict) else {}
    phone = str(body.get('phone', ''))[:40]
    visitor = visitor_profile(request, locale=fields.get('locale') or request.headers.get('X-Iguana-Locale', ''),
                              browser_language=context.get('browserLanguage', ''), time_zone=context.get('timeZone', ''))
    context['visitor'] = visitor
    # Judged before anything is created, so the reason can be stored with the row.
    spam = rejection_reason(fields)
    if spam:
        context['spam'] = spam
    submission = FormSubmission.objects.create(
        endpoint=endpoint, email=email, phone=phone, fields=fields, context=context,
        visitor_key=str(body.get('visitorKey', ''))[:100],
        ip=visitor.get('ip') or None,
        # Marked handled so it never shows up as a person waiting for an answer.
        handled=bool(spam),
    )
    if spam:
        log.info('form %s: dropped a %s submission from %s', endpoint.slug, spam, email)
        # Answered exactly like a real one. Telling a bot which gate caught it is how it learns to pass.
        # No contact row, no list membership, and above all no alert email: the cost of this was never the
        # rows, it was teaching the owner to ignore the alert a real enquiry arrives in.
        return JsonResponse({'ok': True, 'successMessage': endpoint.success_message or None,
                             'redirectUrl': None, 'id': submission.pk})
    if endpoint.intent == 'newsletter':
        remember_on_contact(_join_newsletter(email, context, lang=fields.get('locale') or 'en'), visitor)
        # A sign-up is not an enquiry: no alert email per subscriber.
        return JsonResponse({'ok': True, 'successMessage': endpoint.success_message or None, 'redirectUrl': None, 'id': submission.pk})
    contact = upsert_contact(email, 'CONTACT_FORM', fields.get('firstName', '') or fields.get('first_name', ''),
                             fields.get('lastName', '') or fields.get('last_name', ''), phone)
    remember_on_contact(contact, visitor)
    if settings.NOTIFY_EMAILS:
        lines = [f'Form: {endpoint.slug}', f'Email: {email}', f'Phone: {phone}', ''] + [f'{k}: {v}' for k, v in fields.items()]
        send_mail(f'New {endpoint.title or endpoint.slug} enquiry from {email}', '\n'.join(lines),
                  settings.DEFAULT_FROM_EMAIL, settings.NOTIFY_EMAILS, fail_silently=True)
    return JsonResponse({'ok': True, 'successMessage': endpoint.success_message or None, 'redirectUrl': None, 'id': submission.pk})


def _join_newsletter(email, context, lang='en'):
    """Record the request and ask them to confirm it. The address does NOT join the list here.

    A bot sends exactly what the real form sends, so nothing about the request can tell them apart; what it
    cannot do is read the mail. Until the link in that mail is clicked the contact stays unsubscribed, off
    every list, and out of the Monday send.
    """
    # get_or_create rather than upsert_contact, because whether this address is NEW is the whole decision and
    # `subscribed` cannot answer it: the model defaults it to True, so a brand-new contact looks confirmed.
    contact, created = Contact.objects.get_or_create(
        email=email, defaults={'source': 'NEWSLETTER', 'subscribed': False, 'email_marketing_eligible': False})
    if not created and contact.subscribed and contact.email_marketing_eligible:
        # Already on the list, for whatever reason. Asking again must never take somebody off it.
        _add_to_lists(contact, context)
        return contact
    if not created:
        contact.subscribed = False
        contact.email_marketing_eligible = False
        contact.save(update_fields=['subscribed', 'email_marketing_eligible'])
    # Remembered so confirming puts them on the right city list without asking again.
    contact.custom_data = dict(contact.custom_data or {}, pending_lists=_list_names(context))
    contact.save(update_fields=['custom_data'])
    send_confirmation(email, lang)
    return contact


def _list_names(context):
    names = ['Newsletter']
    city_slug = context.get('citySlug', '')
    if re.fullmatch(r'[a-z0-9-]{2,40}', city_slug):
        names.append(f'City alerts: {(context.get("cityLabel") or city_slug)[:60]}')
    return names


def _add_to_lists(contact, context=None, names=None):
    for name in (names or _list_names(context or {})):
        contact_list, _ = ContactList.objects.get_or_create(name=name)
        ContactListMember.objects.get_or_create(contact_list=contact_list, contact=contact)
    return contact


@api_view()
def forms(request):
    return JsonResponse({'forms': []})


def file_json(f):
    return {
        'id': f.id,
        'name': f.name,
        'url': f'{public_base()}{f.file.url}',
        'contentType': f.content_type or 'application/octet-stream',
        'size': f.file.size if f.file else 0,
        'createdAt': f.created_at.isoformat(),
    }


@api_view()
def files(request):
    return JsonResponse({'files': [file_json(f) for f in SiteFile.objects.filter(public=True)[: _limit(request, 50, 100)]]})


def _store_url():
    return settings.SITE_URLS[0] + '/en/store/' if settings.SITE_URLS else ''


def product_json(p, detail=False):
    variants = list(p.variants.all())
    in_stock = any(v.available_quantity is None or v.available_quantity > 0 for v in variants)
    cheapest = min(variants, key=lambda v: v.price_cents, default=None)
    data = {
        'id': p.id,
        'slug': p.slug,
        'name': p.name,
        'description': p.description or None,
        'currency': p.currency,
        'priceFromCents': cheapest.price_cents if cheapest else None,
        'compareAtCents': cheapest.compare_at_cents if cheapest else None,
        'inStock': in_stock,
        'images': [{'url': media(i.url), 'alt': i.alt or None} for i in p.images.all()],
        'productUrl': p.external_url or _store_url(),
        'storeUrl': _store_url(),
    }
    if detail:
        data['variants'] = [
            {
                'id': v.id, 'name': v.name, 'sku': v.sku or None, 'priceCents': v.price_cents,
                'compareAtCents': v.compare_at_cents, 'availableQuantity': v.available_quantity,
                'inStock': v.available_quantity is None or v.available_quantity > 0,
            }
            for v in variants
        ]
    return data


def _products():
    return StoreProduct.objects.filter(active=True).prefetch_related('variants', 'images')


@api_view()
def store_products(request):
    qs = _products()
    if request.GET.get('collection'):
        key = request.GET['collection']
        qs = qs.filter(Q(collections__slug=key) | Q(collections__id=key)).distinct()
    return JsonResponse({'products': [product_json(p) for p in qs[: _limit(request, 50, 100)]]})


@api_view()
def store_product_detail(request, key):
    return JsonResponse({'product': product_json(_by_id_or_slug(_products(), key), detail=True)})


def collection_json(c):
    return {
        'id': c.id, 'slug': c.slug, 'name': c.name, 'description': c.description or None,
        'imageUrl': media(c.image_url), 'productCount': c.products.filter(active=True).count(),
        'collectionUrl': f'{_store_url()}?collection={c.slug}', 'storeUrl': _store_url(),
    }


@api_view()
def store_collections(request):
    return JsonResponse({'collections': [collection_json(c) for c in StoreCollection.objects.all()[: _limit(request, 50, 100)]]})


@api_view()
def store_collection_detail(request, key):
    c = _by_id_or_slug(StoreCollection.objects.all(), key)
    data = collection_json(c)
    data['products'] = [product_json(p) for p in _products().filter(collections=c)]
    return JsonResponse({'collection': data})


@api_view()
def site(request):
    return JsonResponse({'site': {'id': 'iguana-comedy', 'name': 'Iguana Comedy', 'slug': 'iguana-comedy',
                                  'galleryFolderId': None, 'brandAssetsFolderId': None}})


@api_view()
def site_manifest(request):
    eps = {e.intent: {'slug': e.slug, 'intent': e.intent} for e in FormEndpoint.objects.filter(active=True)}
    return JsonResponse({'site': {'id': 'iguana-comedy', 'name': 'Iguana Comedy', 'slug': 'iguana-comedy'},
                         'updatedAt': today_local().isoformat(), 'gallery': [], 'assets': {}, 'forms': {}, 'endpoints': eps})
