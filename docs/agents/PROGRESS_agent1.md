# Agent 1 progress — current task

Task (user, 2026-11-11): integration-branch follow-ups after Step 1. Work in `../wolfee-integration` on `integration`. Commit locally after each item; **never push**; no Fly resources. Stop and report when done.

Resume: `git -C ../wolfee-integration status`, read this file, continue with "Next".

## Done
- [x] 2. Pin dependencies — `5afdb26` (requirements.txt exact pins, requirements.lock hashed for Linux py3.11; 205 tests pass)
- [x] 3. start.sh fails loudly — `5afdb26` (verified: exit 1, uvicorn not started on migration failure)
- [x] 4. Dockerfile, .dockerignore, fly.toml — `4885064`; LF endings `.gitattributes` — `97a5ac1`

- [x] 1. REQ-12 closed in COORDINATION and DEPLOYMENT (fixed by Agent 2 in `agent/backend` `6170686`; not duplicated)

## In progress
- [ ] 5. Record decisions D2 (weighted average default, FIFO parameter), D3 (TRY base, FX from exchange_rates, missing_fx_rate per position but total the rest), approvals (delayed/stale labels, 10,000-transaction cap, realised P/L summing in Agent 2's service)
- [ ] 6. API_CONTRACT §5.2 — Agent 2's holdings/performance shapes (from `agent/backend` `6170686` `schemas/analytics.py`)
- [ ] 7. DATABASE_CONTRACT — approve migration M0b: stock_data, turkish_gold, exchange_rates, ai_insights, ix_auth_tokens_user_id, unique instruments.provider_symbol; migrations-only table creation in production
- [ ] Final report to user, then wait

## Notes for whoever resumes
- D3 "total the rest" conflicts with current `quant.value_positions` (totals None when incomplete) and Agent 2's `analytics_service` (no FX supplied) → REQ for Agents 3 and 2.
- `agent/backend` still has `DEFAULT_COST_BASIS_METHOD = FIFO` → REQ for Agent 2 after D2.
- `fly.toml` release_command needs `services.instrument_service`, which exists only after `agent/backend` merges (Step 2).
