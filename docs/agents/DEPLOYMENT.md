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
| F1 | **`alembic/env.py` picks a driver that is not installed** | Agent 2 | `env.py` rewrites the URL to `postgresql://`. With SQLAlchemy 2.1 (what `sqlalchemy[asyncio]>=2.0.0` installs today: 2.1.8) that means **psycopg 3**, which is not in `requirements.txt`. `alembic upgrade head` fails with `ModuleNotFoundError: No module named 'psycopg'` on any Postgres. Present on `main`, not introduced by `agent/backend`. Fix: replace with `postgresql+psycopg2://` (psycopg2-binary is already required). REQ-12 — **CLOSED**: fixed on `agent/backend` `6170686`, arrives with Step 2 |
| F2 | `start.sh` hides migration failures | Agent 1 | **DONE** `5afdb26` (§7) |
| F3 | Cookies are only `Secure` when Railway env vars exist | config | Set `COOKIE_SECURE=true` on Fly (§4). Without it, session cookies are sent without `Secure` |
| F4 | `init_db()` `create_all` still creates `stock_data`, `turkish_gold`, `exchange_rates`, `ai_insights` (no migration covers them, DATABASE_CONTRACT §5 P3) | Agent 2 | **DONE**: migrations cover all 13 model tables (`alembic check` clean on PG16, 2026-11-15) and `init_db` creates tables only on SQLite (`a63f25d`) |
| F5 | Instruments not seeded (REQ-7) | Agent 2 | **DONE**: `python -m services.instrument_service` is in the release command; idempotent (361 / 0 on two runs, 2026-11-15) |
| F6 | Unpinned dependencies | Agent 1 | **DONE** `5afdb26`: exact pins in `backend/requirements.txt`; hash-pinned `backend/requirements.lock` (Linux, py3.11) installed by the Dockerfile |
| F7 | `Dockerfile`, `.dockerignore`, `fly.toml` | Agent 1 | **DONE** `4885064`, plus `.gitattributes` for LF endings `97a5ac1`. The release command needs `services.instrument_service`, which arrives with `agent/backend` (Step 2) |

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
  REQUIRE_EMAIL_VERIFICATION = "false"   # no e-mail provider at launch (D2)
  REFRESH_INTERVAL_MINUTES = "30"
  # Never set on Fly: AUTO_VERIFY_DEV

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
| `REGISTRATION_INVITE_CODE` | secret | **yes** | Invite code required by `POST /api/auth/register` (D1; merged at `7bf4d6b`). Unset = registration closed. Generate a long random value (e.g. `openssl rand -hex 16`), share it with invited users out of band, rotate with `fly secrets set` (read on every request) |
| `RESEND_API_KEY` **or** `SENDGRID_API_KEY` **or** `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD` | secret | **not at launch** (D2) | Adding one later re-enables password reset and lets `REQUIRE_EMAIL_VERIFICATION` go back to `true` |
| `EMAIL_FROM` | env | with a provider | |
| `ALPHA_VANTAGE_API_KEY`, `FINNHUB_API_KEY`, `POLYGON_API_KEY` | — | no | **Not read by any code** since `api_router.py` was deleted (`fe6d8c6`). Do not set them |
| `COOKIE_SECURE` | env | **yes** | `true` (F3) |
| `APP_BASE_URL` | env | yes | Used in e-mail links; Fly has no `RAILWAY_PUBLIC_DOMAIN` |
| `CORS_ORIGINS` | env | yes | The Fly URL (plus any proxy origin, §6) |
| `REQUIRE_EMAIL_VERIFICATION` | env | yes | `false` at launch (D2, set in `fly.toml`) |
| `GEMINI_MODEL`, `AI_INSIGHT_CACHE_HOURS`, `SESSION_DURATION_DAYS`, `REFRESH_INTERVAL_MINUTES` | env | no | Defaults in code |
| `AUTO_VERIFY_DEV` | env | **must not be set** | Development only |

`RAILWAY_ENVIRONMENT` / `RAILWAY_PUBLIC_DOMAIN` are read by the code but will be absent on Fly. `COOKIE_SECURE`, `APP_BASE_URL` and `CORS_ORIGINS` replace what they did.

---

## 5. Postgres

