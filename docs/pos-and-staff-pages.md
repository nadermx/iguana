# The point of sale and the staff pages

Moved out of CLAUDE.md on 2026-10-23; the rules that always apply are summarised there.

## The point of sale (`backend/pos/`, `/pos/`): a Soft Restaurant clone

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

## The staff pages: who is coming, and what they cost

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
