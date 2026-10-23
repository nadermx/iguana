# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Iguana Comedy (stand-up promoter, Quintana Roo, Mexico). Two apps in one repo: a bilingual **Astro 5 SSR site**
(repo root) and a **Django backend** (`backend/`) that replaced the Kintana SaaS the site was originally built on.
Repo is **`nadermx/iguana`** (public), `origin` since 2026-10-23. It used to be `SlaterMarketing/iguana`, which
now answers 404, so a push there fails with "Repository not found". There is no private repository for this
project, which is worth knowing before writing anything into a commit: the history is world readable and git
history is not a place you can quietly delete from. Backend, deploy and migration work lives on branch
`backend-django`.
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
.venv/bin/python manage.py test api crm pos                                   # all backend tests (api/, crm/, pos/; sales has none of its own)
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

`README.md` at the root is the Kintana starter's and is stale (Kintana hosting, `/shows/` routes); `backend/README.md`
and `docs/` are current. Read the matching `docs/` page before deploy, mail or Meta work.

Local pairing: backend on `127.0.0.1:8000`, site on `127.0.0.1:4321` with `.env` / `.dev.vars` setting
`PUBLIC_KINTANA_BASE_URL=http://127.0.0.1:8000` and `PUBLIC_KINTANA_API_KEY` to a key from `config.PUBLIC_API_KEYS`.

## Architecture

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

### Open mic reservations

Open mics are always free to walk into, but walk-ins can be turned away when full. The room holds 80 and **all 80
are reservable from the nights of 2026-10-06 on** (owner, 2026-09-30; it was 60 plus 20 kept for walk-ins): a free
seat is easy to skip, and a night with 60 reservations saw only 20 to 30 arrive. So there are no walk-in seats to
promise; a sold-out night says that not everyone who reserves turns up, never a number. A reservation is an ordinary ticket type, so it uses the normal
checkout, the per-seat QR codes, the confirmation email and `/checkin/`; "arrive when doors open" lives in the
ticket type description, which the confirmation email prints.

🚨 **What is LIVE is a FREE reservation with NOTHING included, on every night of both series.** The active type
is `Free reserved seat` at 0.00, capacity 80 (60 on nights before 2026-10-06), not pay-at-door, and its description says entry is always free and
reserving costs nothing but holds the seat. There is no drink. The `Drink, ordered in advance` type (50 MXN /
3 USD) exists on every night and is **inactive** on all of them: that is the drinks upsell, taken down 2026-09-22
because it was not converting, and drinks are now handled at the table through `/menu/show/`.
⚠ **The paid model this section used to describe is dormant code, not the product.** 50 MXN Tuesday, 5 USD
Wednesday, a free drink included: the strings still exist (`sales/i18n.py` "Hold your seat for {0}, a free drink
included", `OpenMicPage.astro` `perSeat`, several tests) and none of them render, because `isFreeToReserve()`
prints "free to reserve" instead whenever `priceFrom` is 0. Do not quote that model as the economics: an open mic
seat currently costs the club nothing to give away, so the ad spend per seat is the whole acquisition cost and
the bar is where it comes back. (Checked against production 2026-09-23 after it was stated wrongly in a
cost-per-booking summary.)

**Both nights are doors 20:00, show 21:00.** The English night ran 20:30 until 2026-09-24; moving it meant the
series definition, the lander, the ad copy and the 15 nights already on the calendar, and the lander now reads
the time off the night it is showing rather than repeating it in a copy table.

🔑 **The calendar extends itself.** A Sunday cron runs `setup_open_mics --weeks-ahead 14 --only-new`
(`journalctl -t iguana-open-mic-calendar`), which creates any missing Tuesday/Wednesday night up to 14 weeks out
and sets up only those. A night that already exists is never touched, in any status, so drafting or cancelling a
holiday night sticks. Without it the ads would run out of nights to sell and switch themselves off.

`manage.py setup_open_mics [--show-time 20:00 --doors 19:30] [--dry-run]` publishes every upcoming night of the two
series (`Noche de Open Mic - Espanol!`, `Open Mic Night - English!`), sets currency/language, turns off member
benefits, tags them `open-mic`, and creates or updates the reservation type. It is re-runnable and never drops
capacity below seats already booked.

**Stripe keys are configured now** (Privilegio sold at 300 MXN online on 2026-09-22), so the paid path works. It
is simply not what the open mics use. The command still refuses to publish a PAID night while `stripe_enabled()`
is false, rather than put up nights nobody can pay for. `--pay-at-door` is the stopgap: `TicketType.pay_at_door`
completes the booking with no charge, records
`Order.pay_at_door_cents`, and the check-in page tells the door what to collect. It is limited to one booking per
email per night and locks the ticket types while booking, because nothing paid up front stops seat hoarding.

The site finds the next bookable night per language by the `open-mic` tag (`src/lib/open-mics.ts`), skipping sold-out
nights, and the home page keeps open mics out of its six event slots.
🔑 **An open mic booking is offered the next paid show in that NIGHT's language** (owner, 2026-10-09): one line
on the order page and in the confirmation email, `sales.sharing.paid_show_offer`, linked `?ref=om-thanks` /
`?ref=om-email`. `k.js` saves `ref` on any order, and `/stats/` counts open mic bookers who later paid for a show
by any route (per person) plus the link's own clicks and sales. Baseline when it shipped: 206 bookers, 0 had ever
bought a paid show.
🚨 **A sold-out open mic is SHOWN, never skipped, on the lander** (owner, 2026-09-26). The reservations are gone
but the no-shows are not, so the lander (`upcomingOpenMics`), the cards and the event page draw the AGOTADO
strip plus `walkInLine()` ("not everyone who reserves turns up, come when doors open") and offer the next bookable date. The
callout and hero badge still use `nextBookableOpenMics`, because they are a Reserve button.

### The nudges on a night, and the order they argue in

`sales/demand.py` counts the room; the ladder that turns it into a sentence lives in `src/lib/demand.ts`
(listings, the open mic lander, the home badge) and in `checkout.html`'s `renderDemand` (event pages, where the
iframe prints it because the host does not). Both must say the same thing, in this order:

