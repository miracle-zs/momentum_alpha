from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from momentum_alpha.dashboard import (
    build_dashboard_response_json,
    build_dashboard_summary_payload,
    build_dashboard_tables_payload,
    build_dashboard_timeseries_payload,
    load_dashboard_snapshot,
    normalize_account_range,
    normalize_dashboard_room,
    normalize_review_view,
    render_dashboard_html,
)


def run_dashboard_server(
    *,
    host: str,
    port: int,
    poll_log_file: Path | None = None,
    user_stream_log_file: Path | None = None,
    runtime_db_file: Path,
    now_provider=None,
    server_factory=ThreadingHTTPServer,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
) -> int:
    now_provider = now_provider or datetime.now
    server_factory = server_factory or ThreadingHTTPServer

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            active_room = normalize_dashboard_room(query_params.get("room", [query_params.get("tab", [None])[0]])[0])
            review_view = normalize_review_view(query_params.get("review_view", [None])[0])
            account_range_key = normalize_account_range(query_params.get("range", [None])[0])
            snapshot = load_dashboard_snapshot(
                now=now_provider().astimezone(),
                runtime_db_file=runtime_db_file,
                stop_budget_usdt=stop_budget_usdt,
                entry_start_hour_utc=entry_start_hour_utc,
                entry_end_hour_utc=entry_end_hour_utc,
                testnet=testnet,
                submit_orders=submit_orders,
                account_range_key=account_range_key,
            )
            if parsed_url.path in {"/api/dashboard", "/api/dashboard/summary", "/api/dashboard/timeseries", "/api/dashboard/tables"}:
                if parsed_url.path == "/api/dashboard/summary":
                    payload = build_dashboard_summary_payload(snapshot)
                elif parsed_url.path == "/api/dashboard/timeseries":
                    payload = build_dashboard_timeseries_payload(snapshot)
                elif parsed_url.path == "/api/dashboard/tables":
                    payload = build_dashboard_tables_payload(snapshot)
                else:
                    payload = snapshot
                body = build_dashboard_response_json(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed_url.path == "/":
                body = render_dashboard_html(
                    snapshot,
                    active_room=active_room,
                    review_view=review_view,
                    account_range_key=account_range_key,
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A003
            return

    with server_factory((host, port), DashboardHandler) as server:
        server.serve_forever()
    return 0
