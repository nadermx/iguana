# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Iguana Comedy (stand-up promoter, Quintana Roo, Mexico). Two apps in one repo: a bilingual **Astro 5 SSR site**
(repo root) and a **Django backend** (`backend/`) that replaced the Kintana SaaS the site was originally built on.
Repo is **`nadermx/iguana`** (public), `origin` since 2026-10-23. It used to be `SlaterMarketing/iguana`, which
now answers 404, so a push there fails with "Repository not found". There is no private repository for this
project, which is worth knowing before writing anything into a commit: the history is world readable and git
history is not a place you can quietly delete from. Work happens on branch `backend-django`;
`main` was fast-forwarded to it on 2026-10-23 and carries the backend too, so after pushing the branch run
`git push origin backend-django:main` to keep them identical.
`gh`'s active account is not `nadermx`, so repo settings answer 404 unless run as
`GH_TOKEN=$(gh auth token -u nadermx) gh api ...`.
🚨 **No customer data, ever, including in a comment or a commit message.** A docstring naming the one
subscriber address that had bounced twice was caught on the way out on 2026-09-25 and scrubbed with
`git filter-branch` while the commits were still local. The already-published history was audited at the same
time and is clean: the only addresses in it are a public mail-test service, placeholders, and the phishing
domain. Cite a measurement without the identifier (`one address on the list`, `a Gmail recipient`), and grep
the outgoing diff AND the commit messages for `@` before pushing.

## Commands

```bash
# End to end (needs the backend on :8000 and the BUILT site on :4321, not the dev server: the account and
# checkout islands are React, and a stale Vite dep cache silently breaks hydration)
npm run build:node && node dist/server/entry.mjs &   # port 4321, env from .env
node tests/account-flow.mjs                          # register, code sign-in, magic link
node tests/reserve-flow.mjs                          # reserve a seat through the real checkout iframe

# Against production
node tests/full-sweep.mjs --staff mesero --pass "$(cat ~/.credentials/vpsorg/iguanacomedy/floor_password)"
node tests/mobile-sweep.mjs --staff mesero --pass "$(cat ~/.credentials/vpsorg/iguanacomedy/floor_password)"  # the floor console at 320-430px
node tests/open-mic-e2e.mjs [--base http://127.0.0.1:4321]   # the page the open mic ads point at, iframe included, with screenshots
node tests/show-e2e.mjs --slug <slug> --price <MXN>    # a paid show: both languages, listings, checkout up to a LIVE Stripe refusal of 4242
node tests/comic-e2e.mjs [--submit --email <addr>]    # /comic/ layout 320 to 1280 in both languages; --submit leaves a submission to delete
API_KEY=... node tests/pos-e2e.mjs                     # the POS; needs its throwaway fixtures (see the POS section)

# Offline tests for the operator scripts (no network)
python3 -m unittest discover -s scripts/tests -v

# Site (Node 20, see .node-version)
npm install
npm run dev                      # Astro dev server; needs .env + .dev.vars (copy the .example files)
npm run build                    # Cloudflare Pages build (default adapter) + scripts/verify-dist.mjs
                                 # both builds first run check-kintana-env, check-i18n and check-routes (hreflang pairs)
npm run build:node               # ASTRO_ADAPTER=node standalone server -> dist/server/entry.mjs (what production runs)
npm run start:node               # run that build
npx astro check                  # type check (pre-existing errors on Locals.brandOverrides in middleware.ts)

# Backend (Django 6, SQLite locally via config.py, Postgres in production)
# 🚨 That difference hides a whole class of bug: SQLite IGNORES select_for_update, so a lock that Postgres
# refuses outright passes every local test. `select_for_update()` beside `select_related()` across a NULLABLE
# FK is a LEFT OUTER JOIN, and Postgres answers "FOR UPDATE cannot be applied to the nullable side of an outer
# join". It 500'd the door scanner on the first real scan with 12 green tests behind it. Use
# `select_for_update(of=('self',))` when the query select_relates anything nullable.
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config_example.py config.py   # DEBUG=True, SITE_URLS, PUBLIC_API_KEYS, EMAIL_BACKEND console for local
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000
.venv/bin/python manage.py test api crm pos assistant                         # all backend tests (sales has none of its own)
.venv/bin/python manage.py test api.tests.CheckoutTests.test_member_free_tickets_then_guest_discount  # one test

# Data (one-off / re-runnable, fill blanks unless --overwrite)
.venv/bin/python manage.py import_kintana_export ~/iguana-migration/export     # client's Kintana CSV export
.venv/bin/python manage.py import_archive                                      # Wayback-recovered comedians/venues/posters/merch
.venv/bin/python manage.py seed_site_defaults                                  # form endpoints + membership plan pricing
.venv/bin/python manage.py send_test_email someone@example.com                 # mail test as DEFAULT_FROM_EMAIL

# Production (run from ansible/; inventory + group_vars/all are gitignored, secrets come from ~/.credentials)
ansible-playbook deploy.yml                    # rsync this checkout, build, migrate, restart, apply mail.yml
ansible-playbook deploy.yml --tags all,certs   # also issue missing Let's Encrypt certs listed in cert_sets
ansible-playbook email_check.yml               # end-to-end mail verification (asserts on DNS, DKIM, delivery)
```

