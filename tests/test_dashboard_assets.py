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
        self.assertIn("bindCoreLiveRangeControls", dashboard_assets.render_dashboard_scripts())
        self.assertIn("data-core-live-range", dashboard_assets.render_dashboard_scripts())
        self.assertIn("searchParams.set('range', range)", dashboard_assets.render_dashboard_scripts())
        self.assertIn("refreshDashboard(true)", dashboard_assets.render_dashboard_scripts())

    def test_dashboard_head_hardens_echarts_cdn_loading(self) -> None:
        from momentum_alpha import dashboard_assets

        head = dashboard_assets.render_dashboard_head()

        self.assertIn("https://cdnjs.cloudflare.com/ajax/libs/echarts/5.6.0/echarts.min.js", head)
        self.assertIn('integrity="sha512-XSmbX3mhrD2ix5fXPTRQb2FwK22sRMVQTpBP2ac8hX7Dh/605hA2QDegVWiAvZPiXIxOV0CbkmUjGionDpbCmw=="', head)
        self.assertIn('crossorigin="anonymous"', head)
        self.assertIn("https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js", head)
        self.assertIn("echarts-ready", head)

    def test_dashboard_styles_stack_live_positions_and_render_order_flow_as_rows(self) -> None:
        from momentum_alpha import dashboard_assets

        styles = dashboard_assets.render_dashboard_styles()

        self.assertIn(
            ".live-decision-grid { display: flex; flex-direction: column; gap: 16px; align-items: stretch; }",
            styles,
        )
        self.assertIn(".live-decision-grid .execution-flow-panel { margin-bottom: 0; }", styles)
        self.assertIn(".execution-flow-grid { display: flex; flex-direction: column; gap: 12px; }", styles)
        self.assertIn(".execution-flow-group { display: flex; flex-direction: column; gap: 8px; }", styles)
        self.assertIn(".execution-flow-group + .execution-flow-group { padding-top: 10px; border-top: 1px solid rgba(184,160,120,0.12); }", styles)
        self.assertIn(".execution-flow-group-label { font-size: 0.62rem; color: var(--accent); letter-spacing: 0.12em; text-transform: uppercase; margin: 0 0 2px; }", styles)
        self.assertIn(
            ".execution-flow-row {",
            styles,
        )
        self.assertIn("grid-template-columns: minmax(170px, 0.9fr) minmax(0, 1.25fr) minmax(160px, 0.8fr);", styles)
        self.assertIn(".execution-flow-row-primary {", styles)
        self.assertIn(".execution-flow-row-support {", styles)
        self.assertIn(".execution-flow-body {", styles)
        self.assertIn(".execution-flow-detail { margin-top: 0; font-size: 0.72rem; color: var(--fg-muted); line-height: 1.35; word-break: break-word; text-align: right; }", styles)


if __name__ == "__main__":
    unittest.main()
