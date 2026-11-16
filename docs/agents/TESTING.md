# Testing — official environment (WSL Ubuntu)

Decided by the user on 2026-11-14. Windows Smart App Control blocks the Windows Python venvs, so **all tests run in WSL Ubuntu**. Results from Windows Python are no longer evidence.

Rules:

- Tests run in WSL against the Windows worktrees through `/mnt/c/Users/ozang/Desktop/Projects/<worktree>`.
- **Git stays on Windows.** Never run `git` from WSL against these worktrees: line endings and file modes would show as changes.
- The venv and the Postgres data live in the WSL home directory, outside every repository.
- Run backend tests from the **worktree root** (REQ-11).

Verified layout (2026-11-14):

| What | Where | Version |
|------|-------|---------|
| uv | `~/.local/bin/uv` | 0.13.8 |
| Python | managed by uv | 3.11.9 (same as the Docker image) |
| venv | `~/venvs/wolfee` | from `backend/requirements.lock` + `backend/requirements-test.txt` |
| Node | `~/.local/opt/node` (symlink to `node-v24.14.0-linux-x64`) | 24.14.0 (same as Windows) |
| Postgres test cluster | `~/wolfee-test/pg16`, port **55432**, `127.0.0.1` only, socket dir `~/wolfee-test/run` | 16.16 (PGDG `postgresql-16`, installed 2026-11-14) |
| Scratch files | `~/wolfee-test/` | |

Every command below runs in a WSL shell (`wsl` from Windows, or the Ubuntu terminal).

---

## 1. One-time setup (no sudo)

```bash
# uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"          # the installer also adds this to ~/.bashrc

# Python 3.11.9 and the venv, outside the repo
uv python install 3.11.9
uv venv --python 3.11.9 ~/venvs/wolfee
cd /mnt/c/Users/ozang/Desktop/Projects/wolfee-integration
uv pip install --python ~/venvs/wolfee/bin/python --require-hashes -r backend/requirements.lock
uv pip install --python ~/venvs/wolfee/bin/python -r backend/requirements-test.txt

# Node 24.14.0 for the frontend tests (checksum verified against nodejs.org)
V=v24.14.0; F=node-$V-linux-x64.tar.xz
mkdir -p ~/.local/opt ~/wolfee-test/dl && cd ~/wolfee-test/dl
curl -fsSLO https://nodejs.org/dist/$V/$F
curl -fsSLO https://nodejs.org/dist/$V/SHASUMS256.txt
grep " $F\$" SHASUMS256.txt | sha256sum -c -
tar -xJf $F -C ~/.local/opt
ln -sfn ~/.local/opt/node-$V-linux-x64 ~/.local/opt/node
```

When `backend/requirements.lock` changes, re-run the two `uv pip install` lines. Add `--reinstall` if a pin was downgraded.

## 2. Backend and frontend suites (SQLite, the default)

```bash
cd /mnt/c/Users/ozang/Desktop/Projects/wolfee-integration    # or any other worktree
mkdir -p ~/wolfee-test && rm -f ~/wolfee-test/test.db
env -u GEMINI_API_KEY DATABASE_URL="sqlite+aiosqlite:///$HOME/wolfee-test/test.db" \
    ~/venvs/wolfee/bin/python -m pytest backend/tests -q -p no:cacheprovider

cd frontend && ~/.local/opt/node/bin/node --test
```

`env -u GEMINI_API_KEY` makes sure no test can call the real model. The SQLite file lives in the WSL home directory, not in the worktree.

## 3. Postgres 16 test cluster

Ubuntu 26.04 ships PostgreSQL **18** only. Production is pinned to major version **16** (`flyio/postgres-flex:16`, DEPLOYMENT.md §5), so the PG16 binaries come from the PostgreSQL project's apt repository, which supports Ubuntu 26.04 ("resolute"). Test and production share the major version; minor versions differ (16.16 here, Fly's latest 16.x image in production). If production ever moves to a new major, move this cluster first.

**One-time, needs sudo (the user runs these):**

```bash
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
sudo apt install -y postgresql-16
# On this machine (2026-11-14) the package did NOT create a system cluster
# (`pg_dropcluster --stop 16 main` -> "specified cluster does not exist"). If one appears
# on another machine, the tests do not use it, and it can be removed with that command.
```

