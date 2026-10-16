"""Tell Meta and TikTok what an ad was worth, from the order it produced.

`crm.meta_capi` knows how to talk to Meta; this knows what an Iguana order looks like. Split that way because the
checkout runs in an iframe on the API domain: the browser cookies Meta matches on (`_fbp`, `_fbc`) belong to the
SITE origin, so they can only reach us by riding along in the checkout payload. `k.js` reads them on the site and
posts them as attribution, `checkout_start` stores them on the order, and both functions here read them back.

Matching is everything. An event with only a hashed email attributes far fewer sales than one that also carries
the click id, the browser id, the IP and the user agent, and an unattributed sale teaches the algorithm that the
ad did not work.
"""

from crm import meta_capi, tiktok_events


def _attribution(order):
    return order.attribution if isinstance(order.attribution, dict) else {}


def _visitor(order):
    visitor = _attribution(order).get('visitor')
    return visitor if isinstance(visitor, dict) else {}


def _split_name(order):
    parts = str(order.customer_name or '').strip().split()
    if not parts:
        return '', ''
    return parts[0], parts[-1] if len(parts) > 1 else ''


def _user(order):
    attribution, visitor = _attribution(order), _visitor(order)
    first, last = _split_name(order)
    contact = order.contact
    return meta_capi.user_data(
        email=order.customer_email or (contact.email if contact else ''),
        phone=order.customer_phone or (contact.phone if contact else ''),
        first_name=(contact.first_name if contact and contact.first_name else first),
        last_name=(contact.last_name if contact and contact.last_name else last),
        city=visitor.get('city', ''),
        region=visitor.get('region', ''),
        country=visitor.get('country', ''),
        ip=visitor.get('ip', ''),
        user_agent=attribution.get('userAgent', ''),
        # Set by the pixel on the site and carried across the iframe boundary by k.js.
        fbp=attribution.get('fbp', ''),
        fbc=attribution.get('fbc', ''),
    )


def _tiktok_user(order):
    attribution, visitor = _attribution(order), _visitor(order)
    contact = order.contact
    return tiktok_events.user_data(
        email=order.customer_email or (contact.email if contact else ''),
        phone=order.customer_phone or (contact.phone if contact else ''),
        ip=visitor.get('ip', ''),
        user_agent=attribution.get('userAgent', ''),
        # k.js keeps every query parameter, so a TikTok ad click arrives as attribution['ttclid'].
        ttclid=attribution.get('ttclid', ''),
        ttp=attribution.get('ttp', ''),
        external_id=contact.id if contact else '',
    )


def _tiktok_properties(custom):
    """The same facts as Meta's custom_data, in TikTok's shape."""
    ids = custom.get('content_ids') or []
    return {
        'currency': custom['currency'],
        'value': custom['value'],
        'content_type': 'product',
        'contents': [{'content_id': str(ids[0]), 'content_name': custom.get('content_name', ''),
                      'quantity': custom.get('num_items', 1)}] if ids else [],
    }


def _custom(order):
    items = list(order.items.all())
    # What actually reached us online. A pay-at-the-door reservation is a real booking worth optimising for, but it
    # is worth nothing yet, and telling Meta otherwise inflates the ROAS it learns from.
    charged_cents = max(order.total_amount_cents - order.pay_at_door_cents, 0)
    return {
        'currency': (order.currency or 'mxn').upper(),
        'value': round(charged_cents / 100, 2),
        'content_type': 'product',
        'content_ids': [order.event_id] if order.event_id else [],
        'content_name': order.event_name or '',
        'num_items': sum(item.quantity for item in items),
        'order_id': order.id,
    }


def _source_url(order):
    """The page the fan was on, not the iframe. Meta uses it to group results by landing page."""
    return _attribution(order).get('pageUrl', '')


def report_payment_info_added(order):
    """They filled the form in and we made them a payment intent. This used to be reported as InitiateCheckout,
    which was wrong twice over: Meta means that event for entering a checkout, not finishing one, and the ad
    sets optimise on it precisely because it should be commoner than Purchase. Fired here it was almost as rare,
    so the campaigns had nothing to learn from. `report_checkout_engaged` is the real one now."""
    if is_probe(order):
        return
    custom = _custom(order)
    meta_capi.send('AddPaymentInfo', event_id=f'api-{order.id}', user=_user(order), custom=custom,
                   source_url=_source_url(order))
    tiktok_events.send('AddPaymentInfo', event_id=f'api-{order.id}', user=_tiktok_user(order),
                       properties=_tiktok_properties(custom), page_url=_source_url(order))


def report_checkout_engaged(*, event, attribution, visitor, user_agent, value_cents, currency, key):
    """Somebody started filling the checkout in. No order exists yet, so the identity is only what the browser
    carried in: the click ids, the IP and the user agent. That is enough for Meta to match on, and this is the
    one mid-funnel event with real volume behind it."""
    attribution = attribution if isinstance(attribution, dict) else {}
    user = meta_capi.user_data(
        city=visitor.get('city', ''), region=visitor.get('region', ''), country=visitor.get('country', ''),
        ip=visitor.get('ip', ''), user_agent=user_agent,
        fbp=attribution.get('fbp', ''), fbc=attribution.get('fbc', ''),
    )
    custom = {
        'currency': (currency or 'mxn').upper(),
        'value': round((value_cents or 0) / 100, 2),
        'content_type': 'product',
        'content_ids': [event.id],
        'content_name': event.name,
    }
    meta_capi.send('InitiateCheckout', event_id=f'ic-{key}', user=user, custom=custom,
                   source_url=attribution.get('pageUrl', ''))
    tiktok_events.send('InitiateCheckout', event_id=f'ic-{key}', user=tiktok_events.user_data(
        ip=visitor.get('ip', ''), user_agent=user_agent,
        ttclid=attribution.get('ttclid', ''), ttp=attribution.get('ttp', ''),
    ), properties=_tiktok_properties(custom), page_url=attribution.get('pageUrl', ''))


# The end-to-end test books a real seat through the real checkout, which is the whole point of it: nothing else
# proves the thing the ads are paying for actually works. But a test booking is not a sale, and Meta cannot be
# told to forget one. Left unfiltered it taught the algorithm that a run of the test suite was a customer, and
# it flattered the cost per reservation the campaigns are judged on.
PROBE_EMAIL_PREFIX = 'e2e-'


def is_probe(order):
    return str(order.customer_email or '').lower().startswith(PROBE_EMAIL_PREFIX)


def report_purchase(order):
    """One Purchase per order, keyed on the order id so a Stripe webhook retry cannot double-count it."""
    if is_probe(order):
        return
    custom = _custom(order)
    meta_capi.send('Purchase', event_id=f'purchase-{order.id}', user=_user(order), custom=custom,
                   source_url=_source_url(order))
    # TikTok's standard name for a completed sale.
    tiktok_events.send('CompletePayment', event_id=f'purchase-{order.id}', user=_tiktok_user(order),
                       properties=_tiktok_properties(custom), page_url=_source_url(order))
