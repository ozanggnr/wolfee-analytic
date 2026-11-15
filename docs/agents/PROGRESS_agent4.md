# Agent 4 (frontend) progress

Branch `agent/frontend`, worktree `Wolfee-frontend`, rebased onto `integration` `3515621`.
Tests run in WSL only (`docs/agents/TESTING.md` §2), with Agent 4's own SQLite file under `~/wolfee-test/`.

## Task: UI redesign, phase B (approved 2026-11-15)

White and blue business look, plain CSS. Tokens in `frontend/css/tokens.css`; self-hosted IBM Plex in `frontend/fonts/`.
Visual only: routes, element IDs, form field names, API calls and the safe-html code are unchanged.
Decisions from the user: four mobile tabs (Market, Opportunities, Watchlist, Account); Account opens sign-in, or a sheet with the email and Log out; blue line chart everywhere, skipping bars without a close; mobile market insight starts at two lines with "Show more"; no label badge when the label is null; a null `change_pct` shows "Not available".

## Done
- [x] Page 2: stock modal. Close is a button, dialog semantics, Escape closes, focus returns; blue line chart for every period from closes only (bars without a close skipped); null change shows "Not available"; label badge hidden when null; no inline styles.
- [x] Page 1: shell and market page. New stylesheets replace `style.css`; navy header; mobile tab bar and Account sheet; one search and filter bar on mobile (filters as a bottom sheet); cards, gold and exchange rates null-safe for `change_pct` and prices (`formatChange`, `formatPrice`, `changeDirection`, `directionClass` in `market-fields.js`); `updated_at` without a zone read as UTC (`parseTimestamp`).

- [x] Page 3: Opportunities. Neutral heading and note (no "Buy" wording); cards share the market card markup; condition badges only from available inputs; reason hidden when missing or equal to the label; empty state. Fixed a crash: the page still called the removed getSignalStyle.

## In progress
- Page 4: Watchlist and export.

## Next
- Page 5 auth forms.
- Then: bump the asset version, WSL tests (frontend and backend), browser check of every page at 1440 and 390 px, final screenshots on the review page.
- After phase B: REQ-32 Portfolio page on `/api/v1/portfolios`, then the Portfolio tab returns.

## Notes
- Until page 5 is committed, pages not yet redone show without their old styles (`style.css` is gone).
- For Agent 3: the market insight template text contains an em-dash ("not available yet — no instrument ..."). AI text is shown as sent.
