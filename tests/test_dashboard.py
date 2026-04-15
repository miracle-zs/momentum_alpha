import json
import os
import sys
import unittest
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardTests(unittest.TestCase):
    def test_format_timestamp_for_display_uses_utc_plus_8(self) -> None:
        from momentum_alpha.dashboard import format_timestamp_for_display

        self.assertEqual(
            format_timestamp_for_display("2026-04-15T08:52:00.734144+00:00"),
            "2026-04-15 16:52:00",
        )

    def test_load_dashboard_snapshot_combines_health_state_and_recent_audit(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
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
            self.assertEqual(snapshot["event_counts"], {"poll_tick": 1, "tick_result": 1, "user_stream_worker_start": 1})
            self.assertEqual(snapshot["source_counts"], {"audit-file": 3})
            self.assertEqual(snapshot["leader_history"][0]["symbol"], "INUSDT")
            self.assertIn(3, [point["event_count"] for point in snapshot["pulse_points"]])

    def test_load_dashboard_snapshot_reports_missing_state_as_warning(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
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
                    {
                        "timestamp": "2026-04-15T06:59:01+00:00",
                        "event_type": "tick_result",
                        "payload": {"symbol_count": 538},
                        "source": "poll",
                    }
                ],
                "event_counts": {"poll_tick": 12, "tick_result": 12, "user_stream_event": 3},
                "source_counts": {"poll": 24, "user-stream": 3},
                "leader_history": [{"timestamp": "2026-04-15T06:59:01+00:00", "symbol": "INUSDT"}],
                "pulse_points": [{"bucket": "2026-04-15T06:59:00+00:00", "event_count": 3}],
                "warnings": [],
            }
        )

        self.assertIn("Momentum Alpha", html)
        self.assertIn("交易监控面板", html)
        self.assertIn("OK", html)
        self.assertIn("INUSDT", html)
        self.assertIn("tick_result", html)
        self.assertIn("setInterval(refreshDashboard, 5000)", html)
        self.assertIn("/api/dashboard", html)
        self.assertIn("app", html)
        self.assertIn("pulse-bar", html)
        self.assertIn("metric", html)
        self.assertIn("POSITIONS", html)
        self.assertIn("ACCOUNT METRICS", html)
        self.assertIn("LATEST DECISION", html)
        self.assertIn("LEADER ROTATION", html)
        self.assertIn("TRADE HISTORY", html)
        self.assertIn("SYSTEM HEALTH", html)
        self.assertIn("RECENT EVENTS", html)
        self.assertIn("2026-04-15 14:59:01", html)

    def test_build_dashboard_response_json_serializes_snapshot(self) -> None:
        from momentum_alpha.dashboard import build_dashboard_response_json

        payload = build_dashboard_response_json(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {"previous_leader_symbol": "INUSDT"},
                "recent_events": [],
                "event_counts": dict(Counter(["poll_tick", "tick_result"])),
                "warnings": [],
            }
        )

        self.assertIn('"overall_status": "OK"', payload)
        self.assertIn('"previous_leader_symbol": "INUSDT"', payload)
        self.assertIn('"event_counts"', payload)

    def test_load_dashboard_snapshot_prefers_sqlite_runtime_store(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            insert_audit_event,
            insert_position_snapshot,
            insert_signal_decision,
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
            state_file = root / "state.json"
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            audit_log_file = root / "audit.jsonl"
            runtime_db_file = root / "runtime.db"

            state_file.write_text(
                json.dumps({"previous_leader_symbol": "INUSDT", "positions": {}, "order_statuses": {}}),
                encoding="utf-8",
            )
            for path in (poll_log_file, user_stream_log_file, audit_log_file):
                path.write_text("", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))
            bootstrap_runtime_db(path=runtime_db_file)
            insert_signal_decision(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 58, 59, tzinfo=timezone.utc),
                source="poll",
                decision_type="base_entry",
                symbol="BLESSUSDT",
                previous_leader_symbol="INUSDT",
                next_leader_symbol="BLESSUSDT",
                payload={},
            )
            insert_position_snapshot(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 1, tzinfo=timezone.utc),
                source="poll",
                leader_symbol="BLESSUSDT",
                position_count=2,
                order_status_count=3,
                symbol_count=538,
                payload={},
            )
            insert_audit_event(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, tzinfo=timezone.utc),
                event_type="poll_tick",
                payload={"symbol_count": 538},
                source="poll",
            )
            insert_audit_event(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 2, tzinfo=timezone.utc),
                event_type="user_stream_worker_start",
                payload={"position_count": 0},
                source="user-stream",
            )

            snapshot = load_dashboard_snapshot(
                now=now,
                state_file=state_file,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                audit_log_file=audit_log_file,
                runtime_db_file=runtime_db_file,
                recent_limit=10,
            )

            self.assertEqual(snapshot["event_counts"]["poll_tick"], 1)
            self.assertEqual(snapshot["recent_events"][0]["event_type"], "user_stream_worker_start")
            self.assertEqual(snapshot["source_counts"]["poll"], 1)
            self.assertEqual(snapshot["source_counts"]["user-stream"], 1)
            self.assertEqual(snapshot["runtime"]["previous_leader_symbol"], "BLESSUSDT")
            self.assertEqual(snapshot["runtime"]["position_count"], 2)
            self.assertEqual(snapshot["runtime"]["order_status_count"], 3)

    def test_load_dashboard_snapshot_uses_sqlite_runtime_summary_when_state_file_missing(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot
        from momentum_alpha.runtime_store import RuntimeStateStore, insert_position_snapshot, insert_signal_decision
        from momentum_alpha.state_store import StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            audit_log_file = root / "audit.jsonl"
            runtime_db_file = root / "runtime.db"

            for path in (poll_log_file, user_stream_log_file, audit_log_file):
                path.write_text("", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            insert_signal_decision(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, tzinfo=timezone.utc),
                source="poll",
                decision_type="no_action",
                symbol="BLESSUSDT",
                previous_leader_symbol="ONUSDT",
                next_leader_symbol="BLESSUSDT",
                payload={"blocked_reason": "invalid_stop_price"},
            )
            insert_position_snapshot(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 1, tzinfo=timezone.utc),
                source="poll",
                leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=4,
                symbol_count=538,
                payload={},
            )
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BLESSUSDT",
                    processed_event_ids=["evt-1"],
                    order_statuses={"101": {"symbol": "BLESSUSDT", "status": "NEW"}},
                )
            )

            snapshot = load_dashboard_snapshot(
                now=now,
                state_file=root / "state.json",
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                audit_log_file=audit_log_file,
                runtime_db_file=runtime_db_file,
                recent_limit=10,
            )

            self.assertEqual(snapshot["runtime"]["previous_leader_symbol"], "BLESSUSDT")
            self.assertEqual(snapshot["runtime"]["position_count"], 1)
            self.assertEqual(snapshot["runtime"]["order_status_count"], 4)
            self.assertTrue(any("state file missing" in warning for warning in snapshot["warnings"]))

    def test_load_dashboard_snapshot_includes_structured_runtime_summaries(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot
        from momentum_alpha.runtime_store import (
            insert_account_snapshot,
            insert_broker_order,
            insert_position_snapshot,
            insert_signal_decision,
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
            state_file = root / "state.json"
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"

            state_file.write_text(
                json.dumps({"previous_leader_symbol": "BLESSUSDT", "positions": {}, "order_statuses": {}}),
                encoding="utf-8",
            )
            for path in (state_file, poll_log_file, user_stream_log_file):
                if path is not state_file:
                    path.write_text("", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            insert_signal_decision(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, tzinfo=timezone.utc),
                symbol="BLESSUSDT",
                decision_type="no_action",
                previous_leader_symbol="ONUSDT",
                next_leader_symbol="BLESSUSDT",
                payload={"blocked_reason": "invalid_stop_price"},
                source="poll",
            )
            insert_broker_order(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 1, tzinfo=timezone.utc),
                symbol="BLESSUSDT",
                action_type="submit_entry",
                order_type="MARKET",
                status="NEW",
                payload={"quantity": "5"},
                source="poll",
            )
            insert_position_snapshot(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 2, tzinfo=timezone.utc),
                previous_leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=2,
                symbol_count=538,
                payload={"positions": ["BLESSUSDT"]},
                source="poll",
            )
            insert_account_snapshot(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 3, tzinfo=timezone.utc),
                source="poll",
                wallet_balance="1234.56",
                available_balance="1200.00",
                equity="1260.12",
                unrealized_pnl="25.56",
                position_count=1,
                open_order_count=2,
                leader_symbol="BLESSUSDT",
                payload={"account_alias": "primary"},
            )

            snapshot = load_dashboard_snapshot(
                now=now,
                state_file=state_file,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                audit_log_file=root / "missing-audit.jsonl",
                runtime_db_file=runtime_db_file,
                recent_limit=10,
            )

            self.assertEqual(snapshot["runtime"]["latest_signal_decision"]["decision_type"], "no_action")
            self.assertEqual(snapshot["runtime"]["latest_signal_decision"]["symbol"], "BLESSUSDT")
            self.assertEqual(snapshot["runtime"]["latest_signal_decision"]["payload"]["blocked_reason"], "invalid_stop_price")
            self.assertEqual(snapshot["runtime"]["latest_broker_order"]["action_type"], "submit_entry")
            self.assertEqual(snapshot["runtime"]["latest_position_snapshot"]["position_count"], 1)
            self.assertEqual(snapshot["runtime"]["latest_account_snapshot"]["wallet_balance"], "1234.56")
            self.assertEqual(snapshot["runtime"]["latest_account_snapshot"]["equity"], "1260.12")
            self.assertEqual(snapshot["recent_signal_decisions"][0]["symbol"], "BLESSUSDT")
            self.assertEqual(snapshot["recent_broker_orders"][0]["order_type"], "MARKET")
            self.assertEqual(snapshot["recent_account_snapshots"][0]["payload"]["account_alias"], "primary")

    def test_dashboard_api_helpers_split_summary_timeseries_and_tables(self) -> None:
        from momentum_alpha.dashboard import (
            build_dashboard_summary_payload,
            build_dashboard_tables_payload,
            build_dashboard_timeseries_payload,
        )

        snapshot = {
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "BLESSUSDT",
                "position_count": 1,
                "order_status_count": 2,
                "latest_tick_timestamp": "2026-04-15T08:49:00+00:00",
                "latest_signal_decision": {"decision_type": "base_entry", "symbol": "BLESSUSDT"},
                "latest_account_snapshot": {
                    "wallet_balance": "1234.56",
                    "available_balance": "1200.00",
                    "equity": "1260.12",
                    "unrealized_pnl": "25.56",
                    "position_count": 1,
                    "open_order_count": 2,
                },
            },
            "event_counts": {"poll_tick": 3},
            "source_counts": {"poll": 3},
            "leader_history": [{"timestamp": "2026-04-15T08:49:00+00:00", "symbol": "BLESSUSDT"}],
            "pulse_points": [{"bucket": "2026-04-15T08:49:00+00:00", "event_count": 3}],
            "recent_signal_decisions": [{"timestamp": "2026-04-15T08:49:00+00:00", "decision_type": "base_entry"}],
            "recent_broker_orders": [{"timestamp": "2026-04-15T08:49:01+00:00", "action_type": "submit_order"}],
            "recent_position_snapshots": [{"timestamp": "2026-04-15T08:49:00+00:00", "leader_symbol": "BLESSUSDT"}],
            "recent_account_snapshots": [
                {
                    "timestamp": "2026-04-15T08:48:00+00:00",
                    "wallet_balance": "1230.00",
                    "available_balance": "1190.00",
                    "equity": "1250.00",
                    "unrealized_pnl": "20.00",
                    "position_count": 1,
                    "open_order_count": 1,
                    "leader_symbol": "ONUSDT",
                },
                {
                    "timestamp": "2026-04-15T08:49:00+00:00",
                    "wallet_balance": "1234.56",
                    "available_balance": "1200.00",
                    "equity": "1260.12",
                    "unrealized_pnl": "25.56",
                    "position_count": 1,
                    "open_order_count": 2,
                    "leader_symbol": "BLESSUSDT",
                },
            ],
            "recent_events": [{"timestamp": "2026-04-15T08:49:00+00:00", "event_type": "poll_tick"}],
            "warnings": [],
        }

        summary = build_dashboard_summary_payload(snapshot)
        timeseries = build_dashboard_timeseries_payload(snapshot)
        tables = build_dashboard_tables_payload(snapshot)

        self.assertEqual(summary["account"]["wallet_balance"], 1234.56)
        self.assertEqual(summary["runtime"]["previous_leader_symbol"], "BLESSUSDT")
        self.assertEqual(timeseries["account"][0]["timestamp"], "2026-04-15T08:48:00+00:00")
        self.assertEqual(timeseries["account"][1]["equity"], 1260.12)
        self.assertEqual(tables["recent_signal_decisions"][0]["decision_type"], "base_entry")
        self.assertEqual(tables["recent_account_snapshots"][1]["leader_symbol"], "BLESSUSDT")

    def test_load_dashboard_snapshot_uses_runtime_db_when_audit_file_missing(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot
        from momentum_alpha.runtime_store import bootstrap_runtime_db, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
            state_file = root / "state.json"
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"

            state_file.write_text(
                json.dumps({"previous_leader_symbol": "ONUSDT", "positions": {}, "order_statuses": {}}),
                encoding="utf-8",
            )
            for path in (state_file, poll_log_file, user_stream_log_file):
                if path is not state_file:
                    path.write_text("", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))
            bootstrap_runtime_db(path=runtime_db_file)
            os.utime(runtime_db_file, (now.timestamp(), now.timestamp()))
            insert_audit_event(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 58, tzinfo=timezone.utc),
                event_type="poll_worker_start",
                payload={"symbol_count": 538},
                source="poll",
            )
            insert_audit_event(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, tzinfo=timezone.utc),
                event_type="tick_result",
                payload={"next_previous_leader_symbol": "ONUSDT"},
                source="poll",
            )

            snapshot = load_dashboard_snapshot(
                now=now,
                state_file=state_file,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                audit_log_file=root / "missing-audit.jsonl",
                runtime_db_file=runtime_db_file,
                recent_limit=10,
            )

            self.assertEqual(snapshot["health"]["overall_status"], "OK")
            self.assertEqual(snapshot["event_counts"]["poll_worker_start"], 1)
            self.assertEqual(snapshot["source_counts"]["poll"], 2)
            self.assertEqual(snapshot["leader_history"][0]["symbol"], "ONUSDT")

    def test_build_position_details_extracts_legs_from_payload(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        position_snapshot = {
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "stop_price": "81000",
                        "legs": [
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.01",
                                "entry_price": "82000",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T09:15:00+00:00",
                                "leg_type": "base"
                            },
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.005",
                                "entry_price": "82500",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T10:00:00+00:00",
                                "leg_type": "add_on"
                            }
                        ]
                    }
                }
            }
        }

        details = build_position_details(position_snapshot)

        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["symbol"], "BTCUSDT")
        self.assertEqual(details[0]["total_quantity"], "0.015")
        self.assertEqual(details[0]["entry_price"], "82166.67")
        self.assertEqual(details[0]["stop_price"], "81000")
        self.assertAlmostEqual(float(details[0]["risk"]), 17.50, places=2)

    def test_build_position_details_returns_empty_list_for_missing_payload(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        details = build_position_details({})
        self.assertEqual(details, [])

        details = build_position_details({"payload": {}})
        self.assertEqual(details, [])

    def test_render_trade_history_table_generates_html_rows(self) -> None:
        from momentum_alpha.dashboard import render_trade_history_table

        orders = [
            {
                "timestamp": "2026-04-15T09:15:23+00:00",
                "symbol": "BTCUSDT",
                "action_type": "base_entry",
                "side": "BUY",
                "quantity": 0.015,
                "order_status": "FILLED",
            },
            {
                "timestamp": "2026-04-15T08:30:15+00:00",
                "symbol": "ETHUSDT",
                "action_type": "add_on_entry",
                "side": "BUY",
                "quantity": 0.12,
                "order_status": "NEW",
            },
        ]

        html = render_trade_history_table(orders)

        self.assertIn("BTCUSDT", html)
        self.assertIn("ETHUSDT", html)
        self.assertIn("base_entry", html)
        self.assertIn("add_on_entry", html)
        self.assertIn("09:15:23", html)
        self.assertIn("08:30:15", html)
        self.assertIn("0.015", html)
        self.assertIn("0.12", html)
        self.assertIn("FILLED", html)
        self.assertIn("NEW", html)

    def test_render_trade_history_table_shows_empty_message(self) -> None:
        from momentum_alpha.dashboard import render_trade_history_table

        html = render_trade_history_table([])
        self.assertIn("No orders", html)

    def test_build_strategy_config_extracts_from_runtime_config(self) -> None:
        from momentum_alpha.dashboard import build_strategy_config

        config = build_strategy_config(
            stop_budget_usdt="10",
            entry_start_hour_utc=1,
            entry_end_hour_utc=23,
            testnet=True,
            submit_orders=False,
        )

        self.assertEqual(config["stop_budget_usdt"], "10")
        self.assertEqual(config["entry_window"], "01:00-23:00 UTC")
        self.assertEqual(config["testnet"], True)
        self.assertEqual(config["submit_orders"], False)

    def test_render_position_cards_generates_html(self) -> None:
        from momentum_alpha.dashboard import render_position_cards

        positions = [
            {
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "total_quantity": "0.015",
                "entry_price": "82166.67",
                "stop_price": "81000",
                "risk": "17.50",
                "legs": [
                    {"type": "base", "time": "2026-04-15T09:15:00+00:00"},
                    {"type": "add_on", "time": "2026-04-15T10:00:00+00:00"},
                ],
            }
        ]

        html = render_position_cards(positions)

        self.assertIn("BTCUSDT", html)
        self.assertIn("LONG", html)
        self.assertIn("0.015", html)
        self.assertIn("82166.67", html)
        self.assertIn("81000", html)
        self.assertIn("17.50", html)
        self.assertIn("base", html)
        self.assertIn("add_on", html)

    def test_render_position_cards_shows_empty_message(self) -> None:
        from momentum_alpha.dashboard import render_position_cards

        html = render_position_cards([])
        self.assertIn("No positions", html)

    def test_render_dashboard_html_includes_positions_section(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html({
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "BTCUSDT",
                "position_count": 1,
                "order_status_count": 2,
                "latest_position_snapshot": {
                    "payload": {
                        "positions": {
                            "BTCUSDT": {
                                "symbol": "BTCUSDT",
                                "stop_price": "81000",
                                "legs": [{"symbol": "BTCUSDT", "quantity": "0.01", "entry_price": "82000", "stop_price": "81000", "opened_at": "2026-04-15T09:15:00+00:00", "leg_type": "base"}]
                            }
                        }
                    }
                },
                "latest_account_snapshot": {"wallet_balance": "1000", "equity": "1000"},
                "latest_signal_decision": {},
            },
            "recent_broker_orders": [],
            "recent_account_snapshots": [],
            "recent_events": [],
            "event_counts": {},
            "source_counts": {},
            "leader_history": [],
            "pulse_points": [],
            "warnings": [],
        }, strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": True, "submit_orders": False})

        self.assertIn("POSITIONS", html)
        self.assertIn("TRADE HISTORY", html)
        self.assertIn("STRATEGY CONFIG", html)
        self.assertIn("Stop Budget", html)
        self.assertIn("10", html)
