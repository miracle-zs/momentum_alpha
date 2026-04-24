import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardViewModelSplitTests(unittest.TestCase):
    def test_view_model_stack_exposes_focused_modules(self) -> None:
        from momentum_alpha import (
            dashboard_view_model_common,
            dashboard_view_model_metrics,
            dashboard_view_model_positions,
            dashboard_view_model_range,
        )

        self.assertTrue(callable(dashboard_view_model_common._parse_decimal))
        self.assertTrue(callable(dashboard_view_model_common._object_field))
        self.assertTrue(callable(dashboard_view_model_range._filter_rows_for_range))
        self.assertTrue(callable(dashboard_view_model_range._filter_rows_for_display_day))
        self.assertTrue(callable(dashboard_view_model_range._compute_account_range_stats))
        self.assertTrue(callable(dashboard_view_model_metrics.build_trader_summary_metrics))
        self.assertTrue(callable(dashboard_view_model_metrics._current_streak_from_round_trips))
        self.assertTrue(callable(dashboard_view_model_positions.build_position_details))


if __name__ == "__main__":
    unittest.main()
