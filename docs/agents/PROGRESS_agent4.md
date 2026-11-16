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
- [x] 2. REQ-34 (a), `21ffc67`: the market insight badge comes from the response (`aiSourceLabel`, tested): "AI generated" only for model text, "Template" when `is_fallback` or `generated_by == "template"`, hidden without text. The stock analysis shows the same label in its provenance line.
- [x] 3. REQ-34 (c), `92fbcf3`: `readableApiError` bridged as `window.WolfeeApiErrors`; auth forms show each 422 message under its field (`data-api-field`, `aria-invalid`), body-level text in the alert, never "[object Object]". Also export errors. Fixed the resend-verification form (it called a function out of scope) and the forgot-password form (showed success on an error).
- [x] 4. REQ-34 (d), `1b7394e`: watchlist pills at 2 decimals like the mover, average and cards.
- [x] 5. Registration, `29a3414`: no CAPTCHA token or markup (D1); "Invite code" field sent as `invite_code` (empty caught before the request). The current backend ignores the key until Agent 2's check lands (`RegisterRequest` does not forbid extra fields). Signing in from the dialog now fires `wolfee_auth_changed`, so the Portfolio page loads without a reload.
- [x] 6. Filter sheet backdrop: below 768px the page (header and tab bar too) dims behind the open filter sheet; a tap on it closes the sheet. CSS sibling rule, no new JS state; no animation with reduced motion.

- [x] 6 committed as `8c734ac`.
- [x] Verified 2026-11-16 in WSL per TESTING.md §2 (Agent 4 DB `~/wolfee-test/agent4-frontend-test.db`): frontend 68 passed (also with TZ=America/New_York), backend 598 passed. Browser check at 1440 and 390 px on the smoke DB: Market, Opportunities, Portfolio and Watchlist with no horizontal scroll, no console errors, no "[object Object]", every asset at v=16.1, 5 mobile tabs. Review page updated with Portfolio screenshots (the partial-total shot is the test fixture rendered by the real module, labelled as such).

## Task: REQ-37 remainder (2026-11-16)
- [x] 1. `GET /api/auth/config` on load (`js/auth-features.js`, parsing in `js/core/auth-config.js`, tested). It sets `data-email-enabled` / `data-registration-open` on `<html>`; `css/auth.css` hides every `[data-needs-email]` (Forgot password tab, the "Forgot password?" and "Resend verification email" links, both forms) unless email is `true`, and swaps the register fields for "Registration is closed" when registration is `false`. Before the answer and on any failure: email features hidden, register visible. Only a JSON `true` turns email on and only a JSON `false` closes registration. The auth tab group now sizes to the visible tabs.
- [x] 2. `frontend/worker.js` deleted (nothing referenced it; `wrangler.jsonc` only names `frontend` as the Pages output dir). The mentions in `TEAM_STRUCTURE.md` and `IMPLEMENTATION_STATUS.md` are Agent 1's to update.
- [x] 3. Asset version 16.2 (`index.html`, `globals.js`, the new module).
- Verified in WSL: frontend 72 passed (also TZ=America/New_York). Browser at 1440 and 390 px: with the endpoint not yet in this backend (404) the safe state applies; the all-on and closed states checked by setting the same attributes; no horizontal scroll; all assets v=16.2.

## In progress
- Nothing. Ready for the user to review; not merged or pushed.

## Next
- Agent 2: `GET /api/auth/config` (until it lands the page logs one 404 and a warning and shows the safe state) and the `invite_code` check on `POST /api/auth/register`.
- Possible follow-up: the Portfolio page uses the default weighted-average cost basis; a FIFO switch (`cost_basis_method`) and realised lots (`realized_lots`) are in the API but not shown yet.

## Notes
- Smoke DB: `POST /api/v1/portfolios` returned 500 "database is locked" once while the start-up stock fill was writing to SQLite; it worked on retry. Local SQLite only; for Agent 2 if it shows up elsewhere.
- For Agent 2: `GET /api/watchlist/summary` still turns a null change_pct into 0.0 and counts it as flat (REQ-31).
- For Agent 3: the market insight template text contains an em-dash. AI text is shown as sent.

## Earlier: UI redesign phase B (merged as `10318c3`)
Pages 1 to 5 (shell and market, stock modal, Opportunities, Watchlist and export, account dialog), tokens and self-hosted IBM Plex, asset version 16.0. Verified 2026-11-15: frontend 41 passed, backend 583 passed, every page at 1440 and 390 px.
