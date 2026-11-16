# Agent 4 (frontend) progress

Branch `agent/frontend`, worktree `Wolfee-frontend`, rebased onto `integration` `f9e64d2` (redesign merged as `10318c3`).
Tests run in WSL only (`docs/agents/TESTING.md` §2), with Agent 4's own SQLite files under `~/wolfee-test/`.

## Task: Portfolio page and REQ-34 fixes (2026-11-16)

Order from the user, one commit each: 1 REQ-32 Portfolio page, 2 REQ-34 (a) AI badge, 3 REQ-34 (c) readable validation errors, 4 REQ-34 (d) watchlist change at 2 decimals, 5 registration without CAPTCHA plus "Invite code" (`invite_code`), 6 dim the page behind the mobile filter sheet. Then tests and a browser check at 1440 and 390 px in WSL, review page screenshots of the Portfolio page. No merge, no push.

## Done
- [x] 1. REQ-32 Portfolio page on `/api/v1/portfolios` (API_CONTRACT §5.1.1, §5.2.1), commit `7e61301`.
  - Modules: `js/ledger/ledger-api.js` (requests via `authFetch`, CSRF on writes), `ledger-render.js` (escaped markup), `ledger-page.js` (controller, ES module); `js/core/ledger-format.js` (display rounding with BigInt and strings, no float arithmetic; per-type transaction rules and body builder); `js/core/api-errors.js` (422 detail to per-field messages); `css/ledger.css`.
  - Create and select a portfolio (TRY only, D3; 409 shown on the name field); add transactions with type-driven fields (labels above, errors below, decimal strings sent); void with an inline confirmation, voided and reversal rows marked; holdings, summary and realised P/L in TRY as the API returns them.
  - Partial state: "Partial total, N positions not valued" plus the unvalued symbols. A null figure shows "Not available" with the reason (`missing_fx_rate` reads "No exchange rate to TRY"; a trade without a stored rate gives no TRY cost basis). The API's own figure in the instrument currency is shown under it, never converted by the frontend.
  - Empty states: signed out, no portfolio, no positions, no transactions. Errors inline with "Try again".
  - Desktop tab "Portfolio" and a fifth mobile tab; `switchTab('ledger')` fires `wolfee_tab_changed`. Asset version 16.1.
  - Tests: `ledger-format`, `ledger-render`, `api-errors` (67 frontend tests on Windows node). Browser smoke at 1440 and 390 against the smoke DB (instruments seeded with `python -m services.instrument_service`, TESTING §3.3).

## In progress
- 2. REQ-34 (a): AI badge only for model text, "Template" otherwise.

## Next
- 3 to 6 above, then WSL tests, browser check, review page, report HEAD.

## Notes
- Smoke DB: `POST /api/v1/portfolios` returned 500 "database is locked" once while the start-up stock fill was writing to SQLite; it worked on retry. Local SQLite only; for Agent 2 if it shows up elsewhere.
- For Agent 2: `GET /api/watchlist/summary` still turns a null change_pct into 0.0 and counts it as flat (REQ-31).
- For Agent 3: the market insight template text contains an em-dash. AI text is shown as sent.

## Earlier: UI redesign phase B (merged as `10318c3`)
Pages 1 to 5 (shell and market, stock modal, Opportunities, Watchlist and export, account dialog), tokens and self-hosted IBM Plex, asset version 16.0. Verified 2026-11-15: frontend 41 passed, backend 583 passed, every page at 1440 and 390 px.
