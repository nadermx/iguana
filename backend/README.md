# Iguana Comedy backend

Django replacement for the Kintana workspace that iguanacomedy.com was built on. It serves the same HTTP
API paths `@kintana/sdk` calls, so the Astro site runs unchanged: point `PUBLIC_KINTANA_BASE_URL` at this
backend and set `PUBLIC_KINTANA_API_KEY` to one of `PUBLIC_API_KEYS`.

## What it covers

| Kintana feature | Here |
| --- | --- |
| Events, venues, comedians, store listings (`/api/public/v1/...`) | `api/public_views.py`, managed in `/admin/` |
| Contact / perform / hotels forms (`endpoints/<slug>/submit`) | `FormSubmission` rows, emailed to `NOTIFY_EMAILS` |
| Fan sign-in (magic link + 6-digit code) | `api/fan_views.py`, signed session tokens |
| Memberships: plans, status, codes, credit transfers, Stripe subscribe / one-off / billing portal | `api/fan_views.py`, `sales/` |
| Ticket checkout widget (`/_t/k.js` + `/embed/event/<id>` iframe) | `api/embed_views.py`, `templates/embed/` |
| Order page with QR codes, door check-in for staff | `/orders/<token>/`, `/checkin/<token>/` |
| Stripe webhooks | `/api/stripe/webhook` (`payment_intent.succeeded`, `customer.subscription.*`) |
| Pageview / event ingest | `crm.TrackedEvent` |
| CRM: contacts, lists, campaign history, inbox history | imported from the export, read-only history in admin |

There is no membership on sale any more (the plan is inactive and `members_eligible` is off on every event), so
the member pricing below is dormant code kept under test.

Members get `free_tickets_per_order` free tickets (priciest first) on events with `members_eligible`,
then `guest_discount_percent` off the rest. Member pricing only applies when the checkout email matches
the signed-in member.

## Local development

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config_example.py config.py        # set DEBUG=True, SITE_URLS, keys; EMAIL_BACKEND console for local
.venv/bin/python manage.py migrate
.venv/bin/python manage.py import_kintana_export ~/iguana-migration/export
.venv/bin/python manage.py seed_site_defaults
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Then in the repo root `.env` and `.dev.vars`:

```
PUBLIC_SITE_URL=http://127.0.0.1:4321
PUBLIC_KINTANA_API_KEY=<a key from config.PUBLIC_API_KEYS>
PUBLIC_KINTANA_BASE_URL=http://127.0.0.1:8000
```

and `npm run dev`. With `DEBUG=True` and no Stripe keys the checkout shows a "simulate payment" button, and
sign-in emails print to the runserver console.

Tests: `.venv/bin/python manage.py test api`

## Data sources

- `import_kintana_export <folder>`: the CSV export Kintana handed over (contacts, orders, tickets, memberships,
  lists, campaign recipients, inbox, events). Contains customer personal data: keep the CSVs out of git.
- Comedians, venue details, event posters and merch were not in the export and are recovered from Wayback
  Machine captures of the old Framer site and the Kintana-era site.

## Production

Single VPS on the VPS.org `free` account: `38.86.78.36` / `2001:550:2:dd::f9:68`, Ubuntu 24.04, user `iguana`
(credentials in `~/.credentials/vpsorg/iguanacomedy/`). nginx fronts Astro (Node adapter, supervisor
`iguana:iguana-web` on :3000) and Django (gunicorn, `iguana:iguana-api` on :8001). Postgres `iguana`.

| Host | DNS | Serves |
| --- | --- | --- |
| `iguanacomedy.com` | Cloudflare, DNS-only (token `~/.credentials/cloudflare/iguanacomedy/`) | the site (canonical) |
| `www.iguanacomedy.com` | Cloudflare | 301 to apex |
| `api.iguanacomedy.com` | Cloudflare | Django API, admin, checkout, media |
| `iguanacomedy.mx`, `www.` | VPS.org (ns1-3.vps.org) | 301 to the same path on `.com` |
| `api.iguanacomedy.mx` | VPS.org | Django API (kept answering for old links) |
| `mail.iguanacomedy.mx` | VPS.org | the MX for **both** zones, SMTP STARTTLS cert; mail is sent as `no-reply@iguanacomedy.com` |

Cloudflare's `iguanacomedy.com` records must stay **DNS-only** (grey cloud): proxied records previously pointed at
Cloudflare's own IPs, which is what produced Error 1000. A pre-change backup of the zone is in the credentials folder.
Framer-era URLs (`/comedians/<slug>`, `/events/<slug>`, `/locations/<city>`, ...) 301 via `src/lib/legacy-paths.ts`.

```bash
cd ansible
ansible-playbook deploy.yml                    # sync code from this checkout, build, restart, apply mail.yml
ansible-playbook deploy.yml --tags all,certs   # also issue any missing certificates from cert_sets
ansible-playbook mail.yml                      # Postfix + OpenDKIM only
ansible-playbook email_check.yml               # end-to-end mail test (see below)
```

### Email

`mail.yml` follows the fleet golden standard: direct delivery, DKIM selector `mail`, MX `mail.iguanacomedy.mx`
with a Let's Encrypt cert for STARTTLS, SPF `-all`, DMARC `p=reject` with `rua` to the local `dmarc` mailbox.
It serves every zone in `mail_zones` from that one host: `iguanacomedy.mx` and `iguanacomedy.com`, each with
its own DKIM key (`/etc/opendkim/keys/<zone>/`) and its own MX, SPF, DKIM and DMARC records. `.com` mail moved
off Kintana on 2026-09-15; the Kintana MX records and the leftover leadconnector/mailgun SPF record were
removed then (two SPF records on one name is a permerror, which fails DMARC on a `p=reject` domain).

Addresses come from `mail_human_aliases` (`hello`, `info`, `bills`, `andrew`, `john`, and Will Slater's old `will`
and `will.slater`, kept so mail still sent to him reaches the team), which deliver to the
local `inbox` user (`sudo mail -f /var/mail/inbox`) **and** forward to every address in `mail_forwards`.
Role/DSN addresses (`noreply`, `no-reply`, `postmaster`, `abuse`, `mailer-daemon`) deliver locally only, so
bounce noise stays off the forwards. Nothing forwards *instead* of delivering: the local copy is what survives
if a forward is rejected. There is no catch-all, so any other address is rejected at RCPT with 550.

`email_check.yml` asserts on content: public DNS values and forward-confirmed PTR (v4 + v6), per zone the MX,
a **single** SPF record, the published DKIM key against the key on disk, and DMARC with `rua`; plus the
STARTTLS certificate name, open-relay refusal, inbound delivery to `hello@` in every zone with `status=sent`
on each forward leg tracked by queue ID, per-message `status=sent` outbound tracked by Message-ID, and
SPF/DKIM `pass` from `check-auth@verifier.port25.com` (its report is read back from the local inbox). Send a
one-off test with `venv/bin/python manage.py send_test_email you@example.com`.

**IPv4 is on the Spamhaus PBL.** 38.86.78.0/24 returns `127.0.0.11` (ISP-maintained PBL), so Gmail answers
`550-5.7.1 ... not authorized to send email directly`. Postfix therefore sets `smtp_address_preference = ipv6`;
Gmail and most large providers accept over IPv6. Receivers without AAAA MX still see the v4 address, so the
real fix is the network owner (VPS.org / Cogent) removing the PBL listing for the range.
`ASTRO_ADAPTER=node` (`npm run build:node`) builds the Node server; the default build stays Cloudflare Pages.
