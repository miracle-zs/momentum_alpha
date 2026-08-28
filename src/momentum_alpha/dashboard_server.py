from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sqlite3
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urlparse

from momentum_alpha.dashboard_assets import (
    DASHBOARD_CSS_ASSET_ROUTE,
    DASHBOARD_JS_ASSET_ROUTE,
    render_dashboard_script_asset,
    render_dashboard_stylesheet,
)
from momentum_alpha.dashboard import (
    build_dashboard_response_json,
    build_dashboard_summary_payload,
    build_dashboard_tables_payload,
    build_dashboard_timeseries_payload,
    load_dashboard_live_snapshot,
    load_dashboard_snapshot,
    normalize_account_range,
    normalize_dashboard_room,
    normalize_review_view,
    render_dashboard_body,
    render_dashboard_html,
)
from momentum_alpha.runtime_schema import ensure_dashboard_live_schema


_DASHBOARD_SNAPSHOT_CACHE_TTL_SECONDS = 5.0


def _runtime_db_signature(path: Path) -> tuple[tuple[int, int] | None, ...]:
    signature: list[tuple[int, int] | None] = []
    for suffix in ("", "-wal"):
        candidate = path if not suffix else Path(f"{path}{suffix}")
        try:
            stat = candidate.stat()
        except OSError:
            signature.append(None)
        else:
            signature.append((stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


class _DashboardSnapshotCache:
    def __init__(self, *, ttl_seconds: float = _DASHBOARD_SNAPSHOT_CACHE_TTL_SECONDS) -> None:
        self._ttl_seconds = max(0.0, float(ttl_seconds))
        self._entries: dict[tuple[object, ...], tuple[float, tuple[tuple[int, int] | None, ...], dict]] = {}
        self._lock = Lock()

    def get_or_load(
        self,
        *,
        key: tuple[object, ...],
        runtime_db_file: Path,
        loader: Callable[[], dict],
    ) -> dict:
        now = monotonic()
        signature = _runtime_db_signature(runtime_db_file)
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                created_at, cached_signature, snapshot = cached
                if now - created_at < self._ttl_seconds and cached_signature == signature:
                    return snapshot

            snapshot = loader()
            self._entries[key] = (monotonic(), _runtime_db_signature(runtime_db_file), snapshot)
            return snapshot


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
    static_assets = {
        DASHBOARD_CSS_ASSET_ROUTE: (
            render_dashboard_stylesheet().encode("utf-8"),
            "text/css; charset=utf-8",
        ),
        DASHBOARD_JS_ASSET_ROUTE: (
            render_dashboard_script_asset().encode("utf-8"),
            "application/javascript; charset=utf-8",
        ),
    }
    snapshot_cache = _DashboardSnapshotCache()
    if runtime_db_file.exists():
        try:
            ensure_dashboard_live_schema(path=runtime_db_file)
        except (OSError, sqlite3.Error):
            # The normal loader will surface an invalid database in the response.
            pass

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed_url = urlparse(self.path)
            supported_paths = {
                "/",
                "/api/dashboard",
                "/api/dashboard/summary",
                "/api/dashboard/timeseries",
                "/api/dashboard/tables",
                *static_assets,
            }
            if parsed_url.path not in supported_paths:
                self.send_response(404)
                self.end_headers()
                return

            static_asset = static_assets.get(parsed_url.path)
            if static_asset is not None:
                body, content_type = static_asset
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                self.end_headers()
                self.wfile.write(body)
                return

            query_params = parse_qs(parsed_url.query)
            active_room = normalize_dashboard_room(query_params.get("room", [query_params.get("tab", [None])[0]])[0])
            review_view = normalize_review_view(query_params.get("review_view", [None])[0])
            account_range_key = normalize_account_range(query_params.get("range", [None])[0])
            report_date = query_params.get("report_date", [None])[0]
            live_requested = (
                query_params.get("live", ["0"])[0].lower() in {"1", "true", "yes"}
                and parsed_url.path in {"/api/dashboard/summary", "/api/dashboard/timeseries"}
            )
            snapshot = snapshot_cache.get_or_load(
                key=("live" if live_requested else "full", account_range_key, report_date),
                runtime_db_file=runtime_db_file,
                loader=lambda: (load_dashboard_live_snapshot if live_requested else load_dashboard_snapshot)(
                    now=now_provider().astimezone(),
                    runtime_db_file=runtime_db_file,
                    stop_budget_usdt=stop_budget_usdt,
                    entry_start_hour_utc=entry_start_hour_utc,
                    entry_end_hour_utc=entry_end_hour_utc,
                    testnet=testnet,
                    submit_orders=submit_orders,
                    account_range_key=account_range_key,
                    report_date=report_date,
                ),
            )
            if parsed_url.path in {"/api/dashboard", "/api/dashboard/summary", "/api/dashboard/timeseries", "/api/dashboard/tables"}:
                if parsed_url.path == "/api/dashboard/summary":
                    payload = build_dashboard_summary_payload(snapshot)
                    if live_requested:
                        health = snapshot.get("health") or {}
                        payload["live_html"] = (
                            render_dashboard_body(
                                snapshot,
                                active_room="live",
                                account_range_key=account_range_key,
                            )
                            if isinstance(health.get("items"), list)
                            else ""
                        )
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
                    use_external_assets=True,
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        def log_message(self, format, *args):  # noqa: A003
            return

    with server_factory((host, port), DashboardHandler) as server:
        server.serve_forever()
    return 0
