import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardViewModelTests(unittest.TestCase):
    def test_dashboard_view_model_module_exports_snapshot_calculators(self) -> None:
        from momentum_alpha import dashboard_view_model

        for name in (
            "build_trader_summary_metrics",
            "build_position_details",
            "_compute_account_range_stats",
            "_filter_rows_for_range",
        ):
            self.assertTrue(callable(getattr(dashboard_view_model, name)))


if __name__ == "__main__":
    unittest.main()
