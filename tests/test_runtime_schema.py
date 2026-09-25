import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeSchemaTests(unittest.TestCase):
    def test_runtime_schema_bootstraps_runtime_database_tables(self) -> None:
        from momentum_alpha import runtime_schema

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            runtime_schema.bootstrap_runtime_db(path=db_path)

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
            finally:
                connection.close()

        self.assertTrue(
            {
                "audit_events",
                "strategy_state",
                "notification_statuses",
            }.issubset(tables)
        )

    def test_runtime_connections_wait_for_writers(self) -> None:
        from momentum_alpha import runtime_schema

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            runtime_schema.bootstrap_runtime_db(path=db_path)
            with runtime_schema._connect(db_path) as connection:
                self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 30000)

    def test_runtime_connection_can_be_reused_by_nested_reads(self) -> None:
        from momentum_alpha import runtime_schema

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            runtime_schema.bootstrap_runtime_db(path=db_path)
            with runtime_schema._connect(db_path) as connection:
                with runtime_schema._reuse_runtime_connection(path=db_path, connection=connection):
                    with runtime_schema._connect(db_path) as nested_connection:
                        self.assertIs(nested_connection, connection)

    def test_runtime_schema_migrates_existing_runtime_database_columns(self) -> None:
        from momentum_alpha import runtime_schema

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            connection = sqlite3.connect(db_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE audit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        source TEXT
                    );
                    INSERT INTO audit_events(timestamp, event_type, payload_json, source)
                    VALUES ('2026-04-15T14:00:00+00:00', 'tick_result', '{"symbol":"BTCUSDT"}', 'poll');

                    CREATE TABLE broker_orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        source TEXT,
                        symbol TEXT,
                        action_type TEXT NOT NULL,
                        order_type TEXT,
                        order_id TEXT,
                        client_order_id TEXT,
                        order_status TEXT,
                        side TEXT,
                        quantity REAL,
                        price REAL,
                        payload_json TEXT NOT NULL
                    );
                    INSERT INTO broker_orders(timestamp, source, symbol, action_type, order_type, order_id, client_order_id, order_status, side, quantity, price, payload_json)
                    VALUES ('2026-04-15T14:00:01+00:00', 'poll', 'BTCUSDT', 'submit_execution_plan', 'MARKET', '101', 'ma_260415140001_BTCUSDT_b00e', 'NEW', 'BUY', 1, 100.0, '{}');
                    """
                )
                connection.commit()
            finally:
                connection.close()

            runtime_schema.bootstrap_runtime_db(path=db_path)

            connection = sqlite3.connect(db_path)
            try:
                audit_columns = {row[1] for row in connection.execute("PRAGMA table_info(audit_events)")}
                broker_columns = {row[1] for row in connection.execute("PRAGMA table_info(broker_orders)")}
                audit_row = connection.execute(
                    "SELECT decision_id, intent_id, event_type FROM audit_events"
                ).fetchone()
                broker_row = connection.execute(
                    "SELECT client_algo_id, decision_id, intent_id FROM broker_orders"
                ).fetchone()
            finally:
                connection.close()

        self.assertIn("decision_id", audit_columns)
        self.assertIn("intent_id", audit_columns)
        self.assertIn("client_algo_id", broker_columns)
        self.assertIn("decision_id", broker_columns)
        self.assertIn("intent_id", broker_columns)
        self.assertEqual(audit_row, (None, None, "tick_result"))
        self.assertEqual(broker_row, (None, None, None))

    def test_readonly_connection_behavior(self) -> None:
        from momentum_alpha import runtime_schema

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            missing_path = Path(tmpdir) / "missing.db"
            with self.assertRaises(FileNotFoundError):
                with runtime_schema._connect(missing_path, readonly=True):
                    pass

            runtime_schema.bootstrap_runtime_db(path=db_path)
            with runtime_schema._connect(db_path, readonly=True) as ro_conn:
                rows = ro_conn.execute("SELECT 1").fetchall()
                self.assertEqual(rows, [(1,)])
                with self.assertRaises(sqlite3.OperationalError):
                    ro_conn.execute("CREATE TABLE test_fail (id INT)")

    def test_begin_immediate_with_retry_metrics(self) -> None:
        import threading
        import time
        from momentum_alpha import runtime_schema

        runtime_schema.reset_sqlite_lock_stats()
        initial_stats = runtime_schema.get_sqlite_lock_stats()
        self.assertEqual(initial_stats["total_immediate_acquires"], 0)
        self.assertEqual(initial_stats["total_immediate_contentions"], 0)

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            runtime_schema.bootstrap_runtime_db(path=db_path)

            # 1. No contention acquire
            with runtime_schema._connect(db_path) as conn:
                wait_time = runtime_schema.begin_immediate_with_retry(conn)
                self.assertGreaterEqual(wait_time, 0.0)
                conn.commit()

            stats = runtime_schema.get_sqlite_lock_stats()
            self.assertEqual(stats["total_immediate_acquires"], 1)
            self.assertEqual(stats["total_immediate_contentions"], 0)

            # 2. Contention acquire with simulated locked database on first attempt
            logs: list[str] = []

            class ContendedConnection:
                def __init__(self):
                    self.attempts = 0

                def execute(self, sql):
                    if sql.startswith("PRAGMA"):
                        return None
                    self.attempts += 1
                    if self.attempts == 1:
                        raise sqlite3.OperationalError("database is locked")
                    return None

            contended_conn = ContendedConnection()
            wait_time = runtime_schema.begin_immediate_with_retry(contended_conn, logger_fn=logs.append)
            self.assertGreater(wait_time, 0.0)
            self.assertEqual(contended_conn.attempts, 2)

            stats_after = runtime_schema.get_sqlite_lock_stats()
            self.assertEqual(stats_after["total_immediate_acquires"], 2)
            self.assertEqual(stats_after["total_immediate_contentions"], 1)
            self.assertGreater(stats_after["total_wait_seconds"], 0.0)
            self.assertGreater(stats_after["max_wait_seconds"], 0.0)
            self.assertTrue(any("contention" in log for log in logs))

            # Reset stats
            runtime_schema.reset_sqlite_lock_stats()
            cleared_stats = runtime_schema.get_sqlite_lock_stats()
            self.assertEqual(cleared_stats["total_immediate_acquires"], 0)
            self.assertEqual(cleared_stats["total_immediate_contentions"], 0)


if __name__ == "__main__":
    unittest.main()
