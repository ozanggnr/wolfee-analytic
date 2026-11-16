# Implementation Status

Last updated: 2026-11-11 by Agent 1 (audit of commit `66ddcab`; branch review in §9).

Status values:

- **DONE** — implemented in the code that was read.
- **PARTIAL** — exists but incomplete, misleading, or not wired up. The gap is stated.
- **MISSING** — no code found.

"DONE" means the code is present. **The test suite could not be run during the audit** (§7), so nothing here is confirmed by execution.

---

## 1. Existing platform

### 1.1 Market data

| Feature | Status | Evidence / gap |
|---------|--------|----------------|
| BIST universe (about 120 symbols after de-duplication) | DONE | `analysis.BIST_SYMBOLS` |
| Global universe (about 230 symbols) | DONE | `analysis.GLOBAL_SYMBOLS` |
| Commodities (13 futures) | DONE | `analysis.COMMODITIES_SYMBOLS` |
| Quotes through yfinance | DONE | `data_sources/*` — unofficial library |
| BIST fallback: Google Finance HTML scrape | DONE | Depends on obfuscated CSS class names and a hard-coded consent cookie; fragile |
| Turkish gold prices | DONE | Bigpara HTML scrape |
| USD, EUR, GBP against TRY | DONE | TCMB daily XML; change % from yfinance |
| Price history for charts | DONE | Yahoo chart API, then yfinance. Fetched per request, not stored |
| Finnhub / Alpha Vantage / Polygon failover | REMOVED | The unused `api_router.py` was deleted (REQ-31 f, merged at `fe6d8c6`, 2026-11-15). `data_sources.global_market.fetch_global_stock_finnhub` remains but no caller passes a key |
| Background refresh, market-hours aware | DONE | `workers.py`, in-process asyncio loop, default 30 min |
| DB-first serving of the market grid | DONE | `/api/market-data/quick` |
| Data freshness labelling (real-time / delayed / end-of-day) | MISSING | Only a single latest `updated_at` on `/quick` |
| Stored price or FX history | MISSING | |
| Market holiday calendar | MISSING | Schedules use weekday and clock time only |

### 1.2 Analysis

| Feature | Status | Evidence / gap |
|---------|--------|----------------|
| RSI(14), SMA 5/10/20/50, annualised volatility from history | PARTIAL | Correctly computed in `analysis.calculate_indicators` and `get_bulk_analysis`, but only `/api/export/{period}` uses them. `calculate_indicators` has no caller |
| RSI / MA20 / volatility shown on cards, modal, watchlist | PARTIAL | Estimated from one day's change (API_CONTRACT §2.2), stored and displayed as if real |
| Rule-based signal label | PARTIAL | Three separate copies: `analysis.analyze_stock`, `workers._enrich_stock_data`, `ai_service._compute_signal`. The third uses different rules |
| Opportunity scanner | DONE | `get_market_opportunities` — positive day and `change_pct > 0.5` |
| Fundamentals, news, sector data | MISSING | |

### 1.3 AI

| Feature | Status | Evidence / gap |
|---------|--------|----------------|
| Daily market insight (Gemini) | DONE | `ai_service.get_market_insight`, cached in `ai_insights` for 4 h |
| Per-stock AI analysis | DONE | `/api/ai/analyze/{symbol}`, generated on every request, not cached |
| Template fallback when no key or model failure | DONE | |
| Model fallback chain and discovery | DONE | |
| Guardrails required by CLAUDE.md | MISSING | No disclaimer anywhere in backend or frontend. Prompts instruct the model to act as a "trusted financial advisor", name stocks "to buy today", and explain "what is happening with the company" although no company information is supplied |
| Marking output as AI- or template-generated | MISSING | |
| Portfolio-aware AI | MISSING | |

### 1.4 Authentication and security

| Feature | Status | Evidence / gap |
|---------|--------|----------------|
| Registration, login, logout, `/me` | DONE | `auth_routes.py` |
| bcrypt cost 12, password policy | DONE | |
| Email verification and password reset | DONE | Resend, SendGrid or SMTP. With no provider configured the link is logged instead |
| Server-side sessions, sliding renewal | DONE | Session id stored unhashed; expired rows never purged |
| CSRF double-submit | DONE | |
| Per-IP rate limiting | DONE | In memory, per process |
| Account lockout with backoff | DONE | |
| Security headers, CSP | DONE | CSP allows `'unsafe-inline'` scripts because the frontend uses inline handlers |
| Audit log | DONE | `security_logs`, unpruned |
| CAPTCHA | REMOVED | User decision 2026-11-16: no CAPTCHA. Registration needs an invite code (`REGISTRATION_INVITE_CODE`; REQ-36 / REQ-37, merged at `7bf4d6b` / `dd08370`) |
| User-level isolation on watchlist | DONE | All queries filter by `current_user.id` |
| Roles / admin | MISSING | |
| Account deletion, session list, change password while signed in | MISSING | |

