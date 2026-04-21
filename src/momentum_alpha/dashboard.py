from __future__ import annotations

from pathlib import Path

from . import dashboard_common as _dashboard_common
from . import dashboard_data as _dashboard_data
from . import dashboard_render as _dashboard_render
from .dashboard_common import (
    ACCOUNT_RANGE_WINDOWS,
    _compute_margin_usage_pct,
    _parse_numeric,
    build_strategy_config,
    normalize_account_range,
)
from .dashboard_data import (
    build_dashboard_response_json,
    build_dashboard_summary_payload,
    build_dashboard_tables_payload,
    build_dashboard_timeseries_payload,
    build_trade_leg_count_aggregates,
    build_trade_leg_index_aggregates,
    load_dashboard_snapshot,
)
from .dashboard_render import (
    DASHBOARD_ROOMS,
    DISPLAY_TIMEZONE,
    DISPLAY_TIMEZONE_NAME,
    LEGACY_DASHBOARD_TAB_TO_ROOM,
    REVIEW_VIEWS,
    build_position_details,
    build_trader_summary_metrics,
    format_timestamp_for_display,
    normalize_dashboard_room,
    normalize_dashboard_tab,
    normalize_review_view,
    render_closed_trades_table,
    render_cosmic_identity_panel,
    render_dashboard_body,
    render_dashboard_document,
    render_dashboard_head,
    render_dashboard_html,
    render_dashboard_live_room,
    render_dashboard_overview_tab,
    render_dashboard_performance_tab,
    render_dashboard_review_room,
    render_dashboard_room_nav,
    render_dashboard_scripts,
    render_dashboard_shell,
    render_dashboard_styles,
    render_dashboard_system_room,
    render_dashboard_system_tab,
    render_dashboard_tab_bar,
    render_position_cards,
    render_stop_slippage_table,
    render_trade_history_table,
    render_trade_leg_count_aggregate_table,
    render_trade_leg_index_aggregate_table,
)


def __getattr__(name: str):
    for module in (_dashboard_render, _dashboard_data, _dashboard_common):
        try:
            return getattr(module, name)
        except AttributeError:
            continue
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def run_dashboard_server(
    *,
    host: str,
    port: int,
    poll_log_file: Path | None = None,
    user_stream_log_file: Path | None = None,
    runtime_db_file: Path,
    now_provider=None,
    server_factory=None,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
) -> int:
    from momentum_alpha.dashboard_server import run_dashboard_server as _run_dashboard_server

    return _run_dashboard_server(
        host=host,
        port=port,
        poll_log_file=poll_log_file,
        user_stream_log_file=user_stream_log_file,
        runtime_db_file=runtime_db_file,
        now_provider=now_provider,
        server_factory=server_factory,
        stop_budget_usdt=stop_budget_usdt,
        entry_start_hour_utc=entry_start_hour_utc,
        entry_end_hour_utc=entry_end_hour_utc,
        testnet=testnet,
        submit_orders=submit_orders,
    )
