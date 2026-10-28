"""/videos/: the owner's list of videos uploaded for the site (catalog.SiteVideo, catalog/videos.py).

Watch each one, name it in both languages, trim it, choose the order, say whether it shows on the site's Videos
page, or delete it. Superusers only, like /chat/: the same login the owner uses for the admin.

Two AI tools sit on each video (owner, 2026-10-28):
  * "Make clips with AI" queues a `ClipJob` (catalog/clips.py): the best short and long clips, sorted by comedian.
  * "Edit with AI" is the video's OWN conversation with the /chat/ agent: each instruction becomes a `Turn` in it,
    prefixed with where the video is and how to hand the result back (`add_site_video`), and its replies show
    under the video. The full thread is also on /chat/.

Plain form posts that redirect back, so nothing here holds a gunicorn worker. Transcoding, clipping and the agent
all run in the background (`process_videos`, `chat_worker`), never in a request.
"""
import os
import re

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from assistant.models import Conversation, Turn
from catalog import videos as site_videos
from catalog.models import ClipJob, SiteVideo
from sales.i18n import lang_from_request, normalize, tr

from .chat_views import is_owner

# Between the context the agent needs and what the owner typed, so the page can show only the latter.
ASKED = '\n\nThe owner asks:\n'
MAX_INSTRUCTION = 4000

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


def _context(video):
    """What the agent is told about this video on every instruction, so a resumed or fresh session both work."""
    transcript = ''
    job = video.clip_jobs.filter(status=ClipJob.DONE).first() if video.kind == SiteVideo.UPLOAD else None
    if job:
        path = os.path.join(settings.CHAT_FILES_DIR, 'clips-work', str(job.pk), 'transcript.txt')
        if os.path.exists(path):
            transcript = f'Timed transcript with the laughs marked: {path}\n'
    return (
        f'[Video editing from iguanacomedy.com/videos/] Video id {video.pk}, "{video}", a {video.get_kind_display()}'
        f'{" by " + video.comedian if video.comedian else ""}, {clock(video.duration) or "length unknown"} long.\n'
        f'Original file (read only, never change or delete it): {video.source}\n'
        f'Web copy the owner is watching: {settings.SITE_VIDEOS_DIR}/{video.web_file}\n'
        f'{transcript}'
        'Make the change with ffmpeg into a NEW file under /tmp, then hand it back with\n'
        f'  iguana-manage add_site_video /tmp/<file>.mp4 --parent {video.pk} --title "..." --title-es "..."\n'
        'It then appears on /videos/ under this video, not on the public site (the owner decides that there). '
        'Check the result with ffprobe before handing it back. Answer briefly, in the language the owner wrote in.'
    )


def _ask_ai(request, video, lang):
    instruction = request.POST.get('instruction', '').strip()[:MAX_INSTRUCTION]
    if not instruction:
        return tr(lang, 'Write what to change first.'), 'err'
    if video.conversation is None:
        video.conversation = Conversation.objects.create(title=f'Video: {video}'[:120], created_by=request.user)
        video.save(update_fields=['conversation', 'updated_at'])
    conversation = video.conversation
    if conversation.turns.filter(status__in=(Turn.QUEUED, Turn.RUNNING)).exists():
        return tr(lang, 'Wait for the current reply to finish, or stop it'), 'err'
    Turn.objects.create(conversation=conversation, prompt=_context(video) + ASKED + instruction, created_by=request.user)
    conversation.save(update_fields=['updated_at'])
    return tr(lang, 'Sent to the AI. Its answer appears under the video.'), 'ok'


def _act_all(request, lang):
    action = request.POST.get('action', '')
    if action == 'delete_all_clips':
        rows = SiteVideo.objects.filter(kind__in=(SiteVideo.SHORT, SiteVideo.LONG))
    elif action == 'delete_everything' and request.POST.get('confirm', '').strip().upper() in ('DELETE', 'BORRAR'):
        rows = SiteVideo.objects.all()
    elif action == 'delete_everything':
        return tr(lang, 'Type DELETE to confirm.'), 'err'
    else:
        return '', ''
    count = 0
    for video in list(rows):
        site_videos.delete(video)
        count += 1
    return tr(lang, 'Deleted {0} videos.', count), 'ok'


