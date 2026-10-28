"""/videos/: the owner's list of videos uploaded for the site (catalog.SiteVideo, catalog/videos.py).

Watch each one, name it in both languages, trim it, choose the order, say whether it shows on the site's Videos
page, or delete it. Superusers only, like /chat/: the same login the owner uses for the admin.

Plain form posts that redirect back, so nothing here holds a gunicorn worker. Transcoding happens in the
`process_videos` cron, never in a request.
"""
import re

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from catalog import videos as site_videos
from catalog.models import SiteVideo
from sales.i18n import lang_from_request, normalize, tr

from .chat_views import is_owner

TIME = re.compile(r'^\s*(?:(\d+):)?(?:(\d+):)?(\d+(?:[.,]\d+)?)\s*$')


def parse_time(value):
    """'75', '1:15', '1:01:15' or '75.5' as seconds; '' as None. Raises ValueError on anything else."""
    value = (value or '').strip()
    if not value:
        return None
    match = TIME.match(value)
    if not match:
        raise ValueError(value)
    a, b, c = match.groups()
    seconds = float(c.replace(',', '.'))
    if a is not None and b is not None:
        return int(a) * 3600 + int(b) * 60 + seconds
    if a is not None:
        return int(a) * 60 + seconds
    return seconds


def clock(seconds):
    if seconds is None:
        return ''
    seconds = round(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def _act(request, lang):
    video = get_object_or_404(SiteVideo, pk=request.POST.get('id', ''))
    action = request.POST.get('action', '')
    if action == 'save':
        video.title = request.POST.get('title', '').strip()[:160]
        video.title_es = request.POST.get('title_es', '').strip()[:160]
        try:
            video.position = int(request.POST.get('position') or 0)
        except ValueError:
            pass
        wants = request.POST.get('published') == 'on'
        if wants and video.status != SiteVideo.READY:
            video.save()
            return tr(lang, 'Saved. It can go on the site once the web copy is ready.'), 'err'
        video.published = wants
        video.save()
        return tr(lang, 'Saved.'), 'ok'
    if action == 'trim':
        try:
            start, end = parse_time(request.POST.get('start')), parse_time(request.POST.get('end'))
        except ValueError:
            return tr(lang, 'Write times as seconds or minutes:seconds, for example 1:30.'), 'err'
        if start is not None and end is not None and end <= start:
            return tr(lang, 'The end has to come after the start.'), 'err'
        video.trim_start, video.trim_end = (start or None), end
        video.status = SiteVideo.PENDING
        video.save()
        return tr(lang, 'Trimming. The new version appears here in a few minutes; the original is kept.'), 'ok'
    if action == 'untrim':
        video.trim_start = video.trim_end = None
        video.status = SiteVideo.PENDING
        video.save()
        return tr(lang, 'Going back to the full video. It appears here in a few minutes.'), 'ok'
    if action == 'retry':
        video.status = SiteVideo.PENDING
        video.save(update_fields=['status', 'updated_at'])
        return tr(lang, 'Trying again.'), 'ok'
    if action == 'delete':
        site_videos.delete(video)
        return tr(lang, 'Deleted.'), 'ok'
    return '', ''


@user_passes_test(is_owner, login_url='/admin/login/')
def videos(request):
    lang = normalize(request.GET.get('lang') or lang_from_request(request))
    if request.method == 'POST':
        message, tone = _act(request, lang)
        request.session['videos_flash'] = [message, tone]
        return redirect(f'{request.path}?lang={lang}')
    message, tone = request.session.pop('videos_flash', ['', ''])
    rows = []
    for video in SiteVideo.objects.all():
        rows.append({
            'v': video,
            'url': site_videos.url(video.web_file),
            'poster': site_videos.url(video.poster_file),
            'length': clock(video.duration),
            'start': clock(video.trim_start),
            'end': clock(video.trim_end),
            'size_mb': round(video.size / 1024 / 1024),
            'trimmed': (tr(lang, 'trimmed from {0} to {1}', clock(video.trim_start) or '0:00',
                           clock(video.trim_end) or tr(lang, 'the end'))
                        if video.trim_start or video.trim_end else ''),
        })
    return render(request, 'embed/videos.html', {
        'lang': lang, 'other_lang': 'en' if lang == 'es' else 'es',
        'rows': rows, 'message': message, 'tone': tone,
        'busy': any(r['v'].status in (SiteVideo.PENDING, SiteVideo.PROCESSING) for r in rows),
    })
