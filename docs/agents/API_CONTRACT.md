# API Contract

Last updated: 2026-11-11 by Agent 1 (audit of commit `66ddcab`; branch review of `agent/backend` `d4af8bd`, `agent/quant-ai` `19d0501`, `agent/frontend` `cc3fcc3`).

- §1–§3 are **VERIFIED** on `main`: read from `backend/main.py`, `backend/auth_routes.py`, `backend/watchlist_routes.py` and `backend/security_middleware.py`.
- §4–§6 started as **PROPOSED**. Items marked **IMPLEMENTED ON BRANCH** were read from an unmerged agent branch and tested there; they are not on `main` and nothing in them is deployed.
- §7 records the frontend rendering rules for AI text and other untrusted strings.

Response examples in §2 list the fields the code returns. They were read from source, not captured from a running server.

---

## 1. Cross-cutting behaviour (VERIFIED)

### 1.1 Transport and format

- FastAPI app, JSON over HTTP. The same process serves the frontend from `/` (static mount of `frontend/`).
- There is **no response envelope**. Each endpoint returns its own top-level object.
- Errors raised as `HTTPException` return `{"detail": "<message>"}` with the status code. Unhandled errors return `500 {"detail": "An internal server error occurred. Please try again later."}`.
- Several market-data endpoints **catch errors and return HTTP 200 with an empty list** (noted per endpoint). Clients cannot tell "no data" from "failure" on those.
- No API versioning prefix. No OpenAPI customisation beyond FastAPI defaults.

### 1.2 Authentication

- Server-side sessions in the `user_sessions` table. The session id travels in the `wolfee_session` cookie: `HttpOnly`, `SameSite=Lax`, `Secure` when the connection is HTTPS or the app runs on Railway, lifetime `SESSION_DURATION_DAYS` (default 30) with sliding renewal.
- `get_current_user` returns `401` when the cookie is missing, unknown or expired. `get_optional_user` returns `None` instead.
- Only the watchlist endpoints, `/api/auth/me` and the watchlist fallback inside `POST /api/export/portfolio` use the session. **Every other endpoint is public.**

### 1.3 CSRF

- Double-submit cookie: cookie `csrf_token` (readable by JS) must equal header `X-CSRF-Token`.
- Enforced on `POST`, `PUT`, `DELETE`, `PATCH` when a session cookie is present, or when a CSRF cookie is present and the route is not one of the pre-auth routes (`register`, `login`, `forgot-password`, `resend-verification`, `reset-password`).
- `POST /api/export/portfolio` is exempt.
- Failure: `403 {"detail": "CSRF validation failed: missing or invalid X-CSRF-Token header."}`.
- The frontend sends it through `window.authFetch` (`frontend/js/auth.js`).

### 1.4 Rate limiting (in-memory, per process, per client IP)

| Scope | Limit | Response |
|-------|-------|----------|
| `POST`/`PUT` on `/api/auth/{login,register,forgot-password,resend-verification,reset-password}` | 10 per 60 s | `429` + `Retry-After` |
| All other `/api/*` | 120 per 60 s | `429` + `Retry-After` |

Client IP is taken from `CF-Connecting-IP`, then the first `X-Forwarded-For` entry, then the socket.

### 1.5 Symbols

- Accepted pattern: `^[A-Za-z0-9]+(?:[.\-=][A-Za-z0-9]+)*$`, 1–20 characters. Otherwise `400`.
- Path symbols without `.IS` and without `=` are treated as BIST and get `.IS` appended **unless** they are in `GLOBAL_SYMBOLS`.
- Symbols containing `=` are commodities (`GC=F`).
- The form returned in responses is not uniform; see DATABASE_CONTRACT §2.6.

### 1.6 CORS

Allow-list of fixed origins plus `RAILWAY_PUBLIC_DOMAIN`, `CORS_ORIGINS` (comma separated) and the regex `https://*.up.railway.app`. Credentials allowed.

---

## 2. Existing endpoints (VERIFIED) — shapes are frozen

"Used by frontend" is from a search of `frontend/js` and `frontend/index.html`.

