from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardCommonTests(unittest.TestCase):
    def test_dashboard_common_module_exports_shared_dashboard_helpers(self) -> None:
        from momentum_alpha import dashboard_common

        self.assertTrue(callable(dashboard_common.normalize_account_range))
        self.assertTrue(callable(dashboard_common.build_strategy_config))
        self.assertTrue(callable(dashboard_common._parse_numeric))
        self.assertTrue(callable(dashboard_common._compute_margin_usage_pct))


if __name__ == "__main__":
    unittest.main()
