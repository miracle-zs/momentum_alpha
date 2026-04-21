from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardDataTests(unittest.TestCase):
    def test_dashboard_data_module_exports_snapshot_and_payload_helpers(self) -> None:
        from momentum_alpha import dashboard_data

        self.assertTrue(callable(dashboard_data.load_dashboard_snapshot))
        self.assertTrue(callable(dashboard_data.build_dashboard_summary_payload))
        self.assertTrue(callable(dashboard_data.build_dashboard_timeseries_payload))
        self.assertTrue(callable(dashboard_data.build_dashboard_tables_payload))
        self.assertTrue(callable(dashboard_data.build_dashboard_response_json))


if __name__ == "__main__":
    unittest.main()
