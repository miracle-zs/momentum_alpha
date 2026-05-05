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
        self.assertIn("updateCoreLiveChartsFromDocument", dashboard_assets.render_dashboard_scripts())

    def test_dashboard_head_hardens_echarts_cdn_loading(self) -> None:
        from momentum_alpha import dashboard_assets

        head = dashboard_assets.render_dashboard_head()

        self.assertIn("https://cdnjs.cloudflare.com/ajax/libs/echarts/5.6.0/echarts.min.js", head)
        self.assertIn('integrity="sha512-XSmbX3mhrD2ix5fXPTRQb2FwK22sRMVQTpBP2ac8hX7Dh/605hA2QDegVWiAvZPiXIxOV0CbkmUjGionDpbCmw=="', head)
        self.assertIn('crossorigin="anonymous"', head)
        self.assertIn("https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js", head)
        self.assertIn("echarts-ready", head)


if __name__ == "__main__":
    unittest.main()