1. **Sold out** when nothing is left.
2. **Only N seats left of M** when the room is nearly gone, and **Only N seats left for tonight** when the show is
   today in Playa (`demand.tonight`, set by the backend on the Cancun calendar).
3. **N people reserved in the last hour/few hours/day** when at least 2 have.
4. **More than half the room is gone** at 50% or more.
5. **N of M seats taken** once a third is gone (`BAR_FROM`).
6. Nothing at all below that. A small number is not social proof, it is an admission.

🚨 **Rungs 1 to 2 and 4 to 6 describe the ROOM; rung 3 describes OTHER PEOPLE. They are different facts and
they must not compete for one slot.** They did until 2026-09-25: one ladder produced one sentence, a burst
outranked half a room, and since nearly every night here has two or more recent bookings, **the room's own
state was never printed on any surface at all.** Privilegio sat at 40 of 80 and the Tuesday open mic at 37 of
60 while the home page, the listings, the lander and the checkout all said only "N people reserved in the last
day". `demandLine()` now returns `room` and `momentum` separately and `src/components/DemandLines.astro`
renders the bar, the room line and the momentum line together, everywhere. `text` is still the single best
line for the one surface with room for only one (the home hero badge), and its order is unchanged.
`api.tests.DemandNudgeTests.test_a_burst_does_not_silence_the_room` pins it.
⚠ **Uppercase at wide tracking is for the SHORT urgent rungs only.** "Sold out" and "Only 6 seats left" carry
it; "Over half reserved, worth booking early" set that way is a shout, and a shout about a half-full room
reads as a sales tactic rather than a fact.
⚠ A sold-out night says nothing about momentum: there is nothing left to sell, so "3 people reserved" is noise
on top of the answer.

A burst outranks half a room in the ONE-LINE slot on purpose: half is truer for longer, a burst is more
persuasive now.
🚨 **"Nearly gone" is a FIFTH of the room capped at ten, never a flat ten.** A flat ten on a small night is a
lie anybody can check: a room of three with nothing sold has three left, and the page would announce "Only 3
seats left of 3" to an empty house. Caught by a test rather than in the wild, because every live ticket type
happens to hold 60 or 80; the first 20-seat workshop would have shipped it.
⚠ **Seats a guest promoter sold count toward all of it** (`TicketType.sold_elsewhere`), so a night somebody
else is also selling does not read as empty.

### Newsletter, city alerts and who signs up from where

- The home hero's bottom-left is a newsletter sign-up (`NewsletterSignup.astro`, form endpoint slug `newsletter`,
  intent `newsletter`). Subscribers join the `Newsletter` contact list; there is no alert email per sign-up.
- A city page, or `/events/?city=`, with nothing coming up (any city except Playa del Carmen) shows
  `NoEventsNearby.astro`: travel time to the club (`src/content/playa-travel.ts`), links to Playa shows, the open
  mics and directions, and a "tell me when there's a show in <city>" sign-up that also joins `City alerts: <City>`.
  Those lists are who to email when a show is booked in that city.
- Every form sign-up and every booking records who and where (`backend/crm/geo.py`): site language, browser
  language, time zone and IP location (country, region, city). It lands on the contact (`locale`, `geo_*`,
  `time_zone`, `last_ip`), in `FormSubmission.context["visitor"]` and in `Order.attribution["visitor"]`. The real
  IP comes from nginx's `X-Real-IP`, trusted only when the request came from the local proxy (before this, every
  submission recorded 127.0.0.1).
