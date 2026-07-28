from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardServerTests(unittest.TestCase):
    def test_dashboard_server_module_exports_server_entrypoint(self) -> None:
        from momentum_alpha import dashboard_server

        self.assertTrue(callable(dashboard_server.run_dashboard_server))

    def test_unknown_route_does_not_load_dashboard_snapshot(self) -> None:
        from momentum_alpha import dashboard_server

        captured = {}

        class FakeServer:
            def __init__(self, address, handler_class):
                captured["address"] = address
                captured["handler_class"] = handler_class

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def serve_forever(self):
                return None

        with patch.object(dashboard_server, "load_dashboard_snapshot") as load_snapshot:
            dashboard_server.run_dashboard_server(
                host="127.0.0.1",
                port=8080,
                runtime_db_file=Path("/tmp/runtime.db"),
                server_factory=FakeServer,
            )
            handler = captured["handler_class"].__new__(captured["handler_class"])
            handler.path = "/favicon.ico"
            responses = []
            handler.send_response = responses.append
            handler.end_headers = lambda: None

            handler.do_GET()

        self.assertEqual(responses, [404])
        load_snapshot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
