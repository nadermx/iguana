# Meta ads (Facebook/Instagram)

Reference and history behind the ad rules in `CLAUDE.md`. The rules there always apply; read this before touching a campaign.

`scripts/meta-ads.py` (`status`, `campaigns --days N`, `daily --days N`, `pixels`, `pause/resume <id>`) talks to
the Marketing API. It is an operator tool run by hand, so it reads the never-expiring system-user token from
`~/.credentials/meta/iguanacomedy/token`, not `config.py`; no deployed service calls Meta.

| Asset | ID |
| --- | --- |
| Ad account `IGUANA` (MXN, business `IguanaComedy` 681571140696261) | `act_178760798664478` |
| Page `Iguana Comedy Productions` (@iguanacomedy) | `122106930026005410` |
| Instagram @iguanacomedy | `17841461594533193` |
| App `Iguana 2026` / system user `newiguana 2026` | `1616667029816710` |
| Pixel `Ticket Tracking` (used by the Kintana-era site) | `1167556798403907` |
| Pixel `andrew new pixel` (created 2026-09-15, never fired) | `2122037578734069` |

**The goal the spend is judged against (owner, 2026-09-24): fill every night. 80 reservations on an open mic
(60 until 2026-10-06, when the whole room became reservable), 80 on a paid show.** Budget is a means, not a constraint to protect: a paid seat is 200 to 300 MXN against a
measured 35 to 49 MXN to acquire, and a free seat costs about 16 and pays back at the bar. So an underfilled
night with a live campaign is a reason to raise the budget, not to admire the cost per seat.
⚠ **A lifetime budget is a CAP, and a nearly exhausted one goes quiet at the worst possible moment.** On
2026-09-24 the Privilegio ad set had 463 of 1,200 MXN left with 27.7 hours to the show and 40 of 80 seats
unsold: it would have stopped advertising on the Friday evening people actually decide. Raised to 2,400.
Check `budget_remaining` against the hours left whenever a show is close, because nothing surfaces this.

🚨 **A campaign or ad set reading `ACTIVE` is not evidence that it spends.** 31 ad sets report `ACTIVE` while
their `end_time` passed months or years ago, so the UI looks busy and the account has in fact spent nothing
since April 2026. Judge delivery by `end_time` in the future plus non-zero `insights.spend`, which is what
`status` does. The same trap in reverse: `campaigns` only lists campaigns that actually spent in the window.

**Conversion tracking: the backend reports the sale, the pixel only reports the visit.** Checkout is an iframe
served from `api.iguanacomedy.com`, so a pixel on the marketing pages can never see a purchase. `crm/meta_capi.py`
sends `Purchase` (from `complete_order`) and `InitiateCheckout` (from `checkout_start`) to pixel
`2122037578734069` over the Conversions API; `src/components/MetaPixel.astro` sends only `PageView` and
`ViewContent`. One sender per event, so there is no deduplication to get wrong and the money events survive an
ad blocker. Keys are `META_PIXEL_ID` / `META_CAPI_TOKEN` in `config.py` and `PUBLIC_META_PIXEL_ID` in `.env`.

🔑 **Matching is what decides whether a sale is attributed at all, and `_fbp`/`_fbc` belong to the SITE origin,
not the iframe.** `k.js` reads both cookies, rebuilds `_fbc` from `fbclid` when the pixel was blocked before it
could write one, and posts them as attribution; `checkout_start` stores them plus the User-Agent on the order and
`sales/ad_reporting.py` reads them back. A production order carries ten match fields
(`em fn ln ct st country client_ip_address client_user_agent fbp fbc`). Never report a sale without them: an
unattributed sale teaches the algorithm the ad did not work.

Nothing in that path may cost a booking. Every send is queued `on_commit`, runs on a daemon thread and swallows
its failures; `api.tests.MetaConversionTests` asserts a sale still completes with the Graph API throwing.

🚨 **Every PAID show gets the paid-show rules before a peso is spent** (owner, 2026-09-28, after Improvincia
bought 345 clicks, 6 checkout starts and 1 sale). `scripts/meta-show-campaign.py --show <key> preflight` checks
them against the live page, and `apply` refuses on any FAIL (`--force` only with a stated reason):
1. **Tickets are paid ON THE SITE, never at the door** (owner, 2026-09-28, reversing a pay-at-the-door option
   tried for an hour on Improvincia). No `pay_at_door` ticket type on a paid show; preflight FAILs one.