- IP location uses DB-IP "IP to City Lite" (CC BY 4.0) at `geoip_db` (`/var/lib/iguana/dbip-city-lite.mmdb`).
  `deploy.yml` downloads it when missing and installs a monthly cron (`iguana-geoip-refresh`, logs to
  `journalctl -t iguana-geoip`); `geo.py` reopens the file when it changes, so no restart. A missing file only logs a
  warning: sign-ups and checkout never fail over it.
- City pages used to list a city's oldest past shows under "Upcoming in <city>" (no `from` filter); both loaders in
  `src/lib/locations-data.ts` now ask for today onward (`todayInCancun()`) and drop `past`.

### Meta ads (Facebook/Instagram)

**Read `docs/meta-ads.md` before touching a campaign**: asset and campaign IDs, the scripts
(`scripts/meta-ads.py`, `meta-show-campaign.py`, `meta-openmic-campaigns.py`, `meta-audiences.py`,
`meta-social.py`), targeting, and the Graph API traps. Operator scripts read `~/.credentials/meta/iguanacomedy/token`;
ad account `act_178760798664478`, pixel `2122037578734069`. The rules that always apply:

- **The goal is full nights: 80 reservations on an open mic (60 before 2026-10-06), 80 on a paid show** (owner, 2026-09-24). An
  underfilled night with a live campaign is a reason to raise the budget. A lifetime budget is a CAP: check
  `budget_remaining` against the hours left whenever a show is close.
- 🚨 **`ACTIVE` is not evidence of spend.** 31 ad sets say ACTIVE with an `end_time` long gone. Judge by a future
  `end_time` plus non-zero `insights.spend` (`meta-ads.py status`). `--days N` means N+1 days; `--days 0` is today.
- **The backend reports the sale, the pixel only the visit.** Checkout is an iframe on `api.`, so
  `crm/meta_capi.py` sends `Purchase` and `InitiateCheckout` over the Conversions API, with the site's
  `_fbp`/`_fbc` carried in by `k.js`. Nothing in that path may cost a booking (`MetaConversionTests`).
- 🚨 **Every PAID show passes `scripts/meta-show-campaign.py --show <key> preflight` before a peso is spent**:
  paid on the site never at the door, price in the ad's first line, event date equals the flyer's, the flyer
  routes no bookings elsewhere, and the page sells the act. Its ad set optimises on custom conversion
  `1670646004630204` (paid checkouts), never plain InitiateCheckout, which finds free open mic bookers.
- 🚨 **Open mic ads point at `/open-mic/`, never at a dated event page, and the server switches them.**
  `open_mic_ads --apply` runs every 10 minutes. 🔑 **A night's ads run only on the show day and the two days
  before** (owner, 2026-10-15: Sunday to Tuesday for a Tuesday night, Monday to Wednesday for a Wednesday), and
  stop when the night is full or under an hour away; inside that window a pause in Ads Manager is undone.
  🚨 **A campaign that says ACTIVE can still spend nothing** when its ad set or ads are paused by hand: from
  2026-10-11 to 10-19 the autopilot logged "ACTIVE already" over a paused Spanish ad set and paused English ads.
  Inside the window it now also un-pauses the builder's `... · checkout` ad set and its ads (never the retired
  ones), and `meta-ads.py status` lists an ACTIVE ad set with no active ad as NOT delivering.
  **Paid shows start as soon as their campaign is built** (`meta-show-campaign.py` sets `start_time` to now). To stop them set `open_mic_ads_autopilot: false`, deploy, then
  `meta-openmic-campaigns.py pause`.
- 🚨 **Check the Graph API before believing any mail about the ad account**: phishing for it arrives with
  DKIM passing (`docs/mail.md`).

### TikTok ads (set up 2026-10-15)

TikTok for Business login is hello@iguanacomedy.com (password in `~/.credentials/tiktok/iguanacomedy/ads_password`;
verification codes arrive at hello@, read them with `iguana-mail`). Ad account `IGUANA COMEDY SA DE CV_adv`,
advertiser `7697050080028737556`, MXN, time zone Panama (UTC-5 all year, the same as Playa; TikTok has no Cancun).
Pixel `DB8MPFRC77UAEK318EU0` with an Events API token (`events_api_token`), both rendered into config by the deploy.
- It mirrors Meta exactly: `TikTokPixel.astro` sends page views and ViewContent only, `k.js` carries `_ttp` and
  `ttclid`, and `crm/tiktok_events.py` reports InitiateCheckout, AddPaymentInfo and CompletePayment from the
  backend with the same event ids (`TikTokEventsTests`). TikTok answers 200 with a non-zero `code` when it
  refuses an event, so the sender checks `code`, never the status.
