# Coordination, Git Workflow and Integration Process

Last updated: 2026-11-11 by Agent 1.

Everything in this document is **PROPOSED** process, except §1 which records the verified starting state.

---

## 1. Starting state (VERIFIED)

- Remote: `origin` on GitHub. Local branch `main` at `66ddcab`. One other remote branch, `origin/update_worker_name_to_wolfeeanalytics`.
- One worktree only (the repository root). No agent worktrees exist yet.
- `CLAUDE.md` and `docs/` are **untracked** — they are not committed, so a fresh worktree will not contain them until they are.
- No CI configuration exists (no `.github/`). Nothing runs tests automatically.
- `railway.json` deploys with `cd backend && bash start.sh` and watches `backend/**` and `frontend/**`. Which branch Railway deploys from is configured in Railway and could not be verified from the repository; treat `main` as production.

---

## 2. Branch strategy

```
main            production. Only the user merges here.
└── integration shared staging branch, created from main. Agent 1 curates it.
    ├── agent1/<topic>
    ├── agent2/<topic>
    ├── agent3/<topic>
    └── agent4/<topic>
```

- Each agent works in its own git worktree, for example `../wolfee-agent2`, on a branch named `agent<N>/<short-topic>`.
- Branches are short-lived and cut from the current `integration`.
- Agents open pull requests into `integration`, never into `main`.
- Agent 1 reviews and merges into `integration`. The user merges `integration` into `main`.
- No force-push to `integration` or `main`. Rebase your own branch onto `integration` before opening a PR.

First step once this plan is approved: commit `CLAUDE.md` and `docs/` on a branch, create `integration`, then create the worktrees.

---

## 3. Commit and PR rules

- Conventional commits: `feat|fix|refactor|docs|test|chore|perf|ci(scope): description`.
- One concern per PR. A PR touches only files its author owns (TEAM_STRUCTURE §2–3).
- A PR that needs a file owned by someone else is split: the owner makes that part.
- Never commit another agent's uncommitted work, `wolfee.db`, `.env`, exports, or secrets.
- PR description states: what changed, which contract sections it implements, test evidence (command and result), and anything not verified.

---

## 4. Definition of done

A change is done when all of these hold:

1. Tests for the new behaviour exist and pass, and the pre-existing suite still passes.
2. Financial results are reproduced by a test with hand-checked expected values.
3. Every user-owned resource is filtered by the authenticated `user_id`, with a test proving user A cannot read or change user B's data.
4. Input is validated by a schema at the boundary.
5. No fabricated or estimated value is returned as if it were market data (CLAUDE.md "Financial Integrity").
6. The relevant contract and `IMPLEMENTATION_STATUS.md` are updated in the same PR, or a request to Agent 1 is filed.
7. Code review and, for auth, input handling, queries or external calls, security review have been run.

---

## 5. Requesting a change outside your ownership

Add an entry to §9 of this document (through Agent 1) with:

```
ID:        REQ-<n>
From:      Agent <N>
To:        Agent <M>
Needs:     the exact change (endpoint, field, column, function signature, dependency)
Why:       what it unblocks
Blocking:  yes/no
Status:    open | accepted | done | rejected
```

Agent 1 answers contract questions and updates the contract first; implementation follows the contract, never the other way round.

---

## 6. Contract change process

1. Proposer describes the change and whether it is additive or breaking.
2. Agent 1 updates `API_CONTRACT.md` or `DATABASE_CONTRACT.md`, marks the item PROPOSED, and names the affected agents.
3. Additive changes proceed after Agent 1 approval. Breaking changes and any destructive database change wait for the user.
4. Order of work for a new endpoint: contract → Agent 3 pure function (if maths is involved) → Agent 2 schema, service, route → Agent 4 UI.
5. When implemented and merged, the item is re-labelled VERIFIED with the commit that introduced it.

Existing response shapes listed in API_CONTRACT §2 are frozen: fields may be added, never renamed or removed, without step 3.

---

## 7. Database change process

- Schema changes ship only as Alembic migrations written by Agent 2.
- Migrations are additive by default: new tables, new nullable columns, new indexes.
- Not allowed without explicit user approval: dropping or renaming tables or columns, narrowing types, deleting or rewriting rows, changing the meaning of an existing column.
- Every migration has a working `downgrade` and is run against a copy of real data before merge.
- **Blocker before the first new migration:** the Alembic state of the production database is unknown (DATABASE_CONTRACT §2.1). It must be inspected, read-only, before anything is migrated.

---

## 8. Integration cadence

- Agent 1 keeps `integration` green: after each merge, run the backend suite and a manual smoke test of the existing dashboard (market grid, stock modal with chart, watchlist add/remove, export, login/logout).
- "Preserve existing functionality" is checked against the smoke list in IMPLEMENTATION_STATUS §8 on every integration.
- Agents rebase on `integration` at the start of each work session.
- `IMPLEMENTATION_STATUS.md` is the single status board. Each agent reports status changes to Agent 1, who edits the file.

---

