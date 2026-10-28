"""Videos uploaded for the site: registering them, and making the copy a browser can play.

An upload under "For the site" on /upload/ that looks like a video becomes a `SiteVideo` (status pending). The
`process_videos` cron (every minute, one at a time under flock, at nice 19 so the site keeps its CPU) turns the
original into an H.264/AAC MP4 no larger than 1920 px on its long side, with `+faststart` so it starts playing
before it has finished downloading, and grabs a poster frame. A trim set on /videos/ re-makes the copy from the
original, which is never changed. A delete moves the original into `upload/.trash/`, emptied after 30 days.
"""
import logging
import os
import secrets
import shutil
import subprocess
import time

from django.conf import settings

from .models import SiteVideo

log = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi', '.3gp', '.hevc', '.mts', '.wmv'}
TRASH = '.trash'
TRASH_DAYS = 30
# A long show recorded on a phone transcodes in well under this on two cores; a hung ffmpeg must not hold the lock.
TRANSCODE_TIMEOUT = 6 * 3600


def is_video(name):
    return os.path.splitext(name or '')[1].lower() in VIDEO_EXTENSIONS


def _title_from(name):
    stem = os.path.splitext(os.path.basename(name or ''))[0]
    return ' '.join(stem.replace('_', ' ').replace('-', ' ').split())[:160]


def register(path, original_name):
    """Make a SiteVideo for an upload if it is a video. Returns it, or None."""
    if not is_video(original_name or path):
        return None
    return SiteVideo.objects.create(
        source=path, original_name=os.path.basename(original_name or path)[:200],
        title=_title_from(original_name or path), size=os.path.getsize(path) if os.path.exists(path) else 0)


def folder():
    os.makedirs(settings.SITE_VIDEOS_DIR, mode=0o755, exist_ok=True)
    return settings.SITE_VIDEOS_DIR


def url(name):
    return f'{settings.SITE_VIDEOS_URL}{name}' if name else ''


def _remove(name):
    if name:
        try:
            os.remove(os.path.join(settings.SITE_VIDEOS_DIR, name))
        except FileNotFoundError:
            pass


def probe_duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                         capture_output=True, text=True, timeout=120)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def transcode_command(source, dest, start=None, end=None):
    cmd = ['nice', '-n', '19', 'ffmpeg', '-nostdin', '-y', '-hide_banner', '-loglevel', 'error']
    if start:
        cmd += ['-ss', f'{start:.3f}']
    cmd += ['-i', source]
    if end is not None and end > (start or 0):
        cmd += ['-t', f'{end - (start or 0):.3f}']
    # Portrait phone video is 1080x1920 and landscape 1920x1080: cap the long side either way, keep it even.
    scale = "scale='if(gt(iw,ih),min(1920,iw),-2)':'if(gt(iw,ih),-2,min(1920,ih))'"
    cmd += ['-map', '0:v:0', '-map', '0:a:0?', '-vf', scale,
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-f', 'mp4', dest]
    return cmd


def process(video):
    """Make the web copy and poster for one video. Never raises; the outcome is on the row."""
    video.status, video.error = SiteVideo.PROCESSING, ''
    video.save(update_fields=['status', 'error', 'updated_at'])
    out_dir = folder()
    token = secrets.token_hex(10)
    web, poster = f'{video.id}-{token}.mp4', f'{video.id}-{token}.jpg'
    web_path, poster_path = os.path.join(out_dir, web), os.path.join(out_dir, poster)
    part = web_path + '.part'
    try:
        if not os.path.exists(video.source):
            raise RuntimeError('The original file is missing on the server.')
        result = subprocess.run(transcode_command(video.source, part, video.trim_start, video.trim_end),
                                capture_output=True, text=True, timeout=TRANSCODE_TIMEOUT)
        if result.returncode != 0 or not os.path.exists(part) or os.path.getsize(part) == 0:
            raise RuntimeError((result.stderr or 'ffmpeg failed').strip()[-1500:])
        os.replace(part, web_path)
        os.chmod(web_path, 0o644)
        duration = probe_duration(web_path)
        at = min(1.0, (duration or 0) / 3)
        subprocess.run(['nice', '-n', '19', 'ffmpeg', '-nostdin', '-y', '-hide_banner', '-loglevel', 'error',
                        '-ss', f'{at:.2f}', '-i', web_path, '-frames:v', '1', '-q:v', '3', poster_path],
                       capture_output=True, timeout=300)
        if os.path.exists(poster_path):
            os.chmod(poster_path, 0o644)
        old = (video.web_file, video.poster_file)
        video.web_file = web
        video.poster_file = poster if os.path.exists(poster_path) else ''
        video.duration = duration
        video.status = SiteVideo.READY
        video.save()
        for name in old:
            _remove(name)
        log.info('videos: %s ready (%s)', video.id, web)
    except Exception as exc:  # noqa: BLE001 - the reason goes on the row for /videos/ to show
        for path in (part, web_path, poster_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        video.status, video.error = SiteVideo.FAILED, str(exc)[:2000]
        video.save(update_fields=['status', 'error', 'updated_at'])
        log.warning('videos: %s failed: %s', video.id, exc)
    return video


def delete(video):
    """Take a video off the site and out of the list. The original goes to the trash, kept TRASH_DAYS."""
    _remove(video.web_file)
    _remove(video.poster_file)
    if os.path.exists(video.source):
        trash = os.path.join(os.path.dirname(video.source), TRASH)
        os.makedirs(trash, mode=0o2750, exist_ok=True)
        shutil.move(video.source, os.path.join(trash, os.path.basename(video.source)))
    video.delete()


def empty_trash():
    trash = os.path.join(settings.CHAT_FILES_DIR, 'upload', TRASH)
    cutoff = time.time() - TRASH_DAYS * 86400
    try:
        names = os.listdir(trash)
    except FileNotFoundError:
        return 0
    removed = 0
    for name in names:
        path = os.path.join(trash, name)
        if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            os.remove(path)
            removed += 1
    return removed
