from __future__ import annotations

import json
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from pathlib import Path

from .health import build_runtime_health_report


def _load_state_file(*, path: Path) -> tuple[dict, list[str]]:
    if not path.exists():
        return {}, [f"state file missing path={path}"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return {}, [f"state file invalid path={path} error={exc}"]


def _select_latest_timestamp(events: list[dict], event_type: str) -> str | None:
    for event in events:
        if event.get("event_type") == event_type:
            return event.get("timestamp")
    return None


def _load_recent_events(*, path: Path, recent_limit: int) -> tuple[list[dict], list[str]]:
    if not path.exists():
        return [], [f"audit file missing path={path}"]
    events: list[dict] = []
    warnings: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            warnings.append(f"audit file invalid path={path} line={line_number} error={exc}")
    return sorted(events, key=lambda item: item.get("timestamp", ""), reverse=True)[:recent_limit], warnings


def load_dashboard_snapshot(
    *,
    now: datetime,
    state_file: Path,
    poll_log_file: Path,
    user_stream_log_file: Path,
    audit_log_file: Path,
    recent_limit: int = 20,
) -> dict:
    health_report = build_runtime_health_report(
        now=now,
        state_file=state_file,
        poll_log_file=poll_log_file,
        user_stream_log_file=user_stream_log_file,
        audit_log_file=audit_log_file,
    )
    state_payload, warnings = _load_state_file(path=state_file)
    positions = state_payload.get("positions") or {}
    order_statuses = state_payload.get("order_statuses") or {}
    recent_events, audit_warnings = _load_recent_events(path=audit_log_file, recent_limit=recent_limit)
    warnings.extend(audit_warnings)

    return {
        "health": {
            "overall_status": health_report.overall_status,
            "items": [
                {"name": item.name, "status": item.status, "message": item.message}
                for item in health_report.items
            ],
        },
        "runtime": {
            "previous_leader_symbol": state_payload.get("previous_leader_symbol"),
            "position_count": len(positions),
            "order_status_count": len(order_statuses),
            "latest_tick_timestamp": _select_latest_timestamp(recent_events, "poll_tick"),
            "latest_tick_result_timestamp": _select_latest_timestamp(recent_events, "tick_result"),
            "latest_poll_worker_start_timestamp": _select_latest_timestamp(recent_events, "poll_worker_start"),
            "latest_user_stream_start_timestamp": _select_latest_timestamp(recent_events, "user_stream_worker_start"),
        },
        "recent_events": recent_events,
        "warnings": warnings,
    }


def build_dashboard_response_json(snapshot: dict) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


def render_dashboard_html(snapshot: dict) -> str:
    health_items = "".join(
        f"<li><strong>{escape(item['name'])}</strong> "
        f"<span>{escape(item['status'])}</span> "
        f"<code>{escape(item['message'])}</code></li>"
        for item in snapshot["health"]["items"]
    )
    warnings = "".join(f"<li>{escape(warning)}</li>" for warning in snapshot["warnings"]) or "<li>none</li>"
    recent_events = "".join(
        "<li>"
        f"<strong>{escape(event['event_type'])}</strong> "
        f"<code>{escape(event['timestamp'])}</code> "
        f"<pre>{escape(json.dumps(event['payload'], ensure_ascii=False, indent=2))}</pre>"
        "</li>"
        for event in snapshot["recent_events"]
    ) or "<li>none</li>"
    runtime = snapshot["runtime"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Momentum Alpha Dashboard</title>
  <style>
    :root {{ color-scheme: light; --bg: #f3efe7; --panel: #fffdfa; --text: #1d1b18; --muted: #6c655c; --ok: #175c3a; --fail: #a23b2a; --line: #d8cfc3; }}
    body {{ margin: 0; font-family: Georgia, "Times New Roman", serif; background: linear-gradient(180deg, #efe7da 0%, #f7f3ec 100%); color: var(--text); }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
    .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
    section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 18px; box-shadow: 0 8px 24px rgba(60, 42, 20, 0.06); }}
    h1, h2 {{ margin: 0 0 12px; }}
    .status {{ font-weight: 700; }}
    .ok {{ color: var(--ok); }}
    .fail {{ color: var(--fail); }}
    ul {{ margin: 0; padding-left: 18px; }}
    li {{ margin: 8px 0; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f5f0e8; padding: 10px; border-radius: 10px; }}
    dl {{ margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 8px 12px; }}
    dt {{ color: var(--muted); }}
    code {{ font-size: 0.9em; }}
  </style>
</head>
<body>
  <main>
    <h1>Momentum Alpha Dashboard</h1>
    <section>
      <h2>Health</h2>
      <p class="status {'ok' if snapshot['health']['overall_status'] == 'OK' else 'fail'}">overall={escape(snapshot['health']['overall_status'])}</p>
      <ul>{health_items}</ul>
    </section>
    <div class="grid">
      <section>
        <h2>Runtime</h2>
        <dl>
          <dt>Previous leader</dt><dd>{escape(str(runtime['previous_leader_symbol']))}</dd>
          <dt>Position count</dt><dd>{runtime['position_count']}</dd>
          <dt>Order status count</dt><dd>{runtime['order_status_count']}</dd>
          <dt>Latest tick</dt><dd>{escape(str(runtime['latest_tick_timestamp']))}</dd>
          <dt>Latest tick result</dt><dd>{escape(str(runtime['latest_tick_result_timestamp']))}</dd>
          <dt>Latest poll start</dt><dd>{escape(str(runtime['latest_poll_worker_start_timestamp']))}</dd>
          <dt>Latest user-stream start</dt><dd>{escape(str(runtime['latest_user_stream_start_timestamp']))}</dd>
        </dl>
      </section>
      <section>
        <h2>Warnings</h2>
        <ul>{warnings}</ul>
      </section>
    </div>
    <section>
      <h2>Recent Events</h2>
      <ul>{recent_events}</ul>
    </section>
  </main>
</body>
</html>"""


def run_dashboard_server(
    *,
    host: str,
    port: int,
    state_file: Path,
    poll_log_file: Path,
    user_stream_log_file: Path,
    audit_log_file: Path,
    now_provider=None,
    server_factory=ThreadingHTTPServer,
) -> int:
    now_provider = now_provider or datetime.now

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            snapshot = load_dashboard_snapshot(
                now=now_provider().astimezone(),
                state_file=state_file,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                audit_log_file=audit_log_file,
            )
            if self.path == "/api/dashboard":
                body = build_dashboard_response_json(snapshot).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/":
                body = render_dashboard_html(snapshot).encode("utf-8")
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
