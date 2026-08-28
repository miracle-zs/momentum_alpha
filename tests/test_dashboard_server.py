from __future__ import annotations

from io import BytesIO
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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

    def test_static_dashboard_assets_do_not_load_dashboard_snapshot(self) -> None:
        from momentum_alpha import dashboard_server

        captured = {}

        class FakeServer:
            def __init__(self, address, handler_class):
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
            handler.path = "/assets/dashboard.css?v=1"
            responses = []
            headers = []
            handler.send_response = responses.append
            handler.send_header = lambda name, value: headers.append((name, value))
            handler.end_headers = lambda: None
            handler.wfile = BytesIO()

            handler.do_GET()

        self.assertEqual(responses, [200])
        self.assertIn(("Content-Type", "text/css; charset=utf-8"), headers)
        self.assertIn(("Cache-Control", "public, max-age=31536000, immutable"), headers)
        self.assertIn(".app", handler.wfile.getvalue().decode("utf-8"))
        load_snapshot.assert_not_called()

    def test_dashboard_snapshot_cache_reuses_and_invalidates_entries(self) -> None:
        from momentum_alpha.dashboard_server import _DashboardSnapshotCache

        with TemporaryDirectory() as tmpdir:
            runtime_db_file = Path(tmpdir) / "runtime.db"
            runtime_db_file.write_bytes(b"initial")
            cache = _DashboardSnapshotCache(ttl_seconds=60)
            calls = []

            def load_snapshot():
                calls.append(len(calls) + 1)
                return {"version": len(calls)}

            first = cache.get_or_load(
                key=("1D", None),
                runtime_db_file=runtime_db_file,
                loader=load_snapshot,
            )
            second = cache.get_or_load(
                key=("1D", None),
                runtime_db_file=runtime_db_file,
                loader=load_snapshot,
            )
            runtime_db_file.write_bytes(b"changed")
            os.utime(runtime_db_file, None)
            third = cache.get_or_load(
                key=("1D", None),
                runtime_db_file=runtime_db_file,
                loader=load_snapshot,
            )

        self.assertEqual(first, {"version": 1})
        self.assertIs(second, first)
        self.assertEqual(third, {"version": 2})
        self.assertEqual(calls, [1, 2])

    def test_dashboard_requests_share_snapshot_cache(self) -> None:
        from momentum_alpha import dashboard_server

        captured = {}

        class FakeServer:
            def __init__(self, address, handler_class):
                captured["handler_class"] = handler_class

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def serve_forever(self):
                return None

        with TemporaryDirectory() as tmpdir:
            runtime_db_file = Path(tmpdir) / "runtime.db"
            runtime_db_file.write_bytes(b"initial")
            with (
                patch.object(dashboard_server, "load_dashboard_snapshot", return_value={"snapshot": True}) as load_snapshot,
                patch.object(dashboard_server, "render_dashboard_html", return_value="<html></html>") as render_html,
            ):
                dashboard_server.run_dashboard_server(
                    host="127.0.0.1",
                    port=8080,
                    runtime_db_file=runtime_db_file,
                    server_factory=FakeServer,
                )
                handler = captured["handler_class"].__new__(captured["handler_class"])
                handler.path = "/"
                handler.send_response = lambda status: None
                handler.send_header = lambda name, value: None
                handler.end_headers = lambda: None

                for _ in range(2):
                    handler.wfile = BytesIO()
                    handler.do_GET()

        self.assertEqual(load_snapshot.call_count, 1)
        self.assertEqual(render_html.call_count, 2)
        self.assertTrue(render_html.call_args.kwargs["use_external_assets"])

    def test_live_summary_api_uses_lightweight_snapshot_loader(self) -> None:
        from momentum_alpha import dashboard_server

        captured = {}

        class FakeServer:
            def __init__(self, address, handler_class):
                captured["handler_class"] = handler_class

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def serve_forever(self):
                return None

        with TemporaryDirectory() as tmpdir:
            runtime_db_file = Path(tmpdir) / "runtime.db"
            runtime_db_file.write_bytes(b"initial")
            with (
                patch.object(dashboard_server, "load_dashboard_snapshot") as full_loader,
                patch.object(dashboard_server, "load_dashboard_live_snapshot", return_value={
                    "runtime": {"latest_account_snapshot": {"equity": "1"}},
                    "health": {"overall_status": "OK"},
                }) as live_loader,
            ):
                dashboard_server.run_dashboard_server(
                    host="127.0.0.1",
                    port=8080,
                    runtime_db_file=runtime_db_file,
                    server_factory=FakeServer,
                )
                handler = captured["handler_class"].__new__(captured["handler_class"])
                handler.path = "/api/dashboard/summary?range=1D&live=1"
                handler.send_response = lambda status: None
                handler.send_header = lambda name, value: None
                handler.end_headers = lambda: None
                handler.wfile = BytesIO()

                handler.do_GET()

        self.assertEqual(live_loader.call_count, 1)
        full_loader.assert_not_called()
        self.assertIn(b'"account"', handler.wfile.getvalue())


if __name__ == "__main__":
    unittest.main()
