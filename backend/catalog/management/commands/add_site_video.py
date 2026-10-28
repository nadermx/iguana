"""Put a video file the /chat/ agent made onto /videos/ (an "edit by instruction" result).

    iguana-manage add_site_video /tmp/iguana-edit-<id>-1.mp4 --parent <video id> --title "..." --title-es "..."

The file is copied in (the agent works as `claude`, this runs as the app user), stored beside the other uploads,
and gets a web copy like any of them. It is NOT put on the site: the owner ticks that on /videos/.
"""
import os
import shutil
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import get_valid_filename

from catalog import videos
from catalog.models import SiteVideo


class Command(BaseCommand):
    help = 'Add a video file to /videos/ as an AI edit of another video'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--parent', default='')
        parser.add_argument('--title', default='')
        parser.add_argument('--title-es', default='')
        parser.add_argument('--comedian', default='')

    def handle(self, *args, **opts):
        src = opts['path']
        if not os.path.isfile(src):
            raise CommandError(f'No such file: {src}')
        if not videos.is_video(src):
            raise CommandError('That does not look like a video file (mp4, mov, webm...).')
        parent = SiteVideo.objects.filter(pk=opts['parent']).first() if opts['parent'] else None
        if opts['parent'] and parent is None:
            raise CommandError(f'No video with id {opts["parent"]}')
        folder = os.path.join(settings.CHAT_FILES_DIR, 'upload', 'edits')
        os.makedirs(folder, mode=0o2750, exist_ok=True)
        name = get_valid_filename(os.path.basename(src))[-120:]
        dest = os.path.join(folder, f'{datetime.now():%Y%m%d-%H%M%S}__{name}')
        shutil.copyfile(src, dest)
        os.chmod(dest, 0o640)
        video = SiteVideo.objects.create(
            source=dest, original_name=name, kind=SiteVideo.EDIT, parent=parent,
            comedian=opts['comedian'] or (parent.comedian if parent else ''),
            title=opts['title'] or (f'{parent} (edited)' if parent else name)[:160],
            title_es=opts['title_es'], size=os.path.getsize(dest))
        self.stdout.write(f'added {video.id}: it appears on /videos/ in a minute or two, once its web copy is made')
