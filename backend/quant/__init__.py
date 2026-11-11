"""Deterministic financial calculations for Wolfee Analytics.

Rules for everything in this package (API_CONTRACT §6):

* pure functions: no database, no HTTP, no LLM, no clock, no randomness;
* money and quantities are ``Decimal`` (floats are rejected), results are
  immutable dataclasses from :mod:`quant.types`;
* the same input always gives the same output;
* a value that cannot be computed is ``None`` (with a reason where useful),
  never an estimate.

The one exception is :mod:`quant.signals`, which reproduces the legacy
float-based display enrichment so the three existing copies can be replaced by
one. It is not used for portfolio arithmetic.
"""
