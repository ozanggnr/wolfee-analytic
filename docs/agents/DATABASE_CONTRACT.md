# Database Contract

Last updated: 2026-11-11 by Agent 1 (audit of commit `66ddcab`; branch review of `agent/backend` `d4af8bd` — see §4.1 and §5).

- §1–§2 are **VERIFIED** from `backend/models.py`, `backend/database.py`, `backend/alembic/` and the code that reads and writes each table.
- §3–§4 are **PROPOSED**. No proposed table exists. Nothing here authorises a migration.

No database was queried or modified during the audit. The production database was not inspected.

---

## 1. Engine and lifecycle (VERIFIED)

| Item | Value |
|------|-------|
| ORM | SQLAlchemy 2.x async, `DeclarativeBase` in `database.py` |
| Production | PostgreSQL through `asyncpg`, from `DATABASE_URL` (`postgres://` and `postgresql://` are rewritten; `sslmode=` is converted to `ssl=require`) |
| Local and tests | SQLite file `./wolfee.db` through `aiosqlite` when `DATABASE_URL` is unset |
| Pool (Postgres) | size 5, overflow 10, timeout 30 s, recycle 1800 s |
| Table creation | `init_db()` runs `Base.metadata.create_all` on **every startup** |
| Migrations | Alembic, one revision `8c15c00878ff`. `start.sh` runs `alembic upgrade head \|\| echo ...` before uvicorn, so a failed migration is ignored and startup continues |
| Ownership | Agent 2 owns models and migrations. Agent 1 approves changes. Destructive changes need user approval |

---

## 2. Existing schema (VERIFIED)

### 2.1 Migration coverage — unresolved risk

| Table | In Alembic revision `8c15c00878ff` | Created by `create_all` |
|-------|-------------------------------------|--------------------------|
| `users` | yes | yes |
| `watchlist_items` | yes | yes |
| `user_sessions` | yes | yes |
| `auth_tokens` | yes | yes |
| `security_logs` | yes | yes |
| `stock_data` | **no** | yes |
| `turkish_gold` | **no** | yes |
| `exchange_rates` | **no** | yes |
| `ai_insights` | **no** | yes |

Consequences:

- Four tables have no migration. Alembic autogenerate would see them as new.
- If `create_all` created the auth tables before Alembic ever ran against a database, `alembic upgrade head` fails with "table already exists", the failure is swallowed by `start.sh`, and that database has **no `alembic_version` row**. Whether production is in this state is unknown.
- The migration uses `server_default` for `email_verified`, `failed_login_count` and `is_used`; the models use Python-side `default` only. A database built by `create_all` has no server defaults on those columns.

**Required before any new migration:** read `alembic_version` and the actual table definitions in production (read-only), then decide between stamping the existing revision and writing a baseline migration. This is decision D8 in COORDINATION §9.

### 2.2 `users`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, autoincrement |
| `email` | String(255) | NOT NULL, unique index. Stored lower-cased by the routes |
| `password_hash` | String(255) | NOT NULL. bcrypt, cost 12 |
| `email_verified` | Boolean | NOT NULL, default false |
| `created_at` | DateTime(tz) | NOT NULL, server default now |
| `failed_login_count` | Integer | NOT NULL, default 0 |
| `locked_until` | DateTime(tz) | nullable |

Relationships: `watchlist_items`, `sessions`, `auth_tokens`, all `cascade="all, delete-orphan"`.

There is no display name, role, locale, base currency or soft-delete column. There is no account-deletion endpoint.

### 2.3 `watchlist_items`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK |
| `user_id` | Integer | NOT NULL, FK `users.id` ON DELETE CASCADE, indexed |
| `ticker` | String(20) | NOT NULL. Upper-case; `.IS` removed when market is `BIST100` |
| `market` | String(20) | NOT NULL. Written values: `BIST100`, `US`, `GLOBAL`, `COMMODITY` |
| `added_at` | DateTime(tz) | NOT NULL, server default now |

Unique `(user_id, ticker)` as `uq_user_ticker`. Index `idx_watchlist_user_ticker (user_id, ticker)` duplicates the unique constraint's index.

This is the only user-owned financial table. It records interest in a ticker, with **no quantity, price, date or cost**. The UI calls it "Portfolio".

