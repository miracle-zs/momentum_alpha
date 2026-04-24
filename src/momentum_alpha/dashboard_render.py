from __future__ import annotations

from .dashboard_assets import render_dashboard_head, render_dashboard_scripts, render_dashboard_styles
from .dashboard_render_charts import (
    _render_bar_chart_svg,
    _render_line_chart_svg,
    _render_pie_chart_svg,
    _render_timeline_svg,
)
from .dashboard_render_cosmic import (
    _render_cosmic_color_swatches,
    _render_cosmic_component_gallery,
    _render_cosmic_data_display,
    _render_cosmic_visual_elements,
    render_cosmic_identity_panel,
)
from .dashboard_render_live import (
    render_dashboard_execution_tab,
    render_dashboard_live_room,
    render_dashboard_overview_tab,
)
from .dashboard_render_panels import (
    _build_account_metrics_panel,
    _build_account_snapshot_panel,
    _build_execution_flow_panel,
    _build_live_account_risk_panel,
    _build_live_core_lines_panel,
    _build_overview_home_command,
    render_daily_review_panel,
)
from .dashboard_render_review import (
    render_daily_review_room,
    render_dashboard_performance_tab,
    render_dashboard_review_room,
    render_dashboard_review_tabs,
)
from .dashboard_render_shell import (
    DISPLAY_TIMEZONE,
    DISPLAY_TIMEZONE_NAME,
    DASHBOARD_ROOMS,
    LEGACY_DASHBOARD_TAB_TO_ROOM,
    REVIEW_VIEWS,
    _build_execution_mode,
    format_timestamp_for_display,
    normalize_dashboard_room,
    normalize_dashboard_tab,
    normalize_review_view,
    render_dashboard_body,
    render_dashboard_document,
    render_dashboard_html,
    render_dashboard_room_nav,
    render_dashboard_shell,
    render_dashboard_tab_bar,
)
from .dashboard_render_system import (
    render_dashboard_system_room,
    render_dashboard_system_tab,
)
from .dashboard_render_tables import (
    _render_round_trip_item,
    _render_round_trip_leg_rows,
    render_closed_trades_table,
    render_position_cards,
    render_stop_slippage_table,
    render_trade_history_table,
    render_trade_leg_count_aggregate_table,
    render_trade_leg_index_aggregate_table,
)
from .dashboard_render_utils import (
    _build_dashboard_room_href,
    _build_dashboard_tab_href,
    _daily_review_impact,
    _daily_review_win_rate,
    _format_datetime_compact,
    _format_datetime_review,
    _format_decimal_metric,
    _format_duration_seconds,
    _format_metric,
    _format_pct_value,
    _format_price,
    _format_quantity,
    _format_round_trip_exit_reason,
    _format_round_trip_id_label,
    _format_time_only,
    _format_time_short,
)
