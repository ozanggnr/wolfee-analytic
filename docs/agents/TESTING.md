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

`WOLFEE_TEST_POSTGRES_URL` and `backend/tests/api` come from `agent/backend` (`6a168a5`). On `integration` they exist only after `agent/backend` is merged (Step 3b). Until then, run this from the `Wolfee-backend` worktree. When running against another agent's worktree, prefix with `PYTHONDONTWRITEBYTECODE=1` so nothing is written into it.

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

The temporary PostgreSQL 18 cluster (`~/wolfee-test/pg18` and `pg18.log`) was deleted on 2026-11-14.