### 1.5 Watchlist and export

| Feature | Status | Evidence / gap |
|---------|--------|----------------|
| Per-user watchlist CRUD | DONE | |
| Guest watchlist in `localStorage` | DONE | Not merged into the account on sign-in |
| Watchlist summary card | DONE | Unweighted average of daily moves |
| Market Excel export | DONE | Slow: one provider call per symbol inside the request, unauthenticated |
| Portfolio Excel export | PARTIAL | Figures come from client-supplied data; "period" is a label only (API_CONTRACT §2.6) |

### 1.6 Frontend

| Feature | Status | Evidence / gap |
|---------|--------|----------------|
| Market, Portfolio (watchlist) and Opportunities tabs | DONE | Vanilla JS, global functions, no build step |
| Stock modal with Plotly chart and AI analysis | DONE | |
| Auth modal (login, register, forgot, resend) | DONE | |
| Search and filters, responsive layout | DONE | |
| Auto-polling every 60 s | DONE | |
| Unused scripts | PARTIAL | `mock-data.js` and `yahoo-client.js` are not loaded by `index.html`. `api.js` is loaded but calls legacy paths (`/stocks`, `/analyze/…`) that do not exist. **On `agent/frontend` all three files are deleted and `index.html` no longer loads `api.js`. Every function it defined that is still called is defined in `main.js`** (REQ-6) |
| Types, modules, tests | MISSING | `style.css` is 2,698 lines; no frontend tests |

### 1.7 Deployment and operations

| Feature | Status | Evidence / gap |
|---------|--------|----------------|
| Railway deployment | REMOVED | `railway.json` deleted 2026-11-16; production target is Fly.io (`fly.toml`, `Dockerfile`) |
| Cloudflare Pages config for the frontend | REMOVED | `wrangler.jsonc` and the Pages worker deleted 2026-11-16 (`92a5ca0`, `dd08370`) |
| Alembic migrations | PARTIAL | Cover 5 of 9 tables; failures ignored at startup (DATABASE_CONTRACT §2.1) |
| CI | MISSING | |
| `.env.example` / environment documentation | MISSING | Variables are listed in §4 below |
| Working local environment | PARTIAL | `backend/.venv` points to a non-existent interpreter; runtime pins Python 3.11.9 |

---

## 2. Target features — multi-user investment intelligence

| Feature | Status | Owner | Notes |
|---------|--------|-------|-------|
| Canonical instrument registry and one symbol normaliser | MISSING | 3 (logic), 2 (table) | Prerequisite for transactions |
| Portfolios (multiple per user) | MISSING | 2 | |
| Transaction ledger, append-only | MISSING | 2 | |
| Holdings derived from transactions | MISSING | 3 | |
| Cost basis, realised and unrealised P/L | MISSING | 3 | Needs decision D2 |
| Fees and dividends | MISSING | 2, 3 | |
| Currency conversion with dated rates | MISSING | 3 | Needs decision D3 and FX history |
| Stored end-of-day price history | MISSING | 3 (fetch), 2 (storage, job) | |
| Real technical indicators from history | PARTIAL | 3 | Formulae exist; need wiring to stored history |
| Risk metrics (volatility, drawdown, concentration) | MISSING | 3 | |
| Data provenance and freshness on every figure | MISSING | 3, 2, 4 | |
| Portfolio endpoints with typed schemas | MISSING | 2 | |
| Portfolio UI (transactions entry, holdings, performance) | MISSING | 4 | |
| AI explanations grounded in computed figures, with guardrails | MISSING | 3 | |
| Paper trading | MISSING | 2, 3, 4 | Later phase |
| Trader Skill workflow adaptation | MISSING | 3 | Skill not located (D7) |
| Alerts / notifications | MISSING | — | Not planned yet |
| Live brokerage trading | Out of scope | — | CLAUDE.md: no autonomous live trading |