### 2.1 Health and root

| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET, HEAD | `/` | no | `frontend/index.html` |
| GET | `/health`, `/healthz` | no | `{"status": "healthy"\|"degraded", "service": "Wolfee Analytics API", "database": "connected"\|"disconnected"}` — always 200 |

### 2.2 Market data

| Method | Path | Auth | Used by frontend | Response |
|--------|------|------|------------------|----------|
| GET | `/api/stocks` | no | no | `{"stocks": [symbol], "commodities": [symbol], "bist_count", "global_count", "commodity_count"}` |
| GET | `/api/market-data/quick` | no | yes | `{"stocks": [Stock], "updated_at": iso\|null}`. Empty DB: `{"stocks": [], "status": "loading", "message"}` and a background refresh starts. On error: 200 `{"stocks": [], "error": "<exception text>"}` |
| GET | `/api/market-data/full` | no | no | `{"stocks": [Stock]}`. On error: 200 `{"stocks": []}` |
| GET | `/api/market-data` | no | no | Alias of `/quick` |
| GET | `/api/turkish-gold` | no | yes | `{"gold": [{"gold_type", "display_name", "buying_price", "selling_price", "change_pct", "updated_at"}]}`. On error: 200 with `[]` |
| GET | `/api/exchange-rates` | no | yes | `{"rates": [{"pair", "display_name", "buying", "selling", "change_pct", "updated_at"}]}`. On error: 200 with `[]` |

`/quick` and `/full` currently return the same rows: all of `stock_data`, de-duplicated by symbol with `.IS` stripped, excluding rows with price ≤ 0.

**`Stock` object** (from `_stock_to_dict`):

```
symbol          string
name            string
price           number
change_pct      number   percent, e.g. 1.25
volume          number
day_high        number
day_low         number
open            number
previous_close  number
bid             number   always 0 from current providers
ask             number   always 0 from current providers
rsi             number   see warning below
ma_20           number   see warning below
volatility      "LOW" | "MEDIUM" | "HIGH"
currency        string   "TRY", "USD", or provider currency
market_type     "BIST" | "GLOBAL" | "COMMODITY"
prediction      string   label text, e.g. "ACCUMULATE — steady upward movement"
reason          string   same text as prediction
is_favorable    boolean  change_pct > 0
is_buyable      boolean  change_pct > 0.5 and rsi < 65
market_cap      number
```

Warning, verified in `workers._enrich_stock_data` and `analysis.analyze_stock`: the data sources never supply `rsi` or `ma_20`, so both are always computed as `rsi = clamp(50 + 3 × change_pct, 5, 95)` and `ma_20 = price × (1 − change_pct / 200)`. They are not a 14-period RSI or a 20-day average. `volatility` is derived from one day's `change_pct`. No field states whether a price is real-time, delayed or end-of-day.

### 2.3 Analysis, prices and history

| Method | Path | Auth | Used by frontend | Response |
|--------|------|------|------------------|----------|
| GET | `/api/analyze/{symbol}` | no | no | `Stock` fields plus `buy_signals: []` (always empty). `404` if no data |
| GET | `/api/live-price/{symbol}` | no | yes (stock modal) | Same as `/api/analyze`. Fetches from the provider on each call and queues a DB upsert. `404`, `500` |
| GET | `/api/history/{symbol}?period=1y` | no | no | `{"symbol", "name", "history": [Candle]}`. `400` bad period, `404`, `500` |
| GET | `/api/chart/{symbol}/{period}` | no | yes | `{"history": [Candle]}`. `400`, `404`, `500` |

`Candle`: `{"time": "YYYY-MM-DD HH:MM", "open", "high", "low", "close", "volume"}`.

Accepted `period` values: `1d, 5d, 1wk, 1mo, 3mo, 6mo, 1y, 5y, max`. The data-source maps only define `1d, 1w, 1mo, 3mo, 6mo, 1y, 5y`; `5d`, `1wk` and `max` pass validation and silently fall back to one month of daily data.

"Live" in `/api/live-price` means "fetched now from yfinance", not exchange real-time data.