`README.md` (rewritten 2026-10-23) is the public overview; `backend/README.md` and `docs/` are current, except
`docs/deploy-cloudflare.md` and `docs/deploy-dokploy.md`, which are earlier hosting kept for reference. Read the matching `docs/` page before working in that area: `deploy-history`, `mail`, `meta-ads`,
`tiktok-ads`, `open-mics`, `pos-and-staff-pages`, `comic-and-drop`, `chat-agent`. CLAUDE.md keeps the rules; the pages keep
the history and evidence behind them.

Local pairing: backend on `127.0.0.1:8000`, site on `127.0.0.1:4321` with `.env` / `.dev.vars` setting
`PUBLIC_KINTANA_BASE_URL=http://127.0.0.1:8000` and `PUBLIC_KINTANA_API_KEY` to a key from `config.PUBLIC_API_KEYS`.

## Architecture

### Where things live

| URL | Code |
| --- | --- |
| Public pages `/en/...`, `/es/...`, `/open-mic/` | `src/pages/{en,es}/` thin wrappers around `src/components/`, routes in `src/i18n/routes.ts` |
| `/api/public/v1/*`, `/api/fan/v1/*` | `backend/api/public_views.py`, `backend/api/fan_views.py` |
| Checkout iframe `/embed/event/<id>`, `/_t/k.js`, `/orders/<token>/`, Stripe webhook | `backend/api/embed_views.py`, `backend/templates/embed/` |
| `/pos/` (bar POS, PIN pad, printing, inventory) | `backend/pos/` (`views.py`, `api.py`, `services.py`, `views_pay.py`) |
| `/scan/`, `/checkin/<token>/` (the door) | `backend/api/door_views.py`, `backend/api/floor_views.py` |
| `/reservations/`, `/reservas/` | `backend/api/reservations_views.py` |
| `/stats/`, `/revenue/` | `backend/api/stats_views.py`, `backend/api/revenue_views.py` |
| `/comic/`, `/drop/` | `backend/api/comic_views.py`, `backend/api/drop_views.py` |
| `/chat/` (owner's Claude Code agent) | `backend/api/chat_views.py`, `backend/assistant/`, server side `ansible/agent.yml` + `ansible/files/agent/` |
| `/admin/` | Django admin on `api.iguanacomedy.com` |
| Prices, orders, demand, reminders | `backend/sales/` (`services.py`, `demand.py`, `reminders.py`, `i18n.py`) |
| Contacts, mail, ads reporting, geo | `backend/crm/` (`mail.py`, `meta_capi.py`, `tiktok_events.py`, `geo.py`) |
| Scheduled jobs | management commands, cron installed by `ansible/deploy.yml` |
| Operator scripts (ads, posters) | `scripts/` |

### The site still talks "Kintana", the backend answers it

The Astro code calls `@kintana/sdk` (vendored tarball in `vendor/`) everywhere. Rather than rewrite the site, the
Django backend implements the same HTTP contract, so only the base URL and key differ:

- `backend/api/public_views.py`: `/api/public/v1/{events,artists,venues,endpoints,store,files,site}`
- `backend/api/fan_views.py`: `/api/fan/v1/*` (magic-link sign-in, profile, tickets, memberships, redeem codes,
  credit transfers, Stripe subscribe / one-off / billing portal)
- `backend/api/embed_views.py`: `/_t/k.js` (drop-in for Kintana's tracker script), `/embed/event/<id>` (checkout
  iframe), `/orders/<token>/`, staff `/checkin/<token>/`, `/api/stripe/webhook`, `/api/ingest/*`
- `backend/api/serializers.py` produces the exact SDK JSON shapes. When the site needs a field, check the SDK
  types in `node_modules/@kintana/sdk/dist/*.d.ts` and add it there.

Auth: the site's key arrives as `Authorization: Bearer` (checked by `api_view` in `api/auth.py`); signed-in fans add
`X-Customer-Authorization: Bearer <signed token>` issued by `auth/verify`. Browser calls rely on
`api/middleware.py` CORS for `SITE_URLS`.

🚨 **An outside probe worked through checkout and sign-in on 2026-10-23** (one IP, `maxxspace.com` throwaway
inboxes, `pt<run>` addresses, names like `MassAssign`/`XSS`; the same IP hit best.free and youtgo that night). It
was NOT us. It held 39 free open mic seats and stored a dict as an email; nothing was taken over. Since then every
email in passes `sales.services.clean_email`, and sign-in emails (10/IP/hour), code guesses (10 across an address's
live codes) and free bookings (4 per IP per night, 12 per day) are capped (`api.tests.ProbeHardeningTests`). The IP
is denied in ufw. If `pentest`/`pt…@` bookings appear again, they are not a test of ours.

🚨 **There is no membership, and nothing may offer member pricing** (owner, 2026-09-24: "we don't have member
price bullshit anymore"). The plan is inactive, the one membership row ever created is cancelled and belonged
to a departed colleague, and `0009_alter_event_members_eligible` turned `members_eligible` off on all 51
events and defaulted it off for new ones. The admin no longer shows the checkbox, because a tick that promises
member pricing is a promise the checkout cannot keep, and the checkout's "Member pricing applied" note is
gone. The price path itself stays: removing it is surgery on the checkout for no gain while nobody holds a
membership, so `api.tests.CheckoutTests` still exercises it by opting a fixture in explicitly.
`api.tests.NoMembershipTests` pins the rest. What remains live is an `isMember: false` in the bootstrap and a
code comment; neither is visible to anyone.

Checkout flow: `EventCheckoutWidget.astro` renders `data-kintana-widget="event:<id>"`; `k.js` injects the iframe,
posts the fan token in, and follows `kintana-embed-checkout-success` to the order page. Prices are always
computed server-side in `sales/services.py::price_cart` (member free tickets priciest-first, then guest discount;
member pricing only when checkout email equals the signed-in member). With `DEBUG=True` and no Stripe keys the
iframe offers a simulated payment; in production without keys it refuses payment.

Backend apps: `catalog` (venues, artists, events, lineup, ticket types, store, form endpoints, site files),
`crm` (contacts, lists, campaigns, inbox history, tracked events), `sales` (orders, tickets, memberships, plans,
redeem codes, credit transfers, login tokens), `api` (views only, no models). Image fields hold either absolute
URLs or `/media/...` paths; `serializers.media()` makes them absolute with `BACKEND_URL`.

### Site structure

- `output: "server"`: every page renders per request from the API. Pages hold no data at build time.
- Routes are locale-prefixed and translated: `src/i18n/routes.ts` maps route keys to `/en/...` and `/es/...`
  slugs; always build links with `localizePath(locale, key, params)`. UI strings live in `src/i18n/ui.ts` via
  `t(locale, key, vars)`.
- `src/pages/en/**` and `src/pages/es/**` are parallel thin wrappers around shared components
  (`<EventsIndexPage locale="es" />`). A page change usually means touching both trees or the shared component.
- `src/middleware.ts`: `/` picks a locale (cookie, Accept-Language), 301s Framer-era URLs via
  `legacyRedirectTarget` in `src/lib/legacy-paths.ts`, and loads brand-image overrides from `listFiles`.
- `src/lib/kintana-env.ts` reads env from Cloudflare runtime, `process.env`, then `import.meta.env`. Public vars
  must use Astro's `PUBLIC_` prefix; `KINTANA_SECRET_API_KEY` is server-only and must never reach islands.
- React islands only where hooks are needed: contact form (`ContactFormIsland`, `useKintanaSubmit(slug)` with
  endpoint slugs `contact`, `perform-with-us`, `hotels-and-resorts`), account/sign-in, membership (Stripe
  Elements), event member offer.
- **A past show sells nothing and says what happened.** The API adds `past: {soldOut, seats, capacity}` once
  `status` is `past` (`serializers.past_summary`; `soldOut` keeps the owner's SOLD_OUT mark, `seats` is only what
  we counted). `eventSupportsOnSiteCheckout` refuses `past`, the event page puts "this show has already happened",
  AGOTADO or "It's over", and "76 of 80 tickets sold" where the form was, and past calendar rows say the same.
- Event dates come from the API as `YYYY-MM-DD` (Cancun day) and the API sets `status: "past"` by the Cancun
  calendar, so filter on status rather than comparing against the server clock (`src/lib/home-page-data.ts`).
- Static brand media (logo, city photos, hero video) is self-hosted in `public/media/`, not on Kintana.
- `astro.config.mjs` switches adapter on `ASTRO_ADAPTER=node`; the Cloudflare build keeps its `react-dom/server.edge`
  aliases, the Node build must not use them.

### Production

**Always deploy.** A change is finished when it is live on the VPS and checked there, not when it is committed:
the club is trading off this site, so nothing of value happens until production has it. Backend data changes
(a new event, seeded copy) also need their management command run on the server, because the deploy only ships
code. Anything that genuinely cannot be deployed, such as a Stripe dashboard setting, gets said out loud.

One VPS (VPS.org `free` account, 38.86.78.36, user `iguana`, creds `~/.credentials/vpsorg/iguanacomedy/`).
The app is `/home/www/iguana`; the server's venv is **`backend/venv`**, not `.venv` as locally. A one-off query:
copy a script up and `ansible all --become --become-user iguana -m shell -a "cd /home/www/iguana/backend &&
venv/bin/python manage.py shell < /tmp/q.py" </dev/null` (without `</dev/null` ansible can abort on a
non-blocking stdin).
nginx fronts supervisor programs `iguana:iguana-web` (Node, :3000) and `iguana:iguana-api` (gunicorn, :8001);
Postgres `iguana`. `iguanacomedy.com` is canonical (DNS on Cloudflare, records must stay DNS-only: proxied records
pointing at Cloudflare IPs caused the old Error 1000); `iguanacomedy.mx` 301s to it; API at
`api.iguanacomedy.com` (and `api.iguanacomedy.mx`). Admin: `https://api.iguanacomedy.com/admin/`.

- `ansible/files/nginx.conf.j2` renders TLS blocks only for certificates that exist (`cert_sets`), so redeploys
  never strip HTTPS. nginx is 1.24: use `listen 443 ssl http2`, not `http2 on`.
- 🚨 **The VM's disk is VPS.org's shared Ceph cluster.** If the site hangs with load climbing, 100% iowait and
  processes in `D` state, the app is not the cause: check `ceph health` (2026-10-09, 21:05 to 21:30 UTC, one full
  OSD froze every VPS.org guest; see `~/admin.vps.org/CLAUDE.md`). It recovers by itself once Ceph does.
- Code is rsynced from the local checkout (not git-pulled). `backend/media/` syncs add-only so server uploads survive.
  To deploy exactly a commit while the working tree has other changes, deploy from a clean worktree:
  `git worktree add --detach /tmp/x HEAD && ansible-playbook deploy.yml -e repo_root=/tmp/x -e media_src=$PWD/../backend/media`.
  🚨 Never make `backend/media` a symlink in the source tree. On 2026-09-17 that slipped past the old
  `--exclude=backend/media/` (a trailing slash matches directories only), rsync `--delete` replaced the server's media
  folder with a dangling symlink, and every event image returned 404 for about 4 minutes until it was restored from
  the local copy. The exclude is now anchored and type-agnostic (`/backend/media`), and deploy.yml asserts both the
  server path and `media_src` are real directories before syncing.
- **Backups.** `/usr/local/sbin/iguana-db-backup` (from `ansible/files/iguana-db-backup.sh`, `/etc/cron.d/iguana-backup`,
  07:20 UTC nightly) dumps Postgres to `/var/backups/iguana/daily/`, **restores it into a scratch database and
  checks seven key tables' row counts before pruning anything**, copies Sunday's dump to `weekly/` and tars
  `backend/media` to `media/`. Kept 30 days / 26 weeks / 8 weeks. Any failure prunes nothing, logs
  `journalctl -t iguana-backup` and emails `john@iguanacomedy.com`; `LAST_OK` holds the last verified run.
  The dev box pulls the folder at 03:40 local (`ansible/files/pull-iguana-backups.sh`, john's crontab) into
  `~/backups/iguana/`, never with `--delete`, keeping 90 days; errors are `ERROR iguana_backup_pull` in its
  `pull.log`. Restore: `gunzip -c <dump> | sudo -u postgres psql -d iguana` into an EMPTY database (the dump
  is `--no-owner --no-acl`, so re-grant to `iguana` afterwards).
- Mail (`ansible/mail.yml`): Postfix + OpenDKIM for every zone in `mail_zones` (`iguanacomedy.mx` and
  `iguanacomedy.com`, each with its own DKIM key under selector `mail`), one mail host `mail.iguanacomedy.mx`
  because the PTR points there. `mail_human_aliases` (hello, info, bills, andrew, john, will, will.slater) deliver to the local
  `inbox` user **and** forward to `mail_forwards`; role/DSN addresses deliver locally only; no catch-all, so
  anything else is rejected at RCPT. 38.86.78.0/24 is on the Spamhaus PBL, so Postfix prefers IPv6 (Gmail
  rejects the v4 address).

**The deploy is shaped by incidents** (`docs/deploy-history.md`), so keep these:
- 🚨 **Give any new NOT NULL column a DB default in a follow-up migration** (Postgres only). Between `migrate` and
  the worker reload, old code inserts without the column and live checkouts 500, leaving no row behind. The API
  reloads directly after migrating.
- Gunicorn reloads with `supervisorctl signal HUP`, never a hard restart; the site builds into `dist.next` and
  renames; `/_astro/` falls back to `dist.old` so a page open across a deploy still hydrates.

**The checkout's reserved height is MEASURED, so re-measure it whenever the form changes** (Stripe settings, a
field, the wallet row). `EventCheckoutWidget.astro` holds the with-wallet height per breakpoint; it was left at
the Link-era 1230px for two weeks and held 450px of empty box before snapping shut. `k.js` keeps the reserve
exactly until the checkout reports settled (card form AND wallet row drawn, 4s/10s fallbacks), never on a
momentary overshoot. The event hero's photo layer is pinned to its first painted height, because it is cropped
to cover the section the checkout sits in and every height change re-cropped it into a visible zoom.

### Everything is bilingual, always

The owner's rule: every string a visitor or customer sees exists in English and Spanish. Three guards enforce it,
and a new string should go through one of them rather than be written inline:

- **Site:** `t(locale, key)` with keys in both `ui.en` and `ui.es` (`src/i18n/ui.ts`), or a component-local
  `{ en, es }[locale]` dictionary. `t()` silently falls back to English for a missing Spanish key, so
  `scripts/check-i18n.mjs` runs before every `build`/`build:node` and fails on a missing key or mismatched `{slot}`.
  English prop defaults on shared components must be locale-aware, not English literals.
- **Backend (checkout iframe, order page, confirmation and sign-in emails, check-in, API errors):** English source
  strings go through `tr(lang, text, *params)` / `{% t lang "..." %}` / `CheckoutError('...', *params)` with Spanish
  in `backend/sales/i18n.py` (positional `{0}` slots). `api.tests.TranslationTests` scans the code for every such
  string and fails when one has no Spanish or a slot differs; it also asserts it found over 100 strings, so a broken
  scan cannot pass by matching nothing.
- **How the language travels:** the site's checkout widget sets `data-kintana-locale`, `k.js` appends `&lang=` to the
  iframe, checkout posts `lang`, and `Order.locale` stores it for the order page and email. Browser API calls add
  `X-Iguana-Locale` (`src/lib/kintana-auth.ts`), and `api.middleware.TranslateErrorsMiddleware` translates any JSON
  `{"error": ...}`. The sign-in email takes its language from the `/en/` or `/es/` redirect URL. Door check-in
  follows the staff phone's `Accept-Language`. Ticket types carry `name_es` / `description_es`, snapshotted into the
  order in the customer's language.

### Open mics and the demand nudges (detail: `docs/open-mics.md`)

- 🚨 **What is LIVE is a FREE reservation with NOTHING included**, both series (Spanish Tuesday, English Wednesday,
  doors 20:00, show 21:00): type `Free reserved seat`, 0.00, capacity 80, not pay-at-door. The `Drink, ordered in
  advance` type is inactive on every night. The paid model (50 MXN / 5 USD with a drink) is dormant code whose
  strings never render; never quote it as the economics.
- All 80 seats are reservable, so there are no walk-in seats to promise. A sold-out open mic is SHOWN on the lander
  with AGOTADO and `walkInLine()` ("not everyone who reserves turns up"), never a number and never skipped.
- 🔑 **The calendar extends itself**: a Sunday cron runs `setup_open_mics --weeks-ahead 14 --only-new` and never
  touches a night that already exists, so drafting or cancelling a holiday night sticks.
- The site finds open mics by the `open-mic` tag (`src/lib/open-mics.ts`). An open mic booking is offered the next
  paid show in that night's language (`sales.sharing.paid_show_offer`, `?ref=om-thanks` / `om-email`).
- **The demand ladder** (`sales/demand.py` counts, `src/lib/demand.ts` and `checkout.html`'s `renderDemand` word it;
  both must agree): sold out, then only N left (a FIFTH of the room capped at ten, never a flat ten), then N reserved
  recently (2 or more), then over half gone, then N of M taken from a third, then nothing.
  🚨 **The room line and the momentum line are different facts and both render** (`DemandLines.astro`); one slot
  for both hid the room's state everywhere until 2026-09-25 (`DemandNudgeTests`). Seats a guest promoter sold
  (`TicketType.sold_elsewhere`) count.

### Newsletter, city alerts and who signs up from where

- The home hero's newsletter sign-up (`NewsletterSignup.astro`, endpoint `newsletter`) joins `Newsletter`, double
  opt-in. A city with nothing coming up shows `NoEventsNearby.astro` with a sign-up that joins `City alerts: <City>`.
- Every sign-up and booking records site language, browser language, time zone and IP location (`crm/geo.py`) on the
  contact, `FormSubmission.context["visitor"]` and `Order.attribution["visitor"]`. The IP is nginx's `X-Real-IP`,
  trusted only from the local proxy. DB-IP City Lite lives at `/var/lib/iguana/dbip-city-lite.mmdb`, refreshed
  monthly; a missing file only logs a warning.

### Meta and TikTok ads

**Read `docs/meta-ads.md` before touching a campaign** (IDs, scripts, targeting, Graph API traps, and how `/stats/`
reports spend); TikTok is in `docs/tiktok-ads.md`. Operator scripts read `~/.credentials/meta/iguanacomedy/token`;
ad account `act_178760798664478`, pixel `2122037578734069`. Always:

- **The goal is full nights: 80 reservations on an open mic, 80 on a paid show.** An underfilled night with a live
  campaign is a reason to raise the budget; a lifetime budget is a CAP, so check `budget_remaining` near a show.
- 🚨 **`ACTIVE` is not evidence of spend**, at any level: ad sets say ACTIVE past their `end_time`, and an ACTIVE
  campaign spends nothing when its ad set or ads are paused. Judge by `meta-ads.py status`.
  🚨 `meta-ads.py --days N` means N+1 days; `--days 0` is today.
- **The backend reports the sale, the pixel only the visit**: `crm/meta_capi.py` and `crm/tiktok_events.py` send
  checkout and purchase events from the server. Nothing in that path may cost a booking. TikTok answers 200 with a
  non-zero `code` when it refuses, so check `code`. TikTok ad links must carry `utm_source=tiktok`.
- 🚨 **Every PAID show passes `scripts/meta-show-campaign.py --show <key> preflight` before a peso is spent**, and
  optimises on custom conversion `1670646004630204` (paid checkouts), never plain InitiateCheckout.
- 🚨 **Open mic ads point at `/open-mic/` and the server switches them** (`open_mic_ads --apply`, every 10 minutes):
  a night's ads run only on the show day and the two days before, stop when full or under an hour away, and a
  hand pause inside that window is undone. Stop it with `open_mic_ads_autopilot: false`, deploy, then
  `meta-openmic-campaigns.py pause`.
- 🚨 **No request path may call Meta.** `snapshot_ad_spend` writes `crm.AdSpend` every 15 minutes and `/stats/`
  reads rows. Reach and frequency are never summed across days (`window='WEEK'` rows hold them; sum spend over
  `window=DAY` only). Cost per seat is spend over OUR seats, never Meta's purchase count.
- 🚨 **Check the Graph API before believing any mail about the ad account**: phishing for it arrives with DKIM
  passing (`docs/mail.md`).

### The point of sale and the staff pages (detail: `docs/pos-and-staff-pages.md`)

- 🚨 **The bar runs on `/pos/`** (a Soft Restaurant clone, since 2026-09-28); `/mesas/` and `/tables/` redirect to
  it, and the old `TableOrder` models are history only. **The PIN pad is the only door**: `pos.Staff` with roles
  MESERO / CAJERO / GERENTE (labelled Mesero, Barra, Administración), five wrong PINs in 15 minutes lock the address,
  and voids, discounts, courtesy, cancel and reopen need a manager PIN. A PIN session is never a Django user.
- A waiter sees their own section and checks only (`Staff.tables`, `Staff.may_open`). Flow: map, check, ENVIAR (a
  `Comanda`, prints, takes the RECIPE out of stock once per line), CUENTA, COBRAR into the open `Shift`, CAJA corte.
  Customer QR ordering is OFF (`ONLINE_ORDERING = false` in `MenuPage.astro`).
- **Stock follows recipes** (`catalog.MenuItemIngredient`); an item with no recipe consumes nothing on purpose.
  `CheckLine.stock_deltas` records what was really taken, so a void or deleted order never invents stock. A void
  asks whether the drink was made (waste) or not (stock back).
- 🚨 **`is_staff = False` is the entire security model for the floor accounts** (`mesero`, `bar`, `door`):
  `ensure_floor_accounts` forces it every deploy and only sets the password when it differs, or every tablet is
  signed out. Logins are in `~/.credentials/vpsorg/iguanacomedy/` (`iguana` is the owner superuser).
- Staff pages: `/reservations/` (emails only for `can_see_the_money`), `/reservas/` (the door list, in Spanish),
  `/scan/` (a good scan marks the ticket in the same breath; nobody has ever been checked in, so `checked_in_at`
  says nothing about attendance), `/stats/`, `/revenue/`.
- Rules for all of these:
  - 🚨 Test at 320px (`tests/mobile-sweep.mjs`), and make Playwright text checks case-insensitive (CSS uppercases).
  - 🚨 **Poll, never push**: gunicorn has three SYNC workers, so SSE or long-poll would take the checkout down.
  - 🚨 A SOLD OUT night is still tonight's show: filter `status__in=(ACTIVE, SOLD_OUT)` (`SoldOutIsStillAShowTests`).
  - The night runs 6am to 6am (`service_start`); build "tonight" in tests from `service_start().date()` in
    `CANCUN_TZ`, never bare `timezone.now()`.
  - Money on `/stats/` is a string per currency, never a float. `sales.demand` counts `OrderItem.quantity`.
  - A `{# #}` comment is one line only; never give two context variables in one view the same name; keep the
    order screen's `serial()` request queue.

### Mail

Detail and evidence: **`docs/mail.md`**. `iguana-mail` on the server reads the local copy of every human alias
(`iguana-mail`, `show 37`, `search reservation`, `list --box dmarc`).

- Automatic sends (all Playa time): `send_show_reminders` daily 10:00 (open mics carry a give-your-seat-back link,
  paid shows do not), `send_whats_on` Monday 09:00, `send_after_show` daily 11:00 (stamped, so it never sends twice,
  and it must not thank anyone for coming: attendance is not a fact we hold).
- 🔑 **The weekly mail is ONE language per reader** (`crm.mail.reader_language`: contact locale, else latest booking,
  else English).
- Marketing mail goes only through `crm.mail.send_marketing` / `send_newsletter` (dry run without `--send`), which
  drops unsubscribed contacts and adds the footer and `List-Unsubscribe`. 🚨 Never `message.send(fail_silently=True)`
  with a connection; put it on `get_connection`.
- 🚨 **Only no-such-mailbox bounces unsubscribe** (5.1.x). A `5.7.1` is Gmail refusing our IPv4 (Spamhaus PBL).
- 🚨 Postfix keeps `smtp_mx_session_limit = 1` and `smtp_balance_inet_protocols = no`; check the running master
  after a change, not just `postconf`.

### `/comic/` and `/drop/` (detail: `docs/comic-and-drop.md`)

- `/comic/` (`api/comic_views.py`): comedians send photos, clips and dates, stored as `crm.ComicSubmission` with files
  in `/var/lib/iguana/comics`, reviewed at `/admin/crm/comicsubmission/`; `manage.py comic_submission` lists and
  prints them.
- `/drop/` (`api/drop_views.py`): the owner's upload-only document drop behind `drop_pin`, files in
  `/var/lib/iguana/drop`. Never copy any of it into the repo; read it into `~/.credentials/iguanacomedy-business/`
  and delete it from the server once used.

### `/chat/`: a Claude Code instance runs the site too (detail: `docs/chat-agent.md`)

- 🚨 **Production now has TWO deployers.** The owner's agent (unix user `claude` on the VPS) commits, pushes to
  GitHub and runs `sudo iguana-agent-deploy`. So **`git pull` before working**, and `deploy.yml` refuses when
  GitHub is ahead of your checkout. `/home/www/iguana/DEPLOYED_COMMIT` says which commit is live and who put it
  there; deploying uncommitted work marks it `dirty`, and the agent then refuses to deploy over it until it is
  pushed. Commits by "Iguana Comedy chat agent" are the agent's.
- The owner wanted it able to do everything (sudo, refunds they name, users, campaigns). The guardrails are
  only against the irreversible: `ansible/files/agent/guard.py` (managed PreToolUse hook), `pii_scan.py`
  (system git hooks: no customer email/phone or secret in a commit), and the deploy script's tests, pre-deploy
  dump and rollback. Tests: `assistant` (Django) and `scripts/tests/test_agent_guards.py`.
- Infrastructure is still ansible's alone. If the agent changed something live with sudo, its deploy email
  says so; land the matching `ansible/` change before the next `deploy.yml` undoes it.

### Data outside the repo

`~/iguana-migration/` holds the Kintana CSV export (customer PII), the Wayback Machine mirror, and
`extracted/*.json` + images recovered from the old Framer and Kintana-era sites. Never commit any of it.
`backend/local_data.json` fixtures are gitignored for the same reason.
