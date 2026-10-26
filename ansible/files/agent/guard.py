#!/usr/bin/env python3
"""PreToolUse hook for the /chat/ agent (installed to /usr/local/lib/iguana-agent/guard.py, wired in by
/etc/claude-code/managed-settings.json, which the claude user's own settings cannot override).

The agent is the owner's hands: it may add users, refund an order the owner names, run campaigns, change the
site. So this is NOT a permission system. It stops the handful of things that cannot be undone and that no
chat message is a good enough reason for: rewriting the public git history, getting past the commit scanner,
destroying the database or the backups, removing these guards, and locking everyone out of the box. Anything
it blocks, the owner can still do over SSH, on purpose.

Claude Code reads exit code 2 as "blocked" and hands stderr back to the model as the reason.
"""

import json
import re
import shlex
import sys

PROTECTED_PATHS = (
    '/etc/claude-code', '/usr/local/lib/iguana-agent', '/usr/local/bin/iguana-agent-run',
    '/usr/local/sbin/iguana-agent-deploy', '/etc/sudoers', '/etc/ssh', '/var/backups/iguana',
    '/usr/local/sbin/iguana-db-backup', '/etc/cron.d/iguana-backup', '/home/claude/.gitconfig', '/home/claude/.ssh',
)
# Paths whose recursive deletion is never the fix for anything.
PRECIOUS_TREES = ('/', '/home', '/home/www', '/home/www/iguana', '/home/www/iguana/backend',
                  '/home/www/iguana/backend/media', '/var/lib/iguana', '/var/lib/iguana/chat-files',
                  '/var/lib/iguana/drop', '/var/lib/iguana/comics', '/var/backups', '/var/backups/iguana',
                  '/home/claude', '/home/claude/iguana', '/home/claude/iguana/.git', '/etc', '/usr', '/var',
                  '/var/lib/postgresql', '~', '$HOME', '.', '..', '*', '/*')

RULES = [
    (r'\bgit\b[^|;&]*\bpush\b[^|;&]*(\s(-f|--force|--force-with-lease|--mirror|--delete|-d)\b|\s\+\S|\s:\S)',
     'Force-pushing or deleting a branch rewrites the public history. Push normal commits; to undo something, '
     'commit a revert.'),
    (r'\bgit\b[^|;&]*\b(filter-branch|filter-repo)\b',
     'Rewriting git history is not something to do from the chat. If a secret or customer detail reached '
     'GitHub, tell the owner so they can deal with it.'),
    (r'--no-verify\b|\bcore\.hooksPath\b|\bGIT_HOOKS?\w*=',
     'The commit hooks keep customer data and secrets out of the public repo, so they cannot be skipped. Fix '
     'what the hook reported instead.'),
    (r'\bdropdb\b|\bdrop\s+(database|schema|table)\b|\btruncate\s+(table\s+)?\w',
     'Dropping or truncating database objects is blocked. Change rows with the Django ORM or a migration.'),
    (r'\bmanage\.py\s+(flush|sqlflush|reset_db)\b|\bmigrate\s+\w+\s+zero\b|\biguana-manage\s+(flush|sqlflush)\b',
     'Wiping the database is blocked.'),
    (r'\bufw\s+(disable|reset)\b|\bpasswd\b|\busermod\b[^|;&]*\s-L\b|\bdeluser\b|\buserdel\b',
     'Changes that could lock everyone out of the server are blocked; the owner does those over SSH.'),
    (r'\b(shutdown|poweroff|halt)\b|\bsystemctl\s+(poweroff|halt)\b',
     'Shutting the server down would take the site off line until someone restarts it by hand.'),
    (r'\bcrontab\s+-r\b', 'Removing the whole crontab is blocked; edit one line instead.'),
]


def _deny(reason):
    sys.stderr.write(f'Blocked by the server guard: {reason}\n')
    sys.exit(2)


def _touches_protected(text):
    # Reading these is fine (cat, ls, less, grep); anything that can write is not. Harmless redirections are
    # dropped first, so `ls /var/backups/iguana 2>&1` still reads as a read.
    writes = re.sub(r'\d?>\s*/dev/null|\d>&\d|&>\s*/dev/null', ' ', text)
    if not re.search(r'(\b(rm|mv|cp|tee|install|chmod|chown|chattr|truncate|ln|rsync|dd|sed\s+-i|perl\s+-[pi]'
                     r'|crontab|visudo|python3?\s+-c|bash\s+-c|sh\s+-c)\b|>)', writes):
        return None
    return next((path for path in PROTECTED_PATHS if path in text), None)


LAUNCHERS = ('sudo', 'env', 'nice', 'ionice', 'timeout', 'nohup', 'command', 'exec')


def _recursive_delete_of_precious(command):
    for part in re.split(r'[|;&]+|\$\(|`', command):
        try:
            words = shlex.split(part)
        except ValueError:
            words = part.split()
        # Walk past `sudo -u x`, `timeout 30`, `FOO=bar` and the like to the program actually being run.
        while words and words[0] != 'rm' and (words[0] in LAUNCHERS or words[0].startswith('-')
                                              or '=' in words[0] or words[0].isdigit()):
            words = words[1:]
        if not words or words[0] != 'rm':
            continue
        options = [w for w in words[1:] if w.startswith('-')]
        if not any(w == '--recursive' or (not w.startswith('--') and re.search('[rR]', w)) for w in options):
            continue
        for target in (w for w in words[1:] if not w.startswith('-')):
            if target in PRECIOUS_TREES or (target.rstrip('/') or '/') in PRECIOUS_TREES:
                return target
    return None


def check(tool, args):
    """None when the call may run, otherwise the reason it may not."""
    args = args if isinstance(args, dict) else {}
    if tool == 'Bash':
        command = str(args.get('command') or '')
        for pattern, reason in RULES:
            if re.search(pattern, command, re.IGNORECASE):
                return reason
        target = _recursive_delete_of_precious(command)
        if target:
            return f'Recursively deleting {target} is blocked.'
        path = _touches_protected(command)
        if path:
            return f'{path} holds the guardrails, the backups or the way in to the server, so it is read-only from the chat.'
        return None
    if tool in ('Edit', 'Write', 'MultiEdit', 'NotebookEdit'):
        path = str(args.get('file_path') or args.get('notebook_path') or '')
        if any(path.startswith(p) for p in PROTECTED_PATHS):
            return f'{path} holds the guardrails, the backups or the way in to the server, so it is read-only from the chat.'
        if re.search(r'/\.git/(hooks|config)$|/\.git/hooks/', path):
            return 'The git hooks and git config of the checkout are managed by ansible.'
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    reason = check(event.get('tool_name'), event.get('tool_input'))
    if reason:
        _deny(reason)


if __name__ == '__main__':
    main()
