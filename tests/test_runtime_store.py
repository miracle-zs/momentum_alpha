import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeStoreTests(unittest.TestCase):
    def test_bootstrap_and_insert_audit_event(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_audit_event_counts,
            fetch_recent_audit_events,
            insert_audit_event,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_audit_event(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
                event_type="tick_result",
                payload={"symbol_count": 538, "leader": "INUSDT"},
                source="poll",
            )

            events = fetch_recent_audit_events(path=db_path, limit=10)
            counts = fetch_audit_event_counts(path=db_path, limit=10)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "tick_result")
            self.assertEqual(events[0]["payload"]["leader"], "INUSDT")
            self.assertEqual(events[0]["source"], "poll")
            self.assertEqual(counts, {"tick_result": 1})

    def test_fetch_recent_audit_events_returns_newest_first(self) -> None:
        from momentum_alpha.runtime_store import bootstrap_runtime_db, fetch_recent_audit_events, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_audit_event(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
                event_type="poll_tick",
                payload={"symbol_count": 538},
            )
            insert_audit_event(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc),
                event_type="user_stream_worker_start",
                payload={"position_count": 0},
            )

            events = fetch_recent_audit_events(path=db_path, limit=10)
            self.assertEqual([event["event_type"] for event in events], ["user_stream_worker_start", "poll_tick"])

    def test_bootstrap_runtime_db_is_idempotent(self) -> None:
        from momentum_alpha.runtime_store import bootstrap_runtime_db

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            bootstrap_runtime_db(path=db_path)
            self.assertTrue(db_path.exists())

    def test_bootstrap_creates_structured_tables(self) -> None:
        from momentum_alpha.runtime_store import bootstrap_runtime_db

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            import sqlite3

            with sqlite3.connect(db_path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }

            self.assertTrue({"signal_decisions", "broker_orders", "position_snapshots"}.issubset(tables))

    def test_structured_inserts_preserve_summary_fields(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_recent_broker_orders,
            fetch_recent_position_snapshots,
            fetch_recent_signal_decisions,
            insert_broker_order,
            insert_position_snapshot,
            insert_signal_decision,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            first_timestamp = datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc)
            second_timestamp = datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc)

            insert_signal_decision(
                path=db_path,
                timestamp=first_timestamp,
                source="poll",
                decision_type="base_entry",
                symbol="BLESSUSDT",
                previous_leader_symbol="ONUSDT",
                next_leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=0,
                payload={"note": "leader switch"},
            )
            insert_broker_order(
                path=db_path,
                timestamp=second_timestamp,
                source="poll",
                symbol="BLESSUSDT",
                action_type="submit",
                order_status="FILLED",
                side="BUY",
                order_id="12345",
                client_order_id="abc-123",
                payload={"filled_qty": "1.25"},
            )
            insert_position_snapshot(
                path=db_path,
                timestamp=second_timestamp,
                source="poll",
                leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=2,
                symbol_count=538,
                submit_orders=True,
                restore_positions=True,
                execute_stop_replacements=False,
                payload={"mode": "LIVE"},
            )

            signal_decisions = fetch_recent_signal_decisions(path=db_path, limit=10)
            broker_orders = fetch_recent_broker_orders(path=db_path, limit=10)
            snapshots = fetch_recent_position_snapshots(path=db_path, limit=10)

            self.assertEqual(signal_decisions[0]["decision_type"], "base_entry")
            self.assertEqual(signal_decisions[0]["previous_leader_symbol"], "ONUSDT")
            self.assertEqual(signal_decisions[0]["next_leader_symbol"], "BLESSUSDT")
            self.assertEqual(signal_decisions[0]["payload"]["note"], "leader switch")
            self.assertEqual(broker_orders[0]["action_type"], "submit")
            self.assertEqual(broker_orders[0]["order_status"], "FILLED")
            self.assertEqual(broker_orders[0]["payload"]["filled_qty"], "1.25")
            self.assertEqual(snapshots[0]["leader_symbol"], "BLESSUSDT")
            self.assertTrue(snapshots[0]["submit_orders"])
            self.assertEqual(snapshots[0]["symbol_count"], 538)

    def test_dashboard_helpers_return_leader_history_and_pulse_points(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_event_pulse_points,
            fetch_leader_history,
            insert_broker_order,
            insert_position_snapshot,
            insert_signal_decision,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            insert_position_snapshot(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
                source="poll",
                leader_symbol="ONUSDT",
                position_count=0,
                order_status_count=0,
                symbol_count=538,
                submit_orders=True,
                restore_positions=True,
                execute_stop_replacements=True,
                payload={},
            )
            insert_signal_decision(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc),
                source="poll",
                decision_type="base_entry",
                symbol="BLESSUSDT",
                previous_leader_symbol="ONUSDT",
                next_leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=0,
                payload={},
            )
            insert_broker_order(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc),
                source="poll",
                symbol="BLESSUSDT",
                action_type="submit",
                order_status="NEW",
                side="BUY",
                payload={},
            )
            insert_position_snapshot(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 2, tzinfo=timezone.utc),
                source="poll",
                leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=1,
                symbol_count=538,
                submit_orders=True,
                restore_positions=True,
                execute_stop_replacements=False,
                payload={},
            )

            leader_history = fetch_leader_history(path=db_path, limit=10)
            pulse_points = fetch_event_pulse_points(
                path=db_path,
                now=datetime(2026, 4, 15, 8, 5, tzinfo=timezone.utc),
                since_minutes=10,
                bucket_minutes=1,
                limit=10,
            )

            self.assertEqual([row["symbol"] for row in leader_history], ["BLESSUSDT", "ONUSDT"])
            self.assertEqual([row["bucket"] for row in pulse_points[-3:]], [
                "2026-04-15T08:00:00+00:00",
                "2026-04-15T08:01:00+00:00",
                "2026-04-15T08:02:00+00:00",
            ])
            self.assertEqual([row["event_count"] for row in pulse_points[-3:]], [1, 2, 1])