### 2.4 Opportunities and AI

| Method | Path | Auth | Used by frontend | Response |
|--------|------|------|------------------|----------|
| GET | `/api/opportunities` | no | yes | `{"opportunities": [Stock]}` — up to 15 rows where `is_favorable` and `change_pct > 0.5`, BIST first. On error: 200 with `[]` |
| GET | `/opportunities` | no | no caller once `agent/frontend` merges (REQ-6) — was legacy `api.js` | Alias |
| GET | `/api/insight` | no | yes | `{"insight": string}` — latest `ai_insights` row of type `daily`, or generated on the fly. Never fails; returns a placeholder string on error |
| GET | `/insight` | no | no caller once `agent/frontend` merges (REQ-6) — was legacy `api.js` | Alias |
| GET | `/api/ai/analyze/{symbol}` | no | yes (stock modal) | `{"symbol", "analysis": string}`. `404` if the stock is unknown. On other errors: 200 with a placeholder string |

The AI text comes from Gemini when `GEMINI_API_KEY` is set, otherwise from a template. The response does not say which.

### 2.5 Refresh

| Method | Path | Auth | Used by frontend | Response |
|--------|------|------|------------------|----------|
| POST | `/api/refresh` | **no** | yes | `{"status": "Refresh triggered", "message"}` — starts a forced full refresh in the background |
| GET | `/api/refresh` | **no** | no | `{"status": "Refresh triggered"}` — same effect through a GET |

### 2.6 Export (Excel, `.xlsx` attachment)

| Method | Path | Auth | Used by frontend | Request | Notes |
|--------|------|------|------------------|---------|-------|
| POST | `/api/export/portfolio` | optional | yes | `{"period": "daily"\|"weekly"\|"monthly", "stocks": [Stock-like]}` | Body is an untyped `dict`. Rows are built from the **client-supplied** stock objects. If `stocks` is empty and the caller is signed in, the watchlist is used. `400` if neither. CSRF-exempt |
| GET | `/api/export/portfolio?symbols=A,B&period=` | no | no | max 50 symbols | Fetches each symbol from the provider. Failed symbols produce a row of zeros |
| GET | `/api/export/{period}` | no | no | | Up to 113 symbols fetched one by one from yfinance inside the request |

Columns: Symbol, Currency, Name, Report Period, Analysis Date, Trend, Current Price, Start Price, Change %, Change Amt, Period High, High Date, Period Low, Low Date, RSI (14), RSI Status, Volatility %, MA(20), Volume (Period).

In the two portfolio exports, `period` only changes a label: the figures are single-day values, "Period High/Low" are the day's high/low (or price ±1 % when missing) and "RSI (14)" is the estimate from §2.2. Only `/api/export/{period}` computes real period statistics.

### 2.7 Authentication — prefix `/api/auth`

| Method | Path | Request | Success | Errors |
|--------|------|---------|---------|--------|
| POST | `/register` | `{"email", "password", "captcha_token"?}` | 200 `{"message"}` — same generic message whether or not the email exists | 400 password policy, 400 captcha, 429 |
| GET | `/verify-email?token=` | | HTML page | HTML error page |
| POST | `/resend-verification` | `{"email"}` | 200 `{"message"}` | 429 |
| POST | `/login` | `{"email", "password", "captcha_token"?}` | 200 `{"user": {"id", "email", "email_verified"}, "message"}` + session and CSRF cookies | 401 generic, 401 locked (with seconds), 400 captcha (header `X-Captcha-Required: true`), 403 unverified, 429 |
| POST | `/logout` | | 200 `{"message"}`, cookies cleared | 403 CSRF |
| GET | `/me` | | 200 `{"id", "email", "email_verified", "created_at"}` | 401 |
| POST | `/forgot-password` | `{"email", "captcha_token"?}` | 200 generic `{"message"}` | 429 |
| POST | `/reset-password` | `{"token", "new_password"}` | 200 `{"message"}`, all sessions revoked | 400 policy, 400 invalid token, 429 |
| GET | `/csrf` | | 200 `{"csrf_token"}` | |

