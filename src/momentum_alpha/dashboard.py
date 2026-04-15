from __future__ import annotations

import json
from collections import Counter
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from pathlib import Path

from .health import build_runtime_health_report
from .runtime_store import fetch_audit_event_counts, fetch_recent_audit_events


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
    runtime_db_file: Path | None = None,
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
    if runtime_db_file is not None and runtime_db_file.exists():
        recent_events = fetch_recent_audit_events(path=runtime_db_file, limit=recent_limit)
        event_counts = fetch_audit_event_counts(path=runtime_db_file, limit=recent_limit)
    else:
        recent_events, audit_warnings = _load_recent_events(path=audit_log_file, recent_limit=recent_limit)
        warnings.extend(audit_warnings)
        event_counts = dict(Counter(event.get("event_type") for event in recent_events if event.get("event_type")))

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
        "event_counts": event_counts,
        "recent_events": recent_events,
        "warnings": warnings,
    }


def build_dashboard_response_json(snapshot: dict) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


def render_dashboard_html(snapshot: dict) -> str:
    health_items = "".join(
        f"<article class='health-row health-{escape(item['status'].lower())}'><div><strong>{escape(item['name'])}</strong></div>"
        f"<div>{escape(item['status'])}</div><div>{escape(item['message'])}</div></article>"
        for item in snapshot["health"]["items"]
    )
    warnings = "".join(f"<li>{escape(warning)}</li>" for warning in snapshot["warnings"]) or "<li>none</li>"
    recent_events = "".join(
        "<article class='timeline-event'>"
        f"<header><strong>{escape(event['event_type'])}</strong><time>{escape(event['timestamp'])}</time></header>"
        f"<pre>{escape(json.dumps(event['payload'], ensure_ascii=False, indent=2))}</pre>"
        "</article>"
        for event in snapshot["recent_events"]
    ) or "<article class='timeline-event'><header><strong>none</strong></header></article>"
    event_bars = "".join(
        f"<div class='event-bar'><span>{escape(event_type)}</span><strong>{count}</strong></div>"
        for event_type, count in sorted(snapshot.get("event_counts", {}).items())
    ) or "<div class='event-bar'><span>none</span><strong>0</strong></div>"
    runtime = snapshot["runtime"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Momentum Alpha Dashboard</title>
  <style>
    :root {{ color-scheme: dark; --bg: #09111b; --panel: #101b27; --panel-2: #0d1621; --text: #e8f0f8; --muted: #8ea2b7; --line: #223446; --ok: #36d98a; --warn: #ffbc42; --fail: #ff5d73; --accent: #4cc9f0; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "SFMono-Regular", "Menlo", monospace; background: radial-gradient(circle at top, #122033 0%, var(--bg) 55%); color: var(--text); }}
    .desk-shell {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
    .hero {{ display: flex; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 20px; }}
    .hero h1 {{ margin: 0; font-size: 2rem; letter-spacing: 0.04em; text-transform: uppercase; }}
    .hero p {{ margin: 6px 0 0; color: var(--muted); }}
    .status-pill {{ padding: 8px 14px; border-radius: 999px; font-weight: 700; border: 1px solid var(--line); }}
    .status-pill.ok {{ background: rgba(54, 217, 138, 0.14); color: var(--ok); }}
    .status-pill.fail {{ background: rgba(255, 93, 115, 0.14); color: var(--fail); }}
    .metrics {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 18px; }}
    .metric-card, section {{ background: linear-gradient(180deg, rgba(20,33,48,0.96), rgba(13,22,33,0.96)); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(0,0,0,0.25); }}
    .metric-card {{ padding: 16px; min-height: 110px; }}
    .metric-card .label {{ color: var(--muted); font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.08em; }}
    .metric-card .value {{ margin-top: 10px; font-size: 1.75rem; font-weight: 700; }}
    .metric-card .sub {{ margin-top: 8px; color: var(--muted); font-size: 0.85rem; }}
    .main-grid {{ display: grid; gap: 16px; grid-template-columns: 1.2fr 0.8fr; }}
    .stack {{ display: grid; gap: 16px; }}
    section {{ padding: 18px; }}
    h2 {{ margin: 0 0 14px; font-size: 1rem; letter-spacing: 0.08em; text-transform: uppercase; }}
    .health-list {{ display: grid; gap: 10px; }}
    .health-row {{ display: grid; grid-template-columns: 1.1fr 0.4fr 1.8fr; gap: 10px; padding: 12px; border-radius: 12px; background: rgba(255,255,255,0.02); }}
    .health-ok {{ border: 1px solid rgba(54, 217, 138, 0.2); }}
    .health-fail {{ border: 1px solid rgba(255, 93, 115, 0.2); }}
    .event-bars {{ display: grid; gap: 10px; }}
    .event-bar {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 14px; border-radius: 12px; background: linear-gradient(90deg, rgba(76,201,240,0.16), rgba(76,201,240,0.05)); border: 1px solid rgba(76,201,240,0.18); }}
    .event-bar span {{ color: var(--muted); text-transform: uppercase; font-size: 0.82rem; }}
    .timeline {{ display: grid; gap: 12px; max-height: 640px; overflow: auto; }}
    .timeline-event {{ border-left: 3px solid var(--accent); padding: 10px 12px; background: rgba(255,255,255,0.02); border-radius: 0 12px 12px 0; }}
    .timeline-event header {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; }}
    .timeline-event time {{ color: var(--muted); font-size: 0.85rem; }}
    .warnings ul {{ margin: 0; padding-left: 18px; }}
    .warnings li {{ margin: 8px 0; color: #ffd7a1; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; background: rgba(3, 10, 18, 0.72); color: #c8f1ff; padding: 12px; border-radius: 12px; overflow: auto; }}
    @media (max-width: 980px) {{ .main-grid {{ grid-template-columns: 1fr; }} .hero {{ flex-direction: column; align-items: start; }} }}
  </style>
</head>
<body>
  <main class="desk-shell">
    <div class="hero">
      <div>
        <h1>Momentum Alpha Dashboard</h1>
        <p>Trade desk view with live health, state, and event flow. Auto refresh every 5 seconds.</p>
      </div>
      <div class="status-pill {'ok' if snapshot['health']['overall_status'] == 'OK' else 'fail'}">overall={escape(snapshot['health']['overall_status'])}</div>
    </div>
    <div class="metrics">
      <article class="metric-card"><div class="label">Leader</div><div class="value">{escape(str(runtime['previous_leader_symbol']))}</div><div class="sub">Current previous leader symbol</div></article>
      <article class="metric-card"><div class="label">Positions</div><div class="value">{runtime['position_count']}</div><div class="sub">Open local positions</div></article>
      <article class="metric-card"><div class="label">Order States</div><div class="value">{runtime['order_status_count']}</div><div class="sub">Tracked order lifecycle entries</div></article>
      <article class="metric-card"><div class="label">Latest Tick</div><div class="value">{escape(str(runtime['latest_tick_timestamp']))}</div><div class="sub">Most recent poll tick seen</div></article>
    </div>
    <div class="main-grid">
      <div class="stack">
        <section>
          <h2>Health Matrix</h2>
          <div class="health-list">{health_items}</div>
        </section>
        <section class="warnings">
          <h2>Warnings</h2>
          <ul>{warnings}</ul>
        </section>
      </div>
      <div class="stack">
        <section>
          <h2>Event Pulse</h2>
          <div class="event-bars">{event_bars}</div>
        </section>
        <section>
          <h2>Latest Result</h2>
          <pre>{escape(json.dumps(runtime, ensure_ascii=False, indent=2))}</pre>
        </section>
      </div>
    </div>
    <section style="margin-top: 16px;">
      <h2>Recent Event Timeline</h2>
      <div class="timeline">{recent_events}</div>
    </section>
  </main>
  <script>
    async function loadDashboard() {{
      try {{
        const response = await fetch('/api/dashboard', {{ cache: 'no-store' }});
        if (!response.ok) return;
        const payload = await response.json();
        const title = document.querySelector('.status-pill');
        if (title) {{
          title.textContent = `overall=${{payload.health.overall_status}}`;
        }}
      }} catch (error) {{
        console.error(error);
      }}
    }}
    setInterval(loadDashboard, 5000);
  </script>
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
    runtime_db_file: Path | None = None,
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
                runtime_db_file=runtime_db_file,
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