---

## 3. Recommended implementation order

### Phase 0 — Foundation (no product features)

- [ ] User approves ownership, workflow and contracts (D1)
- [ ] Commit `CLAUDE.md` and `docs/`; create `integration` and the agent worktrees — Agent 1
- [ ] Rebuild the local environment on Python 3.11 and record the test baseline — Agent 2
- [ ] Add CI that runs the backend tests on pull requests — Agent 1
- [ ] Inspect production Alembic state read-only; settle the baseline (D8, M0) — Agents 1 and 2
- [ ] Write `.env.example` from §4 — Agent 1
- [ ] Locate Trader Skill and list which workflows apply to BIST (D7) — Agent 3
- [ ] Settle D2–D6 and D9

### Phase 1 — Integrity fixes to existing behaviour (each needs approval because visible output changes)

- [ ] One symbol normaliser; stop duplicate `stock_data` rows — Agent 3, then Agent 2
- [ ] One signal function replacing the three copies — Agent 3, then Agent 2
- [ ] Stop presenting estimated RSI / MA20 / ranges as real values (D4) — Agent 3, Agent 4 for display
- [ ] AI disclaimer, generated-by marker and prompt revision (D5) — Agent 3, Agent 4
- [ ] Protect `/api/refresh` and the heavy export (D9) — Agent 2
- [ ] Freshness fields on quotes (additive) — Agents 3, 2, 4

### Phase 2 — Portfolio core

- [ ] `instruments` (M1) — Agent 2, seeded with Agent 3
- [ ] `quant/` positions, cost basis and P/L with hand-checked tests — Agent 3
- [ ] `portfolios` and `transactions` (M2), schemas, routes, isolation tests — Agent 2
- [ ] Holdings and performance endpoints — Agent 2 calling Agent 3
- [ ] Portfolio UI: create portfolio, add transaction, holdings table — Agent 4

### Phase 3 — History, valuation and risk

- [ ] `price_history`, `fx_rate_history` (M3) and the daily job — Agents 2 and 3
- [ ] Multi-currency valuation — Agent 3
- [ ] Real indicators and risk metrics — Agent 3
- [ ] Allocation and risk endpoints and UI — Agents 2 and 4

### Phase 4 — AI on verified data

- [ ] Portfolio summary explanation with guardrails and traceability — Agent 3, Agent 2, Agent 4

### Phase 5 — Paper trading and Trader Skill workflows

- [ ] Simulated orders filled against stored quotes into `paper` portfolios — all agents

---

## 4. Environment variables read by the code (VERIFIED)

