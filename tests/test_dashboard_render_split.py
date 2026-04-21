from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardRenderSplitTests(unittest.TestCase):
    def test_dashboard_render_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import dashboard_render_panels, dashboard_render_shell, dashboard_render_tables, dashboard_render_utils

        self.assertTrue(callable(dashboard_render_utils.normalize_dashboard_room))
        self.assertTrue(callable(dashboard_render_tables.render_trade_history_table))
        self.assertTrue(callable(dashboard_render_panels.render_cosmic_identity_panel))
        self.assertTrue(callable(dashboard_render_shell.render_dashboard_html))


if __name__ == "__main__":
    unittest.main()
