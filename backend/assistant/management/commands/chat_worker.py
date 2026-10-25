"""The loop behind /chat/: take the oldest queued turn, run it through Claude Code, repeat.

Runs as supervisor program `iguana:iguana-chat` (ansible/files/supervisor.conf.j2), one at a time on purpose: a
second agent working in the same checkout at the same moment would trample the first one's edits.

It restarts itself between turns when a deploy has changed the code, rather than being restarted BY the deploy,
because the deploy is usually running inside one of its turns and killing the worker would kill the deploy.
"""

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from assistant.models import Turn
from assistant.runner import run_turn

DEPLOYED_MARKER = Path(settings.BASE_DIR).parent / 'DEPLOYED_COMMIT'


def _marker():
    try:
        return DEPLOYED_MARKER.stat().st_mtime
    except OSError:
        return None


def claim_next():
    with transaction.atomic():
        turn = (Turn.objects.select_for_update(skip_locked=True, of=('self',)).filter(status=Turn.QUEUED)
                .order_by('created_at', 'pk').first())
        if turn is None:
            return None
        turn.status, turn.started_at = Turn.RUNNING, timezone.now()
        turn.save(update_fields=['status', 'started_at'])
    return Turn.objects.select_related('conversation').get(pk=turn.pk)


class Command(BaseCommand):
    help = 'Run queued /chat/ turns through Claude Code, one at a time.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Run at most one turn and exit (tests, debugging).')

    def handle(self, *args, once=False, **options):
        # Whatever was running when the last worker died did not finish, and nothing else will finish it.
        Turn.objects.filter(status=Turn.RUNNING).update(
            status=Turn.FAILED, error='Interrupted: the chat worker restarted mid-turn.', finished_at=timezone.now())
        started_with = _marker()
        while True:
            turn = claim_next()
            if turn is not None:
                self.stdout.write(f'turn {turn.pk} started')
                run_turn(turn)
                self.stdout.write(f'turn {turn.pk} {Turn.objects.get(pk=turn.pk).status}')
            if once:
                return
            if _marker() != started_with:
                self.stdout.write('new code deployed; exiting so supervisor starts the new worker')
                return
            if turn is None:
                time.sleep(2)
