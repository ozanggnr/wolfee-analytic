# Deployment Plan — Fly.io

Last updated: 2026-11-11 by Agent 1. Status: **PROPOSED — nothing here has been created.** No `fly launch`, no Fly apps, no Postgres cluster, no secrets set. Railway is retired as the target (user decision, 2026-11-11). Railway data is disposable.

Audience: the user and a few friends. Sizing is the smallest that works, with machines that stop when idle.

---

## 1. Decisions this plan assumes

| Topic | Decision |
|-------|----------|
| Backend host | One Fly app running the FastAPI backend |
| Frontend host | **Served by the same Fly app** (recommended, §6). Cloudflare Pages / Netlify only as a proxy, if kept |
| Database | One single-node Postgres on Fly, created empty. No data export from Railway, no baseline stamp |
| Migrations | Fly `release_command` runs `alembic upgrade head` before each deploy; a failure stops the deploy |
| Region | `fra` (Frankfurt) — closest general-purpose region to Turkey. Confirm with `fly platform regions` |
| D8 | Resolved by this plan: production starts empty, so the chain starts from revision `8c15c00878ff` (verified §8) |

---

## 2. Blockers before the first deploy

| # | Blocker | Owner | Detail |
|---|---------|-------|--------|
| F1 | **`alembic/env.py` picks a driver that is not installed** | Agent 2 | `env.py` rewrites the URL to `postgresql://`. With SQLAlchemy 2.1 (what `sqlalchemy[asyncio]>=2.0.0` installs today: 2.1.8) that means **psycopg 3**, which is not in `requirements.txt`. `alembic upgrade head` fails with `ModuleNotFoundError: No module named 'psycopg'` on any Postgres. Present on `main`, not introduced by `agent/backend`. Fix: replace with `postgresql+psycopg2://` (psycopg2-binary is already required). REQ-12 |
| F2 | `start.sh` hides migration failures | Agent 1 | §7. Not used on Fly (the release command replaces it), but fix it so no path hides failures |
| F3 | Cookies are only `Secure` when Railway env vars exist | config | Set `COOKIE_SECURE=true` on Fly (§4). Without it, session cookies are sent without `Secure` |
| F4 | `init_db()` `create_all` still creates `stock_data`, `turkish_gold`, `exchange_rates`, `ai_insights` (no migration covers them, DATABASE_CONTRACT §5 P3) | Agent 2 | Works on an empty database because Alembic runs first. Clean-up: a migration for those four tables, then limit `create_all` to SQLite. Not blocking a first deploy |
| F5 | Instruments not seeded (REQ-7) | Agent 2 | Only matters once `agent/backend` is deployed. Add the seed step to the release command when it exists |
| F6 | Unpinned dependencies | Agent 1 | Every requirement is `>=`. F1 is what that costs. Add a lock file (`uv pip compile` → `requirements.lock`) and build from it |

---

## 3. Files to add (drafts — not committed as files)

### 3.1 `Dockerfile` (repository root)

```dockerfile
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

RUN useradd --create-home app && chown -R app /app
USER app
WORKDIR /app/backend

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*"]
```

The frontend is copied because `main.py` serves `../frontend` at `/` (same origin, §6). Add a `.dockerignore` excluding `.venv`, `wolfee.db`, `*.xlsx`, `.git`, `__pycache__`, `.pytest_cache`.

### 3.2 `fly.toml`

```toml
app = "wolfee-analytics"          # must be globally unique on Fly; adjust
primary_region = "fra"

[build]
  dockerfile = "Dockerfile"

[deploy]
  release_command = "alembic upgrade head"   # runs in /app/backend; non-zero exit aborts the deploy
  strategy = "immediate"                     # one machine, nothing to roll

[env]
  COOKIE_SECURE = "true"
  APP_BASE_URL = "https://wolfee-analytics.fly.dev"
  CORS_ORIGINS = "https://wolfee-analytics.fly.dev"
  REQUIRE_EMAIL_VERIFICATION = "true"
  REFRESH_INTERVAL_MINUTES = "30"
  # Never set on Fly: ALLOW_DEV_CAPTCHA_BYPASS, AUTO_VERIFY_DEV

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

  [http_service.concurrency]
    type = "requests"
    soft_limit = 50
    hard_limit = 80

  [[http_service.checks]]
    method = "GET"
    path = "/healthz"
    interval = "30s"
    timeout = "5s"
    grace_period = "30s"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
```

Why 512 MB, not 256 MB: the process imports pandas, yfinance and google-generativeai and starts a refresh task over 361 symbols at boot. 256 MB is likely to be killed for running out of memory. Try 256 MB only after watching `fly logs` for memory pressure.

Health check: `/healthz` already exists. Fly does not wake a stopped machine to run a check, so checks do not defeat scale-to-zero.

