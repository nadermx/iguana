"""`/upload/` (also `/drop/`): where the owner uploads the business documents that ad and video account setup asks
for, and, under "For the site", photos and videos for the /chat/ agent to put on the site.

Upload-only by design. The PIN is short and was sent by email, so nothing behind it may be readable (it holds IDs and the ad billing card): the page
never lists a file name, never serves a file back, and stores everything in `DROP_DIR`, outside `backend/media`,
so nginx has no route to it. What the page does show is which items have arrived, so the person uploading can see
what is still missing. Copies come off the box through ansible. Wrong PINs share the point of sale's lockout
(`pos.auth`), five per address in fifteen minutes.

"For the site" is the exception to where things go: those files are meant for the agent, so they land in
`CHAT_FILES_DIR/upload/` (assistant/files.py), which the agent's group can read, and never beside the IDs. A video
among them also becomes a `SiteVideo`, managed on /videos/ (catalog/videos.py).

Any size (owner, 2026-10-28). The page sends each file in CHUNK pieces (`action=chunk`), each written at its
offset into `DROP_DIR/.parts/<upload id>`, so a dropped connection retries one piece rather than the whole video
and no single request comes near nginx's limit. `action=finish` checks every part has the size the browser
declared and moves it into place. The only ceiling left is the free disk (`low_on_disk`). Without JavaScript the
plain form post still works, up to nginx's 1700m for the request.
"""
import hmac
import json
import logging
import os
import re
import time
from datetime import datetime

from django.conf import settings
from django.core.mail import send_mail
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.text import get_valid_filename

from assistant import files as chat_files
from catalog import videos as site_videos
from pos.auth import clear_failures, locked_out, record_failure
from sales.i18n import lang_from_request, normalize, tr

log = logging.getLogger(__name__)

SESSION_KEY = 'drop_ok'
MAX_FILES = 20
PARTS = '.parts'
UPLOAD_ID = re.compile(r'^[a-f0-9]{32}$')
# Parts nobody finished (a closed tab) are removed after this long.
STALE_PARTS_SECONDS = 2 * 86400
FOR_THE_SITE = 'site'