Recommended: **one unmanaged single-node Fly Postgres**, the development configuration (shared-cpu-1x, 256 MB, 1 GB volume), in `fra`, attached to the app:

```
fly postgres create --name wolfee-db --region fra --image-ref flyio/postgres-flex:16   # choose "Development - Single node"
fly postgres attach wolfee-db --app wolfee-analytics
```

**PostgreSQL major version is pinned to 16** (user, 2026-11-14), the same major as the official test cluster (TESTING.md §3, 16.16 in WSL):

- `--image-ref flyio/postgres-flex:16` is required. Without it, `fly postgres create` uses Fly's current default, which can be a newer major. The `16` tag tracks the latest 16.x (16.11 on Docker Hub, checked 2026-11-14), so minor and security updates still arrive. Exact minor versions cannot match: Fly's images lag the PGDG packages.
- **Verify right after creation**, before `attach`: `fly postgres connect -a wolfee-db`, then `SHOW server_version;` must start with `16.`. If it does not, destroy the empty database app and create it again with the image ref.
- **Upgrades:** before any `fly image update -a wolfee-db`, check that the target image is still a `16.x` tag. A major upgrade (16 → 17+) needs a dump and restore, plus moving the test cluster to the same major first. It is a decision for the user, not a routine update.
- `fly.toml` cannot pin this: Postgres is a separate Fly app, created by the command above. `fly.toml` only carries a comment that points here.

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

### 8.1 Re-verification in the official test environment (2026-11-14, WSL, PostgreSQL 16.16)

Commands in TESTING.md §3.1 / §3.2, run read-only against `agent/backend` @ `771368f`:

| Step | Result |
|------|--------|
| `alembic upgrade head` on an empty database | `8c15c00878ff` → `a1f3c9d27b10` → `b2e4d8a31c55` → `c3f5a7e91d20` (REQ-16) → `d7b2e6f4a913` (price_history, REQ-26), exit 0. F1 is fixed: no driver change needed |
| `alembic downgrade base` | all five downgrades, exit 0 |
| `alembic upgrade head` again | clean, single head `d7b2e6f4a913` |
| `alembic check` | "No new upgrade operations detected", exit 0: migrations alone build the models' schema |
| Tables | 14: the 13 model tables + `alembic_version` |
| API tests on Postgres (REQ-9 harness) | **179 passed**. The §8 event-loop problem is solved by `DB_POOL=null` under test |

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

### 2.1 Readiness review on `integration` @ `10318c3` (2026-11-15)

Everything on `integration` passes in WSL (TESTING.md §5) and the browser smoke test (TESTING.md §3.4). No Fly resource exists yet.

**Must be settled before the first `fly deploy`:**