## 9. Open requests and decisions log

### Decisions waiting on the user

| ID | Decision | Detail in |
|----|----------|-----------|
| D1 | ~~Approve the proposed architecture, ownership and branch strategy~~ — **APPROVED by the user on 2026-11-11** (architecture and shared contracts). D2–D9 remain open | this document, TEAM_STRUCTURE |
| D2 | ~~Cost-basis method for realised P/L~~ — **DECIDED 2026-11-11: default weighted average; FIFO stays available as a request parameter** | DATABASE_CONTRACT §3.6, API_CONTRACT §5.2 |
| D3 | ~~Portfolio base currency and FX source~~ — **DECIDED 2026-11-11: base currency TRY; FX from the existing `exchange_rates` source; a foreign position without a rate is marked `missing_fx_rate` and the rest is still totalled** | DATABASE_CONTRACT §3.6, API_CONTRACT §5.2 |
| D4 | Whether to stop returning estimated RSI / MA20 / day range as real values, which changes what existing cards show | IMPLEMENTATION_STATUS §5 (R1) |
| D5 | Wording and guardrails of AI output (current prompts ask the model to speak as a financial adviser and recommend entries) | IMPLEMENTATION_STATUS §5 (R2) |
| D6 | Frontend direction: keep vanilla JS, or introduce a build step and TypeScript | IMPLEMENTATION_STATUS §6 |
| D7 | Location of the "Trader Skill" referenced in CLAUDE.md — not found in the repository or in the local skills directory | IMPLEMENTATION_STATUS §6 |
| D8 | ~~Inspect the production database~~ — **RESOLVED 2026-11-11: production moves to Fly.io and starts with an empty database; Railway data is disposable; no export or baseline stamp** | DEPLOYMENT.md |
| D9 | Whether `/api/refresh` and `/api/export/{period}` should require authentication | IMPLEMENTATION_STATUS §5 (R5) |

Decision status after the first branch review (2026-11-11). Every one of D2–D9 is still open:

| ID | Blocks merge of first branches? | Blocks next work? |
|----|--------------------------------|-------------------|
| D2 | Decided — REQ-13 | — |
| D3 | Decided — REQ-14, REQ-15 | — |
| D4 | No — `quant.signals` keeps the legacy proxies value for value | Yes: Phase 1 integrity fix |
| D5 | No — new AI layer already has guardrails and a disclaimer; legacy prompts unchanged | Yes: legacy `/api/ai/analyze` and `/api/insight` still use adviser wording |
| D6 | No — Agent 4 stayed with vanilla JS and added a `node --test` runner without dependencies | Yes: before building portfolio screens |
| D7 | No | Only Phase 5 |
| D8 | Resolved (empty Fly database) | — |
| D9 | No | Security hardening; unchanged by these branches |