Password policy: minimum 10 characters plus a common-password blocklist. Lockout: 1 min after 5 failures, 5 min after 6, 15 min after 7 or more.

### 2.8 Watchlist — prefix `/api/watchlist` (session required)

| Method | Path | Request | Success | Errors |
|--------|------|---------|---------|--------|
| GET | `` | | `{"items": [WatchlistItem], "count"}` | 401 |
| POST | `` | `{"ticker", "market"?}` — market one of `BIST100, US, GLOBAL, COMMODITY`; inferred when omitted | 201 `{"message", "ticker", "market"}`. If already present: **201** `{"message", "ticker"}` | 401, 403 CSRF, 422 validation |
| DELETE | `/{ticker}` | | 200 `{"message", "ticker"}` | 401, 403, 404 |
| GET | `/summary?force_refresh=false` | | `WatchlistSummary` | 401 |

`WatchlistItem`: `id, ticker, market, added_at, name, price, change_pct, volume, day_high, day_low, rsi, currency, prediction, market_type`. `ticker` is stored without `.IS` for `BIST100`.

`WatchlistSummary`: `total_count, up_count, down_count, flat_count, avg_change_pct, biggest_mover {symbol, name, price, change_pct, currency, direction, market} | null, ticker_changes [{symbol, name, price, change_pct, currency, market}], last_updated, from_cache, cache_expires_in`. Cached 60 s per user in process memory.

`avg_change_pct` is the unweighted mean of daily percentage changes. It is a watchlist statistic, not a portfolio return.

---

## 3. Shared types in use today (VERIFIED)

There is no shared type definition. The backend has Pydantic models only for auth requests, `UserResponse` and `AddWatchlistRequest`. Every other response is a hand-built `dict`. The frontend is untyped JavaScript that reads fields by name.

Enumerations as they appear in the data:

| Name | Values | Where |
|------|--------|-------|
| `market_type` | `BIST`, `GLOBAL`, `COMMODITY` | `stock_data`, Stock responses |
| watchlist `market` | `BIST100`, `US`, `GLOBAL`, `COMMODITY` | `watchlist_items` — a different vocabulary from `market_type` |
| `volatility` | `LOW`, `MEDIUM`, `HIGH` | Stock responses |
| signal label | `PURCHASABLE`, `ACCUMULATE`, `WATCH TO BUY`, `AVOID FOR NOW`, `TAKE PROFITS` | prefix of `prediction`; AI prompt |
| export `period` | `daily`, `weekly`, `monthly` | export endpoints |

---

## 4. Proposed conventions for new endpoints (PROPOSED)

These apply to new endpoints only. Existing endpoints keep their shapes.

- Prefix `/api/v1/`.
- Every request and response has a Pydantic schema in `backend/schemas/`; no untyped `dict` bodies.
- Errors keep the existing `{"detail": ...}` form, with correct status codes. No 200-with-empty-list on failure.
- All user-owned resources require a session and are scoped by `user_id`; a resource owned by someone else returns `404`.
- State-changing methods require the CSRF header, with no exemptions.
- Money and quantities are serialised as **decimal strings** (`"1234.5600"`), never floats.
- Timestamps are ISO-8601 UTC with offset. Trade dates are `YYYY-MM-DD`.
- Lists are paginated: `?limit=&offset=`, response `{"items": [...], "total", "limit", "offset"}`.
- Every market-derived value carries its provenance:

```
PriceQuote {
  symbol       string        canonical form, see DATABASE_CONTRACT §3.1
  price        decimal string
  currency     ISO 4217
  as_of        ISO-8601 UTC
  freshness    "realtime" | "delayed" | "end_of_day" | "stale"
  source       string        e.g. "yfinance"
}
```

- A value that cannot be computed is `null` with a reason; it is never estimated.

---

## 5. Proposed endpoints (PROPOSED — none exist)

Listed to reserve names and let the agents plan. Field-level schemas are written by Agent 1 with Agents 2 and 3 once the open decisions (COORDINATION §9) are settled.