---

## 4. Secrets and environment (names only)

Set secrets with `fly secrets set NAME=…`. **No values are recorded here.**

| Name | Kind | Required | Notes |
|------|------|----------|-------|
| `DATABASE_URL` | secret | yes | Set automatically by `fly postgres attach`. `database.py` converts `postgres://` to asyncpg |
| `GEMINI_API_KEY` | secret | no | Without it the AI text uses the template |
| `CAPTCHA_SECRET_KEY` | secret | if CAPTCHA is used | |
| `CAPTCHA_SITE_KEY` | env | if CAPTCHA is used | public |
| `CAPTCHA_VERIFY_URL` | env | no | |
| `RESEND_API_KEY` **or** `SENDGRID_API_KEY` **or** `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD` | secret | for e-mail verification | Pick one provider |
| `EMAIL_FROM` | env | for e-mail | |
| `ALPHA_VANTAGE_API_KEY`, `FINNHUB_API_KEY`, `POLYGON_API_KEY` | secret | no | Optional data sources |
| `COOKIE_SECURE` | env | **yes** | `true` (F3) |
| `APP_BASE_URL` | env | yes | Used in e-mail links; Fly has no `RAILWAY_PUBLIC_DOMAIN` |
| `CORS_ORIGINS` | env | yes | The Fly URL (plus any proxy origin, §6) |
| `GEMINI_MODEL`, `AI_INSIGHT_CACHE_HOURS`, `SESSION_DURATION_DAYS`, `REFRESH_INTERVAL_MINUTES`, `REQUIRE_EMAIL_VERIFICATION` | env | no | Defaults in code |
| `ALLOW_DEV_CAPTCHA_BYPASS`, `AUTO_VERIFY_DEV` | env | **must not be set** | Development only |

`RAILWAY_ENVIRONMENT` / `RAILWAY_PUBLIC_DOMAIN` are read by the code but will be absent on Fly. `COOKIE_SECURE`, `APP_BASE_URL` and `CORS_ORIGINS` replace what they did.

---

## 5. Postgres

Recommended: **one unmanaged single-node Fly Postgres**, the development configuration (shared-cpu-1x, 256 MB, 1 GB volume), in `fra`, attached to the app:

```
fly postgres create --name wolfee-db --region fra   # choose "Development - Single node"
fly postgres attach wolfee-db --app wolfee-analytics
```

- When the CLI offers to stop the single node when idle, accept it: it then costs only storage while nobody uses the app. First request after idle waits for both machines to start.
- Unmanaged means Fly does not handle backups, upgrades or failover. Acceptable because the data is disposable. Take a volume snapshot before risky migrations (`fly volumes snapshots create`).
- Fly **Managed Postgres** (`fly mpg`) starts at $38/month for the Basic plan — out of proportion for this app. Revisit only if real data starts to matter.
- Fly may steer `fly postgres create` towards Managed Postgres or change the unmanaged option. Confirm what the CLI offers at creation time.

---

## 6. Frontend

The existing auth design requires the browser to see **one origin** for pages and API:

- `frontend/js/config.js` uses `API_URL = ''` (relative URLs) whenever there is no port in the address.
- Session and CSRF cookies are `SameSite=Lax`; the CSRF token is read by page JavaScript from a cookie. Neither works when the page is on `*.pages.dev` / `*.netlify.app` and the API on `*.fly.dev` (different sites).

Options:

| Option | Work | Recommendation |
|--------|------|----------------|
| A. Serve the frontend from the Fly app (already how `main.py` works) and give friends the Fly URL or a custom domain | None | **Recommended.** Then disconnect the Cloudflare Pages and Netlify Git integrations, which also stops non-main pushes from deploying previews (the reason `integration` was not pushed) |
| B. Keep Netlify, proxy the API through it | `frontend/_redirects`: `/api/*  https://wolfee-analytics.fly.dev/api/:splat  200`, plus `/healthz` | Works: the browser only sees the Netlify origin. Adds a hop and a second host to keep in sync |
| C. Keep Cloudflare Pages, proxy through a Pages Function | `functions/api/[[path]].js` forwarding to the Fly URL with cookies | Works, more code. Cloudflare `_redirects` cannot proxy to another domain |

Pointing the frontend directly at the Fly URL across origins is **not** an option without changing cookie, CSRF and CORS behaviour, which is a security-relevant change requiring a separate review.

---

## 7. `start.sh` — fails silently today

Current (`backend/start.sh` on `main`):

```bash
alembic upgrade head || echo "Alembic migrations completed or handled by database init_db"
```

Any migration error prints a reassuring message and the server starts anyway, on whatever schema `create_all` produced. F1 shows this was very likely happening on every Railway deploy.