- 🔑 **TikTok ad links must carry `utm_source=tiktok`.** `/stats/` credits each booking to the platform whose link
  it landed on (`stats_views.platform_of`: ttclid or utm_source=tiktok, else fbclid/fb/ig/fbc), and compares
  cost per seat on our own seats. TikTok spend has no snapshot yet, so its cost shows "not connected".
- The account had no payment method when it was made, so nothing on it can spend until one is added.

### The point of sale (`backend/pos/`, `/pos/`): a Soft Restaurant clone

🚨 **Since 2026-09-28 the bar runs on `/pos/`, not on `/tables/` + `/mesas/`** (owner: "the entire
order/menu/table/inventory system is fucked, make it a clone of Soft Restaurant", same layout so staff land on
what they know). `/mesas/`, `/tables/`, `/mesas/carta/` and `/mesas/inventario/` now 302 to it; `/mesas/reservas/`
and the door (`/scan/`, also `/mesas/puerta/`) are unchanged and linked from its function bar. The old board's
models (`TableOrder` etc.) keep the history, and /stats and /revenue add both.

- **The PIN pad is the only door** (owner, 2026-09-28: no username screen). `/pos/` goes straight to a 4 to 6
  digit PIN (`pos.Staff`, roles MESERO / CAJERO / GERENTE, 30 min idle). Five wrong PINs from one address in 15
  minutes lock it (`pos.PinFailure`), and wrong manager PINs typed in dialogs count too. A PIN session is a
  person, never a Django user, so /admin/ stays shut to it; `floor_required` pages (Reservas, Puerta, /checkin/)
  accept it as well. Voiding a SENT line, discounts, courtesy, cancelling or reopening need a manager PIN typed on
  the spot (not if a manager is signed in). The first manager is "Administrador" (`pos_setup` from deploy; PIN in
  `~/.credentials/vpsorg/iguanacomedy/pos_manager_pin`, changed by hand to the owner's choice, never rewritten by
  a deploy); everyone else is created at `/pos/personal/`.
- **E2E:** `API_KEY=... node tests/pos-e2e.mjs` against production needs the throwaway fixtures (E2E staff 4242 /
  4343, table 99, category "E2E prueba") created and removed around it, and `SKIP_TILL=1` whenever a real shift
  is open (it never charges into or closes one). The staff tutorial went to hello@ on 2026-09-28.
- **Hierarchy (floor's list, 2026-09-28):** Mesero < Barra < Administración (codes MESERO / CAJERO / GERENTE,
  only the labels changed). A waiter sees their section (`Staff.tables`, set at /pos/personal/ as "1-6, 9";
  empty = whole room) plus checks they opened, never another waiter's (`Staff.may_open`, `api.claim`), takes an
  unclaimed QR check by opening it, and charges/closes their own checks. Barra and Administración see and work
  everything and run the till. Anyone adds a table from the map (`/pos/mesa/nueva/`). A check can be named
  (`label`, shown as "Mesa 3 · Ana"). ENVIAR returns to the map.
- **Flow:** map (zones, colours: green free, blue occupied, amber bill printed, orange pulsing = QR order not
  sent) -> check (`pos.Check`, one open per table unless DIVIDIR) -> lines from the category/product grid, with
  modifiers -> ENVIAR makes a `Comanda`, takes the RECIPE out of stock (`catalog.MenuItemIngredient`, per line,
  once, `stock_applied_at`) and prints at the bar -> CUENTA prints the bill with a phone-pay QR -> COBRAR takes
  one or more `Payment`s (cash with change, terminal card with reference, transfer, phone, courtesy) into the open
  `Shift`; the check closes at zero and prints a ticket -> CAJA closes the shift with a corte (expected cash =
  fondo + cash sales + cash tips + entradas - retiros).
- **Customer QR orders are OFF** (owner, 2026-09-29): `ONLINE_ORDERING = false` in
  `src/components/menu/MenuPage.astro`, so `/menu/show/` and the table QR pages (`/menu/<n>/`) show the plain menu
  under "raise your hand and a waiter will come". Set it true to bring the form back; orders then arrive through
  `/api/public/v1/table-orders` on the table's check UNSENT (`from_customer`), email the bar, and the waiter
  confirms and sends. Phone payment is `/pos/pagar/<check.pay_token>/` (same page
  as the old table pay, Stripe metadata `purpose: pos`, webhook settles).
- **Printing** without a computer at the club: Epson TM (Server Direct Print) or Star (CloudPRNT) poll
  `/pos/print/<printer token>/` (`pos/views_pay.py`); until one exists every ticket opens in the tablet's print
  dialog (`/pos/imprimir/<job>/`, 42 columns for 80mm). Set up at `/pos/impresoras/`.
