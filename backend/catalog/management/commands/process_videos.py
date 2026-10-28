"""The background work behind /videos/ (catalog/videos.py, catalog/clips.py), one thing at a time.

    manage.py process_videos            # web copies first, then one AI clip job, repeat; then empty old trash

Run every minute by cron under `flock -n`, so a second run never starts while one is working. That is also why a
row left in `processing` or `running` is reset here: with the lock held nothing else can be working on it, so it
was cut off (a reboot, a deploy) and starts again. Web copies go first because they are quick and the owner is
waiting to watch them; a clip job can take an hour on a long show, and its clips come back through the same loop.
"""
import os

from django.core.management.base import BaseCommand

from catalog import clips, videos
from catalog.models import ClipJob, SiteVideo


class Command(BaseCommand):
    help = 'Make web copies of uploaded site videos, and run AI clip jobs'

    def handle(self, *args, **opts):
        os.nice(10)  # transcription runs in this process; ffmpeg is niced on its own
        SiteVideo.objects.filter(status=SiteVideo.PROCESSING).update(status=SiteVideo.PENDING)
        ClipJob.objects.filter(status=ClipJob.RUNNING).update(status=ClipJob.QUEUED, step='Starting again')
        done = jobs = 0
        while True:
            video = SiteVideo.objects.filter(status=SiteVideo.PENDING).order_by('updated_at').first()
            if video is not None:
                videos.process(video)
                self.stdout.write(f'{video.id} {video.status} {video.error[:200]}')
                done += 1
                continue
            job = ClipJob.objects.filter(status=ClipJob.QUEUED).order_by('created_at').first()
            if job is None:
                break
            clips.run(job)
            self.stdout.write(f'clip job {job.id} {job.status} {job.clips_made} clips {job.error[:200]}')
            jobs += 1
        removed = videos.empty_trash()
        if done or jobs or removed:
            self.stdout.write(f'processed {done}, clip jobs {jobs}, removed {removed} from the trash')
