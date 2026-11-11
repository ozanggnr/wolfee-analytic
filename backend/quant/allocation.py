"""Portfolio allocation and concentration, computed from a valuation."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Mapping

from quant._math import ONE, ZERO, divide, fixed_context, to_decimal, weights_summing_to_one
from quant.types import AllocationSlice, Concentration, PortfolioValuation

UNCLASSIFIED = "UNCLASSIFIED"


@fixed_context()
def allocation_by(
    valuation: PortfolioValuation, group_of: Mapping[str, str]
) -> tuple[AllocationSlice, ...] | None:
    """Weights grouped by ``group_of[symbol]`` (market, currency, asset class...).

    Largest group first. Returns None when the valuation is incomplete, because
    weights of a partly valued portfolio would be wrong, and an empty tuple when
    there is nothing of value to allocate.
    """
    if not valuation.is_complete:
        return None

    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for position in valuation.positions:
        totals[group_of.get(position.symbol, UNCLASSIFIED)] += position.market_value_base

    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    weights = weights_summing_to_one([amount for _, amount in ordered])
    if weights is None:
        return ()
    return tuple(
        AllocationSlice(group=group, market_value_base=amount, weight=weight)
        for (group, amount), weight in zip(ordered, weights)
    )


@fixed_context()
def concentration(weights: Mapping[str, Decimal]) -> Concentration | None:
    """Herfindahl–Hirschman index of position weights (fractions that sum to 1).

    ``hhi`` runs from 1/n (equal weights) to 1 (a single holding);
    ``effective_holdings`` is its inverse.
    """
    if not weights:
        return None
    checked = {symbol: to_decimal(weight, "weight") for symbol, weight in weights.items()}
    hhi = sum((weight * weight for weight in checked.values()), ZERO)
    if hhi <= ZERO:
        return None
    largest_symbol, largest_weight = min(checked.items(), key=lambda item: (-item[1], item[0]))
    return Concentration(
        hhi=hhi,
        largest_symbol=largest_symbol,
        largest_weight=largest_weight,
        effective_holdings=divide(ONE, hhi),
    )