| Variable | Used in | Default |
|----------|---------|---------|
| `DATABASE_URL` | `database.py` | local SQLite file |
| `PORT` | `start.sh` | 8000 |
| `REFRESH_INTERVAL_MINUTES` | `main.py`, `workers.py` | 30 |
| `AI_INSIGHT_CACHE_HOURS` | `workers.py` | 4 |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | `ai_service.py` | none, `gemini-3.6-flash` |
| `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_ENVIRONMENT` | CORS, cookies, base URL | — |
| `CORS_ORIGINS` | `main.py` | — |
| `SESSION_DURATION_DAYS`, `COOKIE_SECURE` | `security_middleware.py` | 30, false |
| `REGISTRATION_INVITE_CODE` | `auth_utils.py` | empty (registration closed) |
| `AUTO_VERIFY_DEV`, `REQUIRE_EMAIL_VERIFICATION` | `auth_routes.py` | false, true (`fly.toml` sets `false` for launch, D2) |
| `APP_BASE_URL`, `EMAIL_FROM` | `auth_utils.py` | — |
| `RESEND_API_KEY`, `SENDGRID_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | `auth_utils.py` | — |

No secrets were found hard-coded in the tracked files that were read. The Google consent cookie in `turkish_market.py` is a public bypass value, not a credential.

Dependencies listed in `requirements.txt` with no import in application code: `slowapi`, `apscheduler`, `isyatirimhisse`, `pydantic-settings`, `aiohttp`. `psycopg2-binary` is used only by Alembic's sync connection.

---

## 5. Critical technical risks

| ID | Risk | Detail |
|----|------|--------|
| R1 | Fabricated metrics conflict with CLAUDE.md "never fabricate … financial metrics" | Estimated RSI and MA20 everywhere outside the market export; day high/low filled with price ±1 %; open and previous close back-calculated; failed export rows written as zeros |
| R2 | AI output conflicts with CLAUDE.md "AI Requirements" | Advisor framing, buy recommendations, "Never write HOLD", a default positive bias in `_compute_signal`, no disclaimer, and prompts asking for company explanations with no company data supplied |
| R3 | Unknown production migration state | DATABASE_CONTRACT §2.1. Blocks every schema change |
| R4 | Market data sources are unofficial | yfinance and HTML scraping can break or be blocked without notice. Licensing and delay of BIST quotes are not established; nothing is labelled as delayed |
| R5 | Unauthenticated expensive endpoints | `GET` and `POST /api/refresh` start a forced full refresh for any caller. `/api/export/{period}` makes over a hundred provider calls per request |
| R6 | Blocking calls inside async handlers | `analyze_stock` (network I/O) is called directly in `/api/analyze`, `/api/live-price`, the watchlist fallback and the GET export, and `get_bulk_analysis` in the market export. Each stalls the event loop for all users |
| R7 | Single-process assumptions | Rate limiters, summary cache, refresh lock and AI model cache live in process memory, and the refresh loop runs inside the web process. A second instance would duplicate refreshes and split rate limits |
| R8 | `Float` money and no ledger | Fine for the cache, unusable for portfolio accounting. New tables must use `NUMERIC` |
| R9 | Symbol ambiguity | Duplicate cache rows and per-layer normalisation (DATABASE_CONTRACT §2.6). Must be fixed before transactions reference instruments |
| R10 | CAPTCHA is not effective | Resolved 2026-11-16: CAPTCHA removed, invite-code registration merged (`7bf4d6b`, `dd08370`) |
| R11 | No verified test baseline and no CI | §7 |
| R12 | Business logic in route handlers | `main.py` export handlers and `watchlist_routes.get_watchlist_summary` compute inline, against CLAUDE.md. New work must not copy the pattern |
| R13 | Trader Skill is US-oriented and not located | SEC, House Clerk and NYSE data have no direct BIST equivalent; scope must be reviewed before any adaptation |

---

## 6. Unresolved decisions

See COORDINATION §9 for the list (D1–D9). Agent 1 recommendations:

| ID | Recommendation |
|----|----------------|
| D2 | FIFO default, method as a parameter |
| D3 | Base currency per portfolio; TCMB dated rates; trade-time rate stored on the transaction |
| D4 | Yes — return `null` where a real value is unavailable and show "n/a"; compute real indicators once history is stored |
| D5 | Reframe as explanation of computed figures; add a disclaimer and a generated-by marker; remove adviser framing |
| D6 | Keep vanilla JS for now; add ES modules and JSDoc types for new code; no rewrite and no build step in the first phases |
| D9 | Require a session for `POST /api/refresh`, remove or restrict the `GET` variant, and move the market export to a cached file |

---

## 7. What was not verified

- **Tests were not run.** System Python has no `pytest`; `backend/.venv` references an interpreter path that does not exist on this machine. No packages were installed during the audit. The suite contains 26 test functions across three files; their pass/fail state is unknown.
- **No server was started**; response shapes were read from source.
- **No database was opened**, local or production.
- **External providers were not called**; whether each source currently works is unknown.
- The duplicate-row behaviour in DATABASE_CONTRACT §2.6 is inferred from code.
- Parts of `auth_utils.py`, `frontend/js/ui.js`, `auth.js`, `filter.js`, `main.js`, `index.html` and `style.css` were searched rather than read line by line.
- README drift noted but not corrected: `SameSite=Strict` cookies (the code sets `Lax`). The CAPTCHA line was replaced 2026-11-16.

---

## 8. Smoke list for "existing functionality preserved"

Run on `integration` after every merge:

1. `/healthz` returns `healthy`.
2. Market grid loads with BIST, global and commodity cards.
3. Gold and exchange-rate strips load.
4. Stock modal opens; chart renders for a BIST and a US symbol; AI analysis text appears.
5. Opportunities tab lists rows.
6. Daily insight text appears.
7. Register, verify, log in, `/me`, log out.
8. Add and remove a watchlist ticker; summary card updates.
9. Portfolio export downloads an `.xlsx`.
10. Guest watchlist persists across a reload.

---

## 9. Branch review — 2026-11-11 (Agent 1)

Nothing below is on `main`. All three branches are unmerged and unchanged by the review.

### 9.1 Branches reviewed

| Branch | Commits | Size | Verdict |
|--------|---------|------|---------|
| `agent/backend` | `d4af8bd` | 25 files, +2,272 | Code sound. **Blocked for `main`** by DATABASE_CONTRACT §5 (P1, P2, P4, P6) |
| `agent/quant-ai` | `034313e`, `19d0501` | 26 files, +3,175 / −200 | Ready to integrate. Library only, with no new route and no schema |
| `agent/frontend` | `43f2b2b`, `718d7c3`, `cc3fcc3` | escaping fixes, removes 3 dead scripts | Ready to integrate **after a browser smoke test** (§8), which is not yet done |

No file is changed by more than one branch. Pairwise and three-way `git merge-tree` produced no conflicts.

### 9.2 Test evidence (Python 3.11.9 — the production version — in a throwaway virtualenv)

| Tree | Run from repo root (`pytest backend/tests`) | Run from `backend/` (`pytest tests`) |
|------|---------------------------------------------|--------------------------------------|
| `main` `de0575a` (baseline) | 26 passed | 23 passed, **3 failed** |
| `agent/backend` | 143 passed | 140 passed, same 3 failed |
| `agent/quant-ai` | 205 passed | 202 passed, same 3 failed |
| backend + quant-ai merged (in memory) | **322 passed** | not run |
| `agent/frontend` `node --test` | 9 passed | — |

The three failures are `test_fetch_bist_stock_handles_fast_info_keyerror`, `test_fetch_global_stock_handles_fast_info_keyerror` and `test_turkish_gold_parser_html_mock`. They are **pre-existing and depend on the working directory**: they patch `backend.data_sources…`, which only imports when the repository root is on `sys.path`. They also fail on `main`. They are not caused by Agent 2's change (REQ-11).

Alembic on SQLite (merged tree): `upgrade head`, `downgrade base`, `upgrade head` all clean, single head `b2e4d8a31c55`. Not run on PostgreSQL.

Frontend static serving, checked with the ASGI test client on `agent/frontend`: `js/core/globals.js` and `safe-html.js` are served as `application/javascript`, and `js/api.js` returns 404. No real browser was run.

### 9.3 Target feature status after integration (if merged)

| Feature | Status on branch | Gap |
|---------|------------------|-----|
| Instrument registry and symbol normaliser | PARTIAL | Table, service and seed exist; nothing runs the seed (REQ-7) |
| Portfolios | DONE on branch | Postgres not tested |
| Transaction ledger, append-only | DONE on branch | ORM-level guard only (DB §5 P5) |
| Holdings, cost basis, realised/unrealised P/L, cash | PARTIAL | Pure functions done (FIFO and weighted average). No ORM adapter or route; D2 |
| Currency conversion | PARTIAL | Uses stored trade rates and supplied `FxRate`. No FX source (D3), no history table |
| Price history | MISSING | M3 not started |
| Real indicators | PARTIAL | Wilder and simple RSI, SMA and volatility in `quant.indicators`; not wired; legacy proxies still displayed (D4) |
| Risk metrics, allocation, concentration | PARTIAL | Functions done; need price history |
| Provenance and freshness | PARTIAL | Carried in `PriceQuote` and valuation; `stock_data` columns (M4) not added |
| AI explanations with guardrails | PARTIAL | Library done (API_CONTRACT §5.4.1); no route |
| Escaping of untrusted text in the UI | DONE on branch | Browser smoke test pending |
| Portfolio UI | MISSING | Next frontend milestone (§9.4) |

### 9.4 Next frontend milestone (Agent 4)

1. **Run the browser smoke test** (§8) on `agent/frontend` with the backend running, in a real browser, and report results. This is what gates merging. Check especially the stock modal AI text, opportunities, watchlist add and remove with an invalid ticker, the ticker pills, and the exchange-rate click handler.
2. Then build the portfolio screens against API_CONTRACT §5.1.1, which is stable now: portfolio list, create, rename and archive; ledger list with pagination; add-transaction form following the type rules table; void with confirmation. Render Decimal strings as given and do no arithmetic. Handle `401`, `404`, `409` and `422` with user-facing messages. Work against a locally running `agent/backend`; do not merge it.
3. Holdings and AI summary views wait for §5.2 and §5.4 routes from Agent 2.