### 2.4 `user_sessions`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | String(64) | PK. The raw session token (256-bit hex), stored unhashed |
| `user_id` | Integer | NOT NULL, FK `users.id` CASCADE, indexed |
| `created_at` | DateTime(tz) | NOT NULL |
| `expires_at` | DateTime(tz) | NOT NULL, indexed. Extended on use |
| `ip_address` | String(45) | nullable |
| `user_agent` | String(255) | nullable |

No job deletes expired rows.

### 2.5 `auth_tokens` and `security_logs`

`auth_tokens`: `id` PK; `user_id` FK CASCADE, indexed; `token_hash` String(64) unique (SHA-256 of the raw token); `token_type` String(30) — `verify_email` or `password_reset`; `created_at`; `expires_at` indexed; `is_used` Boolean default false.

`security_logs`: `id` PK; `event_type` String(50) indexed; `email` String(255) nullable, indexed; `ip_address` String(45) NOT NULL; `user_agent` String(255); `details` Text; `created_at` DateTime(tz) indexed. It has no `user_id` and no foreign key, and it grows without pruning.

### 2.6 `stock_data` — a latest-quote cache, not history

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `symbol` | String(20) | NOT NULL, indexed, **not unique** |
| `name` | String(200) | Providers return the ticker itself as the name |
| `price`, `change_pct`, `volume`, `day_high`, `day_low`, `open_price`, `previous_close`, `bid`, `ask`, `market_cap` | Float | default 0. `bid` and `ask` are always 0 from current providers |
| `rsi` | Float | default 50. Always the estimate `50 + 3 × change_pct` |
| `ma_20` | Float | Always the estimate `price × (1 − change_pct / 200)` |
| `volatility` | String(10) | `LOW` / `MEDIUM` / `HIGH` from one day's change |
| `currency` | String(5) | default `TRY` |
| `market_type` | String(20) | `BIST`, `GLOBAL`, `COMMODITY` |
| `prediction`, `reason` | String(500) | Rule-based label text; both hold the same string |
| `is_favorable`, `is_buyable` | Boolean | |
| `extra_data` | JSON | Never written |
| `updated_at` | DateTime (**naive**) | server default now, on update now |

Indexes: `(symbol, updated_at)`, `(market_type)`.

One row per symbol is intended, enforced only by application code (`_upsert_stock` selects by exact symbol, then updates or inserts).

**Symbol inconsistency.** The scheduled BIST refresh stores symbols without the suffix (`fetch_bist_stock` returns `THYAO`). `/api/live-price` passes the `analyze_stock` result, whose symbol is `THYAO.IS`, to the same upsert. An exact-match lookup for `THYAO.IS` does not find `THYAO`, so a second row is inserted. `_deduplicate_stocks` in `main.py` hides this from the market grid by keeping the first row per suffix-stripped symbol. `/api/ai/analyze/{symbol}` looks up one exact symbol with `scalar_one_or_none`. This was established by reading the code; it was not reproduced against a database.

There is no price history table. Charts are fetched from the provider on every request.

### 2.7 `turkish_gold`, `exchange_rates`, `ai_insights`

`turkish_gold`: `id` PK; `gold_type` String(50) unique (`gram_altin`, `ceyrek_altin`, `yarim_altin`, `tam_altin`, `cumhuriyet_altini`); `display_name`; `buying_price`, `selling_price`, `change_pct` Float; `updated_at` naive. Source: HTML scrape of bigpara.hurriyet.com.tr.

`exchange_rates`: `id` PK; `pair` String(10) unique (`USD/TRY`, `EUR/TRY`, `GBP/TRY`); `display_name`; `buying`, `selling`, `change_pct` Float; `updated_at` naive. Buying and selling come from the TCMB daily XML; `change_pct` comes from yfinance, a different source. Latest value only — no dated history.

`ai_insights`: `id` PK; `insight_type` String(20) default `daily`; `symbol` String(20) nullable; `insight_text` Text; `created_at` naive. Only `daily` rows are written; the newest 10 are kept and older ones deleted. No `user_id`, model name or fallback flag.

### 2.8 Observations that affect new work

