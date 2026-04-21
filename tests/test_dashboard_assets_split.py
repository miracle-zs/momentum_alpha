from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardAssetsSplitTests(unittest.TestCase):
    def test_dashboard_assets_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import dashboard_assets_head, dashboard_assets_scripts, dashboard_assets_styles

        self.assertTrue(callable(dashboard_assets_styles.render_dashboard_styles))
        self.assertTrue(callable(dashboard_assets_head.render_dashboard_head))
        self.assertTrue(callable(dashboard_assets_scripts.render_dashboard_scripts))


if __name__ == "__main__":
    unittest.main()
