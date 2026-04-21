import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardAssetsTests(unittest.TestCase):
    def test_dashboard_assets_module_exports_styles_scripts_and_head(self) -> None:
        from momentum_alpha import dashboard_assets

        self.assertTrue(callable(dashboard_assets.render_dashboard_styles))
        self.assertTrue(callable(dashboard_assets.render_dashboard_head))
        self.assertTrue(callable(dashboard_assets.render_dashboard_scripts))
        self.assertIn("render_dashboard_styles", dashboard_assets.render_dashboard_head())
        self.assertIn("ACCOUNT_METRIC_STORAGE_KEY", dashboard_assets.render_dashboard_scripts())


if __name__ == "__main__":
    unittest.main()
