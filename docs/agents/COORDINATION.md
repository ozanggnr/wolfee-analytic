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
| D2 | Cost-basis method for realised P/L (FIFO or weighted average) | DATABASE_CONTRACT §3.6 |
| D3 | Portfolio base currency and the FX source used for conversion | DATABASE_CONTRACT §3.6 |
| D4 | Whether to stop returning estimated RSI / MA20 / day range as real values, which changes what existing cards show | IMPLEMENTATION_STATUS §5 (R1) |
| D5 | Wording and guardrails of AI output (current prompts ask the model to speak as a financial adviser and recommend entries) | IMPLEMENTATION_STATUS §5 (R2) |
| D6 | Frontend direction: keep vanilla JS, or introduce a build step and TypeScript | IMPLEMENTATION_STATUS §6 |
| D7 | Location of the "Trader Skill" referenced in CLAUDE.md — not found in the repository or in the local skills directory | IMPLEMENTATION_STATUS §6 |
| D8 | Permission to inspect the production database read-only to establish Alembic state | DATABASE_CONTRACT §2.1 |
| D9 | Whether `/api/refresh` and `/api/export/{period}` should require authentication | IMPLEMENTATION_STATUS §5 (R5) |

### Requests between agents

None yet.