- **Inventory** reuses `catalog.InventoryItem`/`InventoryChange`: existencias with mermas, compras (add stock,
  set `pos.ItemCost` for recipe costing), inventario físico (count sheet applied in one go).
- ⚠ The order screen serialises its requests (`serial()` in `templates/pos/cuenta.html`): two fast taps used
  to race and one drink vanished. Keep it.
- Tests: `manage.py test pos`.
- **Eliminar pedido** (owner, 2026-09-29): one tap on the order screen removes an unpaid order from service
  and returns to the map, ready for a fresh order. Staff can delete checks they may work without another PIN;
  orders with any payment record are refused. The cancelled check and all its lines remain as history, with
  the staff member recorded. Pending comandas and linked print jobs are cleared. `CheckLine.stock_deltas`
  records the stock actually deducted, so deleting/voiding never creates stock when the shelf was empty.

### The staff pages: who is coming, and what they cost

**Logins** (`~/.credentials/vpsorg/iguanacomedy/`): **`iguana`** is the owner account, superuser, so it reaches
everything including the money (`owner_password`). `admin` is the account the first deploy creates
(`admin_password`). Both passwords are set only when the account is created, so changing one in the admin is
not undone by the next deploy. Day to day the staff use a PIN (see the point of sale above), not these.

**`mesero`, `bar` and `door` are the old floor accounts and they are NOT staff** (`floor_password`, shared,
re-applied on every deploy). They still open the `floor_required` pages (`/mesas/reservas/`, `/scan/`,
`/checkin/`) and nothing else; `/pos/` itself takes only a PIN.
🚨 **`is_staff = False` is the entire security model, on purpose.** Django's admin turns away a non-staff
account at the login form, before it consults a single permission, so `/admin/` is shut by construction.
`manage.py ensure_floor_accounts --password <pw>` forces the flag off every deploy, because somebody ticking
"staff status" in the admin to be helpful is the realistic way that protection disappears.
`api.tests.FloorConsoleTests` asserts the refusal.
🚨 **`ensure_floor_accounts` must only set the password when it actually DIFFERS.** `set_password` rotates the
session auth hash, so calling it unconditionally signed out every tablet on every deploy.
`api.tests.DeployDoesNotSignTheTabletsOutTests` pins it. A floor login gets a one-year session
(`floor_views.sign_in`), set per session so the owner's admin session keeps the short default.

- **`/reservations/`** (any staff): every night with seats against capacity, a fill bar, bookings, seats left,
  what was taken online, and under each night the guest list with when they booked. Names show to all staff;
  **email addresses only to whoever passes `can_see_the_money`**, because the door needs a name and does not
  need the mailing list.
- **`/reservas/`** (`iguanacomedy.com/reservas`, floor accounts and PINs; `/mesas/reservas/` is the same page, kept
  for bookmarks): the same guest list in Spanish, every upcoming night's list open. It is the DOOR list, because
  nobody scans the QR codes. Each night on `/stats/` links to `/reservations/#n<event id>`.
- **`/scan/`** (`iguanacomedy.com/scan`, the address staff are given; any staff PIN, any role; `/mesas/puerta/`
  is the same page, kept for bookmarks): the door scanner. The camera stays open, a ticket's QR is read in
  place, and the verdict fills the screen: `PASA`, `YA PASÓ`, `REPETIDO`, `NO SIRVE`, `SIN PAGAR`.
  🔑 **A good scan marks the ticket used in the same breath, with no confirming tap**, atomically, so a second
  scanner on the same queue is told `REPETIDO`. The same code read again within 20 seconds is `YA PASÓ`, not
  an alarm (the camera sees one QR many times a second). `Deshacer` is on every good scan. An unpaid order is
  refused and NOT marked.
  ⚠ **iOS Safari has no `BarcodeDetector`**: the page tells them to use the phone's camera app, which opens
  `/checkin/<token>/` (what the QR holds, same check), or to type the code.
  🚨 **Nobody has ever been checked in here** (0 of 24 on one night, 0 of 16 on another), so `checked_in_at`
  says nothing about attendance.
- **`/stats/`** (`can_see_the_money`): ads campaign by campaign (spend, reach, frequency, clicks and CTR, seven
  days and today), the room night by night, today's funnel from visit to booking, cost per reservation free
  against paid, the list size and the bar's takings per night. Refreshes itself every 60s.
  ⚠ **Seats left is a LIE on a sold-out night**, because a guest promoter sells a block we never see, so the row
  says "no seats to sell" and the bar fills to 100.
  ⚠ **`sales.demand` counts `OrderItem.quantity`, not `Ticket` rows.** A fixture with tickets but no items reads
  as an empty room.
  ⚠ **Money on this page is a STRING per currency** (`'600.00 MXN · 25.00 USD'`), never a float: English
  nights sell in dollars, Spanish ones in pesos. `|floatformat` over it silently prints a bare `$`.
