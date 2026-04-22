from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class UserStreamEvent:
    event_type: str
    payload: dict
    symbol: str | None = None
    order_status: str | None = None
    execution_type: str | None = None
    side: str | None = None
    average_price: Decimal | None = None
    filled_quantity: Decimal | None = None
    last_filled_price: Decimal | None = None
    last_filled_quantity: Decimal | None = None
    realized_pnl: Decimal | None = None
    commission: Decimal | None = None
    commission_asset: str | None = None
    stop_price: Decimal | None = None
    original_order_type: str | None = None
    event_time: datetime | None = None
    order_id: int | None = None
    trade_id: int | None = None
    client_order_id: str | None = None
    account_update_reason: str | None = None
    # Algo order fields
    algo_id: int | None = None
    client_algo_id: str | None = None
    algo_status: str | None = None
    trigger_price: Decimal | None = None
