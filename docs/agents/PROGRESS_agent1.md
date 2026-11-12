# Agent 1 progress — current task

Work in `../wolfee-integration` on `integration`. Commit locally after each item; **never push**; no Fly resources; main checkout stays on `main`.

Resume: `git -C ../wolfee-integration status`, read this file, continue with "In progress" / "Next".

## Done
- Step 1 — `agent/quant-ai` merged: `723bf19`
- Follow-ups 1–7 (2026-11-11): REQ-12 closed `018cf34`; pins + start.sh `5afdb26`; Fly files `4885064`, `97a5ac1`; decisions `b2c5415`, `30dde71`, `fb96878`, `48ef971`; API §5.2 `7ade3a0`; DB §4.2 `3fd0585`
- Step 2 (2026-11-12) — reviewed `71ae712` (same patch as reviewed `e4a4a5e`, message only) and `ad6cf21` (CSS.escape in filter.js/main.js, assets v=15.1; no unescaped selectors or v=15.0 left). Merged `agent/frontend` at `ad6cf21` with --no-ff: **`cc488f0`**. Backend 205 passed, frontend 9 passed
- Smoke-test REQs logged `eec38ae`: REQ-18 (HIGH, empty exchange rates, blocks REQ-15), REQ-19 THYAO→US, REQ-20 insight before refresh, REQ-21 watchlist summary cache (Agent 2); REQ-22 empty grid on start, REQ-23 chart.js:19 encoding (Agent 4)

## In progress
- Nothing. **Waiting for the user's approval before Step 3.**

## Next (only after approval)
- Step 3: merge `agent/backend` into `integration`. Review its unseen commits first (head was `ed17e01` on 2026-11-12). Open before/with it: REQ-13, REQ-15 (blocked by REQ-18), REQ-16 from Agent 2; REQ-14, REQ-17 from Agent 3. Verify REQ-7 (seed CLI) at the merge.

## Notes for whoever resumes
- `fly.toml` release_command needs `services.instrument_service`, which exists only after `agent/backend` merges.
- Test commands: backend `python -m pytest backend/tests -q -p no:cacheprovider` from the worktree root (Python 3.11.9 venv in the scratchpad, scratch SQLite DATABASE_URL); frontend `node --test` in `frontend/`.