1. All monetary values are `Float`. Acceptable for a display cache; not acceptable for a ledger.
2. Auth tables use timezone-aware timestamps; market tables use naive ones. The code patches this at read time.
3. Two vocabularies exist for market (`BIST`/`GLOBAL`/`COMMODITY` and `BIST100`/`US`/`GLOBAL`/`COMMODITY`), plus the two symbol forms in §2.6.
4. No table records where a price came from or how fresh it is.
5. There are no `CHECK` constraints or database enums; every enumeration is a free string.

---

## 3. Proposed schema additions (PROPOSED)

All additive. No existing table or column is dropped, renamed or retyped. Types below are Postgres; SQLite is used for tests only.

### 3.1 `instruments` — one canonical identity per tradable thing

Purpose: end the symbol ambiguity and give transactions something stable to reference.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `symbol` | String(20) NOT NULL | Canonical display form without provider suffix, e.g. `THYAO`, `AAPL`, `GC=F` |
| `exchange` | String(10) NOT NULL | `BIST`, `US`, `CMDTY`, `FX`, `TR_GOLD` |
| `provider_symbol` | String(30) NOT NULL | What the data source needs, e.g. `THYAO.IS` |
| `name` | String(200) | |
| `currency` | CHAR(3) NOT NULL | |
| `asset_class` | String(20) NOT NULL | `equity`, `commodity`, `fx`, `gold` |
| `is_active` | Boolean NOT NULL default true | |

Unique `(symbol, exchange)`. Seeded from the symbol lists in `analysis.py`. `stock_data` and `watchlist_items` are not altered in the first phase; they are mapped through the normaliser.

### 3.2 `portfolios`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `user_id` | Integer NOT NULL, FK `users.id` | ON DELETE RESTRICT — see §3.7 |
| `name` | String(100) NOT NULL | |
| `base_currency` | CHAR(3) NOT NULL | |
| `kind` | String(10) NOT NULL | `real` (user-recorded) or `paper` (simulated). CHECK constraint |
| `created_at` | timestamptz NOT NULL | |
| `archived_at` | timestamptz | soft delete |

Unique `(user_id, name)` among non-archived rows. Index `(user_id)`.

### 3.3 `transactions` — the source of truth for holdings

| Column | Type | Notes |
|--------|------|-------|
| `id` | BigInteger PK | |
| `portfolio_id` | Integer NOT NULL, FK `portfolios.id` | |
| `instrument_id` | Integer, FK `instruments.id` | NULL for cash-only rows |
| `type` | String(12) NOT NULL | `BUY`, `SELL`, `DIVIDEND`, `FEE`, `DEPOSIT`, `WITHDRAWAL`, `SPLIT`. CHECK |
| `quantity` | NUMERIC(24,8) NOT NULL | ≥ 0; direction comes from `type` |
| `price` | NUMERIC(20,6) | per unit, in `currency` |
| `fee` | NUMERIC(20,6) NOT NULL default 0 | |
| `currency` | CHAR(3) NOT NULL | Trade currency |
| `fx_rate_to_base` | NUMERIC(20,8) | Rate applied at trade time; stored, never recomputed |
| `trade_date` | Date NOT NULL | |
| `executed_at` | timestamptz | when known |
| `note` | String(500) | |
| `source` | String(20) NOT NULL | `manual`, `import`, `paper_fill` |
| `voids_transaction_id` | BigInteger, FK `transactions.id` | Set on a reversal row |
| `created_at` | timestamptz NOT NULL | |
| `created_by_user_id` | Integer NOT NULL, FK `users.id` | |

Rules:

- **Append-only.** No UPDATE or DELETE from application code. A correction is a new row that voids an earlier one.
- Holdings, cost basis and P/L are always derived from this table by Agent 3's functions. No table stores an editable "current quantity".
- Index `(portfolio_id, trade_date, id)`; index `(instrument_id)`.

### 3.4 `price_history` and `fx_rate_history`

Needed for valuation on past dates, real indicators and risk metrics.

`price_history`: `instrument_id` FK, `date`, `open`, `high`, `low`, `close` NUMERIC(20,6), `volume` NUMERIC(24,2), `currency`, `source`, `fetched_at`. Primary key `(instrument_id, date)`. End-of-day only.

