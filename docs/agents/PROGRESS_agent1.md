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
- WSL test environment (2026-11-14): TESTING.md, backend/requirements-test.txt (`d7dd9d3`); in WSL 224 backend + 9 frontend pass; 179 API tests on a temporary PG 18 cluster
- PG 16.16 test cluster up (~/wolfee-test/pg16, 127.0.0.1:55432, left running). On it, `agent/backend` @ `771368f`: API tests 179 passed; migration chain up/down/up clean to `d7b2e6f4a913`, `alembic check` clean. Fly Postgres pinned to major 16 (`--image-ref flyio/postgres-flex:16`, DEPLOYMENT §5; comment in fly.toml)
- Step 3c (2026-11-14): reviewed and merged `agent/quant-ai` `def3511` → **`da57548`** (REQ-24, REQ-25, labels, open/prev_close) and `agent/frontend` `ceecbda` → **`f0b9fc9`** (REQ-27, v=15.4). WSL: backend 281 passed, frontend 28/28. Decisions recorded (volatility bands, open/prev_close null, label table + 2 %, Up/Down today, local times, 0 = n/a, ai_insights provenance §4.4, daily_bars.py). API_CONTRACT §2.2/§2.4/§3, DATABASE_CONTRACT §2.6/§4.4, PROGRESS_agent3.md rewritten. New REQ-28 (Agent 2 routes + migration), REQ-29 (Agent 4), REQ-30 (Agent 2 open/prev_close). `bb00a11` pre-approved. PG18 cluster deleted
- Step 3b, backend only (2026-11-15): reviewed `agent/backend` `13b8c61` (rebased onto integration; clean merge) → **`a63f25d`**. WSL: backend 564 passed, frontend 28/28, PG16 API 187 passed, migration chain clean to `e4a8c2f6b1d3`, seed CLI idempotent (361 / 0). Closed REQ-7, 8, 9, 10, 13, 15, 16, 17 (Agent 2 half), 18–21, 26, 28, 30; REQ-22/23 status corrected (done at d3f30bf). REQ-11 still open (3 failures from backend/). Contracts' status notes updated
- Step 3d (2026-11-15): merged `agent/quant-ai` `631dc76` → **`836c3a3`** (legacy estimates and `estimated_fields` gone, `change_pct` null without previous close, chart bars without filled OHLC, loading fact). WSL: backend 583 passed, frontend 28/28. API_CONTRACT §2.2/§2.4/§5 updated. New REQ-31 (Agent 2: watchlist `round(None)` HIGH, market_placeholder loading, main.py chart fallback, stock_card, gold/FX change, delete api_router.py) and REQ-32 (Agent 4: Portfolio page after the redesign). Watchlist crash accepted on local-only integration
- Step 4 (2026-11-15): merged `agent/backend` `98ee277` → **`fe6d8c6`** (REQ-31 closed) and `agent/frontend` `a75332b` → **`10318c3`** (redesign, REQ-29 closed, v=16.0). The "▲ 0.00%" report was re-checked: fixed by the redesign. api_router.py doc references removed. Final WSL verification all green (598 / 41 / PG16 191 / migrations / seed / browser smoke at 1440 and 390). Readiness: DEPLOYMENT §2.1 (D1 CAPTCHA, D2 e-mail, D3 Postgres UTC, D4 app name, D5 PG16). New REQ-33 (Agent 2), REQ-34 (Agent 4), REQ-35 (Agent 3)
- Decisions recorded (2026-11-16): D1 invite code, no CAPTCHA; D2 no e-mail verification at launch, reset unavailable; D3 UTC check at DB creation; D4 app name at deploy. `fly.toml` `REQUIRE_EMAIL_VERIFICATION=false`. `railway.json` and `wrangler.jsonc` deleted. New REQ-36 (Agent 2), REQ-37 (Agent 4)
- Final merge (2026-11-16): `agent/quant-ai` `f8bef1d` → **`6fbb26d`**, `agent/backend` `cf440a2` → **`7bf4d6b`**, `agent/frontend` `ee33aee` → **`dd08370`**. REQ-32…37 DONE. API_CONTRACT §1/§2.7 (invite code 403/429, no CAPTCHA, 503s, `/api/auth/config`), DEPLOYMENT (invite secret, CAPTCHA rows removed, D6 spoofable IP, §10 split into user / Agent 1 commands), worker.js refs removed, README CAPTCHA line replaced. New REQ-38 (Agent 2 DISCLAIMER fallback), REQ-39 (Agent 2 `Fly-Client-IP`), REQ-40 (Agent 4 comment). Full WSL verification green (643 / 72 / PG16 194 / migrations / seed / browser smoke with invite code, no tokens in logs). Nothing pushed; `main` untouched

- GitHub Actions plan (2026-11-16): merged `c238476` → **`c9aff26`** (REQ-38/39) and `0475bc8` → **`3a75e0a`** (REQ-40); Dockerfile flags dropped `037077d`; `.github/workflows/deploy.yml` `d90f9d9`; `.gitignore` hardened `2762671`; history secret scan (only test data in the old `wolfee.db`, already public); docs + REQ-41. Then local `main` fast-forwarded to `integration` (not pushed). WSL on `main` @ `8cfbd11`: backend 657 passed, frontend 72/72, PG16 API 194 passed. `origin/main` is `66ddcab` (local `de0575a` was never pushed)

## Next (only after approval)
- User: DEPLOYMENT §10.1 U1–U8, then pushes `main` (U9)
- Agent 1 after the push: watch the workflow, §10.2 A1 and A3 (read-only)
- Merge REQ-41 when it lands

## Notes for whoever resumes
- `fly.toml` release_command (`alembic upgrade head && python -m services.instrument_service`) is runnable on integration since `a63f25d`. Still no Fly resources; nothing deployed.
- WSL restart stops the PG16 cluster; start it first (TESTING.md §3).
- Tests run in WSL only; exact commands in docs/agents/TESTING.md (venv ~/venvs/wolfee, Node ~/.local/opt/node, PG test cluster port 55432). Git stays on Windows.
