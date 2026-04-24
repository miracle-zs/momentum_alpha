from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardRenderSplitTests(unittest.TestCase):
    def test_dashboard_render_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import dashboard_render_panels, dashboard_render_shell, dashboard_render_tables, dashboard_render_utils

        self.assertTrue(callable(dashboard_render_utils.normalize_dashboard_room))
        self.assertTrue(callable(dashboard_render_tables.render_trade_history_table))
        self.assertTrue(callable(dashboard_render_panels.render_cosmic_identity_panel))
        self.assertTrue(callable(dashboard_render_shell.render_dashboard_html))

    def test_dashboard_render_stack_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import (
            dashboard_render_charts,
            dashboard_render_cosmic,
            dashboard_render_live,
            dashboard_render_review,
            dashboard_render_system,
            dashboard_render_tables_aggregates,
            dashboard_render_tables_positions,
            dashboard_render_tables_trades,
        )

        self.assertTrue(callable(dashboard_render_live.render_dashboard_live_room))
        self.assertTrue(callable(dashboard_render_review.render_dashboard_review_room))
        self.assertTrue(callable(dashboard_render_system.render_dashboard_system_room))
        self.assertTrue(callable(dashboard_render_charts._render_line_chart_svg))
        self.assertTrue(callable(dashboard_render_cosmic.render_cosmic_identity_panel))
        self.assertTrue(callable(dashboard_render_tables_trades.render_trade_history_table))
        self.assertTrue(callable(dashboard_render_tables_aggregates.render_trade_leg_count_aggregate_table))
        self.assertTrue(callable(dashboard_render_tables_positions.render_position_cards))

    def test_dashboard_panel_stack_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import (
            dashboard_render_panels_account,
            dashboard_render_panels_execution,
            dashboard_render_panels_overview,
            dashboard_render_panels_review,
        )

        self.assertTrue(callable(dashboard_render_panels_account._build_account_metrics_panel))
        self.assertTrue(callable(dashboard_render_panels_account._build_live_core_lines_panel))
        self.assertTrue(callable(dashboard_render_panels_overview._build_overview_home_command))
        self.assertTrue(callable(dashboard_render_panels_execution._build_execution_flow_panel))
        self.assertTrue(callable(dashboard_render_panels_review.render_daily_review_panel))


if __name__ == "__main__":
    unittest.main()
