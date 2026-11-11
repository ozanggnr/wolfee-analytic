"""AI explanations of figures that deterministic code has already computed.

The model never produces a number, never sees a transaction it could change
and has no tools: it receives formatted facts and returns prose. Every result
carries who generated it, when, the age of the data behind it and a
disclaimer (API_CONTRACT §5.4). If the model is unavailable, fails, or writes
anything the guardrails reject, a deterministic template is returned instead.
"""
