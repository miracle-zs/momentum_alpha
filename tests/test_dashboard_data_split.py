from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardDataSplitTests(unittest.TestCase):
    def test_dashboard_data_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import dashboard_data_common, dashboard_data_loader, dashboard_data_payloads

        self.assertTrue(callable(dashboard_data_common._account_flow_since))
        self.assertTrue(callable(dashboard_data_common._select_latest_timestamp))
        self.assertTrue(callable(dashboard_data_common._normalize_events))
        self.assertTrue(callable(dashboard_data_common._build_source_counts))
        self.assertTrue(callable(dashboard_data_common._build_leader_history))
        self.assertTrue(callable(dashboard_data_common._build_pulse_points))
        self.assertTrue(callable(dashboard_data_common._runtime_summary_from_sources))
        self.assertTrue(callable(dashboard_data_payloads.build_dashboard_summary_payload))
        self.assertTrue(callable(dashboard_data_payloads.build_dashboard_timeseries_payload))
        self.assertTrue(callable(dashboard_data_payloads.build_trade_leg_count_aggregates))
        self.assertTrue(callable(dashboard_data_payloads.build_trade_leg_index_aggregates))
        self.assertTrue(callable(dashboard_data_payloads.build_dashboard_tables_payload))
        self.assertTrue(callable(dashboard_data_payloads.build_dashboard_response_json))
        self.assertTrue(callable(dashboard_data_loader.load_dashboard_snapshot))


if __name__ == "__main__":
    unittest.main()
