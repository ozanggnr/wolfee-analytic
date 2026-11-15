"""Values exactly as a provider supplied them (REQ-30, user decision 2026-11-14).

A missing, zero, negative or non-finite open / previous close is ``None``: it is
never replaced by 0.0, by the current price, or by anything derived from the
day's change.
"""
from __future__ import annotations

import math
from typing import Any, Optional


def provided_price(value: Any) -> Optional[float]:
    """A positive, finite price as float; None when the provider gave none."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None
