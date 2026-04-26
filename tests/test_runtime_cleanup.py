from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeCleanupTests(unittest.TestCase):
    def test_prune_runtime_db_removes_old_audit_and_snapshot_rows(self) -> None:
        from momentum_alpha.runtime_cleanup import prune_runtime_db
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_recent_audit_events,
            fetch_recent_account_snapshots,
            fetch_recent_position_snapshots,
            insert_audit_event,
            insert_account_snapshot,
            insert_position_snapshot,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            old_timestamp = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)
            recent_timestamp = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)

            insert_audit_event(
                path=db_path,
                timestamp=old_timestamp,
                event_type="tick_result",
                payload={"old": True},
            )
            insert_audit_event(
                path=db_path,
                timestamp=recent_timestamp,
                event_type="tick_result",
                payload={"old": False},
            )
            insert_position_snapshot(
                path=db_path,
                timestamp=old_timestamp,
                source="poll",
                leader_symbol="BTCUSDT",
                position_count=1,
                order_status_count=0,
                payload={"old": True},
            )
            insert_position_snapshot(
                path=db_path,
                timestamp=recent_timestamp,
                source="poll",
                leader_symbol="ETHUSDT",
                position_count=2,
                order_status_count=1,
                payload={"old": False},
            )
            insert_account_snapshot(
                path=db_path,
                timestamp=old_timestamp,
                source="user-stream",
                position_count=1,
                open_order_count=0,
                payload={"old": True},
            )
            insert_account_snapshot(
                path=db_path,
                timestamp=recent_timestamp,
                source="user-stream",
                position_count=2,
                open_order_count=1,
                payload={"old": False},
            )

            summary = prune_runtime_db(
                path=db_path,
                now=datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
                audit_retention_days=7,
                snapshot_retention_days=7,
            )

            self.assertEqual(summary["audit_events_deleted"], 1)
            self.assertEqual(summary["position_snapshots_deleted"], 1)
            self.assertEqual(summary["account_snapshots_deleted"], 1)
            self.assertEqual(summary["audit_cutoff"], "2026-04-19T08:00:00+00:00")
            self.assertEqual(summary["snapshot_cutoff"], "2026-04-19T08:00:00+00:00")

            audit_events = fetch_recent_audit_events(path=db_path, limit=10)
            position_snapshots = fetch_recent_position_snapshots(path=db_path, limit=10)
            account_snapshots = fetch_recent_account_snapshots(path=db_path, limit=10)

            self.assertEqual(len(audit_events), 1)
            self.assertEqual(audit_events[0]["payload"]["old"], False)
            self.assertEqual(len(position_snapshots), 1)
            self.assertEqual(position_snapshots[0]["payload"]["old"], False)
            self.assertEqual(len(account_snapshots), 1)
            self.assertEqual(account_snapshots[0]["payload"]["old"], False)
