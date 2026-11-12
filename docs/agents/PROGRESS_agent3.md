# Agent 3 progress — current task

Task (user, 2026-11-12): in `../Wolfee-quant-ai` on `agent/quant-ai`, stay inside `backend/quant/`, `backend/ai/` and their tests. Commit after each item; **never merge or push**.

Resume: `git -C ../Wolfee-quant-ai status`, read this file, continue with "Next".

Test command (repo root, Python 3.11.9): `.venv311/Scripts/python -m pytest backend/tests -q -p no:cacheprovider`
`.venv311` is local only (listed in `.git/info/exclude`), built with `uv venv --python 3.11.9` from `backend/requirements.txt`.

## Done
- [x] 0. Start state: HEAD `19d0501`, working tree clean
- [x] 1. `git merge --ff-only integration` → `48ef971`
- [x] 2. Read REQ-14 and REQ-17
- [x] 3. REQ-14 — partial totals in `value_positions`, new `convert_amounts` (214 tests pass on 3.11.9)
- [x] 4. REQ-17 — `realized_summary` and `sum_realized`; weighted average is the default `method` of `build_positions`, `realized_pnl` and `realized_summary`
- [x] 5. D4 and D5 put to the user as options with a recommendation (in the final report; nothing implemented)
- [x] 6. Full suite on Python 3.11.9 from the repo root: 224 passed (26 existing + 198 quant/AI), at `ba52666`

## In progress
- Nothing. **Waiting for the user** on D4 and D5, and for Agent 1 to record the new signatures in API_CONTRACT §6.1 and close REQ-14 / REQ-17 (Agent 3 half).

## Next (only after the user decides)
- D4: recommended — return `null` for RSI / MA20 / day range when there is no real history, and compute real values with `quant.indicators` once price history exists
- D5: recommended — move `/api/insight` and `/api/ai/analyze` onto `ai.explain` (facts in, guardrails, disclaimer)

## For Agent 2 (new or changed since `19d0501`)
- `quant.valuation.value_positions(positions, quotes, fx, base_currency)` — same signature; totals and weights now cover the valued positions when `is_complete` is false
- `quant.valuation.convert_amounts(amounts, fx, base_currency="TRY") -> ConvertedAmounts`
- `quant.positions.realized_summary(transactions, method=WEIGHTED_AVERAGE, base_currency="TRY") -> RealizedSummary`
- `quant.positions.sum_realized(lots, base_currency="TRY") -> RealizedSummary`
- `build_positions` / `realized_pnl`: `method` now defaults to weighted average
- `quant.types.DEFAULT_COST_BASIS_METHOD`, `DEFAULT_BASE_CURRENCY`

## Notes for whoever resumes
- `allocation_by` still returns None for an incomplete valuation (a group with unvalued holdings would show too small a share). Not asked for in REQ-14; raise with Agent 1 if partial allocation is wanted.
- `ai.facts.portfolio_facts` words every total as partial when `is_complete` is false.
- The Python 3.13 `.venv` stopped importing SQLAlchemy's compiled module on 2026-11-12 ("Application Control policy has blocked this file"). Use `.venv311`.