| # | Item | Owner | Detail |
|---|------|-------|--------|
| D1 | **No CAPTCHA; registration needs an invite code** — DECIDED (user, 2026-11-16) | Agent 2 (REQ-36), Agent 4 (REQ-37) | CAPTCHA is dropped: `CAPTCHA_SECRET_KEY` / `CAPTCHA_SITE_KEY` / `CAPTCHA_VERIFY_URL` are removed from the plan and are not set. `POST /api/auth/register` requires an invite code compared with the new secret `REGISTRATION_INVITE_CODE`; the form gets an invite-code field. The IP rate limits and the login lockout stay. **DONE**: REQ-36 merged at `7bf4d6b`, REQ-37 at `dd08370`; verified 2026-11-16 (TESTING.md §5) |
| D2 | **No e-mail provider at launch** — DECIDED (user, 2026-11-16) | Agent 1 (`fly.toml`), Agent 2 (REQ-36 c), Agent 4 (REQ-37 b) | `REQUIRE_EMAIL_VERIFICATION=false` (set in `fly.toml`): accounts are usable right after registration. Password reset and resend-verification stay **unavailable** until a provider is added. Today, without a provider, `auth_utils` writes the full reset / verification link to the log, which would put live reset tokens in Fly logs: REQ-36 (c) makes those routes refuse without creating a token, and the UI hides them. **DONE**: merged at `7bf4d6b` / `dd08370`; verified 2026-11-16, no token in the logs |
| D3 | **Postgres time zone must be UTC** — DECIDED (user, 2026-11-16) | Agent 1 at deploy; Agent 2 for the permanent fix | Right after `fly postgres create`, run `show timezone`; if it is not `UTC`, run `ALTER DATABASE <db> SET timezone TO 'UTC'` before the first `fly deploy` (§10 step 3). Why: `stock_data`, `turkish_gold`, `exchange_rates` `updated_at` and `ai_insights.created_at` are `timestamp without time zone` with `server_default=now()` and are read as UTC; on the Europe/Istanbul WSL cluster the insight's "data as of" read 3 h ahead. Permanent fix REQ-33 (a) merged at `7bf4d6b`: the application now writes UTC on insert and update, so only the `server_default` path still depends on the database time zone; keep the check (§10.1 U4, U6) |
| D4 | **App name** — DECIDED (user, 2026-11-16): checked at deploy time | Agent 1 at deploy | `fly.toml` uses `wolfee-analytics` and `https://wolfee-analytics.fly.dev` in `APP_BASE_URL` / `CORS_ORIGINS`. If `fly apps create` reports the name taken, change all three together before deploying |
| D6 | **Client IP is spoofable** — found 2026-11-16 | Agent 2 (REQ-39) | `get_client_ip` trusts `CF-Connecting-IP` and the left-most `X-Forwarded-For`; both come from the client, and uvicorn runs with `--forwarded-allow-ips=*`. A different fake IP per request bypasses the 5-per-hour invite limit, the 10/min auth limit and the 120/min API limit (the per-account login lockout still holds). On Fly the trusted value is `Fly-Client-IP`, which the Fly proxy sets. **DONE 2026-11-16**: REQ-39 merged at `c9aff26` (on Fly only `Fly-Client-IP`; locally the socket peer) and the uvicorn trust-all flags removed at `037077d`. Keep the long random invite code anyway |
| D5 | Fly Postgres major version | user runs | `--image-ref flyio/postgres-flex:16` (§5); tests run on 16.16 |

**Should be fixed soon after; not blocking:**

| # | Item | Owner | Detail |
|---|------|-------|--------|
| S1 | Stale CORS origins | Agent 2 (REQ-33 b) | `main.py` still allows `*.up.railway.app` (regex), `RAILWAY_PUBLIC_DOMAIN`, `wolfee-backend.onrender.com` and `solitary-scene-04bc…workers.dev`, all with credentials. Not exploitable today because the session cookie is `SameSite=Lax`, but the list should hold only the Fly origin and localhost |
| S2 | Old deploy configs | done / user | `railway.json` and `wrangler.jsonc` **deleted** (user, 2026-11-16: Railway is gone, Cloudflare is being disconnected). The Cloudflare Pages worker was deleted with REQ-37 (`dd08370`). The user disconnects the Cloudflare project |
| S3 | Indicators start empty | none | On a fresh database every card shows "Not available" for RSI / average / volatility and `/api/opportunities` is empty until the daily-close job has stored 15 / 20 / 21 closes. With `auto_stop_machines = "stop"` the job runs only while the machine is awake. Expected (D4); tell users at launch |
| S4 | UI and AI wording | Agent 4 (REQ-34 a, c, d), Agent 3 (REQ-35) | "AI generated" badge on template text; a 422 would show "[object Object]"; the market disclaimer mentions "your recorded transactions" |
| S5 | Portfolio page | Agent 4 (REQ-32) | The ledger API is live but has no UI yet |

---

## 10. Deploy sequence (when approved — not started)

Ready on `integration` @ the commit after `dd08370` (verified 2026-11-16, TESTING.md §5). `fly deploy` builds from the local `wolfee-integration` checkout, so **nothing is pushed** and `main` is not touched. `fly launch` is never used (it would rewrite `fly.toml`). Names below: app `wolfee-analytics`, database app `wolfee-db`, region `fra`; the database that `attach` creates is `wolfee_analytics`.

**Changed 2026-11-16 (user): deploys run from GitHub Actions** (`.github/workflows/deploy.yml`): pull requests to `main` run the tests; a push to `main` runs the tests and, only if they pass, `flyctl deploy --remote-only` (one deploy at a time). The user pushes; Agent 1 never pushes. D6 is resolved (REQ-39). Order: U1–U8 first, then the push.

### 10.1 Commands the user runs (they create resources, cost money, or carry secret values)

