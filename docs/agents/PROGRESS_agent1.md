# Agent 1 progress — current task

Task (user, 2026-11-11): integration-branch follow-ups after Step 1. Work in `../wolfee-integration` on `integration`. Commit locally after each item; **never push**; no Fly resources. Stop and report when done.

Resume: `git -C ../wolfee-integration status`, read this file, continue with "Next".

## Done
- [x] 2. Pin dependencies — `5afdb26` (requirements.txt exact pins, requirements.lock hashed for Linux py3.11; 205 tests pass)
- [x] 3. start.sh fails loudly — `5afdb26` (verified: exit 1, uvicorn not started on migration failure)
- [x] 4. Dockerfile, .dockerignore, fly.toml — `4885064`; LF endings `.gitattributes` — `97a5ac1`

- [x] 1. REQ-12 closed in COORDINATION and DEPLOYMENT (fixed by Agent 2 in `agent/backend` `6170686`; not duplicated)

- [x] 5. Decisions recorded — `b2c5415` (COORDINATION §9: D2, D3, D8 resolved, approvals, REQ-13/14/15) + follow-up commit for DATABASE_CONTRACT §3.6

- [x] 6. API_CONTRACT §5.2.1 holdings/performance shapes, §6.1 note updated for D3

- [x] 7. DATABASE_CONTRACT §4.2 approved migration + §5 status; COORDINATION REQ-16 (supersedes REQ-8)

## In progress
- [ ] Final report to user, then wait

## Notes for whoever resumes
- D3 "total the rest" conflicts with current `quant.value_positions` (totals None when incomplete) and Agent 2's `analytics_service` (no FX supplied) → REQ for Agents 3 and 2.
- `agent/backend` still has `DEFAULT_COST_BASIS_METHOD = FIFO` → REQ for Agent 2 after D2.
- `fly.toml` release_command needs `services.instrument_service`, which exists only after `agent/backend` merges (Step 2).
