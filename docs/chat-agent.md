# /chat/: the Claude Code instance that runs the site

Set up 2026-10-25 at the owner's request: one person (the owner) talks to a Claude Code instance on the VPS
through https://iguanacomedy.com/chat/, and it can do anything the owner could do: change code and layout,
add shows and users, refund an order the owner names, run ad campaigns, send mail. It is billed to the club's
own Claude subscription, signed in on the server as the unix user `claude`.
The account is `hello@iguanacomedy.com` (Pro, signed in 2026-10-28). Its sign-in mail and the SMS codes,
forwarded from Andrew's phone through phone-leash, arrive at hello@, so a re-login can be finished from the
server: `sudo -iu claude claude auth login --email hello@iguanacomedy.com` in tmux, open the printed link (a
headless browser is stopped by Cloudflare, so a person does this step), and paste the code back.

## How a message travels

1. `/chat/` (`backend/api/chat_views.py`, `templates/embed/chat.html`) is Django, reached through nginx on the
   main domain like `/stats/`. **Superusers only** (`is_owner`); anyone else is sent to `/admin/login/`, and the
   JSON endpoints answer 403. The page polls every 2 seconds, never pushes (three sync gunicorn workers).
2. A message becomes an `assistant.Turn` (queued). The supervisor program `iguana:iguana-chat` runs
   `manage.py chat_worker`, which claims the oldest queued turn and runs
   `sudo -u claude /usr/local/bin/iguana-agent-run <session uuid>` with the prompt on stdin.
3. `iguana-agent-run` runs `claude -p --output-format stream-json --permission-mode bypassPermissions` in
   `/home/claude/iguana`, resuming the conversation's session, with `SERVER.md` appended to the system prompt.
4. `assistant/runner.py` turns the stream into the reply and one line of activity per tool call, saved on the
   row every 1.5 seconds. Stop sets `stop_requested`; the worker terminates the process. A turn is capped at an
   hour. If the worker dies mid-turn, the next one marks that turn failed.
5. One turn at a time, across all conversations, because they share one checkout.

The full transcript (prompts, replies, every tool call) is in Postgres, so it is in the nightly backup and
readable at `/admin/assistant/conversation/`.

## What it can do, and the guardrails that remain

The owner asked for it to be able to do everything, so `claude` has passwordless sudo, reads `config.py`
through `iguana-manage` (`manage.py` against the live app, logged to `journalctl -t iguana-agent-manage`), and
has the Meta and TikTok credentials under `/home/claude/.credentials/`. The guardrails are for mistakes that
cannot be undone, not for limiting the owner:

| Guardrail | Where | Stops |
| --- | --- | --- |
| PreToolUse hook | `ansible/files/agent/guard.py`, wired by `/etc/claude-code/managed-settings.json` (managed settings outrank anything the agent can write) | force-push, branch deletion, history rewrites, `--no-verify`, dropping or truncating the database, `flush`, recursive deletes of the app, media, backups or checkout, writes to the guardrails, sudoers, ssh, the backup job, `ufw disable`, shutdown |
| Commit scanner | `pii_scan.py`, run by system-wide git hooks (`core.hooksPath`) | any email or phone belonging to a real person in the database, new webmail addresses, secrets (Stripe, Meta, GitHub, Anthropic, private keys). Fails closed if it cannot read the database |
| Deploy script | `iguana-agent-deploy` | deploying anything not pushed to GitHub, deploying over dev-box work that was never pushed, untested code (full backend suite, missing migrations, scripts/tests, i18n and route checks), a deploy with no database dump first, a broken site (health check, automatic rollback) |
| Instructions | `SERVER.md` | refunds or cancellations nobody asked for, bulk sends without a dry run, customer data in replies to strangers, prompt injection from customer-written data |

Anything the hook blocks, the owner can still do over SSH, deliberately.

## Deploys from two places

Production is deployed by `ansible-playbook deploy.yml` from the dev box (rsync of the local checkout) AND by
`iguana-agent-deploy` on the server (from GitHub). They agree through `/home/www/iguana/DEPLOYED_COMMIT`
(`<sha> devbox|agent <time> [dirty unpushed]`):

- `deploy.yml` refuses when GitHub has commits the local checkout lacks (`git pull` first, or
  `-e allow_behind=true` knowingly), and writes the marker, flagged `dirty`/`unpushed` when it is.
- `iguana-agent-deploy` refuses to overwrite a marker that is not a pushed commit, or a live commit the
  target does not contain, unless given `--allow-unknown-live`.
- Infrastructure (nginx, supervisor, cron, `config.py`, mail) only changes through ansible. The agent's deploy
  email says so when a commit touches `ansible/`.

Every agent deploy dumps the database to `/var/backups/iguana/predeploy/` (newest 20 kept) and emails
`john@iguanacomedy.com` the commit list.

## Operating it

```bash
ansible-playbook agent.yml                                    # (re)install the agent side; deploy.yml imports it
ssh -t iguana@38.86.78.36 sudo -iu claude claude              # sign in: /login, then /exit (one time)
ansible web --become -m shell -a "supervisorctl status iguana:iguana-chat; tail -20 /var/log/iguana/chat.err.log" </dev/null
ansible web --become -m shell -a "journalctl -t iguana-agent-deploy -n 50 --no-pager" </dev/null
```

To switch it off: `supervisorctl stop iguana:iguana-chat` (messages queue and wait). To cut its GitHub access:
delete the "iguana server /chat/ agent" deploy key in the repo settings. To sign it out:
`sudo -iu claude claude` then `/logout`.

Usage counts against the club's subscription; when the limit is reached a turn fails with Claude Code's own
message, shown in the chat, and works again when the limit resets.
