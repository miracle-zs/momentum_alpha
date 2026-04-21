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


if __name__ == "__main__":
    unittest.main()
