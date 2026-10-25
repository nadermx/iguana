"""Runs one chat turn through Claude Code and writes what happens onto the `Turn` row as it goes.

The command is `iguana-agent-run` under sudo as the `claude` user (ansible/files/agent/), which prints Claude
Code's `--output-format stream-json`: one JSON object per line. Assistant text becomes the reply, each tool call
becomes one line of activity, and the closing `result` event carries the final answer, or the error when there
is no answer (not signed in, usage limit reached).
"""

import json
import queue
import subprocess
import threading
import time
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils import timezone

from .models import Turn

DEFAULT_COMMAND = ['sudo', '-n', '-u', 'claude', '-H', '/usr/local/bin/iguana-agent-run']
TURN_TIMEOUT = 60 * 60
FLUSH_EVERY = 1.5
MAX_ACTIVITY = 400


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
    process.stdin.write(turn.prompt)
    process.stdin.close()
    lines = queue.Queue()
    threading.Thread(target=_pump, args=(process.stdout, lines), daemon=True).start()
    threading.Thread(target=lambda: stderr_tail.extend(process.stderr.read().splitlines()[-20:]),
                     daemon=True).start()

    started, flushed, stopped, ended = time.monotonic(), 0.0, False, False
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
    else:
        _finish(turn, state, Turn.DONE, '')


def _finish(turn, state, status, error):
    Turn.objects.filter(pk=turn.pk).update(status=status, reply=state.reply, activity=state.activity,
                                           error=error or '', cost_usd=state.cost, finished_at=timezone.now())
