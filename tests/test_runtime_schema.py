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


if __name__ == "__main__":
    unittest.main()
