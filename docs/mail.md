# Mail: what the server sends, reads and refuses

Reference and incident history behind the mail rules in `CLAUDE.md`.

## Reading the mailbox

Every human alias delivers to the local `inbox` user **as well as** forwarding, so the box is the copy that
survives a rejected forward. `/usr/local/bin/iguana-mail` (installed by `mail.yml`, read only) reads it:
`iguana-mail`, `iguana-mail show 37`, `iguana-mail search reservation`, `iguana-mail list --box dmarc`.
Worth checking when a customer says they wrote in, or when Stripe/Google send an account notice: a Stripe
"acción requerida" about an overdue ID check was sitting there unread while the API only said
`payouts_enabled: false`.

🚨 **`/var/mail/inbox` is 0600 `inbox:mail` and the deploy user was in neither group, so `iguana-mail` read
NOTHING and a check reported the mailbox as a clean channel.** An unread channel is not an empty one. `mail.yml`
now puts `deploy_user` in `mail` and sets the boxes 0640. Reading it is what found the Stripe "acción
requerida" thread and the performer enquiry that had waited a month.

## Forwards and SRS (2026-10-28)

Forwarded copies to the Gmail inboxes in `mail_forwards` were landing in spam. Each forward kept its original
envelope sender (`bounce.stripe.com`, `amazonses.com` for the phone-leash SMS relay, `mail.anthropic.com`), so
Gmail saw our IP sending for domains whose SPF does not list it, and SPF failed on every forward. `mail.yml` now
runs `postsrsd`: a foreign envelope sender becomes `SRS0=...@iguanacomedy.com` (SPF passes), and a bounce to that
address is turned back into the original sender. Our own zones are excluded, so mail we send is unchanged. Test:
`postmap -q x@stripe.com tcp:127.0.0.1:10001` prints an SRS0 address, and `grep SRS0 /var/log/mail.log` shows it
on real forwards. The original DKIM signatures survive the forward (Postfix does not touch the body), so DMARC
still passes on the original domain.

SRS alone was not enough: the forwards still went to spam. The missing piece was an ARC seal, the forwarder's
signed record of what the message passed when it arrived, which Google asks forwarders for. OpenARC is not
packaged for Ubuntu 24.04, so `mail.yml` runs rspamd as a second milter purely to seal (every spam action off,
its own DKIM signing off), using a copy of the recipient zone's DKIM key in `/var/lib/rspamd/arc/`. Check a
forwarded message for `ARC-Seal: i=1 ... d=iguanacomedy.com` (i=2 when Gmail sealed it first), or test with
`rspamc -h 127.0.0.1:11334 -i <sender ip> -r hello@iguanacomedy.com --mime <file.eml>`, which shows `ARC_SIGNED`.
If the DKIM key is ever rotated, re-run `mail.yml` so the ARC copy follows.

Spam that reaches `hello@` is forwarded too and still hurts the forward's standing at Gmail (one forward was
refused `5.7.1 likely unsolicited` on 2026-10-28). If forwards keep landing in spam, the next step is a content
filter before forwarding, or a Gmail filter on the receiving side: `to:(hello@iguanacomedy.com)`, Never send it
to Spam.

## Sign-up bots and the double opt-in

🚨 **Every newsletter sign-up this site had ever received was ONE BOT, and nothing about the requests could
tell it from a person.** All 59, found 2026-09-21: `timeZone: Europe/Moscow` on every one, `page: /en/`,
`browserLanguage: en-US`, arriving through Tor exits in DE/SE/US/NL, paced at a median 63-minute gap and never
under four so the rate never looked like a burst. The addresses were scraped and belonged to real strangers at
universities and companies. The Monday cron was hours from making this domain's FIRST bulk send to all of
them, which would have taken the 626 real contacts' deliverability down with it.
🔑 **The payload is not a discriminator: the bot sends exactly what the real form sends.** The gate is the one
thing it cannot do, which is read the mail. `crm/optin.py` holds the signed confirm token (its own salt, so an
unsubscribe link can never re-subscribe someone who used it to leave); a sign-up creates the contact
**unsubscribed and on no list**, sends one confirmation, and only `/newsletter/confirm/<token>` makes it
mailable. `api.tests.NewsletterOptInTests` covers it.
⚠ **Do NOT key "already confirmed" on `Contact.subscribed`**: the model defaults it to `True`, so every brand
new contact reads as confirmed and the gate silently does nothing. That was the first version of this. Key it
on whether `get_or_create` actually created the row, and never downgrade an existing subscriber who signs up
again.
⚠ **A missing `visitorKey` proves nothing**: the real newsletter form has never sent one, so "0 of 59 carry a
visitor key" is not evidence of automation. The uniform timezone was.
⚠ **The contact form was being farmed too** (15 random-string submissions in 3 days, each one emailing
`hello@`). `catalog/spam.py` is a honeypot plus a check that free text is not one unbroken run of letters and
digits; a dropped submission gets the SAME success response as a real one, because naming the gate teaches the
bot to pass it. The rows were never the cost: the cost is the owner learning to ignore the alert that a real
enquiry arrives in.

