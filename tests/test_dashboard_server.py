from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardServerTests(unittest.TestCase):
    def test_dashboard_server_module_exports_server_entrypoint(self) -> None:
        from momentum_alpha import dashboard_server

        self.assertTrue(callable(dashboard_server.run_dashboard_server))


if __name__ == "__main__":
    unittest.main()