**Everything else runs as your own user.** The cluster below is disposable, trusts local connections only on `127.0.0.1`, and holds no real data.

```bash
# create once
B=/usr/lib/postgresql/16/bin; D=$HOME/wolfee-test/pg16; R=$HOME/wolfee-test/run
mkdir -p "$R"
[ -d "$D" ] || $B/initdb -D "$D" -U postgres --auth=trust --encoding=UTF8 --locale=C.UTF-8

# start (again after every WSL restart; WSL does not start it for you)
$B/pg_ctl -D "$D" -l "$D.log" -o "-p 55432 -k $R -c listen_addresses=127.0.0.1" -w start

# stop
$B/pg_ctl -D "$D" -w stop
```

### 3.1 API tests on Postgres (REQ-9)

They need a **fresh, empty** database every run, because the fixtures run `alembic upgrade head` and then write users and ledgers.

```bash
B=/usr/lib/postgresql/16/bin
$B/dropdb   -h 127.0.0.1 -p 55432 -U postgres --if-exists wolfee_tests
$B/createdb -h 127.0.0.1 -p 55432 -U postgres wolfee_tests
cd /mnt/c/Users/ozang/Desktop/Projects/wolfee-integration
env -u GEMINI_API_KEY WOLFEE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/wolfee_tests \
    ~/venvs/wolfee/bin/python -m pytest backend/tests/api -q -p no:cacheprovider -W ignore
```

`WOLFEE_TEST_POSTGRES_URL` and `backend/tests/api` came from `agent/backend` and are on `integration` since `a63f25d` (2026-11-15). When running against another agent's worktree, prefix with `PYTHONDONTWRITEBYTECODE=1` so nothing is written into it.

### 3.2 Migration chain on an empty Postgres

```bash
B=/usr/lib/postgresql/16/bin
$B/dropdb   -h 127.0.0.1 -p 55432 -U postgres --if-exists wolfee_migrations
$B/createdb -h 127.0.0.1 -p 55432 -U postgres wolfee_migrations
cd /mnt/c/Users/ozang/Desktop/Projects/wolfee-integration/backend
export DATABASE_URL=postgresql://postgres@127.0.0.1:55432/wolfee_migrations
~/venvs/wolfee/bin/alembic upgrade head
~/venvs/wolfee/bin/alembic downgrade base
~/venvs/wolfee/bin/alembic upgrade head
~/venvs/wolfee/bin/alembic check          # must report no differences (DATABASE_CONTRACT §4.2, §4.3)
unset DATABASE_URL
```

### 3.3 Instrument seed (REQ-7) on the migrated database

Run after §3.2, with the database still at head. A second run must insert and update nothing.

```bash
cd /mnt/c/Users/ozang/Desktop/Projects/wolfee-integration/backend
for i in 1 2; do
  env -u GEMINI_API_KEY DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/wolfee_migrations \
      ~/venvs/wolfee/bin/python -m services.instrument_service
done
/usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -p 55432 -U postgres -d wolfee_migrations \
    -Atc "select count(*), count(distinct provider_symbol) from instruments"
```

### 3.4 Browser smoke test against the real backend

Start the app in WSL on port **8000**: the frontend's `js/config.js` calls the API on `:8000` unless the page is served from port 8000 or from a URL without a port. Use its own migrated and seeded database, real providers and no model key:

```bash
B=/usr/lib/postgresql/16/bin
$B/dropdb -h 127.0.0.1 -p 55432 -U postgres --if-exists wolfee_smoke
$B/createdb -h 127.0.0.1 -p 55432 -U postgres wolfee_smoke
cd /mnt/c/Users/ozang/Desktop/Projects/wolfee-integration/backend
DATABASE_URL=postgresql://postgres@127.0.0.1:55432/wolfee_smoke ~/venvs/wolfee/bin/alembic upgrade head
env -u GEMINI_API_KEY DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/wolfee_smoke \
    ~/venvs/wolfee/bin/python -m services.instrument_service
env -u GEMINI_API_KEY -u RESEND_API_KEY -u SENDGRID_API_KEY -u SMTP_HOST PYTHONDONTWRITEBYTECODE=1 \
    REGISTRATION_INVITE_CODE="$(openssl rand -hex 16)" \
    DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/wolfee_smoke \
    AUTO_VERIFY_DEV=true COOKIE_SECURE=false \
    ~/venvs/wolfee/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

Then drive it from Windows with headless Chrome (Playwright, own throwaway profile) at **1440×900** and **390×844** (mobile, touch). Cover Market, the stock detail modal (add to watchlist), Opportunities, Watchlist, the account dialog (register and sign in with an `example.com` address; the server rejects reserved names such as `.test`), the signed-in Watchlist and, on mobile, the account sheet. On each page check: no horizontal scroll, no element past the viewport, no "NaN" / "undefined" / "[object Object]" / "▲ 0.00%" text, console errors and HTTP ≥ 400. `AUTO_VERIFY_DEV` is for this local run only.

## 4. What counts as evidence

A report of "tests pass" names the worktree, its commit (from Windows `git log -1`), the command from this file, and the last pytest / `node --test` summary line. Postgres results also give `select version()`.

## 5. Verification log

| Date | Worktree @ commit | Command | Result |
|------|-------------------|---------|--------|
| 2026-11-14 | `wolfee-integration` @ `acfd92e` | §2 backend | 224 passed, 1 warning (67 s) |
| 2026-11-14 | `wolfee-integration` @ `acfd92e` | §2 frontend | 9 tests, 9 pass, 0 fail |
| 2026-11-14 | `Wolfee-backend` @ `771368f` (read-only) | §3.1 on a **temporary PostgreSQL 18.6** user cluster (`~/wolfee-test/pg18`), because PG16 is not installed yet | 179 passed |
| 2026-11-14 | `Wolfee-backend` @ `771368f` (read-only) | §3.1 on **PostgreSQL 16.16**, fresh `wolfee_tests` | **179 passed** (23 s) |
| 2026-11-14 | `Wolfee-backend` @ `771368f` (read-only) | §3.2 on **PostgreSQL 16.16**, empty `wolfee_migrations` | upgrade head → downgrade base → upgrade head all exit 0 through `8c15c00878ff`, `a1f3c9d27b10`, `b2e4d8a31c55`, `c3f5a7e91d20`, `d7b2e6f4a913`; single head `d7b2e6f4a913`; `alembic check`: "No new upgrade operations detected"; 14 tables (13 model tables + `alembic_version`) |

| 2026-11-14 | `wolfee-integration` @ `f0b9fc9` (after merging `agent/quant-ai` `def3511` and `agent/frontend` `ceecbda`) | §2 backend | **281 passed**, 1 warning (67 s) |
| 2026-11-14 | `wolfee-integration` @ `f0b9fc9` | §2 frontend | **28 tests, 28 pass, 0 fail** |

| 2026-11-15 | `wolfee-integration` @ `a63f25d` (after merging `agent/backend` `13b8c61`; frontend still `ceecbda`) | §2 backend (repo root) | **564 passed**, 3 warnings (94 s) |
| 2026-11-15 | `wolfee-integration` @ `a63f25d` | §2 frontend | **28 tests, 28 pass, 0 fail** |
| 2026-11-15 | `wolfee-integration` @ `a63f25d` | §3.1 on **PostgreSQL 16.16**, fresh `wolfee_tests` | **187 passed** (47 s) |
| 2026-11-15 | `wolfee-integration` @ `a63f25d` | §3.2 on **PostgreSQL 16.16**, empty `wolfee_migrations` | upgrade head → downgrade base → upgrade head all exit 0; single head **`e4a8c2f6b1d3`**; `alembic check`: "No new upgrade operations detected"; 14 tables; `ai_insights.generated_by/generated_at/inputs_as_of/is_fallback` nullable, no default |
| 2026-11-15 | `wolfee-integration` @ `a63f25d` | §3.3 seed on the migrated `wolfee_migrations` | run 1 "361 inserted, 0 updated"; run 2 "0 inserted, 0 updated"; 361 distinct `provider_symbol` |
| 2026-11-15 | `wolfee-integration` @ `a63f25d` | §2 backend run from `backend/` (REQ-11 check) | 3 failed, 561 passed: the known `test_performance_and_sources.py` failures (`No module named 'backend'`); not evidence, use the repo root |

| 2026-11-15 | `wolfee-integration` @ `836c3a3` (after merging `agent/quant-ai` `631dc76`) | §2 backend (repo root) | **583 passed**, 3 warnings (110 s). No test covers a null `change_pct` in the watchlist (REQ-31 a), so the known crash does not show here |
| 2026-11-15 | `wolfee-integration` @ `836c3a3` | §2 frontend | **28 tests, 28 pass, 0 fail** |

The temporary PostgreSQL 18 cluster (`~/wolfee-test/pg18` and `pg18.log`) was deleted on 2026-11-14.

| 2026-11-15 | `wolfee-integration` @ `10318c3` (after merging `agent/backend` `98ee277` and `agent/frontend` `a75332b`) | §2 backend (repo root) | **598 passed**, 3 warnings (159 s) |
| 2026-11-15 | `wolfee-integration` @ `10318c3` | §2 frontend | **41 tests, 41 pass, 0 fail** |
| 2026-11-15 | `wolfee-integration` @ `10318c3` | §3.1 on **PostgreSQL 16.16**, fresh `wolfee_tests` | **191 passed** (31 s) |
| 2026-11-15 | `wolfee-integration` @ `10318c3` | §3.2 on **PostgreSQL 16.16**, empty `wolfee_migrations`: upgrade → downgrade base → upgrade → downgrade base → upgrade | all exit 0; single head `e4a8c2f6b1d3`; `alembic check`: "No new upgrade operations detected"; 14 tables |
| 2026-11-15 | `wolfee-integration` @ `10318c3` | §3.3 seed twice | "361 inserted, 0 updated", then "0 inserted, 0 updated"; 361 / 361 distinct |
| 2026-11-15 | `wolfee-integration` @ `10318c3` | §3.4 browser smoke, real providers (355 quotes cached), headless Chrome, 1440 px and 390 px | all 7 views at each width: no horizontal scroll, no overflow, no bad text; register 200, sign-in 200; the only HTTP error is the expected `401 /api/auth/me` before sign-in. Found: insight "data as of" 3 h ahead (cluster time zone, REQ-33 a); "AI generated" badge on template text (REQ-34 a) |
| 2026-11-16 | `wolfee-integration` @ `dd08370` (after merging `agent/quant-ai` `f8bef1d`, `agent/backend` `cf440a2`, `agent/frontend` `ee33aee`) | §2 backend (repo root) | **643 passed**, 3 warnings (88 s) |
| 2026-11-16 | `wolfee-integration` @ `dd08370` | §2 frontend | **72 tests, 72 pass, 0 fail** |
| 2026-11-16 | `wolfee-integration` @ `dd08370` | §3.1 on **PostgreSQL 16.16**, fresh `wolfee_tests` | **194 passed** (16 s) |
| 2026-11-16 | `wolfee-integration` @ `dd08370` | §3.2 migrations up/down/up/down/up on an empty database | all exit 0; single head `e4a8c2f6b1d3`; `alembic check`: "No new upgrade operations detected"; 14 tables (REQ-33 a needed no migration) |
| 2026-11-16 | `wolfee-integration` @ `dd08370` | §3.3 seed twice | 361 inserted, then 0 inserted; 361 / 361 distinct |
| 2026-11-16 | `wolfee-integration` @ `dd08370` | §3.4 browser smoke with `REGISTRATION_INVITE_CODE` set, no e-mail provider, `REQUIRE_EMAIL_VERIFICATION=false`, no `AUTO_VERIFY_DEV`; headless Chrome at 1440 px and 390 px | all 11 views at each width: no horizontal scroll, no overflow, no bad text. `/api/auth/config` 200 `{"email_enabled":false,"registration_open":true}`, no 404. Forgot-password tab and resend link hidden (no visible `[data-needs-email]`). Wrong code → **403**, "Registration requires a valid invite code." shown; right code → 200, account verified, sign-in 200. Portfolio page: create 201, BUY THYAO 201, note `<b>smoke</b> & note` shown as text, void 201 (reversal row added, both struck through, positions empty). HTTP errors only the expected `401 /api/auth/me` before sign-in and the deliberate 403. Server log (281 lines): 0 matches for `token=`, `verify-email`, `reset-password?`, session / CSRF cookie names, `Set-Cookie`, the invite code, the wrong code, or the password |

Note (2026-11-15): the PG16 test cluster runs in `Europe/Istanbul` (WSL's zone). Production must be UTC (DEPLOYMENT §2.1 D3); until REQ-33 (a) is fixed, local "as of" times read 3 h ahead.

Note (2026-11-15): after a WSL restart the PG16 cluster is stopped and the §3 commands fail with "Connection refused". Run the §3 start command first.
