# Open mics and the demand nudges

Moved out of CLAUDE.md on 2026-10-23; the rules that always apply are summarised there.

## Open mic reservations

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

## The nudges on a night, and the order they argue in

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
