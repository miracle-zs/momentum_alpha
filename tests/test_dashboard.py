import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardTests(unittest.TestCase):
    def test_load_dashboard_snapshot_combines_health_state_and_recent_audit(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 15, 0, tzinfo=timezone.utc)
            state_file = root / "state.json"
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            audit_log_file = root / "audit.jsonl"

            state_file.write_text(
                json.dumps(
                    {
                        "current_day": "2026-04-15",
                        "previous_leader_symbol": "INUSDT",
                        "positions": {
                            "ETHUSDT": {
                                "symbol": "ETHUSDT",
                                "entry_price": "100",
                                "stop_price": "95",
                                "legs": [],
                            }
                        },
                        "order_statuses": {"123": {"symbol": "ETHUSDT", "status": "NEW"}},
                    }
                ),
                encoding="utf-8",
            )
            poll_log_file.write_text("tick 2026-04-15T06:00:00+00:00\n", encoding="utf-8")
            user_stream_log_file.write_text("listen_key=abc\n", encoding="utf-8")
            audit_log_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp": "2026-04-15T06:59:00+00:00",
                                "event_type": "poll_tick",
                                "payload": {"symbol_count": 538, "rate_limited_until": None},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp": "2026-04-15T06:59:01+00:00",
                                "event_type": "tick_result",
                                "payload": {"next_previous_leader_symbol": "INUSDT"},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp": "2026-04-15T06:59:02+00:00",
                                "event_type": "user_stream_worker_start",
                                "payload": {"position_count": 1},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            for path in (state_file, poll_log_file, user_stream_log_file, audit_log_file):
                os.utime(path, (now.timestamp(), now.timestamp()))

            snapshot = load_dashboard_snapshot(
                now=now,
                state_file=state_file,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                audit_log_file=audit_log_file,
                recent_limit=10,
            )

            self.assertEqual(snapshot["health"]["overall_status"], "OK")
            self.assertEqual(snapshot["runtime"]["previous_leader_symbol"], "INUSDT")
            self.assertEqual(snapshot["runtime"]["position_count"], 1)
            self.assertEqual(snapshot["runtime"]["order_status_count"], 1)
            self.assertEqual(snapshot["runtime"]["latest_tick_timestamp"], "2026-04-15T06:59:00+00:00")
            self.assertEqual(snapshot["runtime"]["latest_user_stream_start_timestamp"], "2026-04-15T06:59:02+00:00")
            self.assertEqual(len(snapshot["recent_events"]), 3)
            self.assertEqual(snapshot["recent_events"][0]["event_type"], "user_stream_worker_start")

    def test_load_dashboard_snapshot_reports_missing_state_as_warning(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 15, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            audit_log_file = root / "audit.jsonl"

            for path in (poll_log_file, user_stream_log_file, audit_log_file):
                path.write_text("x\n", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            snapshot = load_dashboard_snapshot(
                now=now,
                state_file=root / "state.json",
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                audit_log_file=audit_log_file,
                recent_limit=5,
            )

            self.assertEqual(snapshot["health"]["overall_status"], "FAIL")
            self.assertEqual(snapshot["runtime"]["previous_leader_symbol"], None)
            self.assertEqual(snapshot["runtime"]["position_count"], 0)
            self.assertTrue(any("state file missing" in warning for warning in snapshot["warnings"]))

    def test_render_dashboard_html_includes_health_runtime_and_recent_events(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {
                    "overall_status": "OK",
                    "items": [{"name": "state_file", "status": "OK", "message": "fresh"}],
                },
                "runtime": {
                    "previous_leader_symbol": "INUSDT",
                    "position_count": 1,
                    "order_status_count": 2,
                    "latest_tick_timestamp": "2026-04-15T06:59:00+00:00",
                    "latest_tick_result_timestamp": "2026-04-15T06:59:01+00:00",
                    "latest_poll_worker_start_timestamp": "2026-04-15T06:58:00+00:00",
                    "latest_user_stream_start_timestamp": "2026-04-15T06:58:05+00:00",
                },
                "recent_events": [
                    {"timestamp": "2026-04-15T06:59:01+00:00", "event_type": "tick_result", "payload": {"symbol_count": 538}}
                ],
                "warnings": [],
            }
        )

        self.assertIn("Momentum Alpha Dashboard", html)
        self.assertIn("overall=OK", html)
        self.assertIn("INUSDT", html)
        self.assertIn("tick_result", html)

    def test_build_dashboard_response_json_serializes_snapshot(self) -> None:
        from momentum_alpha.dashboard import build_dashboard_response_json

        payload = build_dashboard_response_json(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {"previous_leader_symbol": "INUSDT"},
                "recent_events": [],
                "warnings": [],
            }
        )

        self.assertIn('"overall_status": "OK"', payload)
        self.assertIn('"previous_leader_symbol": "INUSDT"', payload)
