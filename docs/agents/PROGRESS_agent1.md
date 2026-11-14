# Agent 1 progress — current task

Work in `../wolfee-integration` on `integration`. Commit locally after each item; **never push**; no Fly resources; main checkout stays on `main`.

Resume: `git -C ../wolfee-integration status`, read this file, continue with "In progress" / "Next".

## Done
- Step 1 — `agent/quant-ai` merged: `723bf19`
- Follow-ups 1–7 (2026-11-11): REQ-12 closed `018cf34`; pins + start.sh `5afdb26`; Fly files `4885064`, `97a5ac1`; decisions `b2c5415`, `30dde71`, `fb96878`, `48ef971`; API §5.2 `7ade3a0`; DB §4.2 `3fd0585`
- Step 2 (2026-11-12) — `agent/frontend` `ad6cf21` merged: `cc488f0`. Smoke-test REQ-18…23 logged `eec38ae`
- Step 3a (2026-11-12):
  - [x] 1. Reviewed and merged `agent/quant-ai` `a7bb094` (REQ-14 `8d2b13c`, REQ-17 `ba52666`, ai/facts partial labels): **`d489b68`**
  - [x] 2. Reviewed and merged `agent/frontend` `b5f8c6d` (REQ-22 polling, REQ-23 encoding, v=15.2): **`d3f30bf`**
  - [x] 3. Backend 224 passed, frontend 9 passed (on `d3f30bf`)
  - [x] 4. API_CONTRACT §6.1 / §5.2.1, REQ-14 done, REQ-17 Agent 3 half done: `f0b9083`
  - [x] 5. D4, D5, TRY-only API rule: `7f19a0f`
  - [x] 6. REQ-24 (Agent 3, D4), REQ-25 (Agent 3, D5), REQ-26 (Agent 2, history), REQ-27 (Agent 4, display): `083b466`

## In progress
- Nothing. **Waiting for Agent 2 to report, then the user approves Step 3b.** `agent/backend` NOT merged.

## Done 2026-11-12 (after Step 3a)
- price_history approved (DATABASE_CONTRACT §4.3, REQ-26); volatility added to D4 / REQ-24; corrections accepted by the user
- WSL test environment (2026-11-14): TESTING.md, backend/requirements-test.txt (`d7dd9d3`); in WSL 224 backend + 9 frontend pass; 179 API tests on a temporary PG 18 cluster. PG16 needs the user's one-time sudo step (TESTING §3), then rerun §3.1/§3.2 on 16

## Next (only after approval)
- Step 3b: review and merge `agent/backend` (head `e30f1db` on 2026-11-12: REQ-13 `5e464a7`, REQ-15 `a4ce4e7`, REQ-16 `7c484e9`, REQ-9 `6a168a5`). Verify REQ-7 seed CLI. Expect overlap with quant changes (analytics_service vs REQ-17).

## Notes for whoever resumes
- `fly.toml` release_command needs `services.instrument_service`, which exists only after `agent/backend` merges.
- Tests run in WSL only; exact commands in docs/agents/TESTING.md (venv ~/venvs/wolfee, Node ~/.local/opt/node, PG test cluster port 55432). Git stays on Windows.