## The newsletter

🚨 **The weekly newsletter has never sent a single message, and it reported nothing.** `send_marketing` built
each message with a connection and then called `message.send(fail_silently=True)`. Django refuses that
combination and raises `TypeError: fail_silently cannot be used with a connection` on the FIRST recipient, so
every Monday the cron woke up, resolved its 627 subscribers, wrote the campaign row and died having delivered
none of them. The only evidence anywhere was a traceback under `journalctl -t iguana-newsletter`; the campaign
row exists with zero recipients, which looks like "nobody was due" rather than "it crashed".
Fixed 2026-09-22: the tolerance belongs on the connection, `get_connection(fail_silently=True)`.
🚨 **An unsubscribe that arrives as EMAIL is still an unsubscribe, and offering a `mailto:` beside the
one-click URL is what makes clients send one.** `List-Unsubscribe` carried both; Apple Mail picked the mailto,
sent "unsubscribe" to hello@ on 2026-09-23, and the person stayed on the list having done everything right.
The header now offers the URL alone, because a one-click URL unsubscribes somebody in the request itself while
a mailto only works if a human is reading that mailbox.
`process_unsubscribe_mail --apply` runs every 20 minutes and honours them anyway, because people reply
"unsubscribe" to mail whatever the headers say, and that is the commonest form of the request.
⚠ **It reads the BODY as well as the subject, but only the part they typed.** The commonest real request is a
reply to their own ticket email with the subject unchanged: "Re: Tus boletos" and "ya no quiero recibir
correos" underneath. Subject-only matching read those as ordinary replies and left the person on the list.
Three things keep that safe, and all three are load-bearing: messages from our own domains are refused;
everything from the first quote marker or `On ... wrote:` line down is discarded, because a reply quotes our
own footer and our footer says the word; and what remains must be short and must contain a REQUEST rather
than a mention. "The footer says I can unsubscribe here" is somebody describing the email, and acting on it
would drop a happy customer for being polite. Bilingual by necessity: two thirds of this audience books in
Spanish, so `darme de baja`, `quítame de la lista` and `ya no quiero recibir` matter as much as the English.
An address we do not hold is **created unsubscribed** rather than only logged, because this list has been
imported from a spreadsheet once already and asking twice is how a person becomes a spam complaint.

**Enabled 2026-09-22** (`newsletter_enabled: true` in `group_vars/all`, which `deploy.yml` reads; set it to
false to pause without editing a crontab by hand). Mondays 14:00 UTC, 09:00 in Playa, ~645 recipients paced
0.2s apart, about two minutes inside a 30m timeout. Before the first live run: one was sent to hello@ by hand
and read, and every link in it was opened in a browser.
🔑 **Each open mic line pins `night` and `date`.** The lander offers four dates and defaults to the next one,
so an unpinned link in a Monday mail naming Wednesday opened Tuesday: the reader books, gets a confirmation
and finds out at the door. Verified per-link, not per-page.
Before this the domain's only bulk send was the "Club Opening" campaign on 2026-09-14 to 722 addresses, which
is what people remember when they say emails went out.

## Phishing

