# Deploy on Cloudflare Pages

This site runs as an **Astro SSR app** on **Cloudflare Pages** using `@astrojs/cloudflare`. Kintana data loads on each request from Cloudflare environment variables.

## 1. Connect the repo

In [Cloudflare Dashboard](https://dash.cloudflare.com/) → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**, select:

- Repository: `nadermx/iguana` (was `SlaterMarketing/iguana`, gone since 2026-10)
- Branch: `main` (or your production branch)

## 2. Build settings

| Setting | Value |
| -------- | ------ |
| **Framework preset** | Astro |
| **Build command** | `npm run build` |
| **Build output directory** | `dist` |
| **Node.js version** | `20` |

## 3. Environment variables

Add these under **Settings → Environment variables** for **Production** and **Preview**:

| Variable | Required | Notes |
| -------- | -------- | ----- |
| `PUBLIC_SITE_URL` | Yes | Live URL, no trailing slash (e.g. `https://iguanacomedy.com`) |
| `PUBLIC_KINTANA_API_KEY` | Yes | Publish key (`kpa_live_…`) |
| `PUBLIC_KINTANA_BASE_URL` | Yes | Kintana host, no trailing slash (e.g. `https://kintana.app`) |
| `KINTANA_SECRET_API_KEY` | No | Workspace secret (`kpa_secret_…`) — mark as **encrypted** |
| `PUBLIC_KINTANA_TRACKER_TOKEN` | No | Tracker `data-token` from Kintana → Websites |

Provision submission endpoints in Kintana (`contact`, `perform-with-us`, `hotels-and-resorts`) — see `docs/kintana-forms-architecture.md`.

After changing any variable, trigger a new deployment.

## 4. Custom domain

In the Pages project → **Custom domains**, add `iguanacomedy.com` (and `www` if needed). Cloudflare will issue TLS automatically when DNS is on Cloudflare.

If the domain is already in your Cloudflare account, point the apex/`www` records at the Pages project when prompted.

## 5. Local preview (optional)

Copy `.env.example` to `.env`, fill in values, then:

```bash
npm install
npm run build
npm run preview
```

For Wrangler-specific local bindings, also copy `.dev.vars.example` to `.dev.vars`.

`preview` runs the built app through Wrangler so Cloudflare runtime bindings behave like production.

## Troubleshooting

- **Site returns 404 but deployment is green** — open the latest deployment log and confirm you see `[Cloudflare build] dist output looks valid.` If the build failed on missing Kintana vars, Pages keeps serving an older broken deploy. Set all required env vars, then redeploy.
- **Only `/robots.txt` works** — the Pages project is not publishing the full `dist` folder. Re-check **Build command** (`npm run build`) and **Build output directory** (`dist`, not `public`).
- **Functions compatibility** — in the Pages project → **Settings → Functions**, add compatibility flag `nodejs_compat`.
- **Custom domain still blank** — attach `iguanacomedy.com` under **Custom domains** on the Pages project (DNS in Cloudflare alone is not enough).
- **“Connect ticketing credentials so listings can hydrate”** — confirm `PUBLIC_KINTANA_API_KEY` and `PUBLIC_KINTANA_BASE_URL` are set for the active environment, then redeploy.
- **Empty shows / comedians** — API key rejected or vars missing at runtime. Check Pages **Functions** logs for `[Kintana:…]` errors.
- **Contact form broken** — confirm submission endpoints exist in Kintana and CORS allows your site origin.
- **Wrong canonical URLs** — set `PUBLIC_SITE_URL` to the final public URL, then redeploy.
- **Legacy redirects** — handled in `astro.config.mjs`.

## Migrating from Dokploy

1. Deploy successfully on Cloudflare Pages and verify the `*.pages.dev` URL.
2. Add `iguanacomedy.com` as a custom domain on the Pages project.
3. Move DNS to Cloudflare (or update A/CNAME to the Pages target).
4. Shut down the Dokploy app once traffic is on Cloudflare.

See `docs/deploy-dokploy.md` for the previous Docker/Dokploy setup.