### 5.1 Portfolios and transactions — Agent 2

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/portfolios` | List the caller's portfolios |
| POST | `/api/v1/portfolios` | Create (`name`, `base_currency`, `kind`: `real` \| `paper`) |
| GET | `/api/v1/portfolios/{id}` | Read |
| PATCH | `/api/v1/portfolios/{id}` | Rename |
| DELETE | `/api/v1/portfolios/{id}` | Archive (soft; history is kept) |
| GET | `/api/v1/portfolios/{id}/transactions` | Paginated ledger |
| POST | `/api/v1/portfolios/{id}/transactions` | Append a transaction |
| POST | `/api/v1/portfolios/{id}/transactions/{tx_id}/void` | Reverse a transaction; rows are never edited or deleted |

`TransactionCreate` (draft): `type` (`BUY`, `SELL`, `DIVIDEND`, `FEE`, `DEPOSIT`, `WITHDRAWAL`, `SPLIT`), `symbol`, `quantity`, `price`, `fee`, `currency`, `fx_rate_to_base` (optional), `trade_date`, `note`.

#### 5.1.1 As implemented — IMPLEMENTED ON BRANCH `agent/backend` `d4af8bd` (not merged)

All eight routes above exist with these paths. Every route needs a session; writes need the CSRF header. Responses carry `Cache-Control: no-store`. Errors: unknown or another user's resource → `404` (never `403`, so ids are not confirmed); conflict → `409`; validation → `422`. Request bodies reject unknown fields.

| Route | Detail |
|-------|--------|
| `GET /api/v1/portfolios` | Query `include_archived` (default false), `limit`, `offset`. Returns `Page[PortfolioOut]` |
| `POST /api/v1/portfolios` | `PortfolioCreate{name, base_currency, kind="real"}`. `base_currency` limited to `TRY`, `USD` until D3 is decided. Duplicate active name → `409` |
| `PATCH /api/v1/portfolios/{id}` | `PortfolioUpdate{name}` only. An archived portfolio → `409` |
| `DELETE /api/v1/portfolios/{id}` | Archives; returns `PortfolioOut` with `archived_at`. Repeating it keeps the first time |
| `GET …/transactions` | Newest first (`trade_date` desc, `id` desc). `Page[TransactionOut]` |
| `POST …/transactions` | `201`. Archived portfolio → `409` |
| `POST …/transactions/{tx_id}/void` | `201`, optional body `TransactionVoid{note}`. Appends a reversal row; the original is untouched. A second void, or voiding a reversal → `409` |

`PortfolioOut`: `id, name, base_currency, kind, created_at, archived_at`. The owner id is not exposed.

`TransactionCreate` **adds** to the draft:

- `exchange` (optional). Needed only when a symbol is listed on more than one exchange; otherwise ambiguous symbols are `422`.
- `executed_at` (optional, must carry a UTC offset; stored in UTC).
- Money and quantity fields must be JSON strings or integers. Floats and booleans are rejected, so no binary rounding enters the ledger.
- `trade_date` must be between 1900-01-01 and today + 1 day.

Rules enforced by `TransactionCreate` and the service:

| Type | `symbol` | `quantity` | `price` | `fee` |
|------|----------|------------|---------|-------|
| `BUY`, `SELL`, `DIVIDEND` | required | > 0 | required | ≥ 0 |
| `SPLIT` | required | > 0, the ratio of new units per old unit | — | must be 0 |
| `FEE` | optional | must be 0 | — | > 0 |
| `DEPOSIT`, `WITHDRAWAL` | not allowed | > 0, the cash amount | — | must be 0 |

`—` in the price column means the field is rejected. `currency` is required whenever there is no symbol.

- The symbol must resolve to an active row in `instruments`. The canonical form or the provider form both work (`THYAO` or `THYAO.IS`). An unknown symbol → `422`; it is never guessed.
- For `BUY`, `SELL` and `SPLIT` the currency must equal the instrument's currency.
- When the trade currency equals the portfolio base currency, `fx_rate_to_base` is stored as `1`, and any other value is rejected. For a foreign currency, a missing rate stays `null` and is never looked up or estimated.

`TransactionOut` **adds** to the draft: `symbol`, `exchange`, `source`, `voids_transaction_id`, `voided_by_transaction_id`, `created_at`. Decimals are serialised as strings at fixed scale: quantity 8, money 6, rate 8.

A reversal row copies the original's `type`, amounts and instrument, and sets `voids_transaction_id`. Consumers must ignore **both** the reversal and the row it voids. `quant.positions` already does this.

### 5.2 Portfolio analytics — maths by Agent 3, routes by Agent 2

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/portfolios/{id}/holdings` | Positions derived from transactions: quantity, cost basis, market value, unrealised P/L, each with `PriceQuote` provenance |
| GET | `/api/v1/portfolios/{id}/performance` | Realised and unrealised P/L, dividends, fees, by currency and in base currency |
| GET | `/api/v1/portfolios/{id}/allocation` | Weights by instrument, market, currency |
| GET | `/api/v1/portfolios/{id}/risk` | Volatility, drawdown, concentration, computed from stored price history |

