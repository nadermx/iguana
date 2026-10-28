"""Make the web copies of videos uploaded for the site (catalog/videos.py), one at a time.

    manage.py process_videos            # everything waiting, then empty trash older than 30 days

Run every minute by cron under `flock -n`, so a second run never starts while one is transcoding. That is also why
a row left in `processing` is reset here: with the lock held, nothing else can be working on it, so it was cut off
(a reboot, a deploy) and simply starts again.
"""
from django.core.management.base import BaseCommand

from catalog import videos
from catalog.models import SiteVideo


class Command(BaseCommand):
    help = 'Transcode uploaded site videos into web copies with posters'

    def handle(self, *args, **opts):
        SiteVideo.objects.filter(status=SiteVideo.PROCESSING).update(status=SiteVideo.PENDING)
        done = 0
        while True:
            video = SiteVideo.objects.filter(status=SiteVideo.PENDING).order_by('updated_at').first()
            if video is None:
                break
            videos.process(video)
            self.stdout.write(f'{video.id} {video.status} {video.error[:200]}')
            done += 1
        removed = videos.empty_trash()
        if done or removed:
            self.stdout.write(f'processed {done}, removed {removed} from the trash')