- **`/revenue/`**: the takings.

**Rules for these pages, learnt on the old `/tables/` board and still true for the POS:**
- 🚨 **Test at 320px, not just 390.** Every one of these is read on a phone. `tests/mobile-sweep.mjs` measures
  page overflow, per-element clipping (an element clipped inside its own box never overflows the page, which is
  the fault that hides) and tap targets under 40px at 320/360/390/430. The floor nav is defined once in
  `templates/embed/base.html`.
- 🔑 **Playwright checks here must be case-insensitive**: labels are uppercased in CSS and `innerText` returns
  what is rendered.
- 🚨 **Poll, never push.** Gunicorn runs **three SYNC workers** (`supervisor.conf.j2`), so one held-open SSE or
  long-poll connection per tablet would consume every worker and take the checkout down with it.
- ⚠ **A `{# #}` comment is ONE LINE.** Written across several, Django prints it on the page. Use
  `{% comment %}`.
- ⚠ **Never give two context variables in one view the same name**: a template renders whatever it is handed,
  repr and all, with no error.
- 🚨 **A void is not a delete, and it asks which of two things happened.** `No se preparó` returns the stock;
  `Se preparó y se tiró` takes the money off and leaves the count alone, because the drink is in a bin. An
  unrecognised reason counts as waste, since the cautious default is never to invent stock. The line stays,
  struck through, with who and why.
- ⚠ **The night runs 6am to 6am** (`tables_views.service_start`, used by `pos.services`), so a tab that crosses
  midnight is not zeroed. But **`current_show` matches the CALENDAR DAY** of the service's start, because an
  event's date is stored early in its own day and a timestamp window returned tomorrow's show.
- 🚨 **A SOLD OUT night is still a night; only DRAFT and CANCELLED are not.** Filter
  `status__in=(ACTIVE, SOLD_OUT)` wherever "tonight's show" is looked up (`SoldOutIsStillAShowTests`).
  `crm/after_show.py` and `crm/whats_on.py` exclude sold-out on purpose: they invite people to book.
- ⚠ **A test that builds "tonight" from a bare `timezone.now()` fails from 19:00 to midnight in Playa**, because
  the UTC date has rolled over. Build it from `service_start().date()` in `CANCUN_TZ`.
- Prices are snapshotted onto each line when it is ordered, so a price fixed mid-service cannot restate what a
  table already agreed to pay. Product names are written to `name` and `name_es` together, because the console
  is Spanish and the customer menu reads `name_es`. `/pos/productos/` refuses a second product with the same name
  in the same category.

**Stock follows RECIPES** (`catalog.MenuItemIngredient`: one sale of this takes this much of that), applied once
per line when the line is SENT (`CheckLine.stock_applied_at`, and `stock_deltas` records what was actually
taken, so a void or a deleted order never gives back stock that was not there). A count that is too LOW reads as
theft, so double application is the direction that has to hold.
🚨 **A menu item with NO recipe consumes nothing, and that is deliberate.** A guessed 1:1 between a cocktail and
a bottle drifts the sheet every night. Beers and bottled soft drinks are sold as the unit and wired 1:1;
pours are left for the bar to state. `manage.py seed_bar_inventory [--dry-run]` follows that rule and never
overwrites a count or recipe somebody set. The old board's rounds (`TableOrder`, `sales/stock.py`) are history
only.
⚠ Counts never go negative, a comma is a decimal point, and anything over 100,000 is refused.

🚨 **No request path may call Meta, and `/stats/` does not.** The ad account's rate limit clears only by
waiting, so a page that asked Graph on every load would eventually wall itself and take the numbers down with
it, and a Graph outage would turn the dashboard into a 500 at the moment somebody wanted to decide whether to
keep spending. `manage.py snapshot_ad_spend` runs every 15 minutes and writes `crm.AdSpend`, one row per
campaign per day; the page reads rows and prints how old they are, and says so loudly past 45 minutes.
The token is `META_ADS_TOKEN` in `config.py`, rendered from `config.py.j2` like every other secret.
⚠ **config.py is TEMPLATED on every deploy.** A hand-edited line in it survives until the next deploy and no
longer: add the key to `files/config.py.j2` and `group_vars/all`, never with `lineinfile`.

