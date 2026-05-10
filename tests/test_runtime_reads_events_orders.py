import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeReadsEventsOrdersTests(unittest.TestCase):
    def test_resolve_order_linkage_reads_algo_order_intent_without_client_order_id_column(self) -> None:
        from momentum_alpha.runtime_reads_events_orders import resolve_order_linkage
        from momentum_alpha.runtime_store import bootstrap_runtime_db, insert_algo_order

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_algo_order(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
                source="poll",
                symbol="BTCUSDT",
                algo_id="algo-1",
                client_algo_id="ma_260415080000_BTCUSDT_b00s",
                decision_id="dec-1",
                intent_id="ma_260415080000_BTCUSDT_b00",
                algo_status="TRIGGERED",
                side="SELL",
                order_type="STOP_MARKET",
                trigger_price="100.0",
                payload={"status": "TRIGGERED"},
            )

            linkage = resolve_order_linkage(
                path=db_path,
                client_algo_id="ma_260415080000_BTCUSDT_b00s",
            )

            self.assertIsNotNone(linkage)
            self.assertEqual(linkage["decision_id"], "dec-1")
            self.assertEqual(linkage["intent_id"], "ma_260415080000_BTCUSDT_b00")
            self.assertEqual(linkage["client_algo_id"], "ma_260415080000_BTCUSDT_b00s")
            self.assertIsNone(linkage["client_order_id"])
            self.assertIsNone(linkage["order_id"])
            self.assertEqual(linkage["matched_on"], "algo_orders.intent_id")


if __name__ == "__main__":
    unittest.main()