# (key, label, hint). Labels are English source strings for `tr`; Spanish lives in sales/i18n.py.
ITEMS = [
    (FOR_THE_SITE, 'For the site', 'Photos, videos, menus, posters: anything to go on the site. The chat at iguanacomedy.com/chat/ can use them; tell it what they are for.'),
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
        names = []
    received = {name.split('__')[1] for name in names if name.count('__') >= 2}
    try:
        if os.listdir(os.path.join(settings.CHAT_FILES_DIR, 'upload')):
            received.add(FOR_THE_SITE)
    except FileNotFoundError:
        pass
    return received


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


def _parts_dir():
    path = os.path.join(settings.DROP_DIR, PARTS)
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _clear_stale_parts(folder):
    cutoff = time.time() - STALE_PARTS_SECONDS
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except FileNotFoundError:
            pass


def _chunk(request, lang):
    """One piece of one file, written at its offset. Answers how many bytes of that file the server now holds."""
    upload_id = request.POST.get('upload', '')
    piece = request.FILES.get('chunk')
    try:
        offset = int(request.POST.get('offset', ''))
    except ValueError:
        offset = -1
    if not UPLOAD_ID.match(upload_id) or piece is None or offset < 0:
        return JsonResponse({'error': tr(lang, 'The upload did not finish. Check your connection and send it again, or write to hello@iguanacomedy.com.')}, status=400)
    if chat_files.low_on_disk():
        log.critical('drop: refusing a chunk, the disk is nearly full')
        return JsonResponse({'error': tr(lang, 'The server is short of space. Try again later.')}, status=507)
    folder = _parts_dir()
    path = os.path.join(folder, upload_id)
    have = os.path.getsize(path) if os.path.exists(path) else 0
    if offset > have:
        # A piece went missing: tell the page where to carry on from.
        return JsonResponse({'have': have}, status=409)
    if not os.path.exists(path):
        _clear_stale_parts(folder)
    with open(path, 'r+b' if os.path.exists(path) else 'wb') as out:
        out.seek(offset)
        out.truncate(offset)  # a resent piece replaces whatever half of it arrived before
        for chunk in piece.chunks():
            out.write(chunk)
    os.chmod(path, 0o600)
    return JsonResponse({'have': os.path.getsize(path)})


def _finish(request, lang):
    """Every file has arrived in pieces: check them and move them into place, as a plain upload would."""
    try:
        body = json.loads(request.POST.get('files') or '[]')
    except ValueError:
        body = None
    kind = request.POST.get('kind', '')
    note = request.POST.get('note', '').strip()[:20000]
    if kind not in KEYS:
        return JsonResponse({'error': tr(lang, 'Choose what you are sending.')}, status=400)
    if not isinstance(body, list) or len(body) > MAX_FILES * 10:
        body = None
    parts = []
    for entry in body or []:
        upload_id = str(entry.get('upload', '')) if isinstance(entry, dict) else ''
        path = os.path.join(settings.DROP_DIR, PARTS, upload_id)
        if (not UPLOAD_ID.match(upload_id) or not os.path.exists(path)
                or os.path.getsize(path) != entry.get('size')):
            return JsonResponse({'error': tr(lang, 'The upload did not finish. Check your connection and send it again, or write to hello@iguanacomedy.com.')}, status=400)
        parts.append((path, str(entry.get('name') or 'file')))
    if body is None or (not parts and not note):
        return JsonResponse({'error': tr(lang, 'Add a file or write a note.')}, status=400)
    if kind == FOR_THE_SITE:
        saved = chat_files.store_paths(parts, 'upload', note=note)
        for (path, _), (_, name) in zip(saved, parts):
            site_videos.register(path, name)
        count = len(saved)
    else:
        count = _save_paths(kind, parts, note)
    _notify(kind, count)
    return JsonResponse({'redirect': f'{request.path}?lang={lang}&sent={kind}'})


def _save_paths(kind, parts, note):
    os.makedirs(settings.DROP_DIR, mode=0o700, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    for n, (src, original) in enumerate(parts):
        name = get_valid_filename(os.path.basename(original))[-120:] or 'file'
        dest = os.path.join(settings.DROP_DIR, f'{stamp}-{n}__{kind}__{name}')
        os.replace(src, dest)
        os.chmod(dest, 0o600)
    saved = len(parts)
    if note:
        path = os.path.join(settings.DROP_DIR, f'{stamp}-note__{kind}__note.txt')
        with open(path, 'x', encoding='utf-8') as out:
            out.write(note + '\n')
        os.chmod(path, 0o600)
        saved += 1
    return saved


def _notify(kind, saved):
    log.info('drop: %s item(s) received under %s', saved, kind)
    # Says THAT something arrived and under which heading, never what it is: it goes to a shared inbox.
    send_mail(f'/upload/: {saved} item(s) received ({kind})',
              f'{saved} item(s) were uploaded to iguanacomedy.com/upload/ under "{kind}".\n',
              None, list(settings.NOTIFY_EMAILS), fail_silently=True)


def drop(request):
    if not settings.DROP_PIN:
        raise Http404
    lang = normalize(request.GET.get('lang') or lang_from_request(request))
    context = {'lang': lang, 'other_lang': 'en' if lang == 'es' else 'es'}

    action = request.POST.get('action', '') if request.method == 'POST' else ''
    if action in ('chunk', 'finish'):
        if not request.session.get(SESSION_KEY):
            return JsonResponse({'error': tr(lang, 'That PIN is not right.')}, status=403)
        return _chunk(request, lang) if action == 'chunk' else _finish(request, lang)

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
        elif uploads and chat_files.low_on_disk():
            log.critical('drop: refusing an upload, the disk is nearly full')
            context['error'] = tr(lang, 'The server is short of space. Try again later.')
        else:
            if kind == FOR_THE_SITE:
                stored = chat_files.store(uploads, 'upload', note=note)
                for (path, _), upload in zip(stored, uploads):
                    site_videos.register(path, upload.name)
                saved = len(stored)
            else:
                saved = _save(kind, uploads, note)
            _notify(kind, saved)
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