🚨 **Phishing aimed at the ad account arrives here, and it authenticates.** On 2026-09-24 a fake Meta
"advertising policy violation" with a one-business-day deadline and a `vercel.app` login page reached hello@.
Return-Path `bounce@lynnwon.site`, sent from `api992409.friedrichsonde.site`, Reply-To at `noreply.com`, and
**DKIM passed** for the phisher's own domain, which is all a DKIM pass ever proves. The account was fine:
`account_status: 1`, `disable_reason: 0`, zero ads carrying review feedback. **Check the Graph API before
believing any mail about the ads**, since the thing being phished is an account with a live card on it. Those
senders are in `/etc/postfix/blocked_senders` (managed in `mail.yml`); the list is not a spam filter, it stops
the infrastructure that has already tried.

## Bounces and Postfix

🚨 **A permanent bounce is not automatically a dead address, and treating it as one unsubscribes people who
did nothing wrong.** Nothing read the bounces at all until 2026-09-24, so the Monday send kept going back to
addresses that had already failed. Of the 24 bounces sitting in the mailbox, **ten were `5.1.1` (no such
mailbox) and ten were `5.7.1`, which is Gmail refusing OUR IPv4** because 38.86.78.0/24 is on the Spamhaus
PBL. Both are `5.x.x`, both arrive in the same envelope, and acting on the leading digit would have dropped
seven live people at Yahoo, Outlook, Cox and Netscape plus `john@nader.mx`. The list would then shrink every
time our own reputation slipped. `manage.py process_bounces [--apply]` (daily 06:40 UTC, before the Monday
send, `journalctl -t iguana-bounces`) acts only on the no-such-mailbox codes `5.1.1 5.1.0 5.1.3 5.1.6`,
unsubscribes, tags the contact `hard-bounce` and stamps `CampaignRecipient.bounced_at`; everything else
permanent is printed and left alone. `api.tests.BouncedMailTests` pins the `5.7.1` case specifically.
⚠ **Read the structured `message/delivery-status` part, never the human paragraph above it** (that quotes the
remote server verbatim and it words things however it likes).
🚨 **Postfix was turning Gmail's TEMPORARY failures into permanent ones, using our own IP reputation to do
it, and `smtp_address_preference = ipv6` did not prevent it.** Measured 2026-09-25 over 995 deliveries to
Google: 787 of 797 first attempts went over IPv6 and **197 of 198 retries went over IPv4**. That looks like
random fallback and is not. Postfix opens up to `smtp_mx_session_limit` sessions per delivery attempt,
**default two**, walking down the address list: session one reaches Gmail over IPv6 and gets `452-4.2.2 the
recipient is over quota`, which should simply defer; Postfix then opens session two to the next address,
our IPv4, and Gmail answers that with `550-5.7.1 The IP you are using to send mail is not authorized`. The
last session decides, so a full mailbox becomes a permanent rejection, the message is destroyed, and the
bounce names a cause that makes the RECIPIENT look dead. It is the same trap `process_bounces` refuses to act
on, seen from the sending end.
Fixed in `mail.yml` with `smtp_mx_session_limit = 1` (a soft failure stays soft and retries later over IPv6)
plus `smtp_balance_inet_protocols = no`, because Postfix 3.5+ defaults that to `yes` and deliberately works
IPv4 into the list rather than trying every IPv6 address first, which would hand the single session to IPv4
some of the time. Verified by flushing the queue: the two over-quota messages that had taken IPv4 on every
previous attempt now stay on IPv6 and keep `dsn=4.2.2 status=deferred`.
⚠ **`postconf` shows main.cf, not the running process.** Postfix had not been restarted since 2026-09-21, so
a setting read back correctly and was not in effect. Check `ps -o lstart= -p $(pgrep -o -x master)` and
`postfix reload` before concluding a setting did nothing.
⚠ **Do not diagnose this from the `relay=` field.** One `smtp` process serves several deliveries in a row, so
a v6 session and a v4 `relay=` line share a PID and look like one delivery falling back. The sequence only
reads correctly under `debug_peer_list = <domain>` with `debug_peer_level = 2` (set it, `postfix reload`,
flush, then `postconf -X` both and reload again).
⚠ **A Spamhaus lookup answering `127.255.255.254` is NOT a listing**, it is "query refused, you used a public
resolver". The box resolves through one, so the PBL claim above cannot be checked from there.

## The mails that go out on their own (moved from CLAUDE.md, 2026-10-23)

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

## Inbox, opt-in, bounces and marketing mail (moved from CLAUDE.md, 2026-10-23)

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