`fx_rate_history`: `base` CHAR(3), `quote` CHAR(3), `date`, `rate` NUMERIC(20,8), `source`, `fetched_at`. Primary key `(base, quote, date)`.

### 3.5 Additive columns on existing tables

| Table | Column | Why |
|-------|--------|-----|
| `stock_data` | `source` String(20) NULL, `as_of` timestamptz NULL, `freshness` String(12) NULL | Label delayed / real-time / end-of-day data |
| `ai_insights` | `user_id` NULL FK, `portfolio_id` NULL FK, `model` String(50) NULL, `is_fallback` Boolean NULL, `inputs_as_of` timestamptz NULL | Per-user insights and traceability |

All nullable, so existing rows and existing code keep working.

A unique constraint on `stock_data.symbol` is desirable but **not additive**: duplicate rows may exist (§2.6) and would have to be merged first. It is deferred and needs user approval.

### 3.6 Decisions these tables depend on

| ID | Question | Agent 1 recommendation |
|----|----------|------------------------|
| D2 | Cost-basis method | **DECIDED by the user 2026-11-11:** default **weighted average**; FIFO available as the `cost_basis_method` request parameter. Not stored per portfolio; nothing in the schema changes (REQ-13) |
| D3 | Base currency and FX source | **DECIDED by the user 2026-11-11:** base currency **TRY** (the only accepted value for now). Valuation FX comes from the existing `exchange_rates` table (latest row per pair, e.g. `USD/TRY`), not a new history table. The rate a user gives on a transaction is still stored on that transaction and used for cost in TRY. A foreign position with no usable rate is reported as `missing_fx_rate`; the other positions are still valued and totalled (REQ-14, REQ-15). TCMB history (§3.4) is deferred |
| — | Is cash tracked? | Yes, through `DEPOSIT` / `WITHDRAWAL` rows, optional per portfolio |
| — | Turkish gold and FX as holdings | Supported through `instruments` rows with `asset_class` `gold` / `fx`, in a later phase |

### 3.7 Ownership and deletion

- Every query on `portfolios` and `transactions` filters by the authenticated `user_id` (directly or through the portfolio).
- `portfolios.user_id` and `transactions.portfolio_id` use `ON DELETE RESTRICT`, unlike the existing `CASCADE` on watchlist and sessions, so deleting a user cannot silently erase a ledger. Account deletion needs an explicit, separately designed procedure.

---

## 4. Proposed migration order (PROPOSED)

| Step | Migration | Depends on |
|------|-----------|------------|
| M0 | Establish the Alembic baseline (stamp or baseline revision, after read-only inspection) | D8 |
| M1 | `instruments` + seed from the existing symbol lists | M0 |
| M2 | `portfolios`, `transactions` | M1, D2, D3 |
| M3 | `price_history`, `fx_rate_history` | M1 |
| M4 | Nullable provenance columns on `stock_data` and `ai_insights` | M0 |
| later | De-duplicate `stock_data` and add the unique constraint | user approval |

Each step is one migration by Agent 2, reviewed by Agent 1, tested for upgrade and downgrade on a copy of the data.

### 4.1 Migrations written so far — IMPLEMENTED ON BRANCH `agent/backend` `d4af8bd` (not merged, **not approved for production**)

| Revision | Down revision | Plan step | Creates |
|----------|---------------|-----------|---------|
| `a1f3c9d27b10` create_instruments | `8c15c00878ff` (existing head) | M1, schema only | `instruments` |
| `b2e4d8a31c55` create_portfolios_and_transactions | `a1f3c9d27b10` | M2 | `portfolios`, `transactions` |

- The chain is linear with a single head. No other branch adds a revision.
- Neither migration alters or drops an existing table. Both downgrades drop only the tables they created.
- **M1 deviation:** the migration does not seed rows. Seeding is meant to happen through `services.instrument_service.sync_instruments(db, quant.symbols.instrument_seed())`, but **nothing calls it yet** (REQ-7). With an empty `instruments` table every `BUY`, `SELL`, `DIVIDEND` and `SPLIT` returns `422`.
- **M0 was skipped.** The Alembic state of production is still unknown (§2.1, D8).