### 5.3 Market data additions — Agent 3 and Agent 2

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/instruments?query=` | Search the supported universe |
| GET | `/api/v1/quotes/{symbol}` | `PriceQuote` plus day statistics, with freshness |
| GET | `/api/v1/indicators/{symbol}` | Real RSI(14), SMA(20/50), annualised volatility from price history, with the window and `as_of` |

### 5.4 AI — Agent 3 and Agent 2

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/portfolios/{id}/ai/summary` | Explanation of already-computed portfolio figures. The model receives numbers; it does not produce them |
| GET | `/api/v1/ai/insights?scope=` | Stored insights, with `model`, `generated_at`, `is_fallback` and a disclaimer field |

AI responses always include: `generated_by` (`model name` or `template`), `generated_at`, the `inputs_as_of` timestamp of the data used, and `disclaimer`.

#### 5.4.1 AI layer as implemented — IMPLEMENTED ON BRANCH `agent/quant-ai` `19d0501` (not merged; no route exists yet)

The pieces behind `POST /api/v1/portfolios/{id}/ai/summary` exist as library code in `backend/ai/`. No endpoint uses them yet. Agent 2 builds the route once holdings exist (§5.2).

```python
# backend/ai/facts.py
def portfolio_facts(valuation: PortfolioValuation, risk: RiskMetrics | None = None
                    ) -> tuple[tuple[Fact, ...], datetime | None]: ...   # facts, inputs_as_of (oldest quote)

# backend/ai/explain.py
def explain_portfolio(facts: Sequence[Fact], *, now: datetime, inputs_as_of: datetime | None,
                      generate: Callable[[str], Generation | None] | None = None) -> AIResult: ...

# backend/ai/provider.py
def gemini_generate(prompt: str) -> Generation | None: ...   # wraps ai_service; synchronous network I/O

# backend/ai/guardrails.py
@dataclass(frozen=True)
class Fact:       label: str; value: str              # already formatted by deterministic code
@dataclass(frozen=True)
class Generation: text: str; model: str
@dataclass(frozen=True)
class AIResult:
    text: str
    generated_by: str            # model name, or "template"
    generated_at: datetime       # supplied by the caller (`now`)
    inputs_as_of: datetime | None
    is_fallback: bool
    disclaimer: str              # guardrails.DISCLAIMER
    violations: tuple[str, ...] = ()
def find_violations(text: object, facts: Sequence[Fact]) -> tuple[str, ...]: ...
```

Behaviour:

- The model receives only `Fact` lines and returns prose. Its text is used only when `find_violations` returns nothing. Otherwise, and on any provider error or empty output, the deterministic template is returned with `is_fallback=True`. `explain_portfolio` never raises because of the model. It raises `ValueError` only when `facts` is empty.
- Values of `violations`: `empty`, `no_output`, `too_long` (over 2,000 characters), `ungrounded_number`, `number_word`, `prohibited_language` (advice, prediction or guarantee wording), `markup`, `provider_error`.
- **`violations` is for logs and audit only.** The route must not return it to the browser and the UI must not display it. Log it server-side together with `generated_by`.
- `Fact` must never be built from free text a user typed, such as a portfolio name or a note. Numbers in it become figures the model is allowed to quote.
- `gemini_generate` and `explain_portfolio` block. From an async route, call them with `await asyncio.to_thread(explain_portfolio, …)`.

