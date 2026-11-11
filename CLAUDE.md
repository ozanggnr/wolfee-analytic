# Wolfee Analytics – Project Instructions

## Project Overview

Wolfee Analytics is an existing financial analytics platform being evolved into a multi-user investment intelligence application.

Existing functionality includes:
- BIST 100 and international asset coverage
- Stock analysis
- RSI, SMA and volatility indicators
- Market data integrations
- Caching
- AI-generated market insights

Preserve existing functionality. Prefer extending existing modules over rewriting them.

## Engineering Principles

- Inspect existing code before modifying it.
- Follow the established project architecture unless a change is justified.
- Use clear separation of concerns.
- Keep business logic out of API route handlers.
- Use typed interfaces and validation.
- Write tests for new functionality.
- Never introduce destructive database changes without approval.
- Document important architectural decisions.

## Multi-Agent Collaboration

This project uses four Claude Code agents:

1. Agent 1: Architect and Integration Lead
2. Agent 2: Backend Engineer
3. Agent 3: Quantitative Finance and AI Engineer
4. Agent 4: Frontend Engineer

Read the documents in `docs/agents/` before starting assigned work.

Respect the file ownership defined in `TEAM_STRUCTURE.md`.

Do not independently modify another agent's owned files.

Do not change shared API or database contracts without coordination with Agent 1.

## Financial Integrity

- Financial calculations must be deterministic.
- Never use an LLM for portfolio arithmetic or risk calculations.
- Transactions are the source of truth for portfolio holdings.
- Preserve transaction history and auditability.
- Distinguish realized and unrealized profit/loss.
- Account for fees, dividends and currency conversion where supported.
- Clearly identify delayed, real-time and end-of-day market data.
- Never fabricate prices, financial metrics or financial news.

## AI Requirements

AI may interpret and explain verified financial information.

AI must not:
- Invent missing financial information.
- Directly modify portfolio transactions.
- Execute trades autonomously.
- Present generated analysis as guaranteed financial advice.

## Trader Skill

Use Trader Skill as a reference for financial workflows.

Inspect relevant SKILL.md files and scripts before adapting them.

Adapt US-specific functionality carefully. Do not assume SEC, House Clerk or NYSE data provides equivalent BIST functionality.

Paper trading is the default. No autonomous live trading.

## Security

- Enforce user-level data isolation.
- Validate all user input.
- Never expose API keys or secrets.
- Keep credentials in environment variables or deployment secrets.
- Protect sensitive financial information.
- Add authorization checks to user-owned resources.

## Testing

Use ECC engineering workflows where available:
- Planning
- TDD
- Security review
- Code review

Run relevant tests after every implementation.

Do not claim a feature is complete without verification.

## Git Rules

- Work on the assigned branch or worktree.
- Do not commit another agent's changes.
- Do not merge directly into main.
- Use descriptive commit messages.
- Keep changes focused and reviewable.

## Documentation

Keep these documents updated:

- `docs/agents/TEAM_STRUCTURE.md`
- `docs/agents/COORDINATION.md`
- `docs/agents/API_CONTRACT.md`
- `docs/agents/DATABASE_CONTRACT.md`
- `docs/agents/IMPLEMENTATION_STATUS.md`

When a contract changes, update the relevant document and communicate the change to affected agents.

## Priority

Preserve existing Wolfee functionality first.

Build the foundation before advanced features.

Prefer a modular monolith over unnecessary microservices.

Do not begin large-scale implementation without an approved plan.