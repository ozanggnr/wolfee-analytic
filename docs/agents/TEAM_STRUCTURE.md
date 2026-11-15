# Team Structure and File Ownership

Last updated: 2026-11-11 by Agent 1 (initial audit, commit `66ddcab`).

Legend used in all `docs/agents/` documents:

- **VERIFIED** — read directly from the repository at the commit above.
- **PROPOSED** — recommended by Agent 1, not yet approved or implemented.

---

## 1. Agents

| # | Role | Mission |
|---|------|---------|
| 1 | Architect and Integration Lead | Owns the contracts, the integration branch, deployment config and cross-agent decisions. Reviews every change that touches a shared contract. Writes no product features. |
| 2 | Backend Engineer | Owns the HTTP layer, persistence, auth, sessions, migrations, background scheduling and the portfolio/transaction CRUD. |
| 3 | Quantitative Finance and AI Engineer | Owns market data providers, indicators, deterministic portfolio and risk maths, and the AI layer (prompts, guardrails, model access). |
| 4 | Frontend Engineer | Owns everything under `frontend/`. Consumes the API contract; never computes financial figures that the backend is the source of truth for. |

---

## 2. File ownership — existing files (VERIFIED paths)

An owner is the only agent that edits the file. Everyone may read everything.

### Agent 1 — Architect and Integration Lead

| Path | Notes |
|------|-------|
| `CLAUDE.md` | Project instructions |
| `docs/**` | All coordination and contract documents |
| `README.md` | Has drift from the code (see IMPLEMENTATION_STATUS §7) |
| `railway.json`, `wrangler.jsonc`, `backend/Procfile`, `backend/start.sh`, `backend/runtime.txt`, `.python-version` | Deployment config |
| `requirements.txt`, `backend/requirements.txt` | Dependency changes are requested through COORDINATION §5 |
| `.gitignore`, `backend/.gitignore` | |

### Agent 2 — Backend Engineer

| Path | Notes |
|------|-------|
| `backend/main.py` | App assembly, market-data routes, export routes. **Hotspot**, see §4 |
| `backend/database.py` | Engine, session factory, `init_db` |
| `backend/models.py` | **Shared contract** — every change needs Agent 1 sign-off against `DATABASE_CONTRACT.md` |
| `backend/alembic/**`, `backend/alembic.ini` | Only Agent 2 creates migrations; one open migration at a time |
| `backend/auth_routes.py`, `backend/auth_utils.py`, `backend/security_middleware.py` | Auth, sessions, CSRF, rate limiting |
| `backend/watchlist_routes.py` | Watchlist CRUD and summary |
| `backend/workers.py` | Refresh scheduling and upserts. **Hotspot**, see §4 |
| `backend/tests/test_auth_and_watchlist.py`, `backend/tests/test_security_audit.py` | |

### Agent 3 — Quantitative Finance and AI Engineer

| Path | Notes |
|------|-------|
| `backend/analysis.py` | Symbol universes, indicators, `analyze_stock`, opportunity scan, bulk export analysis |
| `backend/ai_service.py` | Gemini access, prompts, signal labels, fallbacks |
| `backend/data_sources/**` | yfinance, Yahoo chart API, Google Finance scrape, Bigpara scrape, TCMB XML |
| `backend/tests/test_performance_and_sources.py` | Mixed content, see §4 |

### Agent 4 — Frontend Engineer

| Path | Notes |
|------|-------|
| `frontend/**` | `index.html`, `style.css`, `js/*.js`, `worker.js`, images |

### Unowned / local-only

| Path | Status |
|------|--------|
| `wolfee.db` | Local SQLite dev database, git-ignored. Nobody commits or deletes it. |
| `portfolio_monthly.xlsx` | Untracked export sample in the repo root. Not part of the product. |
| `backend/.venv/` | Git-ignored and currently broken (points at an interpreter path that does not exist on this machine). |

---

## 3. File ownership — new code (PROPOSED)

The backend currently uses flat modules imported by bare name (`from database import Base`), run with `backend/` as the working directory. New code goes into packages next to the existing modules, so nothing existing has to move.

