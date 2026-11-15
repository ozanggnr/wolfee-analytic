# Agent 4 (frontend) progress

Branch `agent/frontend`, worktree `Wolfee-frontend`, rebased onto `integration` `3515621`.
Tests run in WSL only (`docs/agents/TESTING.md` §2), with Agent 4's own SQLite file under `~/wolfee-test/`.

## Task: UI redesign, phase B (approved 2026-11-15)

White and blue business look, plain CSS. Tokens in `frontend/css/tokens.css`; self-hosted IBM Plex in `frontend/fonts/`.
Visual only: routes, element IDs, form field names, API calls and the safe-html code are unchanged.
Decisions from the user: four mobile tabs (Market, Opportunities, Watchlist, Account); Account opens sign-in, or a sheet with the email and Log out; blue line chart everywhere, skipping bars without a close; mobile market insight starts at two lines with "Show more"; no label badge when the label is null; a null `change_pct` shows "Not available".

## Done
- [x] Page 1: shell and market page. New stylesheets replace `style.css`; navy header; mobile tab bar and Account sheet; one search and filter bar on mobile (filters as a bottom sheet); cards, gold and exchange rates null-safe for `change_pct` and prices (`formatChange`, `formatPrice`, `changeDirection`, `directionClass` in `market-fields.js`); `updated_at` without a zone read as UTC (`parseTimestamp`).
- [x] Page 2: stock modal. Close is a button, dialog semantics, Escape closes, focus returns; blue line chart for every period from closes only (bars without a close skipped); null change shows "Not available"; label badge hidden when null; no inline styles.
- [x] Page 3: Opportunities. Neutral heading and note (no "Buy" wording); cards share the market card markup; condition badges only from available inputs; reason hidden when missing or equal to the label; empty state. Fixed a crash: the page still called the removed getSignalStyle.
- [x] Page 4: Watchlist and export. Summary panel without emoji (navy mono KPI figures); a null change counts as "not available", not flat, and is left out of the average and the biggest move (`summarizeChanges`, tested); `|| 0` guards on change_pct removed; add field with label above and hint below; empty state; export dialog with text states and inline errors instead of alert(); `css/watchlist.css`.
- [x] Page 5: account dialog. Labels above, hints and server messages below (no placeholder as label), no emoji or inline styles, focus to the first field, Escape closes, password hint by class; sentence-case titles; `css/auth.css`.
- [x] Asset version 16.0 (`index.html`, `js/core/globals.js`).
- [x] Verified 2026-11-15 in WSL per TESTING.md §2 (Agent 4 DB `~/wolfee-test/agent4-frontend-test.db`): frontend 41 passed (also with TZ=America/New_York), backend 583 passed. Browser check of every page at 1440 and 390 px: no horizontal scroll, every asset at v=16.0.

## In progress
- Nothing. Phase B is ready for the user to review; not merged or pushed.

## Next
- Possible follow-up: dim the page behind the mobile filter sheet (it has a shadow, no backdrop).
- After phase B: REQ-32 Portfolio page on `/api/v1/portfolios`, then the Portfolio tab returns.

## Notes
- For Agent 2: `GET /api/watchlist/summary` (`backend/watchlist_routes.py`, summary loop) still turns a null change_pct into 0.0 and counts it as flat; it also feeds the average and biggest mover. The frontend now handles a null if the backend sends one, and shows `unknown_count` when present. Related to REQ-31.
- For Agent 3: the market insight template text contains an em-dash ("not available yet — no instrument ..."). AI text is shown as sent.