🚨 **Reach counts PEOPLE, so it is never summed across days and neither is frequency.** Adding seven daily
reaches counts somebody who saw the ad on Monday and again on Thursday twice, and the frequency derived from
that sum reads LOWER than the truth, which is the direction that hides ad fatigue. The seven-day figures are
therefore asked of Meta AS a seven-day window and stored as their own `AdSpend` row (`window='WEEK'`, same
day and campaign as the daily rows). Anything that sums spend must filter `window=DAY` or it double counts.
Frequency above **1.3 a week is flagged** (`ad_spend.FREQUENCY_TARGET`, the owner's number, set 2026-09-24
looking at 1.7 and 1.8 on the open mics). It is a house target rather than an industry one: 1.7 over seven
days is a quarter of an impression per person per day and nobody would call it fatigue. With the budget fixed
the only honest lever is audience size, so the open mic reservation ad sets went from a 25km to a 40km radius
(Puerto Aventuras and Akumal, the drive people here actually make), matching what Privilegio already used.
⚠ Frequency is a TRAILING seven-day figure, so a targeting change shows up over days, not on the next refresh.

🔑 **Cost per seat is Meta's spend over OUR seats, never over Meta's purchase count.** Their attribution has
run both above and below the orders we hold (5 reported against 7 real on 2026-09-24, 22 against 7 the day
before), so the page shows their number beside ours and never divides by it. Probe bookings (`e2e-` emails)
are excluded from every denominator.

🚨 **`scripts/meta-ads.py --days N` means N+1 days.** `window()` is `since = today - N, until = today`, and
Meta's `time_range` is inclusive at both ends, so `--days 1` is yesterday AND today. It reported 1,162 MXN as
"today" when today was 226, which reads as a fivefold overspend. `--days 0` is today.

### The mails that go out on their own

- **Daily 10:00 Playa**: `send_show_reminders` writes to everyone booked for TONIGHT (`sales/reminders.py`,
  stamped with `Order.reminder_sent_at`, probes and promoter imports skipped). **Open mics carry a "give your seat
  back" link** (`/orders/<token>/release/`); **paid shows get the reminder only**, because a paid ticket given
  back is a refund conversation (owner, 2026-09-27). Releasing sets the order CANCELLED plus `released_at`, and
  since every count reads COMPLETED the seat is instantly back on sale on the lander, the demand lines and the ads
  autopilot. Refused once the show has started or a ticket was scanned. The door shows `LIBERÓ SU LUGAR`.
- **Monday 09:00 Playa**: the what-is-on newsletter (`send_whats_on`, `newsletter_enabled`).
- **Daily 11:00 Playa**: `send_after_show` writes to everyone who booked the night before. It hopes they made
  it, asks them to pass the open mic on, and asks them to reply with anything that could have been better;
  replies go to hello@. Dry run unless `--send`; every booking it considers is stamped with
  `Order.follow_up_sent_at`, so a re-run or a double fire cannot send twice.
  ⚠ **It must not thank them for coming.** Nobody is scanned at the door (0 of 24 on 2026-09-23), so
  attendance is not a fact we hold.

🔑 **The weekly mail is ONE language per reader, never both** (owner, 2026-09-28). `crm.mail.reader_language`
decides it for the subject, body and footer alike: `contact.locale` (set at sign-up from the site language, and
again whenever they click through a marked link), else the language of their latest booking, else **English**.
Most of the blank contacts are the Kintana import. Until 2026-09-28 it carried both languages, reader's first,
and led unknowns with Spanish; do not bring that back without asking.

### Reading the mail the server keeps, and what it refuses

Every human alias delivers to the local `inbox` user as well as forwarding. `/usr/local/bin/iguana-mail`
(read only) reads it: `iguana-mail`, `show 37`, `search reservation`, `list --box dmarc`. Check it when a customer
says they wrote in, or an account notice might be waiting. History and evidence for everything below:
**`docs/mail.md`**.

- 🚨 **Newsletter sign-ups are double opt-in, because every one this site had received was a bot** sending
  exactly what the real form sends. `crm/optin.py`: a sign-up is created unsubscribed and on no list until
  `/newsletter/confirm/<token>`. Key "already confirmed" on whether `get_or_create` created the row, never on
  `Contact.subscribed` (it defaults True). `catalog/spam.py` guards the contact form and answers a dropped
  submission with the same success response.
- **The Monday newsletter** runs while `newsletter_enabled: true` in `group_vars/all`. Each open mic line pins
  `night` and `date`, or the lander defaults to the wrong night.
- **An emailed "unsubscribe" is honoured** (`process_unsubscribe_mail --apply`, every 20 minutes), reading only
  the part of the body the person typed and requiring a request rather than a mention. `List-Unsubscribe`
  offers the one-click URL only, no `mailto:`.
