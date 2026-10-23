# Deploy on Dokploy (legacy)

> **Not the production path.** iguanacomedy.com runs on a VPS deployed with `ansible/deploy.yml` (see `CLAUDE.md`).
> This page is kept for reference only.

This site runs as an **Astro Node server** in Docker. Kintana data is loaded on each request from Dokploy **Environment** variables (no build-time toggle required). Container port **3000**.

## 1. Push the repo

Connect your Git provider in Dokploy and select this repository (branch you deploy from, usually `main`).

## 2. Create the application

| Setting | Value |
| -------- | ------ |
| **Type** | Application → **Docker** |
| **Dockerfile** | `Dockerfile` (repo root) |
| **Build context** | `.` |
| **Container port** | `3000` (must match `PORT` in the app env; default is `3000`) |

Add every variable below under **Environment** (runtime), one per line, exactly like your local `.env`:

```env
PUBLIC_SITE_URL=https://iguanacomedy.com
PUBLIC_KINTANA_API_KEY=kpa_live_…
PUBLIC_KINTANA_BASE_URL=https://kintana.app
```

Provision submission endpoints in Kintana (`contact`, `perform-with-us`, `hotels-and-resorts`) — see `docs/kintana-forms-architecture.md`.

No `export` prefix, no quotes unless the value contains spaces. After saving, **restart** the app.

In **runtime logs** you should see `[iguana] PUBLIC_KINTANA_API_KEY: set (… chars)` then `[iguana] Starting Astro server`. First request after deploy may take a few seconds while the server warms up.

## 3. Environment variables

Copy from `.env.example` and set in Dokploy:

| Variable | Required | Notes |
| -------- | -------- | ----- |
| `PUBLIC_SITE_URL` | Yes | Live URL, no trailing slash (e.g. `https://iguanacomedy.com`) |
| `PUBLIC_KINTANA_API_KEY` | Yes | Publish key (`kpa_live_…`) |
| `PUBLIC_KINTANA_BASE_URL` | Yes | Kintana host, no trailing slash (e.g. `https://kintana.app`) |
| `PUBLIC_KINTANA_TRACKER_TOKEN` | No | Tracker `data-token` from Kintana → Websites |

After changing any `PUBLIC_*` value, **restart** the application so the container rebuilds the static files.

## 4. Domain & HTTPS

In Dokploy, attach your domain to this app and turn on TLS (Let’s Encrypt). Point DNS to the server running Dokploy.

## 5. Smoke test locally (optional)

```bash
docker build -t iguana-comedy \
  --build-arg PUBLIC_SITE_URL=https://iguanacomedy.com \
  --build-arg PUBLIC_KINTANA_API_KEY=your_key \
  --build-arg PUBLIC_KINTANA_BASE_URL=https://kintana.app \
  .

docker run --rm -p 8080:3000 iguana-comedy
```

Open http://localhost:8080

## Troubleshooting

- **“Connect ticketing credentials so listings can hydrate”** — add `PUBLIC_KINTANA_API_KEY` and `PUBLIC_KINTANA_BASE_URL` in Environment, then **restart** the app. Check **runtime** logs (not only Docker build logs) for `[iguana] Building static site`.
- **502 right after deploy** — wait 1–2 minutes on first boot while Astro builds; healthcheck allows up to ~3 minutes.
- **502 Bad Gateway** — container port must match nginx (`3000` by default, or set `PORT` and the same container port).
- **Empty shows / comedians** — API key rejected from the server, or vars not loaded. Check runtime logs for `[Kintana:…]` errors.
- **Contact form broken** — confirm submission endpoints exist in Kintana and CORS allows your site origin.
- **Wrong canonical URLs** — set `PUBLIC_SITE_URL` to the final public URL, then restart.