Proposed replacement (Agent 1 file; **not committed**, pending approval):

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "Running database migrations..."
alembic upgrade head

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
```

On Fly the release command runs the migration and the Docker `CMD` starts uvicorn directly, so `start.sh` is only for running locally or on another host.

---

## 8. Verification already done (2026-11-11, local)

PostgreSQL **16.2**, empty database, `agent/backend` at `978b054`, Python 3.11.9, SQLAlchemy 2.1.8, Alembic 1.20.1. Docker is not installed on this machine, so Postgres ran from portable binaries (`pgserver` package) in a scratch directory instead of a container — the same server version and SQL behaviour.

| Step | Result |
|------|--------|
| `alembic upgrade head` with the branch's code unchanged | **Failed** — F1 (`No module named 'psycopg'`) |
| Same, with only the driver changed to `postgresql+psycopg2://` in a scratch copy | `8c15c00878ff` → `a1f3c9d27b10` → `b2e4d8a31c55`, exit 0 |
| `alembic downgrade base` | All three downgrades ran, exit 0, `current` empty |
| `alembic upgrade head` again | Clean, head `b2e4d8a31c55` |
| Schema check | Partial unique index `uq_portfolios_user_name_active … WHERE (archived_at IS NULL)` created; unique `uq_transactions_voids_transaction_id`; all 7 CHECK constraints; `transactions.id` and `voids_transaction_id` are `bigint`; `created_at` is `timestamptz` |
| Backend tests against Postgres | 64 passed, then stopped at the first error: the API test fixtures create the asyncpg pool in one event loop (`asyncio.run(init_db())`) and reuse it in the TestClient's loop. A test-harness problem, not a product defect. Service tests are hard-wired to SQLite. REQ-9 stays open: Agent 2 to make the fixtures Postgres-safe (for example `NullPool` under test) |

Not verified: anything on Fly itself; the release command in a Fly release machine; memory use at 512 MB; cold-start time.

---

## 9. Expected monthly cost (USD)

List prices from fly.io/pricing as of 2026-11-11: shared-cpu-1x 256 MB **$2.19/month**, 512 MB **$3.69/month**, both billed per second **only while running**. Managed Postgres Basic **$38/month** plus $0.28/GB. Volume price taken from Fly's pricing page at the time of setup (historically about $0.15/GB-month; not re-checked).

| Item | Always on | With scale-to-zero (a few friends, ~2 h use/day) |
|------|-----------|------------------------------------------------|
| App machine, shared-cpu-1x 512 MB | $3.69 | ≈ $0.30 |
| Postgres machine, shared-cpu-1x 256 MB | $2.19 | ≈ $0.20 if it stops when idle; $2.19 if it does not |
| Postgres volume, 1 GB | ≈ $0.15 | ≈ $0.15 |
| Release machine (seconds per deploy) | ≈ $0 | ≈ $0 |
| Shared IPv4 / IPv6, TLS on `*.fly.dev` | $0 | $0 |
| Outbound data (small JSON pages) | ≈ $0 | ≈ $0 |
| **Total** | **≈ $6 / month** | **≈ $1–3 / month** |

With Managed Postgres instead: ≈ $42+/month. A dedicated IPv4 would add $2/month and is not needed.

Do not count on a free allowance; check the Fly billing page after the first month. Set a spending alert in the Fly dashboard.

---

## 10. Deploy sequence (when approved — not started)

1. Fix F1 (Agent 2) and F2/F6 (Agent 1) on `integration`; merge `agent/backend` and `agent/frontend` per the integration plan.
2. Add `Dockerfile`, `.dockerignore`, `fly.toml` on `integration` (Agent 1).
3. `fly apps create`, `fly postgres create`, `fly postgres attach`, `fly secrets set …` — **user runs or approves each command**.
4. `fly deploy` from `integration`. Release command migrates the empty database; app starts; check `/healthz` and the smoke list (IMPLEMENTATION_STATUS §8).
5. Seed instruments once REQ-7 exists.
6. Choose §6 option; disconnect unused Cloudflare/Netlify Git integrations.
7. Merge `integration` into `main` only after the deploy is verified.

---

## 11. Requests raised by this plan

```
ID:        REQ-12
From:      Agent 1
To:        Agent 2
Needs:     backend/alembic/env.py: use "postgresql+psycopg2://" (not "postgresql://") for the
           sync URL, and a test that builds the Alembic URL from a postgres:// DATABASE_URL
Why:       with SQLAlchemy 2.1 "postgresql://" selects psycopg 3, which is not installed;
           every Postgres migration fails (DEPLOYMENT §2 F1)
Blocking:  yes, for any Postgres deploy
Status:    open
```

REQ-9 (Postgres test run) is updated by §8: migrations verified, API test fixtures need to be made Postgres-safe.