def _act(request, lang):
    if not request.POST.get('id'):
        return _act_all(request, lang)
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
    if action == 'clips':
        if video.status != SiteVideo.READY:
            return tr(lang, 'Wait until the video has finished processing.'), 'err'
        if video.clip_jobs.filter(status__in=(ClipJob.QUEUED, ClipJob.RUNNING)).exists():
            return tr(lang, 'Clips are already being made for this video.'), 'err'
        ClipJob.objects.create(video=video, step='Waiting to start')
        return tr(lang, 'Making clips. A long show takes about an hour; they appear below, sorted by comedian.'), 'ok'
    if action == 'delete_clips':
        count = 0
        for clip in list(video.children.filter(kind__in=(SiteVideo.SHORT, SiteVideo.LONG))):
            site_videos.delete(clip)
            count += 1
        return tr(lang, 'Deleted {0} videos.', count), 'ok'
    if action == 'ai':
        return _ask_ai(request, video, lang)
    return '', ''


@user_passes_test(is_owner, login_url='/admin/login/')
def videos(request):
    lang = normalize(request.GET.get('lang') or lang_from_request(request))
    if request.method == 'POST':
        message, tone = _act(request, lang)
        request.session['videos_flash'] = [message, tone]
        return redirect(f'{request.path}?lang={lang}')
    message, tone = request.session.pop('videos_flash', ['', ''])
    only = request.GET.get('who', '')
    everything = list(SiteVideo.objects.select_related('conversation'))
    jobs = {}
    for job in ClipJob.objects.order_by('created_at'):
        jobs[job.video_id] = job  # the newest wins
    rows = [_row(video, lang, jobs.get(video.pk)) for video in everything]
    uploads = [r for r in rows if r['v'].kind == SiteVideo.UPLOAD]
    made = [r for r in rows if r['v'].kind != SiteVideo.UPLOAD]
    names = sorted({r['v'].comedian for r in made if r['v'].comedian}, key=str.lower)
    if only:
        made = [r for r in made if r['v'].comedian == only]
    groups = {}
    for r in sorted(made, key=lambda r: (r['v'].comedian.lower() or '~', r['v'].kind != SiteVideo.SHORT)):
        groups.setdefault(r['v'].comedian or tr(lang, 'Other'), []).append(r)
    busy = (any(r['v'].status in (SiteVideo.PENDING, SiteVideo.PROCESSING) or r['thinking'] for r in rows)
            or any(j.status in (ClipJob.QUEUED, ClipJob.RUNNING) for j in jobs.values()))
    return render(request, 'embed/videos.html', {
        'lang': lang, 'other_lang': 'en' if lang == 'es' else 'es',
        'uploads': uploads, 'groups': list(groups.items()), 'names': names, 'only': only,
        'clip_count': sum(1 for r in rows if r['v'].kind in (SiteVideo.SHORT, SiteVideo.LONG)),
        'total': len(rows), 'message': message, 'tone': tone, 'busy': busy,
    })


def _row(video, lang, job):
    turns = []
    if video.conversation_id:
        for turn in list(video.conversation.turns.order_by('-created_at')[:4])[::-1]:
            turns.append({'asked': turn.prompt.split(ASKED, 1)[-1], 'reply': turn.reply, 'status': turn.status,
                          'error': turn.error})
    return {
        'v': video,
        'job': job,
        'url': site_videos.url(video.web_file),
        'poster': site_videos.url(video.poster_file),
        'length': clock(video.duration),
        'start': clock(video.trim_start),
        'end': clock(video.trim_end),
        'size_mb': round(video.size / 1024 / 1024),
        'trimmed': (tr(lang, 'trimmed from {0} to {1}', clock(video.trim_start) or '0:00',
                       clock(video.trim_end) or tr(lang, 'the end'))
                    if video.trim_start or video.trim_end else ''),
        'turns': turns,
        'thinking': any(t['status'] in (Turn.QUEUED, Turn.RUNNING) for t in turns),
    }