| Proposed path | Owner | Contents |
|---------------|-------|----------|
| `backend/schemas/` | Agent 2 | Pydantic request/response models that implement `API_CONTRACT.md` |
| `backend/routers/` | Agent 2 | New `APIRouter` modules (portfolios, transactions, analytics, AI endpoints). Thin handlers only |
| `backend/services/` | Agent 2 | Orchestration: load rows, call Agent 3's pure functions, persist, return schemas |
| `backend/repositories/` | Agent 2 | Data access for new tables |
| `backend/quant/` | Agent 3 | Pure, deterministic functions: holdings from transactions, cost basis, realised/unrealised P/L, FX conversion, risk metrics, indicators. No DB, no HTTP, no LLM |
| `backend/ai/` | Agent 3 | Prompt templates, input assembly from verified data, output guardrails, provider client |
| `backend/tests/quant/`, `backend/tests/ai/` | Agent 3 | |
| `backend/tests/api/`, `backend/tests/services/` | Agent 2 | |
| `frontend/js/**` new modules | Agent 4 | |
| `docs/adr/` | Agent 1 | Architecture decision records |

The boundary between Agents 2 and 3 is the function signature: Agent 3 exposes typed pure functions; Agent 2 calls them from `services/`. Those signatures are part of the shared contract and are recorded in `API_CONTRACT.md` §6.

---

## 4. Conflict hotspots identified before implementation

These are places where two agents have a legitimate reason to edit the same file. Each has a designated owner and a rule.

| # | Hotspot | Why it conflicts | Rule |
|---|---------|------------------|------|
| H1 | `backend/workers.py` | Scheduling and upserts are backend work; `_enrich_stock_data` (lines 386–444) is signal logic that duplicates `analysis.py` and `ai_service._compute_signal` | Agent 2 owns the file. Agent 3 first publishes one canonical enrichment function in `backend/quant/`; Agent 2 then replaces the local copy in a single dedicated PR |
| H2 | `backend/main.py` | 979 lines holding routes, Excel formatting, export calculations and helpers. Agents 2 and 3 both need changes; Agent 4 depends on its response shapes | Agent 2 owns it. No other agent edits it. New endpoints go in `backend/routers/`, registered by Agent 2 with one `include_router` line each |
| H3 | `backend/models.py` | Single file for all tables | Agent 2 edits, Agent 1 approves. Agent 3 requests columns through COORDINATION §5 |
| H4 | Alembic revision chain | Two parallel migrations create two heads | Only Agent 2 writes migrations, strictly one at a time, each merged before the next starts |
| H5 | `backend/tests/test_performance_and_sources.py` | Contains data-source and AI tests (Agent 3) plus cookie, export and scheduler tests (Agent 2) | Agent 3 owns the file as it stands. New tests go in the per-agent test folders. Splitting the file is a single coordinated PR |
| H6 | Symbol format (`THYAO` vs `THYAO.IS`) | Each layer normalises differently today (see DATABASE_CONTRACT §2.6) | Agent 1 defines the canonical form in the contract; Agent 3 implements the one normaliser; Agents 2 and 4 call it and remove their own |
| H7 | `backend/watchlist_routes.py` imports `analysis.analyze_stock` and `main.py` imports `watchlist_routes._enrich_watchlist_tickers` | Private cross-module imports couple Agent 2 and Agent 3 code | Leave as is until a public function exists; do not add new private cross-imports |
| H8 | Response field names consumed by the frontend | `frontend/js` reads `stocks[].change_pct`, `items[].ticker`, etc. directly | Existing response shapes are frozen (API_CONTRACT §2). Additive changes only, unless Agent 1 approves and Agent 4 is told first |
| H9 | `requirements.txt` | All backend agents add dependencies | Agent 1 owns the file; requests go through COORDINATION §5 |
| H10 | Client-side financial maths | `frontend/js/portfolio.js` computes a watchlist summary locally for guests; the backend computes the same summary for signed-in users | Allowed for the existing guest watchlist only. For real portfolios (transactions, P/L, risk) the frontend displays backend values and computes nothing |

---

## 5. Decision rights

| Decision | Decides | Consulted |
|----------|---------|-----------|
| API or database contract change | Agent 1, with user approval for breaking changes | Affected agents |
| Destructive database change (drop, rename, type narrowing, data rewrite) | **User only** | Agents 1 and 2 |
| Financial calculation method (cost basis, return formula, risk metric definition) | Agent 3 proposes, user approves | Agent 1 |
| AI prompt content and guardrails | Agent 3, within CLAUDE.md "AI Requirements" | Agent 1 |
| New dependency or external data provider | Agent 1 | Requesting agent |
| Merge to `main` | **User only** | Agent 1 prepares |
