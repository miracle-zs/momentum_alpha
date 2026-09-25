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
        from momentum_alpha.runtime_schema import _connect
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

            # Insert old and new signal decisions
            with _connect(db_path) as conn:
                conn.execute(
                    "INSERT INTO signal_decisions(timestamp, decision_type, payload_json) VALUES (?, 'base_entry', '{}')",
                    (old_timestamp.isoformat(),),
                )
                conn.execute(
                    "INSERT INTO signal_decisions(timestamp, decision_type, payload_json) VALUES (?, 'base_entry', '{}')",
                    (recent_timestamp.isoformat(),),
                )

            summary = prune_runtime_db(
                path=db_path,
                now=datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
                audit_retention_days=7,
                snapshot_retention_days=7,
                signal_decision_retention_days=7,
            )

            self.assertEqual(summary["audit_events_deleted"], 1)
            self.assertEqual(summary["position_snapshots_deleted"], 1)
            self.assertEqual(summary["account_snapshots_deleted"], 1)
            self.assertEqual(summary["signal_decisions_deleted"], 1)
            self.assertEqual(summary["audit_cutoff"], "2026-04-19T08:00:00+00:00")
            self.assertEqual(summary["snapshot_cutoff"], "2026-04-19T08:00:00+00:00")
            self.assertEqual(summary["signal_decision_cutoff"], "2026-04-19T08:00:00+00:00")

            audit_events = fetch_recent_audit_events(path=db_path, limit=10)
            position_snapshots = fetch_recent_position_snapshots(path=db_path, limit=10)
            account_snapshots = fetch_recent_account_snapshots(path=db_path, limit=10)

            self.assertEqual(len(audit_events), 1)
            self.assertEqual(audit_events[0]["payload"]["old"], False)
            self.assertEqual(len(position_snapshots), 1)
            self.assertEqual(position_snapshots[0]["payload"]["old"], False)
            self.assertEqual(len(account_snapshots), 1)
            self.assertEqual(account_snapshots[0]["payload"]["old"], False)

            with _connect(db_path, readonly=True) as conn:
                remaining_decisions = conn.execute("SELECT COUNT(*) FROM signal_decisions").fetchone()[0]
            self.assertEqual(remaining_decisions, 1)

    def test_backup_runtime_db_snapshot_and_rotation(self) -> None:
        from momentum_alpha.runtime_cleanup import backup_runtime_db
        from momentum_alpha.runtime_schema import bootstrap_runtime_db, _connect

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            backup_dir = Path(tmpdir) / "backups"
            bootstrap_runtime_db(path=db_path)

            with _connect(db_path) as conn:
                conn.execute("INSERT INTO signal_decisions(timestamp, decision_type, payload_json) VALUES ('2026-04-15', 'base_entry', '{\"k\": 1}')")

            # 1. Create first backup
            t1 = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)
            backup1 = backup_runtime_db(source_path=db_path, backup_dir=backup_dir, max_backups=2, now=t1)
            self.assertIsNotNone(backup1)
            self.assertTrue(backup1.exists())

            # Verify backup content
            with _connect(backup1, readonly=True) as b_conn:
                rows = b_conn.execute("SELECT decision_type FROM signal_decisions").fetchall()
                self.assertEqual(rows, [("base_entry",)])

            # 2. Create second and third backups to test rotation (max_backups=2)
            t2 = datetime(2026, 4, 15, 11, 0, 0, tzinfo=timezone.utc)
            backup2 = backup_runtime_db(source_path=db_path, backup_dir=backup_dir, max_backups=2, now=t2)
            self.assertTrue(backup2.exists())

            t3 = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
            backup3 = backup_runtime_db(source_path=db_path, backup_dir=backup_dir, max_backups=2, now=t3)
            self.assertTrue(backup3.exists())

            # Only 2 newest backups should remain
            all_backups = list(backup_dir.glob("runtime_backup_*.db"))
            self.assertEqual(len(all_backups), 2)
            self.assertNotIn(backup1, all_backups)
            self.assertIn(backup3, all_backups)

    def test_prune_runtime_db_with_archive_transfuse(self) -> None:
        from momentum_alpha.runtime_cleanup import prune_runtime_db
        from momentum_alpha.runtime_schema import bootstrap_runtime_db, _connect

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            archive_path = Path(tmpdir) / "archive.db"
            backup_dir = Path(tmpdir) / "backups"
            bootstrap_runtime_db(path=db_path)

            old_timestamp = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)
            recent_timestamp = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)

            with _connect(db_path) as conn:
                conn.execute(
                    "INSERT INTO audit_events(timestamp, event_type, payload_json) VALUES (?, 'tick', '{\"val\": 1}')",
                    (old_timestamp.isoformat(),),
                )
                conn.execute(
                    "INSERT INTO audit_events(timestamp, event_type, payload_json) VALUES (?, 'tick', '{\"val\": 2}')",
                    (recent_timestamp.isoformat(),),
                )
                conn.execute(
                    "INSERT INTO signal_decisions(timestamp, decision_type, payload_json) VALUES (?, 'base_entry', '{\"val\": 10}')",
                    (old_timestamp.isoformat(),),
                )
                conn.execute(
                    "INSERT INTO signal_decisions(timestamp, decision_type, payload_json) VALUES (?, 'base_entry', '{\"val\": 20}')",
                    (recent_timestamp.isoformat(),),
                )

            summary = prune_runtime_db(
                path=db_path,
                now=datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
                audit_retention_days=7,
                snapshot_retention_days=7,
                signal_decision_retention_days=7,
                archive_path=archive_path,
                backup_before_prune=True,
                backup_dir=backup_dir,
            )

            self.assertIsNotNone(summary["backup_file"])
            self.assertTrue(Path(summary["backup_file"]).exists())
            self.assertEqual(summary["audit_events_deleted"], 1)
            self.assertEqual(summary["signal_decisions_deleted"], 1)
            self.assertEqual(summary["total_archived"], 2)

            # Check that archive_db received the 2 pruned rows
            with _connect(archive_path, readonly=True) as arch_conn:
                arch_audits = arch_conn.execute("SELECT payload_json FROM audit_events").fetchall()
                arch_signals = arch_conn.execute("SELECT payload_json FROM signal_decisions").fetchall()
                self.assertEqual(len(arch_audits), 1)
                self.assertIn("1", arch_audits[0][0])
                self.assertEqual(len(arch_signals), 1)
                self.assertIn("10", arch_signals[0][0])

            # Check that main db only retained recent rows
            with _connect(db_path, readonly=True) as main_conn:
                main_audits = main_conn.execute("SELECT payload_json FROM audit_events").fetchall()
                main_signals = main_conn.execute("SELECT payload_json FROM signal_decisions").fetchall()
                self.assertEqual(len(main_audits), 1)
                self.assertIn("2", main_audits[0][0])
                self.assertEqual(len(main_signals), 1)
                self.assertIn("20", main_signals[0][0])