Also approved by the user on 2026-11-11 (Agent 2's choices on `agent/backend` `6170686`):

- Quote freshness labels: every cached quote is `delayed` at best, and `stale` when older than one hour (`quote_service.QUOTE_DELAYED_MAX_AGE`). Nothing is labelled real-time.
- A cap of 10,000 transactions per portfolio (`ledger_adapter.MAX_TRANSACTIONS_PER_PORTFOLIO`); the next write is refused with a clear message.
- Summing realised P/L per currency and into the base currency stays in Agent 2's `analytics_service` for now. Moving it into `quant` is a later refactor, not a blocker.

Branch naming in practice is `agent/backend`, `agent/quant-ai` and `agent/frontend`, cut from `main` with no `integration` branch yet. §2 is updated when the user decides whether `integration` is still wanted.

### Requests between agents

REQ-1 to REQ-5 were raised in the agents' own reports. Agent 1 has not seen them, so they are not copied here. They will be added when relayed.

```
ID:        REQ-6
From:      Agent 4
To:        Agent 1
Needs:     remove the stale "legacy api.js" references from the docs. api.js, mock-data.js
           and yahoo-client.js are deleted on agent/frontend.
Why:       docs would describe callers that no longer exist
Blocking:  no
Status:    done in docs (API_CONTRACT §2.4, IMPLEMENTATION_STATUS §1.6). The /opportunities and
           /insight aliases stay — removing an endpoint is a contract change needing approval.

ID:        REQ-7
From:      Agent 1
To:        Agent 2 (call site), Agent 3 (seed already provided: quant.symbols.instrument_seed)
Needs:     a single, idempotent way to run sync_instruments(db, instrument_seed()) — e.g. a CLI
           command or start-up step after migrations — plus a test that a BUY of THYAO succeeds
           on a freshly migrated database
Why:       instruments is empty after migration, so every instrument transaction returns 422
Blocking:  yes, for the ledger being usable
Status:    open

ID:        REQ-8
From:      Agent 1
To:        Agent 2
Needs:     new tables must not appear in production through init_db() create_all before the
           migration path is approved (DATABASE_CONTRACT §5 P1). Proposal for Agent 1 review.
Why:       merging agent/backend would otherwise create tables in production on the next deploy
Blocking:  yes, for merging agent/backend to main
Status:    open

ID:        REQ-9
From:      Agent 1
To:        Agent 2
Needs:     run backend/tests and alembic upgrade/downgrade against a disposable PostgreSQL;
           report results (DATABASE_CONTRACT §5 P4)
Why:       every test so far ran on SQLite
Blocking:  yes, for production; no, for integration
Status:    open

ID:        REQ-10
From:      Agent 1
To:        Agent 2
Needs:     replace workers._enrich_stock_data (and main.py's import of it) with
           quant.signals.enrich_quote, in one dedicated PR, with a characterization test
           (TEAM_STRUCTURE H1)
Why:       there are still two copies of the enrichment logic
Blocking:  no
Status:    open — after agent/quant-ai is merged

ID:        REQ-11
From:      Agent 1
To:        Agents 2, 3 and 4
Needs:     make backend tests independent of the working directory. Run from backend/, three
           tests in test_performance_and_sources.py fail on main too, because they patch
           "backend.data_sources…"; run from the repo root, all pass. Agree one command:
           `python -m pytest backend/tests` from the repository root.
Why:       explains Agent 2's "3 pre-existing failures"
Blocking:  no
Status:    open (test file owner: Agent 2)

ID:        REQ-12
From:      Agent 1
To:        Agent 2
Needs:     backend/alembic/env.py must name the psycopg2 driver ("postgresql+psycopg2://");
           SQLAlchemy 2.1 maps a bare "postgresql://" to psycopg 3, which is not installed
Why:       every Postgres migration failed (DEPLOYMENT §2 F1)
Blocking:  yes, for any Postgres deploy
Status:    CLOSED 2026-11-11 — fixed by Agent 2 on agent/backend in 6170686. Not duplicated on
           integration; it arrives with the agent/backend merge (Step 2).
```

```
ID:        REQ-13
From:      Agent 1 (decision D2)
To:        Agent 2
Needs:     analytics_service.DEFAULT_COST_BASIS_METHOD = WEIGHTED_AVERAGE (currently FIFO);
           responses keep reporting cost_basis_method; tests updated
Why:       D2
Blocking:  yes, for the holdings/performance defaults
Status:    open

ID:        REQ-14
From:      Agent 1 (decision D3)
To:        Agent 3
Needs:     quant.valuation.value_positions: when some positions cannot be valued, still return
           total_market_value / total_cost_basis / total_unrealized_pnl summed over the valued
           positions, with is_complete=false and unvalued_symbols listing the rest; weights are
           computed against that partial total. No estimate for the missing positions.
           Update API_CONTRACT §6.1 note and tests.
Why:       D3 — "mark missing_fx_rate but still total the rest"
Blocking:  yes, for foreign positions in holdings
Status:    open

ID:        REQ-15
From:      Agent 1 (decision D3)
To:        Agent 2 (Agent 3 for any conversion helper)
Needs:     supply FxRate values to value_positions from the exchange_rates table: pair "USD/TRY"
           etc. → FxRate(base=<foreign>, quote="TRY", rate=<selling, as Decimal from its string
           form>, as_of=updated_at, source="exchange_rates"). Missing or zero rate → no FxRate
           (position reports missing_fx_rate). Accept only TRY as portfolio base currency for
           now (remove USD from SUPPORTED_BASE_CURRENCIES; no data exists yet). Remove the
           "no automatic rates until D3" note from analytics_service.
Why:       D3
Blocking:  yes, for foreign positions in holdings
Status:    open — choice of selling vs buying rate: selling, as shown in the existing UI;
           Agent 1 to confirm if the user wants buying or mid
```

```
ID:        REQ-16
From:      Agent 1 (approved by the user 2026-11-11)
To:        Agent 2
Needs:     the migration in DATABASE_CONTRACT §4.2 (stock_data, turkish_gold, exchange_rates,
           ai_insights, ix_auth_tokens_user_id, uq_instruments_provider_symbol) and, in the same
           change, init_db() create_all limited to SQLite; evidence: upgrade/downgrade/upgrade and
           a clean `alembic check` on PostgreSQL 16 and SQLite
Why:       migrations become the only way tables are created in production; closes REQ-8
Blocking:  yes, before the first Fly deploy
Status:    open
```

REQ-8 is superseded by REQ-16.

```
ID:        REQ-17
From:      Agent 1 (user decision 2026-11-11)
To:        Agent 3, then Agent 2
Needs:     a pure quant function that sums realised P/L per currency and into the base currency
           from RealizedLot values (None when any lot lacks a base figure); Agent 2 then replaces
           analytics_service._realized_by_currency / _realized_in_base with it. The response
           shape (API_CONTRACT §5.2.1) does not change.
Why:       all portfolio arithmetic belongs in quant; the service copy is temporary
Blocking:  no
Status:    open
```

REQ-7 (instrument seed): Agent 2 added `python -m services.instrument_service` in `agent/backend` `6170686`. `fly.toml` already calls it. It will be verified at the Step 2 merge before the request is closed.