Response shape the route will return (fixed now so Agent 4 can build against it):

```json
{ "text": "string, plain text, may contain \n",
  "generated_by": "gemini-… | template",
  "generated_at": "ISO-8601 UTC", "inputs_as_of": "ISO-8601 UTC | null",
  "is_fallback": true, "disclaimer": "string" }
```

Frontend rendering requirements for this response are in §7.

### 5.5 Paper trading — later phase

`/api/v1/paper/orders` (create, list, cancel). Fills are simulated against stored quotes and written as transactions in a `paper` portfolio. No endpoint places a real order.

---

## 6. Internal contract between Agent 2 and Agent 3 (PROPOSED)

Agent 3 exposes pure functions; Agent 2 calls them. Draft signatures, to be finalised before either side implements:

```python
# backend/quant/symbols.py
def normalize_symbol(raw: str, market_hint: str | None = None) -> CanonicalSymbol: ...

# backend/quant/positions.py
def build_positions(transactions: Sequence[Transaction], method: CostBasisMethod) -> list[Position]: ...
def realized_pnl(transactions: Sequence[Transaction], method: CostBasisMethod) -> list[RealizedLot]: ...

# backend/quant/valuation.py
def value_positions(positions: Sequence[Position], quotes: Mapping[str, PriceQuote],
                    fx: Mapping[str, FxRate], base_currency: str) -> PortfolioValuation: ...

# backend/quant/indicators.py
def rsi(closes: Sequence[Decimal], period: int = 14) -> Decimal | None: ...
def sma(closes: Sequence[Decimal], window: int) -> Decimal | None: ...

# backend/quant/risk.py
def risk_metrics(daily_values: Sequence[DatedValue]) -> RiskMetrics: ...
```

Rules: inputs and outputs are immutable dataclasses using `Decimal`; no I/O; same input always gives the same output; insufficient data returns `None`, never an estimate.

### 6.1 As implemented — IMPLEMENTED ON BRANCH `agent/quant-ai` `034313e` (not merged)

The draft signatures above are honoured, with the additions below. All types are frozen dataclasses in `backend/quant/types.py`. Every public function runs in a fixed `Decimal` context (precision 60, ROUND_HALF_EVEN). Tests pass on Python 3.11.9, the production version.

```python
# quant/symbols.py
def normalize_symbol(raw: str, market_hint: str | None = None) -> CanonicalSymbol   # ValueError if invalid
def instrument_seed() -> tuple[InstrumentSeed, ...]   # 361 rows: 119 BIST/TRY, 229 US/USD, 13 CMDTY/USD
#   market_hint accepts both vocabularies: BIST, BIST100, US, GLOBAL, COMMODITY, CMDTY, FX

# quant/positions.py — raise LedgerError (a ValueError) on an invalid ledger
def build_positions(transactions: Sequence[Transaction], method: CostBasisMethod) -> list[Position]
def realized_pnl(transactions: Sequence[Transaction], method: CostBasisMethod) -> list[RealizedLot]
def cash_summary(transactions: Sequence[Transaction]) -> CashSummary            # added

# quant/valuation.py
def value_positions(positions, quotes: Mapping[str, PriceQuote], fx: Mapping[str, FxRate],
                    base_currency: str) -> PortfolioValuation
#   fx maps a currency to FxRate(base=<currency>, quote=<base_currency>)

# quant/allocation.py                                                            # added
def allocation_by(valuation: PortfolioValuation, group_of: Mapping[str, str]) -> tuple[AllocationSlice, ...] | None
def concentration(weights: Mapping[str, Decimal]) -> Concentration | None

# quant/indicators.py
def rsi(closes, period: int = 14, method: RsiMethod = RsiMethod.WILDER) -> Decimal | None   # `method` added
def sma(closes, window: int) -> Decimal | None
def annualized_volatility_pct(closes, ...) -> Decimal | None                    # added

# quant/risk.py
def risk_metrics(daily_values: Sequence[DatedValue], periods_per_year: int = 252) -> RiskMetrics

# quant/signals.py — legacy float enrichment, moved out of analysis.py value for value (H1)
def enrich_quote(data: Mapping[str, object], market_type: str, currency: str) -> dict
```