2. **Price in the ad's FIRST line**: the feed hides the rest behind "... más".
3. **The event date must equal the flyer's** (Improvincia's page said the 3rd, the flyer the 2nd).
4. **The flyer must not route bookings elsewhere.** The promoter's flyer printed their WhatsApp ("RESERVAS:
   998 844 7132"), which sends buyers around the page and hides every sale from Meta. Record what was checked
   in `SHOW['flyer']`; a booking phone FAILs unless accepted for that run.
5. **The page sells the act:** Spanish description, poster, and a lineup artist with a clip (as Privilegio and
   Improvincia have), ads optimised on the paid-checkout conversion, interests wider than stand-up.
Open mics are exempt: they are free to reserve and run on their own autopilot.

🚨 **A paid show's ad set must optimise on PAID checkouts, never on plain InitiateCheckout.** Every night on
the pixel sends InitiateCheckout, and the cheapest one for Meta to find is a free open mic reservation, so a
paid-show ad set steered on it learns to find people who book free seats. Improvincia's first day: Meta
reported 5 checkouts and 2 purchases, our database held zero Improvincia orders. Custom conversion
`1670646004630204` "Paid checkout (value above 0)" is InitiateCheckout with `value > 0` (every InitiateCheckout
carries the night's price, `sales/ad_reporting.py`), and `scripts/meta-show-campaign.py --show <key>` uses it.
⚠ **Promote a custom conversion ALONE**: `{'custom_conversion_id': ...}`. Adding its `pixel_id` or any
`custom_event_type` is refused as "combinación no válida". The optimisation is frozen once published, so the
builder names the goal in the ad set (`· pagados`), builds a new ad set when it changes, carries the old ads
over by creative, gives it the unspent budget and pauses the old one.
⚠ Meta retired "Improvisational theatre", "Whose Line Is It Anyway?" and "Comedy Central (Latin America)" as
interests (still returned by search, refused on an ad set); the replacements are Theatre, Television comedy
and Comedy TV Channels.

**A pixel's history cannot be imported into another pixel.** The Conversions API refuses any event with an
`event_time` older than seven days, so there is nothing to backfill, and `Ticket Tracking`'s last event (2026-05-17)
is outside every window Meta optimises on anyway. The one thing that *can* be imported is the customer list:
`scripts/meta-audiences.py build [--lookalike]` hashes the CRM **on the production box** (only hashes leave it)
and pushes it as a Custom Audience.
⚠ It needs the Custom Audience Terms accepted once, by hand, at
`business.facebook.com/ads/manage/customaudiences/tos/?act=178760798664478`. There is no API for that, and until
it is accepted every create returns 400.

**The weekly open mic campaigns.** `scripts/meta-openmic-campaigns.py` (`plan`, `apply [--live]`, `status`,
`pause`) builds two campaigns per night and is idempotent: it matches on name and updates rather than duplicating,
so re-running after a copy or budget change is safe. Per night, 1,000 MXN a week: a `OUTCOME_SALES` ad set at 100
MXN/day optimised for `Purchase` against the pixel, and a `OUTCOME_TRAFFIC` ad set at 43 MXN/day optimised for
landing page views. The split is deliberate. A reservation is free, so the conversion ads are paid back only at
the bar, and the cheap traffic ads fill the 20 walk-in seats and seed the pixel at the same time.

Targeting comes from what actually worked here: Playa del Carmen (geo key `1540930`), `home` **and** `recent` so
tourists are not excluded, 18 to 65, interest `6003273904571` "Comedia stand up" on the conversion ad sets and
nothing on the reach ad sets. English night adds locales `[6, 24]`.

🚨 **Ads point at `/open-mic/`, never at an event page.** Event URLs carry their date
(`/events/playa-del-carmen-2026-09-22/`), so a weekly campaign aimed at one needs rewriting every Tuesday and
spends on a dead show in between. `src/components/OpenMicPage.astro` asks the API for the next bookable night in
each language on every request and carries both checkouts inline. Use the apex domain: `www.` 301s, and a redirect
costs clicks.
| Campaign | ID |
| --- | --- |
| Open mic Spanish · reservations / ad set | `120250125973220182` / `120250125973580182` |
| Open mic Spanish · local reach / ad set | `120250125990540182` / `120250126057270182` |
| Open mic English · reservations / ad set | `120250126057820182` / `120250126057990182` |
| Open mic English · local reach / ad set | `120250126062910182` / `120250126063000182` |

🚨 **The two open mic reservation campaigns are switched by the server, not by hand.** `manage.py
open_mic_ads --apply` runs every 10 minutes (`journalctl -t iguana-open-mic-ads`) and sets each campaign
ACTIVE or PAUSED by its series' next night. **It runs only from two days before that night through the show day**
(owner, 2026-10-15, replacing "keep running open mics always" from 2026-09-26): Sunday, Monday and Tuesday for the
Tuesday night, Monday to Wednesday for the Wednesday, counted on the Cancun calendar from 00:00. Inside that window
it pauses when the night is SOLD_OUT, full by `sales.demand`, or less than an hour from `show_time`. It touches the
CAMPAIGN status only, never the ad sets, so the builder's choices (superseded ad sets, retired reach) stand.
⚠ The ad sets carry DAILY budgets, so running three days of seven cuts open mic spend to about 3/7 of what it was
at the same daily figure. Raise the daily budget if the nights stop filling. Raised 25% the same day (Spanish 220 to 275, English 200 to 250 MXN/day).
⚠ Inside the window a pause in Ads Manager is undone within ten minutes (and a resume outside it). To stop them
deliberately set `open_mic_ads_autopilot: false` in `group_vars/all`, deploy, then run `meta-openmic-campaigns.py pause`.
**Paid shows are not windowed**: `meta-show-campaign.py` starts each ad set as soon as it is built (`start_time` now
plus 2 minutes) and ends it at the show.
Found 2026-09-26 with both campaigns paused by hand alongside Privilegio and nothing delivering.

🚨 **The Meta app must be in LIVE mode or no ad creative can be made at all.** App `Iguana 2026`
(`1616667029816710`) is the business's only app, and while it is in Development mode every POST to
`/adcreatives` returns 400 "se creó con una app que se encuentra en modo de desarrollo", with or without
Instagram on the creative. Campaigns, ad sets, video and image uploads all succeed, so the account looks built
and delivers nothing. Toggle it at `developers.facebook.com/apps/1616667029816710/settings/basic/`, then re-run
`apply --live`. An ad set with no ads cannot spend, so leaving the structure ACTIVE meanwhile is safe.

⚠ Creating a campaign without CBO now requires `is_adset_budget_sharing_enabled`; Meta 400s without it.
⚠ **A city radius under 17km is refused** ("el radio geográfico no se encuentra dentro de los límites"), so the
walk-in ad set cannot be drawn tighter than that.
⚠ **Read every edge once per run.** Paging the account for each lookup trips the ad account rate limit partway
through and leaves half the structure built; the builder caches listings and backs off on codes
`{4, 17, 32, 613}` / subcodes `{2446079, 1487742}`, because that limit clears only by waiting.
⚠ No `end_time` on any ad set, on purpose. 31 ad sets on this account say ACTIVE with a schedule that ended
months ago, which is what makes the UI look busy while the account spends nothing.

**Posting to Facebook and Instagram.** `scripts/meta-social.py` (same token, stdlib only) has `whoami` (scopes,
Page and IG visibility, Page tasks, IG publishing quota), `recent` (last 5 Page posts and IG media),
`draft <slug> [--lang en|es|both] [--image URL]` and `post <slug> --to facebook|instagram|both --confirm`. It pulls
the event from the public API (key from `--api-key`, `IGUANA_PUBLIC_API_KEY`, else over ssh from prod `config.py`),
builds brand-voice captions (Spanish block first for `language: es`, no dashes, Instagram says "link in bio"
because the IG bio links to `/events`), and blocks on: no image, image not a public https JPEG/PNG, aspect ratio
outside 4:5 to 1.91:1, event page not 200, event past or cancelled. Without `--confirm`, `post` only drafts and
exits 2. Facebook posts go through `/{page}/photos` with a Page token derived at run time (never printed);
Instagram through `/media`, a `status_code` poll, then `/media_publish`. Weekly open mics have no image and no
`showTime` in the data, so they cannot be posted until one is set (or `--image` is passed); WebP is refused.
Tests: `python3 -m unittest discover -s scripts/tests`.
