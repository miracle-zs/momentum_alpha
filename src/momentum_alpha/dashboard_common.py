from __future__ import annotations

from datetime import timedelta


ACCOUNT_RANGE_WINDOWS = {
    "1H": timedelta(hours=1),
    "1D": timedelta(days=1),
    "1W": timedelta(days=7),
    "1M": timedelta(days=30),
    "1Y": timedelta(days=365),
}


def normalize_account_range(range_key: str | None) -> str:
    normalized = str(range_key or "1D").upper()
    return normalized if normalized in {*ACCOUNT_RANGE_WINDOWS, "ALL"} else "1D"


def _parse_numeric(value: object | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_margin_usage_pct(*, available_balance: object | None, equity: object | None) -> float | None:
    available = _parse_numeric(available_balance)
    equity_value = _parse_numeric(equity)
    if available is None or equity_value in (None, 0):
        return None
    return (1 - (available / equity_value)) * 100


def build_strategy_config(
    *,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
) -> dict:
    return {
        "stop_budget_usdt": stop_budget_usdt or "n/a",
        "entry_window": f"{entry_start_hour_utc:02d}:00-{entry_end_hour_utc:02d}:00 UTC",
        "testnet": testnet,
        "submit_orders": submit_orders,
    }
