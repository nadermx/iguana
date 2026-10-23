# TikTok ads

Moved out of CLAUDE.md on 2026-10-23.

## TikTok ads (set up 2026-10-15)

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