```sh
# U1. Sign in and confirm the organisation
fly auth login
fly orgs list

# U2. App (D4: if the name is taken, stop and tell Agent 1; app, APP_BASE_URL and CORS_ORIGINS change together)
fly apps create wolfee-analytics --org personal

# U3. Postgres 16, single node (D5); choose "Development - Single node" if asked
fly postgres create --name wolfee-db --region fra --image-ref flyio/postgres-flex:16 --org personal

# U4. Check version and time zone (D3, D5) in the psql shell that opens:
fly postgres connect -a wolfee-db
#   SHOW server_version;   -- must start with 16.
#   SHOW timezone;         -- note the value (UTC or Etc/UTC is fine)
#   \q

# U5. Attach: creates database wolfee_analytics and sets the DATABASE_URL secret on the app
fly postgres attach wolfee-db --app wolfee-analytics

# U6. Only if U4 showed a time zone other than UTC / Etc/UTC:
fly postgres connect -a wolfee-db
#   ALTER DATABASE wolfee_analytics SET timezone TO 'UTC';
#   \q

# U7. Secrets: values never go into chat, files or this repository.
#     Generate the invite code locally, keep it in a password manager, share it out of band.
openssl rand -hex 16
fly secrets set --stage -a wolfee-analytics REGISTRATION_INVITE_CODE=<the generated value>
fly secrets set --stage -a wolfee-analytics GEMINI_API_KEY=<key>      # optional; without it the AI text uses the template
fly secrets list -a wolfee-analytics                                   # names and digests only

# U8. CI deploy token, scoped to this app only; paste it as the repository secret FLY_API_TOKEN
#     (GitHub → Settings → Secrets and variables → Actions). Never into chat or a file.
fly tokens create deploy -a wolfee-analytics

# U9. Push (only after Agent 1 reports main == integration and the tests pass in WSL)
git -C <main checkout> push origin main
```

Not set, on purpose: CAPTCHA keys (D1), e-mail provider keys (D2), `AUTO_VERIFY_DEV` (must never be set). `REQUIRE_EMAIL_VERIFICATION=false`, `COOKIE_SECURE`, `APP_BASE_URL` and `CORS_ORIGINS` come from `fly.toml`.

### 10.2 After the push: the workflow deploys; Agent 1 verifies (read-only)

The deploy itself is the `deploy` job of the workflow; A2 below is only the manual fallback if the user asks for it. A1 and A3 are read-only.

```sh
# A1. Pre-flight, read-only
git -C ../wolfee-integration status --short          # must be clean
fly status -a wolfee-analytics
fly secrets list -a wolfee-analytics                 # DATABASE_URL and REGISTRATION_INVITE_CODE present
fly config validate -c fly.toml

# A2. (fallback only, on request) deploy the same commit from the main checkout
fly deploy -c fly.toml -a wolfee-analytics

# A3. Verify
fly status -a wolfee-analytics
fly logs -a wolfee-analytics --no-tail               # release command: migration to e4a8c2f6b1d3, "361 inserted"
curl -fsS https://wolfee-analytics.fly.dev/healthz
curl -fsS https://wolfee-analytics.fly.dev/api/auth/config    # {"email_enabled":false,"registration_open":true}
#   wrong-code register -> 403; forgot-password -> 503 (expected without a provider)
#   then the browser smoke (TESTING.md §3.4) against the Fly URL at 1440 and 390 px, with the code the user supplies at that moment
fly logs -a wolfee-analytics --no-tail | grep -ciE 'token=|reset-password\?|verify-email\?|Set-Cookie'   # must be 0
```

### 10.3 After the deploy is verified (user)

- Railway, Cloudflare and Netlify are disconnected from the repository by the user before the push (2026-11-16).
- Later changes: merge into `integration`, verify, fast-forward `main`, the user pushes; the workflow deploys.

Rollback: `fly releases -a wolfee-analytics`, then `fly deploy --image <previous image>`; or `fly scale count 0 -a wolfee-analytics` to take the app offline. Data is disposable (§5).

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
Status:    CLOSED 2026-11-11 — fixed by Agent 2 on agent/backend 6170686 (arrives with Step 2)
```

REQ-9 (Postgres test run) is updated by §8: migrations verified, API test fixtures need to be made Postgres-safe.
