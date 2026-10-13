"""`/drop/`: where the owner uploads the business documents that ad and video account setup asks for.

Upload-only by design. The PIN is short and was sent by email, so nothing behind it may be readable (it holds IDs and the ad billing card): the page
never lists a file name, never serves a file back, and stores everything in `DROP_DIR`, outside `backend/media`,
so nginx has no route to it. What the page does show is which items have arrived, so the person uploading can see
what is still missing. Copies come off the box through ansible. Wrong PINs share the point of sale's lockout
(`pos.auth`), five per address in fifteen minutes.
"""
import hmac
import json
import logging
import os
from datetime import datetime

from django.conf import settings
from django.core.mail import send_mail
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.text import get_valid_filename

from pos.auth import clear_failures, locked_out, record_failure
from sales.i18n import lang_from_request, normalize, tr

log = logging.getLogger(__name__)

SESSION_KEY = 'drop_ok'
MAX_FILES = 20

# (key, label, hint). Labels are English source strings for `tr`; Spanish lives in sales/i18n.py.
ITEMS = [
    ('csf', 'Constancia de situación fiscal', 'The PDF from the SAT, issued in the last 3 months. It carries the RFC and razón social.'),
    ('id', "Legal representative's ID", 'INE (both sides) or passport, as photos or a PDF.'),
    ('address', 'Proof of address', 'A utility bill or bank statement at the fiscal address, from the last 3 months.'),
    ('acta', 'Acta constitutiva', 'Only if the business is a company (persona moral).'),
    ('card', 'Card for ad billing', 'Photos of the front and back. When the card is replaced, upload the new one here and it takes over.'),
    ('logins', 'Existing accounts', 'Logins for the YouTube channel and TikTok @iguanacomedy, if they are the club’s, and any Google account the club already uses.'),
    ('brand', 'Logo and banner', 'Optional. The site logo is used if nothing is sent.'),
    ('releases', 'Comedian permissions', 'Signed OKs from comedians to post and monetize clips of their sets.'),
    ('other', 'Anything else', 'Answers, notes, links to footage.'),
]
KEYS = {key for key, _, _ in ITEMS}

# Our notes back to the uploader, per heading, in DROP_DIR/status.json (written over ansible, never in the repo,
# since it says what the documents are missing): {"address": {"state": "check", "en": "...", "es": "..."}}.
# state: done (received and fine), check (received, but something is wrong with it), missing (still needed).
STATUS_FILE = 'status.json'
STATES = ('done', 'check', 'missing')


def _notes():
    try:
        with open(os.path.join(settings.DROP_DIR, STATUS_FILE), encoding='utf-8') as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        log.exception('drop: %s is unreadable, showing no notes', STATUS_FILE)
        return {}
    return data if isinstance(data, dict) else {}


def _received():
    try:
        names = os.listdir(settings.DROP_DIR)
    except FileNotFoundError:
        return set()
    return {name.split('__')[1] for name in names if name.count('__') >= 2}


def _save(kind, uploads, note):
    os.makedirs(settings.DROP_DIR, mode=0o700, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    saved = 0
    for n, upload in enumerate(uploads):
        name = get_valid_filename(os.path.basename(upload.name or 'file'))[-120:] or 'file'
        path = os.path.join(settings.DROP_DIR, f'{stamp}-{n}__{kind}__{name}')
        with open(path, 'xb') as out:
            for chunk in upload.chunks():
                out.write(chunk)
        os.chmod(path, 0o600)
        saved += 1
    if note:
        path = os.path.join(settings.DROP_DIR, f'{stamp}-note__{kind}__note.txt')
        with open(path, 'x', encoding='utf-8') as out:
            out.write(note + '\n')
        os.chmod(path, 0o600)
        saved += 1
    return saved


def drop(request):
    if not settings.DROP_PIN:
        raise Http404
    lang = normalize(request.GET.get('lang') or lang_from_request(request))
    context = {'lang': lang, 'other_lang': 'en' if lang == 'es' else 'es'}

    if not request.session.get(SESSION_KEY):
        wait = locked_out(request)
        if request.method == 'POST' and not wait:
            if hmac.compare_digest(request.POST.get('pin', '').strip(), settings.DROP_PIN):
                clear_failures(request)
                request.session[SESSION_KEY] = True
                return redirect(f'{request.path}?lang={lang}')
            record_failure(request)
            wait = locked_out(request)
            context['error'] = tr(lang, 'That PIN is not right.')
        if wait:
            context['error'] = tr(lang, 'Too many wrong PINs. Try again in {0} minutes.', wait)
        return render(request, 'embed/drop.html', context)

    if request.method == 'POST':
        kind = request.POST.get('kind', '')
        uploads = request.FILES.getlist('files')[:MAX_FILES]
        note = request.POST.get('note', '').strip()[:20000]
        if kind not in KEYS:
            context['error'] = tr(lang, 'Choose what you are sending.')
        elif not uploads and not note:
            context['error'] = tr(lang, 'Add a file or write a note.')
        else:
            saved = _save(kind, uploads, note)
            log.info('drop: %s item(s) received under %s', saved, kind)
            # Says THAT something arrived and under which heading, never what it is: it goes to a shared inbox.
            send_mail(f'/drop/: {saved} item(s) received ({kind})',
                      f'{saved} item(s) were uploaded to iguanacomedy.com/drop/ under "{kind}".\n',
                      None, list(settings.NOTIFY_EMAILS), fail_silently=True)
            return redirect(f'{request.path}?lang={lang}&sent={kind}')

    received, notes = _received(), _notes()
    items = []
    for key, label, hint in ITEMS:
        note = notes.get(key) if isinstance(notes.get(key), dict) else {}
        state = note.get('state') if note.get('state') in STATES else ('done' if key in received else '')
        # A note in one language only still shows, rather than a Spanish reader seeing nothing.
        text = note.get(lang) or note.get('en') or note.get('es') or ''
        items.append({'key': key, 'label': tr(lang, label), 'hint': tr(lang, hint), 'state': state, 'note': text})
    sent = request.GET.get('sent', '')
    context.update({
        'unlocked': True,
        'items': items,
        'sent_label': next((tr(lang, label) for key, label, _ in ITEMS if key == sent), ''),
    })
    return render(request, 'embed/drop.html', context)
