"""Maps stored ledger rows to quant.types.Transaction and checks that a ledger replays.

Positions are keyed by `symbol@exchange`, the identity the database keeps unique,
so two instruments can never be merged into one position (API_CONTRACT §6.1),
even if they share a display or provider symbol.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from models import Instrument, Transaction as LedgerRow
from quant.positions import build_positions
from quant.types import CostBasisMethod, LedgerError, Transaction, TransactionType

# Replay is linear and CPU-bound; this bounds the work done per request.
MAX_TRANSACTIONS_PER_PORTFOLIO = 10_000


@dataclass(frozen=True)
class Ledger:
    transactions: tuple[Transaction, ...]
    instruments: Mapping[str, Instrument]  # position key -> instrument


def position_key(instrument: Instrument) -> str:
    return f"{instrument.symbol}@{instrument.exchange}"


def to_quant(row: LedgerRow, *, id_override: Optional[int] = None) -> Transaction:
    instrument = row.instrument
    return Transaction(
        id=id_override if id_override is not None else row.id,
        type=TransactionType(row.type),
        trade_date=row.trade_date,
        currency=row.currency.strip(),
        quantity=row.quantity,
        price=row.price,
        fee=row.fee,
        symbol=position_key(instrument) if instrument is not None else None,
        fx_rate_to_base=row.fx_rate_to_base,
        voids_transaction_id=row.voids_transaction_id,
    )


def to_ledger(rows: Sequence[LedgerRow]) -> Ledger:
    instruments = {position_key(r.instrument): r.instrument for r in rows if r.instrument is not None}
    return Ledger(transactions=tuple(to_quant(row) for row in rows), instruments=instruments)


async def first_replay_error(transactions: Sequence[Transaction]) -> Optional[str]:
    """None if the ledger replays (no overselling, consistent currencies), else the reason."""
    try:
        await asyncio.to_thread(build_positions, transactions, CostBasisMethod.FIFO)
    except LedgerError as exc:
        return str(exc)
    return None
