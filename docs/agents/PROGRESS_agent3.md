# Agent 3 progress — current task

Written by Agent 1 on 2026-11-14 from Agent 3's commit reports (`7683167` … `def3511`) and the user's relay. Accepted by the user as Agent 3's record.

Task: in `../Wolfee-quant-ai` on `agent/quant-ai`, stay inside `backend/quant/`, `backend/ai/` and their tests (plus `analysis.py` / `ai_service.py` where a REQ names them). Commit after each item; **never merge or push**.

Resume: `git -C ../Wolfee-quant-ai status` (on Windows), read this file, continue with "Next".

**Tests run in WSL only** (Windows Smart App Control blocks the Windows venvs). Exact commands are in `docs/agents/TESTING.md` §2. The old `.venv311` / `.venv` on Windows are no longer evidence.

## Done
- [x] REQ-14, REQ-17 — partial totals, `convert_amounts`, `realized_summary` / `sum_realized`, weighted-average default (`8d2b13c`, `ba52666`; merged into `integration` at `d489b68`)
- [x] REQ-24 (D4, quant side) — `7683167`: `quant.indicators.daily_indicators(Sequence[DailyClose])` gives RSI 14 (Wilder), SMA 20 and 20-day annualised volatility, or None when the history is too short (15 / 20 / 21 closes). `enrich_quote(…, history)` estimates nothing: without history rsi, ma_20, volatility, volatility_pct, the day range and every label built on them are None, and estimates present in the input are dropped. New `indicators_as_of`, `indicator_method`
- [x] Volatility bands — `classify_volatility`: LOW < 25, MEDIUM 25 to < 50, HIGH ≥ 50 (annualised %)
- [x] REQ-25 (D5) — `fc9640a`: `ai.insights` (`market_insight[_response]`, `stock_analysis[_response]`), `ai.facts.market_facts` / `stock_facts`, `explain_market` / `explain_stock`, `response_fields`. No model call without market data. Indicators reach the model only with a real `indicators_as_of` and when not in `estimated_fields`. Adviser prompts, the `PURCHASABLE`-style signal and the old fallbacks are removed from `ai_service`
- [x] `open` / `previous_close` None when the provider gives none — `724b2b2` (in `analysis.analyze_stock`)
- [x] Descriptive card labels — `38e14d7`: `indicator_label(rsi, price, ma_20)` (RSI below 30 / above 70 / between 30 and 70; Near (2 %) / Above / Below 20-day average); legacy mode states the day's move (`Up 1.0% today`). Excel RSI status: Not available / Oversold / Overbought / Neutral
- [x] `def3511`: tests pinning the guarded entry points against a row whose indicators, labels and optional quote fields are all None (Agent 2's null-indicator report)
- [x] Verification: Agent 3's own runs on Windows were partial (Smart App Control blocked a pandas DLL: 241–242 pandas-free tests). **Full suite in WSL at `def3511`: 281 passed** (user relay); re-run by Agent 1 on `integration` after the merge: 281 passed
- [x] Merged into `integration` at **`da57548`** (2026-11-14, Step 3c)

## In progress
- Nothing.

## Next
- Remove `legacy_estimates` and `estimated_fields` from `analysis.analyze_stock` once Agent 2's `bb00a11` (consumers accept null) and the history wiring (REQ-26 / REQ-10) are merged. Coordinate with Agent 1.

## For Agent 2 (new since `a7bb094`)
- `quant.types.DailyClose(date, close: Decimal)`, `DailyIndicators(as_of, observations, rsi_14, sma_20, volatility_pct)`
- `quant.indicators.daily_indicators(history) -> DailyIndicators`; constants `RSI_PERIOD`, `SMA_WINDOW`, `VOLATILITY_WINDOW`, `INDICATOR_METHOD`
- `quant.signals.enrich_quote(data, market_type, currency, history=None)`: the replacement for `workers._enrich_stock_data` (REQ-10)
- `analysis.analyze_stock(symbol, …, history=None, legacy_estimates=True)`
- `ai.insights.market_insight_response(market_data, *, now, inputs_as_of=None, generate=…)` and `stock_analysis_response(symbol, stock_data, *, now, …)`: the route bodies for REQ-28. Blocking network I/O, so call them through `asyncio.to_thread`

## Notes for whoever resumes
- `allocation_by` still returns None for an incomplete valuation (unchanged; raise with Agent 1 if partial allocation is wanted).
- `is_favorable` is None without a real RSI although it only uses `change_pct` (D4: labels follow their inputs). Today `/api/opportunities` still reads the workers' legacy `is_favorable`; once the workers use `enrich_quote` (REQ-10), it is empty for any instrument without history.
