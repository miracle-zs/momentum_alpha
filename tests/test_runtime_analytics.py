import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeAnalyticsTests(unittest.TestCase):
    def test_runtime_analytics_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import (
            runtime_analytics_common,
            runtime_analytics_legs,
            runtime_analytics_rebuild,
            runtime_analytics_stops,
        )

        self.assertTrue(callable(runtime_analytics_common._text_to_decimal))
        self.assertTrue(callable(runtime_analytics_common._text_to_optional_decimal))
        self.assertTrue(callable(runtime_analytics_legs._build_trade_round_trip_leg_payload))
        self.assertTrue(callable(runtime_analytics_stops._resolve_stop_trigger_price_for_exit))
        self.assertTrue(callable(runtime_analytics_rebuild.rebuild_trade_analytics))

    def test_runtime_analytics_module_rebuilds_trade_round_trip_rows(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_recent_trade_round_trips,
            insert_broker_order,
            insert_trade_fill,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            entry_time = datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc)
            exit_time = datetime(2026, 4, 15, 8, 5, tzinfo=timezone.utc)

            insert_trade_fill(
                path=db_path,
                timestamp=entry_time,
                source="user-stream",
                symbol="BTCUSDT",
                order_id="entry-1",
                trade_id="trade-entry-1",
                client_order_id="btc-b1e",
                order_status="FILLED",
                execution_type="TRADE",
                side="BUY",
                order_type="MARKET",
                quantity="1",
                cumulative_quantity="1",
                average_price="100",
                last_price="100",
                realized_pnl="0",
                commission="0.1",
                commission_asset="USDT",
                payload={},
            )
            insert_trade_fill(
                path=db_path,
                timestamp=exit_time,
                source="user-stream",
                symbol="BTCUSDT",
                order_id="exit-1",
                trade_id="trade-exit-1",
                client_order_id="btc-b1s",
                order_status="FILLED",
                execution_type="TRADE",
                side="SELL",
                order_type="MARKET",
                quantity="1",
                cumulative_quantity="1",
                average_price="120",
                last_price="120",
                realized_pnl="20",
                commission="0.1",
                commission_asset="USDT",
                payload={},
            )
            insert_broker_order(
                path=db_path,
                timestamp=entry_time,
                source="poll",
                symbol="BTCUSDT",
                action_type="submit",
                order_status="FILLED",
                side="BUY",
                order_id="entry-1",
                client_order_id="btc-b1e",
                payload={"type": "MARKET"},
            )

            from momentum_alpha import runtime_analytics

            runtime_analytics.rebuild_trade_analytics(path=db_path)

            rounds = fetch_recent_trade_round_trips(path=db_path, limit=10)

            self.assertEqual(len(rounds), 1)
            self.assertEqual(rounds[0]["symbol"], "BTCUSDT")
            self.assertEqual(rounds[0]["exit_reason"], "sell")


if __name__ == "__main__":
    unittest.main()