Differences from the §3.1–3.3 proposal (all additive and accepted by Agent 1):

| Table | Difference |
|-------|------------|
| `instruments` | `is_active` has `server_default true`. Constraint named `uq_instruments_symbol_exchange` |
| `portfolios` | `created_at` `server_default now()`. CHECK `ck_portfolios_kind`. Index `ix_portfolios_user_id`. "Unique name among non-archived rows" is a **partial unique index** `uq_portfolios_user_name_active … WHERE archived_at IS NULL` |
| `transactions` | `id` and `voids_transaction_id` are BigInteger on Postgres and Integer on SQLite, so SQLite autoincrement works. `fee` `server_default 0`. `created_at` `server_default now()` |
| `transactions` CHECKs | `type` in the seven types; `source` in `manual`, `import`, `paper_fill`; `quantity >= 0`; `fee >= 0`; `price IS NULL OR price >= 0`; `fx_rate_to_base IS NULL OR fx_rate_to_base > 0` |
| `transactions` FKs | All four (`portfolio_id`, `instrument_id`, `voids_transaction_id`, `created_by_user_id`) are `ON DELETE RESTRICT` |
| `transactions` indexes | `ix_transactions_portfolio_date_id (portfolio_id, trade_date, id)`, `ix_transactions_instrument_id`, and **unique** `uq_transactions_voids_transaction_id`, so a row can be voided only once even under a race |
| ORM guard | `models.Transaction` has `before_update` and `before_delete` listeners that raise `LedgerError`. They cover ORM unit-of-work changes only. Bulk `update()`/`delete()` statements and raw SQL bypass them. A database-level guard (trigger or revoked privileges) is still open (§5) |

Verified locally on 2026-11-11 against SQLite with Python 3.11.9: `upgrade head` → `downgrade base` → `upgrade head` all ran cleanly. **Not verified against PostgreSQL.**

---

## 5. Production database blockers (open)

None of these is resolved. Until they are, neither migration may run against production, and `agent/backend` must not reach `main`. `main` is what Railway deploys.

| # | Blocker | Why it matters | Needs |
|---|---------|----------------|-------|
| P1 | **`init_db()` runs `Base.metadata.create_all` on every start** (§1) | Merging `agent/backend` and deploying **creates `instruments`, `portfolios` and `transactions` in production immediately**, through `create_all` and not Alembic, whatever was approved. `alembic_version` would then not match the tables | A decision on how new tables reach production: either `create_all` stops creating new tables, or the user explicitly accepts it. Agent 2 change after Agent 1 sign-off |
| P2 | Production Alembic state unknown (§2.1, D8) | `start.sh` runs `alembic upgrade head \|\| echo …`, so a failure is **swallowed** and the app starts anyway. Reproduced on SQLite: on a database built by `create_all`, `upgrade head` fails at `8c15c00878ff` with "table users already exists" | D8: read-only inspection of `alembic_version` and the table list, then M0 (stamp or baseline) |
| P3 | Migration chain does not cover the whole model | `alembic check` on a fully migrated database reports 8 differences: `stock_data`, `turkish_gold`, `exchange_rates`, `ai_insights` and their indexes, plus `ix_auth_tokens_user_id`, exist only through `create_all`. A database built only from migrations lacks them | M0 baseline revision |
| P4 | Never run on PostgreSQL | Untested: partial unique index; `SELECT … FOR UPDATE` in `load_writable`; BigInteger self-FK; CHECK constraints; `server_default true` and `now()`; NUMERIC round-trip through asyncpg; `IntegrityError` → `409` mapping with asyncpg's error types | Run the full `backend/tests` suite and upgrade/downgrade against a disposable Postgres matching the production major version |
| P5 | No data-level append-only guard | ORM listeners do not stop bulk statements or manual SQL | Decide: a Postgres trigger rejecting UPDATE/DELETE on `transactions`, or accept ORM-level only |
| P6 | Instruments not seeded | The ledger is unusable without rows (REQ-7) | Seeding path chosen and run, idempotently |
| P7 | No backup or rollback rehearsal | First schema change to a live financial database | Snapshot before migrating; downgrade rehearsed on a copy |

The user has **not** approved either migration for production. Agent 1 does not approve them either.