Key types:

| Type | Fields |
|------|--------|
| `Transaction` (input) | `id, type: TransactionType, trade_date, currency, quantity=0, price=None, fee=0, symbol=None, fx_rate_to_base=None, voids_transaction_id=None` |
| `Position` | `symbol, currency, quantity, cost_basis, average_cost, cost_basis_base, lots` |
| `RealizedLot` | `…, pnl, pnl_base, buy_transaction_id, sell_transaction_id` |
| `CashSummary` | `balances, dividends, fees, net_deposits` — each a tuple of `CurrencyAmount(currency, amount)` |
| `PriceQuote` | `symbol, price, currency, as_of, freshness: Freshness, source` |
| `FxRate` | `base, quote, rate, as_of, source` |
| `PortfolioValuation` | `base_currency, positions: tuple[ValuedPosition], total_market_value, total_cost_basis, total_unrealized_pnl, is_complete, unvalued_symbols` |
| `ValuedPosition` | position fields, value and P/L in both currencies, weight, quote provenance, `unavailable_reason` (`missing_quote`, `quote_currency_mismatch`, `missing_fx_rate`, `quote_symbol_mismatch`, `invalid_quote_price`) |
| `RiskMetrics` | `observations, start, end, period_return_pct, daily_volatility_pct, annualized_volatility_pct, max_drawdown_pct, max_drawdown_peak, max_drawdown_trough` |
| `CostBasisMethod` | `fifo`, `weighted_average` (D2 decides the stored default) |

Semantics the adapter must respect:

- Agent 2's ORM → `quant.types.Transaction` adapter is not written yet. It is the first task of Phase 3.
- `fx_rate_to_base` is passed through as stored. A `null` rate makes the `*_base` fields `None`. It is never filled in.
- Positions are keyed by `symbol` alone. The current seed has no symbol listed on two exchanges, which was checked. If that ever changes, the adapter must pass a unique key, for example `provider_symbol`.
- A reversal and its target are both excluded. Selling more than is held raises `LedgerError`; shorts are not supported.
- The functions are CPU-bound. For large ledgers, call them through `asyncio.to_thread`.
- `value_positions` uses quotes whatever their freshness, and carries the label through. The route must show it.
- If any position cannot be valued, the totals and weights are `None` and `is_complete` is false. The route returns that as it is and does not substitute partial totals.

---

## 7. Frontend rendering rules (IMPLEMENTED ON BRANCH `agent/frontend` `cc3fcc3` for existing views; binding for new ones)

- Text from the API that is not markup is rendered as **plain text**. This covers AI output, instrument and provider names, portfolio names, notes and error messages. Use `textContent`, or `escapeHTML` from `frontend/js/core/safe-html.js` before any `innerHTML`.
- AI text (`/api/insight`, `/api/ai/analyze/{symbol}`, and the future §5.4 `text`) goes only through `aiTextToHTML()`. It strips markdown, escapes everything and turns `\n` into `<br>`. Never insert it as HTML or markdown.
- Every AI view shows `disclaimer`, and shows `generated_by` and `inputs_as_of` when the API returns them. `violations` is never sent to the browser.
- Symbols typed by the user are checked with `isValidSymbol()`, the §1.5 pattern, before any request. In URLs they are wrapped in `encodeURIComponent`.
- Existing classic scripts reach the helpers through `window.WolfeeSafe`, set by the module `js/core/globals.js`. New code imports `safe-html.js` directly.
- Financial figures for real portfolios are displayed exactly as the API returns them, as decimal strings. The frontend does no portfolio arithmetic (TEAM_STRUCTURE H10).
