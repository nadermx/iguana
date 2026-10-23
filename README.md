# Iguana Comedy

The website and back office for [Iguana Comedy](https://iguanacomedy.com), a stand-up comedy promoter in Playa
del Carmen, Quintana Roo. Shows, the weekly open mics (Spanish on Tuesday, English on Wednesday), tickets and
reservations, the bar's point of sale and the door scanner all run from this repository.

Everything a visitor or customer sees is in English and Spanish.

## What is in here

| Part | Where | What it does |
| --- | --- | --- |
| Site | repo root (`src/`) | Astro 5, server rendered on Node. Bilingual routes under `/en/` and `/es/`, React islands for sign-in, account and checkout. |
| Backend | `backend/` | Django 6 on Postgres. Events, comedians, venues, ticketing and the checkout iframe, Stripe, fan sign-in, CRM and newsletters, the POS (`/pos/`), the door scanner (`/scan/`), staff dashboards. See [`backend/README.md`](backend/README.md). |
| Deploy | `ansible/` | One VPS: nginx in front of the Node site and gunicorn, Postfix + OpenDKIM for mail, nightly verified Postgres backups. |
| Tests | `tests/`, `backend/*/tests.py`, `scripts/tests/` | Playwright end-to-end flows against a running site, Django tests, offline tests for the operator scripts. |
| Docs | `docs/` | Mail, Meta ads and deploy history. Read the matching page before touching that area. |

The site was first built on the Kintana SaaS. The Django backend now answers the same HTTP API that
`@kintana/sdk` (vendored in `vendor/`) calls, so the site still speaks "Kintana" and only its base URL and key
point somewhere else.

## Running it locally

Node 20 (`.node-version`) and Python 3.12.

```bash
# Backend on :8000
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config_example.py config.py          # DEBUG=True, SITE_URLS, PUBLIC_API_KEYS, console email
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_site_defaults
.venv/bin/python manage.py runserver 127.0.0.1:8000

# Site on :4321, in another shell
cp .env.example .env && cp .dev.vars.example .dev.vars
# set PUBLIC_KINTANA_BASE_URL=http://127.0.0.1:8000 and PUBLIC_KINTANA_API_KEY to a key from config.PUBLIC_API_KEYS
npm install
npm run dev
```

## Checks

```bash
npm run build:node                          # also runs the i18n, env and route checks
cd backend && .venv/bin/python manage.py test api crm pos
python3 -m unittest discover -s scripts/tests
node tests/account-flow.mjs                 # needs the backend on :8000 and the built site on :4321
node tests/reserve-flow.mjs
```

## Deploying

Production is a single VPS deployed with Ansible from a local checkout (`ansible-playbook deploy.yml` in
`ansible/`). The inventory and secrets are not in the repository. `CLAUDE.md` is the detailed operating guide.

`docs/deploy-cloudflare.md` and `docs/deploy-dokploy.md` describe earlier hosting and are kept for reference
only.

## Branches

Work happens on `backend-django`, and `main` is kept identical to it.
