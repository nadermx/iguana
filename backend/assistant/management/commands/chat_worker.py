"""The loop behind /chat/: take the oldest queued turn, run it through Claude Code, repeat.

Runs as supervisor program `iguana:iguana-chat` (ansible/files/supervisor.conf.j2), one at a time on purpose: a
second agent working in the same checkout at the same moment would trample the first one's edits.

It restarts itself between turns when a deploy has changed the code, rather than being restarted BY the deploy,
because the deploy is usually running inside one of its turns and killing the worker would kill the deploy.

It heals what it can by itself (assistant/runner.py `recover`): a turn cut off by a restart is resumed, a failed
attempt is retried with the error in hand, and while the Claude account is signed out the queue waits and the
worker asks Claude Code every minute whether it is back, then runs what was waiting.
"""

import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError, close_old_connections, transaction
from django.utils import timezone

from assistant.models import Turn
from assistant.runner import (MAX_RETRIES, auth_ok, looks_like_sign_in_code, run_turn, sign_in_link,
                              submit_sign_in_code)
from sales.i18n import tr

log = logging.getLogger(__name__)
AUTH_RECHECK = 60

DEPLOYED_MARKER = Path(settings.BASE_DIR).parent / 'DEPLOYED_COMMIT'


def _marker():
    try:
        return DEPLOYED_MARKER.stat().st_mtime
    except OSError:
        return None


def claim_next(now=None):
    """The oldest turn that may run now. A turn waiting for a retry or a sign-in holds back its own
    conversation (its messages stay in order) but not the others."""
    now = now or timezone.now()
    with transaction.atomic():
        queued = list(Turn.objects.select_for_update(skip_locked=True, of=('self',)).filter(status=Turn.QUEUED)
                      .order_by('created_at', 'pk'))
        seen, turn = set(), None
        for candidate in queued:
            if candidate.conversation_id in seen:
                continue
            seen.add(candidate.conversation_id)
            if candidate.notice != 'signed_out' and (candidate.retry_at is None or candidate.retry_at <= now):
                turn = candidate
                break
        if turn is None:
            return None
        turn.status, turn.started_at = Turn.RUNNING, timezone.now()
        turn.save(update_fields=['status', 'started_at'])
    return Turn.objects.select_related('conversation').get(pk=turn.pk)


def resume_interrupted(now=None):
    """Whatever was running when the last worker died did not finish. Run it again (the agent is told it was
    cut off) unless it has used its retries."""
    now = now or timezone.now()
    error = 'Interrupted: the chat worker restarted mid-turn.'
    cut_off = Turn.objects.filter(status=Turn.RUNNING)
    cut_off.filter(attempts__gte=MAX_RETRIES).update(status=Turn.FAILED, error=error, notice='', retry_at=None,
                                                     finished_at=now)
    for turn in cut_off.filter(attempts__lt=MAX_RETRIES):
        Turn.objects.filter(pk=turn.pk).update(status=Turn.QUEUED, error=error, notice='retry', retry_at=now,
                                               attempts=turn.attempts + 1, started_at=None, finished_at=None)


SIGNED_IN = 'Signed in. The agent works again, and the messages that waited are running now.'
CODE_REFUSED = 'That sign-in code did not work ({0}). Open the new sign-in link on the waiting message and try again, in one go: the code expires after a few minutes.'


def refresh_sign_in_link(link=sign_in_link, new=False):
    """Show the waiting messages a link that signs the account back in. The link belongs to one waiting
    `claude setup-token`, so it is made on the server when needed (and anew after a failed code), never sent
    ahead of time: a link mailed a day earlier pointed at a session that had already ended."""
    waiting = Turn.objects.filter(status=Turn.QUEUED, notice='signed_out')
    if not waiting.exists():
        return ''
    url = link(new=new)
    if url:
        waiting.update(sign_in_url=url)
    return url


def take_sign_in_code(submit=submit_sign_in_code, link=sign_in_link, now=None):
    """While the account is signed out, a message that is nothing but a sign-in code is the owner finishing the
    sign-in, not a task: hand it to the waiting setup-token, answer it, never run it."""
    now = now or timezone.now()
    for turn in Turn.objects.filter(status=Turn.QUEUED, notice='signed_out').order_by('created_at', 'pk'):
        if not looks_like_sign_in_code(turn.prompt):
            continue
        ok, why = submit(turn.prompt)
        if ok:
            reply = tr('en', SIGNED_IN) + '\n\n' + tr('es', SIGNED_IN)
        else:
            log.warning('chat: sign-in code refused: %s', why)
            reply = tr('en', CODE_REFUSED, why or '?') + '\n\n' + tr('es', CODE_REFUSED, why or '?')
        Turn.objects.filter(pk=turn.pk).update(status=Turn.DONE if ok else Turn.FAILED, notice='', reply=reply,
                                               error='', sign_in_url='', prompt='(sign-in code)', finished_at=now)
        if not ok:
            refresh_sign_in_link(link=link, new=True)
        return ok
    return False


def release_signed_out(check=auth_ok, now=None):
    """Once Claude Code answers that it is signed in, the turns that waited for it run. Released as a counted
    retry, so an error that only LOOKS like a sign-in problem cannot loop."""
    waiting = Turn.objects.filter(status=Turn.QUEUED, notice='signed_out')
    if not waiting.exists() or not check():
        return 0
    now = now or timezone.now()
    released = 0
    for turn in waiting:
        if turn.attempts >= MAX_RETRIES:
            Turn.objects.filter(pk=turn.pk).update(status=Turn.FAILED, notice='', finished_at=now)
            continue
        Turn.objects.filter(pk=turn.pk).update(notice='retry', retry_at=now, attempts=turn.attempts + 1,
                                               sign_in_url='')
        released += 1
    return released


class Command(BaseCommand):
    help = 'Run queued /chat/ turns through Claude Code, one at a time.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Run at most one turn and exit (tests, debugging).')

    def handle(self, *args, once=False, **options):
        resume_interrupted()
        started_with, auth_checked = _marker(), 0.0
        while True:
            try:
                if time.monotonic() - auth_checked >= AUTH_RECHECK:
                    auth_checked = time.monotonic()
                    # Just signed in by a pasted code: run what waited without trusting `auth status` to agree
                    # (a token sign-in may not show there; a turn that still cannot sign in just waits again).
                    signed_in = take_sign_in_code()
                    if release_signed_out(check=(lambda: True) if signed_in else auth_ok):
                        self.stdout.write('Claude is signed in again; running the turns that waited')
                    else:
                        refresh_sign_in_link()
                turn = claim_next()
                if turn is not None:
                    self.stdout.write(f'turn {turn.pk} started (attempt {turn.attempts + 1})')
                    run_turn(turn)
                    self.stdout.write(f'turn {turn.pk} {Turn.objects.get(pk=turn.pk).status}')
            except OperationalError:
                # Postgres restarting (the nightly backup, an upgrade) used to crash the worker and fail the turn
                # it was on. Wait for the database instead.
                log.warning('chat worker: database unavailable, waiting', exc_info=True)
                close_old_connections()
                time.sleep(5)
                try:
                    resume_interrupted()  # the turn the outage cut off, if it was mid-run
                except OperationalError:
                    pass
                continue
            if once:
                return
            if _marker() != started_with:
                self.stdout.write('new code deployed; exiting so supervisor starts the new worker')
                return
            if turn is None:
                time.sleep(2)
