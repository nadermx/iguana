"""Runs one chat turn through Claude Code and writes what happens onto the `Turn` row as it goes.

The command is `iguana-agent-run` under sudo as the `claude` user (ansible/files/agent/), which prints Claude
Code's `--output-format stream-json`: one JSON object per line. Assistant text becomes the reply, each tool call
becomes one line of activity, and the closing `result` event carries the final answer, or the error when there
is no answer (not signed in, usage limit reached).

A failure does not end the turn by itself. `recover` reads the error and puts the turn back in the queue: a
glitch (API overload, network, the worker restarting mid-turn, any other error) is retried up to MAX_RETRIES
times, and the retry tells the agent what went wrong so it checks what is already done and fixes what it can;
a signed-out account waits for someone to sign it back in (the worker checks every minute, and the first
turn to hit it mails CHAT_ALERT_EMAILS); a usage limit waits for the reset. Only the owner's Stop, the hour
cap and running out of retries end a turn as failed.
"""

import json
import logging
import queue
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Turn

DEFAULT_COMMAND = ['sudo', '-n', '-u', 'claude', '-H', '/usr/local/bin/iguana-agent-run']
TURN_TIMEOUT = 60 * 60
FLUSH_EVERY = 1.5
MAX_ACTIVITY = 400
MAX_RETRIES = 3
RETRY_DELAYS = (30, 120, 600)  # seconds before retry 1, 2, 3
LIMIT_WAIT = 30 * 60  # when a usage limit gives no reset time, look again after this long

log = logging.getLogger(__name__)

AUTH_ERRORS = re.compile(r'oauth|/login|not logged in|log ?in again|invalid api key|authenticat|unauthori[sz]ed'
                         r'|\b401\b|token (has )?(expired|revoked)', re.I)
LIMIT_ERRORS = re.compile(r'usage limit|limit reached|rate limit|\b429\b|too many requests|out of (extra )?usage', re.I)


def classify(error):
    """What kind of failure an error text is: 'auth', 'limit', 'timeout' or 'other' (retried)."""
    error = str(error or '')
    if error.startswith('Stopped after '):
        return 'timeout'
    if AUTH_ERRORS.search(error):
        return 'auth'
    if LIMIT_ERRORS.search(error):
        return 'limit'
    return 'other'


def limit_reset(error, now=None):
    """When a usage limit lifts. Claude Code has written it as `...|<unix seconds>`; otherwise half an hour on."""
    now = now or timezone.now()
    match = re.search(r'\|(\d{10})\b', str(error or ''))
    if match:
        at = datetime.fromtimestamp(int(match.group(1)), tz=dt_timezone.utc)
        if now < at < now + timedelta(days=8):
            return at + timedelta(seconds=60)
    return now + timedelta(seconds=LIMIT_WAIT)


def agent_prompt(turn):
    """What goes to Claude on stdin. A retry carries the error, so the agent picks up the work instead of
    starting over blind, and fixes the cause when it is something on our side."""
    if not turn.attempts or not turn.error:
        return turn.prompt
    return (f'[Automatic retry {turn.attempts} of {MAX_RETRIES}. Your previous attempt at the message below '
            f'stopped with this error: {_short(turn.error, 600)}\n'
            'Part of the work may already be done. Check the current state first (git status, the live site, '
            'the database) rather than repeating anything. If the error came from our code, the server or a '
            'tool, fix the cause, then finish the request and say briefly what went wrong.]\n\n' + turn.prompt)


def auth_ok(command=None):
    """Whether Claude Code on the server is signed in. False only on a clear "no"; anything unexpected is
    treated as signed in, so a broken check cannot hold the queue forever (the turn itself will tell)."""
    command = (command or agent_command()) + ['--auth-status']
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=60)
        status = json.loads(done.stdout or '{}')
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return True
    return bool(status.get('loggedIn', True)) if isinstance(status, dict) else True