- 🚨 **Only no-such-mailbox bounces unsubscribe** (`process_bounces`, codes `5.1.1 5.1.0 5.1.3 5.1.6`). A
  `5.7.1` is Gmail refusing OUR IPv4 (38.86.78.0/24 is on the Spamhaus PBL), not a dead address. Read the
  `message/delivery-status` part, never the prose.
- 🚨 **Postfix keeps `smtp_mx_session_limit = 1` and `smtp_balance_inet_protocols = no`**, or a Gmail
  over-quota deferral on IPv6 is retried over IPv4 and turned into a permanent rejection. `postconf` shows
  main.cf, not the running process: check the master's start time and `postfix reload`.
- `/etc/postfix/blocked_senders` (managed in `mail.yml`) holds infrastructure that has already phished the ad
  account.
- 🚨 **`send_marketing` must never call `message.send(fail_silently=True)` with a connection**: Django raises on
  the first recipient. The tolerance goes on `get_connection(fail_silently=True)`.

Marketing mail must go through `crm.mail.send_marketing` (or `manage.py send_newsletter`, a dry run without
`--send`), which drops unsubscribed contacts and attaches the unsubscribe footer and `List-Unsubscribe` headers
itself. `crm/unsubscribe.py` signs the per-address token; `/unsubscribe/<token>` serves the bilingual page and
accepts Gmail's cookie-less one-click POST. Receipts and sign-in codes deliberately carry no unsubscribe link.

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

### Data outside the repo

`~/iguana-migration/` holds the Kintana CSV export (customer PII), the Wayback Machine mirror, and
`extracted/*.json` + images recovered from the old Framer and Kintana-era sites. Never commit any of it.
`backend/local_data.json` fixtures are gitignored for the same reason.

### `/drop/`: the owner's documents for ad and video account setup

`iguanacomedy.com/drop/` takes uploads (tax papers, IDs, logins for Google Ads, TikTok and YouTube setup) behind a
PIN (`drop_pin` in the creds folder; it was emailed to hello@, so treat it as known). Files land in `drop_dir`
(`/var/lib/iguana/drop`, 0700, files 0600), never under `backend/media`, and **the page is upload-only**: it shows
which headings have arrived and never a file name, a list or a download. It also takes photos of the ad billing card
(owner, 2026-10-06), and a newer card upload replaces the older one. Wrong PINs share the POS lockout. Each
upload emails `NOTIFY_EMAILS` the heading and count only. Our notes back to the uploader (received / needs attention / still
needed, plus a sentence in each language) come from `drop_dir/status.json`, copied up with ansible (owner `iguana`,
0600), never committed, because they say what a document is missing; no deploy needed to change them. To read them, copy them off with ansible into
`~/.credentials/iguanacomedy-business/` and delete them from the server once used. Never put any of it in the repo.

### `/comic/`: comedians send their photo, clips and dates (owner, 2026-10-09)

`iguanacomedy.com/comic/` (also `/comic`, `/en/comic`, `/es/comic`, linked from the perform-with-us pages) is a
public, bilingual Django page (`api/comic_views.py`, `templates/embed/comic.html`) for a comedian who wants a
show: name, stage name, email, WhatsApp, Instagram/TikTok, home city, languages, bio, links, up to 6 photos
(JPG/PNG/HEIC/WebP, 25 MB each) for the flyer, three clips (about 30s, about 1 min, 2 to 5 min; MP4/MOV, 500 MB
each, a link can stand in) for the ads, requested dates, availability, show name, draw, ticket price idea,
opener/guests, notes, and a consent box to use it all in promotion. Honeypot plus `catalog.spam`, and 3 per
address per hour (8 per day). The page uploads with a progress bar; nginx takes 1700m on this path only and
buffers it to disk, so the three sync workers are never held by a slow phone.

- Stored as `crm.ComicSubmission` + `crm.ComicFile`; files in `COMICS_DIR/<id>/` (`/var/lib/iguana/comics`,
  0700, files 0600), never under `backend/media`. Deleting a submission deletes its folder.
- Each one mails `NOTIFY_EMAILS` (hello@) with everything plus the admin link, Reply-To the comedian, and sends
  the comedian a receipt in the language they used. Clip lengths are read by ffprobe in a thread afterwards.
- **Admin:** `/admin/crm/comicsubmission/`, status (New, In talks, Booked, Declined) and staff notes, every file
  downloadable (photos previewed) behind the admin login.
- **"Make an event from this comic":** `manage.py comic_submission` lists them; `comic_submission <id>` prints
  the details, dates, file paths and the ansible lines to copy the folder off; then `scripts/fit-poster.py` on
  the photo and the event in the admin. `--delete` removes one (tests, or on request).
- `node tests/comic-e2e.mjs` checks the layout at 320 to 1280 in both languages; `--submit` sends one test
  submission as "E2E prueba, ignore", which must then be deleted on the server.
