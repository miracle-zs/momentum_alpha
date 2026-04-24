from __future__ import annotations

from .dashboard_render_tables_aggregates import (
    render_stop_slippage_table,
    render_trade_leg_count_aggregate_table,
    render_trade_leg_index_aggregate_table,
)
from .dashboard_render_tables_positions import render_position_cards
from .dashboard_render_tables_trades import (
    _render_round_trip_item,
    _render_round_trip_leg_rows,
    render_closed_trades_table,
    render_trade_history_table,
)