SIGN_IN_CODE = re.compile(r'^[A-Za-z0-9_.-]{20,}(#[A-Za-z0-9_.-]{8,})?$')


def looks_like_sign_in_code(prompt):
    return bool(SIGN_IN_CODE.match((prompt or '').strip()))


def submit_sign_in_code(code, command=None):
    """Hand a pasted sign-in code to the waiting `claude setup-token` (iguana-agent-run --auth-code)."""
    command = (command or agent_command()) + ['--auth-code']
    try:
        done = subprocess.run(command, input=code.strip(), capture_output=True, text=True, timeout=90)
        return bool(json.loads(done.stdout or '{}').get('ok'))
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
        return False


def _alert_signed_out(error):
    recipients = list(getattr(settings, 'CHAT_ALERT_EMAILS', []) or [])
    if not recipients:
        return
    body = ('The /chat/ agent on the Iguana Comedy server cannot reach Claude: the club\'s account is signed out.\n\n'
            f'Claude Code said: {error}\n\n'
            'Messages wait in the queue and run by themselves once it is signed in again. The lasting fix is a '
            'long-lived token: on the server, `sudo -iu claude claude setup-token`, then save the token it prints '
            'to /home/claude/.claude-oauth-token (mode 600). See docs/chat-agent.md.\n')
    try:
        send_mail('[iguana] /chat/ agent is signed out of Claude', body, settings.DEFAULT_FROM_EMAIL, recipients)
    except Exception:  # noqa: BLE001 - the alert must not take the worker down
        log.exception('chat: could not mail the signed-out alert')


def recover(turn_id, error, now=None):
    """Put a failed attempt back in the queue when it can succeed later; fail it when it cannot.
    Returns the status the turn ends up in."""
    now = now or timezone.now()
    turn = Turn.objects.get(pk=turn_id)
    kind = classify(error)
    update = {'error': error, 'finished_at': None, 'started_at': None}
    if kind == 'auth':
        first = not Turn.objects.filter(status=Turn.QUEUED, notice='signed_out').exclude(pk=turn_id).exists()
        Turn.objects.filter(pk=turn_id).update(status=Turn.QUEUED, notice='signed_out', retry_at=None, **update)
        if first:
            _alert_signed_out(error)
        return Turn.QUEUED
    if kind == 'limit':
        Turn.objects.filter(pk=turn_id).update(status=Turn.QUEUED, notice='limit', retry_at=limit_reset(error, now),
                                               **update)
        return Turn.QUEUED
    if kind == 'other' and turn.attempts < MAX_RETRIES:
        delay = RETRY_DELAYS[min(turn.attempts, len(RETRY_DELAYS) - 1)]
        Turn.objects.filter(pk=turn_id).update(status=Turn.QUEUED, notice='retry', attempts=turn.attempts + 1,
                                               retry_at=now + timedelta(seconds=delay), **update)
        return Turn.QUEUED
    Turn.objects.filter(pk=turn_id).update(status=Turn.FAILED, notice='', retry_at=None, error=error, finished_at=now)
    return Turn.FAILED


def agent_command():
    return list(getattr(settings, 'CHAT_AGENT_COMMAND', DEFAULT_COMMAND))


