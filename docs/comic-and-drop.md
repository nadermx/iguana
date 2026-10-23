# /comic/ and /drop/

Moved out of CLAUDE.md on 2026-10-23.

## `/comic/`: comedians send their photo, clips and dates (owner, 2026-10-09)

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

## `/drop/`: the owner's documents for ad and video account setup

`iguanacomedy.com/drop/` takes uploads (tax papers, IDs, logins for Google Ads, TikTok and YouTube setup) behind a
PIN (`drop_pin` in the creds folder; it was emailed to hello@, so treat it as known). Files land in `drop_dir`
(`/var/lib/iguana/drop`, 0700, files 0600), never under `backend/media`, and **the page is upload-only**: it shows
which headings have arrived and never a file name, a list or a download. It also takes photos of the ad billing card
(owner, 2026-10-06), and a newer card upload replaces the older one. Wrong PINs share the POS lockout. Each
upload emails `NOTIFY_EMAILS` the heading and count only. Our notes back to the uploader (received / needs attention / still
needed, plus a sentence in each language) come from `drop_dir/status.json`, copied up with ansible (owner `iguana`,
0600), never committed, because they say what a document is missing; no deploy needed to change them. To read them, copy them off with ansible into
`~/.credentials/iguanacomedy-business/` and delete them from the server once used. Never put any of it in the repo.
