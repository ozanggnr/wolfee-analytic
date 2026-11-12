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

## Next
- [ ] 4. REQ-17 — realised P/L per currency and in TRY
- [ ] 5. D4 and D5 options for the user (no implementation)
- [ ] 6. Full suite on Python 3.11.9, final report with signatures for Agent 2

## Notes for whoever resumes
- `allocation_by` still returns None for an incomplete valuation (a group with unvalued holdings would show too small a share). Not asked for in REQ-14; raise with Agent 1 if partial allocation is wanted.
- `ai.facts.portfolio_facts` words every total as partial when `is_complete` is false.
- The Python 3.13 `.venv` stopped importing SQLAlchemy's compiled module on 2026-11-12 ("Application Control policy has blocked this file"). Use `.venv311`.
