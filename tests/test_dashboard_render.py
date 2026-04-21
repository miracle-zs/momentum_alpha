import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardRenderTests(unittest.TestCase):
    def test_dashboard_render_module_exports_render_entrypoints(self) -> None:
        from momentum_alpha import dashboard_render

        for name in (
            "render_dashboard_html",
            "render_dashboard_document",
            "render_dashboard_head",
            "render_dashboard_body",
            "render_dashboard_scripts",
            "render_dashboard_styles",
            "render_dashboard_room_nav",
            "render_position_cards",
        ):
            self.assertTrue(callable(getattr(dashboard_render, name)))


if __name__ == "__main__":
    unittest.main()
