from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlencode

from .dashboard_common import _parse_numeric, normalize_account_range
from .dashboard_view_model import _parse_decimal


DISPLAY_TIMEZONE_NAME = "Asia/Shanghai"
DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
DASHBOARD_ROOMS = ("live", "review", "system")
LEGACY_DASHBOARD_TAB_TO_ROOM = {
    "overview": "live",
    "execution": "live",
    "performance": "review",
    "system": "system",
}
REVIEW_VIEWS = ("overview", "daily")


def normalize_dashboard_room(value: str | None) -> str:
    room = (value or "").strip().lower()
    if room in DASHBOARD_ROOMS:
        return room
    return LEGACY_DASHBOARD_TAB_TO_ROOM.get(room, "live")


def normalize_review_view(value: str | None) -> str:
    view = (value or "").strip().lower()
    return view if view in REVIEW_VIEWS else "overview"


def _build_dashboard_room_href(*, room: str, account_range_key: str, review_view: str | None = None) -> str:
    query = {
        "room": normalize_dashboard_room(room),
        "range": normalize_account_range(account_range_key),
    }
    if normalize_dashboard_room(room) == "review":
        query["review_view"] = normalize_review_view(review_view)
    return f"?{urlencode(query)}"


def _build_dashboard_tab_href(*, tab: str, account_range_key: str) -> str:
    return _build_dashboard_room_href(room=normalize_dashboard_room(tab), account_range_key=account_range_key)


def format_timestamp_for_display(timestamp: str | None) -> str:
    if not timestamp:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return str(timestamp)
    return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def _format_time_only(timestamp: str | None) -> str:
    if not timestamp:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(timestamp)
        return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%H:%M:%S")
    except ValueError:
        return str(timestamp)[:8] if len(str(timestamp)) >= 8 else str(timestamp)


def _format_time_short(timestamp: str | None) -> str:
    if not timestamp:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(timestamp)
        return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%H:%M")
    except ValueError:
        return str(timestamp)[:5] if len(str(timestamp)) >= 5 else str(timestamp)


def _format_datetime_compact(timestamp: str | None) -> str:
    if not timestamp:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(timestamp)
        return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(timestamp)


def _format_datetime_review(timestamp: str | None) -> str:
    if not timestamp:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return str(timestamp)
    return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%m-%d %H:%M")


def _format_round_trip_exit_reason(exit_reason: str | None) -> str:
    if not exit_reason:
        return "n/a"
    normalized = str(exit_reason).strip().lower()
    labels = {
        "sell": "SELL",
        "stop_loss": "STOP LOSS",
        "signal_flip": "SIGNAL FLIP",
    }
    return labels.get(normalized, normalized.replace("_", " ").upper())


def _format_round_trip_id_label(round_trip_id: str | None) -> str:
    if not round_trip_id:
        return "#-"
    text = str(round_trip_id)
    if ":" in text:
        suffix = text.rsplit(":", 1)[-1]
        if suffix:
            return f"#{suffix}"
    return text


def _format_duration_seconds(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    total_seconds = int(round(float(value)))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {seconds:02d}s"


def _format_metric(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    numeric_value = float(value)
    if signed and numeric_value == 0:
        return "0.00"
    if signed:
        return f"{numeric_value:+,.2f}"
    return f"{numeric_value:,.2f}"


def _format_price(value: object | None) -> str:
    numeric = _parse_numeric(value)
    if numeric is None:
        return "n/a"
    magnitude = abs(numeric)
    if magnitude >= 100:
        return f"{numeric:,.2f}"
    if magnitude >= 1:
        return f"{numeric:,.4f}"
    return f"{numeric:,.6f}"


def _format_quantity(value: object | None) -> str:
    numeric = _parse_numeric(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:,.4f}".rstrip("0").rstrip(".")


def _format_pct_value(value: object | None, *, signed: bool = False) -> str:
    numeric = _parse_numeric(value)
    if numeric is None:
        return "n/a"
    if signed and numeric != 0:
        return f"{numeric:+,.2f}%"
    return f"{numeric:,.2f}%"


def _format_decimal_metric(value: Decimal | object | None, *, signed: bool = False, suffix: str = "") -> str:
    decimal_value = value if isinstance(value, Decimal) else _parse_decimal(value)
    if decimal_value is None:
        return "n/a"
    if signed and decimal_value == 0:
        return f"0.00{suffix}"
    prefix = "+" if signed and decimal_value > 0 else ""
    return f"{prefix}{decimal_value:,.2f}{suffix}"


def _daily_review_impact(*, actual: object | None, replay: object | None) -> Decimal | None:
    actual_value = _parse_decimal(actual)
    replay_value = _parse_decimal(replay)
    if actual_value is None or replay_value is None:
        return None
    return actual_value - replay_value


def _daily_review_win_rate(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    wins = sum(1 for value in values if value > 0)
    return (Decimal(wins) / Decimal(len(values))) * Decimal("100")