def _short(text, limit=160):
    text = ' '.join(str(text or '').split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def describe_tool(name, args):
    """One readable line for a tool call: what a person would want to see scroll past."""
    args = args if isinstance(args, dict) else {}
    if name == 'Bash':
        return f"Bash: {_short(args.get('description') or args.get('command'))}"
    for key in ('file_path', 'path', 'pattern', 'url', 'query', 'description'):
        if args.get(key):
            return f'{name}: {_short(args[key])}'
    return name


class TurnState:
    """What the stream has said so far. Pure, so the parsing is testable without a process."""

    def __init__(self):
        self.texts = []
        self.activity = []
        self.result = None
        self.error = ''
        self.cost = None
        self._tool_index = {}

    @property
    def reply(self):
        return self.result if self.result is not None else '\n\n'.join(t for t in self.texts if t.strip())

    def feed(self, line):
        try:
            event = json.loads(line)
        except (TypeError, ValueError):
            return
        kind = event.get('type')
        if kind == 'assistant':
            for block in (event.get('message') or {}).get('content') or []:
                if block.get('type') == 'text':
                    self.texts.append(block.get('text') or '')
                elif block.get('type') == 'tool_use' and len(self.activity) < MAX_ACTIVITY:
                    self._tool_index[block.get('id')] = len(self.activity)
                    self.activity.append({'kind': 'tool', 'text': describe_tool(block.get('name'), block.get('input'))})
        elif kind == 'user':
            content = (event.get('message') or {}).get('content')
            for block in content if isinstance(content, list) else []:
                if block.get('type') == 'tool_result' and block.get('is_error'):
                    index = self._tool_index.get(block.get('tool_use_id'))
                    if index is not None:
                        self.activity[index]['error'] = True
        elif kind == 'result':
            if event.get('is_error') or event.get('subtype') not in (None, 'success'):
                self.error = _short(event.get('result') or event.get('subtype') or 'Claude Code reported an error', 2000)
            elif isinstance(event.get('result'), str):
                self.result = event['result']
            try:
                self.cost = Decimal(str(event['total_cost_usd'])).quantize(Decimal('0.0001'))
            except (KeyError, InvalidOperation, TypeError):
                pass


def _pump(stream, lines):
    for line in iter(stream.readline, ''):
        lines.put(line)
    lines.put(None)


def run_turn(turn, command=None, timeout=TURN_TIMEOUT):
    """Run `turn` to the end. Never raises for an agent failure: the row says what happened."""
    state = TurnState()
    command = (command or agent_command()) + [str(turn.conversation.session_id)]
    stderr_tail = []
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, bufsize=1)
    except OSError as exc:
        _finish(turn, state, Turn.FAILED, f'Could not start the agent: {exc}')
        return
    process.stdin.write(agent_prompt(turn))
    process.stdin.close()
    lines = queue.Queue()
    threading.Thread(target=_pump, args=(process.stdout, lines), daemon=True).start()
    threading.Thread(target=lambda: stderr_tail.extend(process.stderr.read().splitlines()[-20:]),
                     daemon=True).start()

    started, flushed, stopped, ended = time.monotonic(), 0.0, False, False
    try:
        while not ended:
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                line = ''
            if line is None:
                ended = True
            elif line:
                state.feed(line)
            now = time.monotonic()
            if ended or now - flushed >= FLUSH_EVERY:
                flushed = now
                Turn.objects.filter(pk=turn.pk).update(reply=state.reply, activity=state.activity)
                if not stopped and Turn.objects.filter(pk=turn.pk, stop_requested=True).exists():
                    stopped = True
                    process.terminate()
            if not stopped and now - started > timeout:
                stopped = True
                state.error = f'Stopped after {timeout // 60} minutes.'
                process.terminate()
    except BaseException:
        # The database went away mid-turn (or worse): never leave Claude running unattended in the checkout.
        process.terminate()
        raise
    try:
        code = process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        code = process.wait()

    if Turn.objects.filter(pk=turn.pk, stop_requested=True).exists():
        _finish(turn, state, Turn.STOPPED, state.error)
    elif state.error or (code != 0 and state.result is None):
        detail = state.error or '\n'.join(stderr_tail[-5:]) or f'The agent exited with status {code}.'
        _finish(turn, state, Turn.FAILED, detail)
        recover(turn.pk, detail)
    else:
        _finish(turn, state, Turn.DONE, '')


def _finish(turn, state, status, error):
    Turn.objects.filter(pk=turn.pk).update(status=status, reply=state.reply, activity=state.activity,
                                           error=error or '', cost_usd=state.cost, finished_at=timezone.now(),
                                           notice='', retry_at=None)
