from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _FakeSyncClient:
    def __init__(self) -> None:
        self.income_calls: list[dict] = []
        self.order_calls: list[dict] = []
        self.trade_calls: list[dict] = []
        self.incomes: list[dict] = []
        self.orders: dict[str, list[dict]] = {}
        self.trades: dict[str, list[dict]] = {}
        self.order_error: Exception | None = None
        self.trade_error: Exception | None = None

    def fetch_income_history(self, **kwargs):
        self.income_calls.append(kwargs)
        return self.incomes

    def fetch_all_orders(self, **kwargs):
        self.order_calls.append(kwargs)
        if self.order_error is not None:
            raise self.order_error
        return self.orders.get(kwargs["symbol"], [])

    def fetch_user_trades(self, **kwargs):
        self.trade_calls.append(kwargs)
        if self.trade_error is not None:
            raise self.trade_error
        return self.trades.get(kwargs["symbol"], [])


class _RateLimitError(RuntimeError):
    status_code = 429


class TradeDataSyncTests(unittest.TestCase):
    def test_legacy_manual_backfill_stops_immediately_on_order_429(self) -> None:
        from momentum_alpha.cli_backfill import backfill_binance_user_trades

        class Client:
            def __init__(self) -> None:
                self.order_symbols = []
                self.trade_symbols = []

            def fetch_all_orders(self, **kwargs):
                self.order_symbols.append(kwargs["symbol"])
                raise _RateLimitError("too many requests")

            def fetch_user_trades(self, **kwargs):
                self.trade_symbols.append(kwargs["symbol"])
                return []

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            client = Client()
            with self.assertRaises(_RateLimitError):
                backfill_binance_user_trades(
                    client=client,
                    runtime_db_path=Path(tmpdir) / "runtime.db",
                    start_time=now - timedelta(hours=1),
                    end_time=now,
                    symbols=["BTCUSDT", "ETHUSDT"],
                    logger=lambda _message: None,
                )

        self.assertEqual(client.order_symbols, ["BTCUSDT"])
        self.assertEqual(client.trade_symbols, [])

    def test_dirty_version_prevents_same_timestamp_event_from_being_cleared(self) -> None:
        from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            store = RuntimeSyncStateStore(path=Path(tmpdir) / "runtime.db")
            store.mark_dirty(symbol="BTCUSDT", reason="order", observed_at=now)
            observed = store.dirty_symbols()[0]
            store.mark_dirty(symbol="BTCUSDT", reason="trade", observed_at=now)
            cleared = store.clear_dirty(
                symbol="BTCUSDT",
                observed_version=observed.version,
            )
            remaining = store.dirty_symbols()

        self.assertFalse(cleared)
        self.assertEqual(remaining[0].version, observed.version + 1)
        self.assertEqual(set(remaining[0].reasons), {"order", "trade"})

    def test_first_cursor_bootstrap_syncs_recent_locally_known_symbols_once(self) -> None:
        from momentum_alpha.runtime_store import insert_broker_order
        from momentum_alpha.trade_data_sync import run_incremental_trade_data_sync

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            insert_broker_order(
                path=path,
                timestamp=now - timedelta(hours=1),
                source="poll",
                action_type="submit_order",
                symbol="BTCUSDT",
                order_id="101",
                client_order_id="ma_test",
                order_status="NEW",
                side="BUY",
                payload={"orderId": 101},
            )
            client = _FakeSyncClient()
            first = run_incremental_trade_data_sync(
                client=client,
                runtime_db_path=path,
                now=now,
                logger=lambda _message: None,
            )
            second_client = _FakeSyncClient()
            second = run_incremental_trade_data_sync(
                client=second_client,
                runtime_db_path=path,
                now=now + timedelta(minutes=15),
                logger=lambda _message: None,
            )

        self.assertEqual(first.request_weight, 40)
        self.assertEqual([call["symbol"] for call in client.order_calls], ["BTCUSDT"])
        self.assertEqual([call["symbol"] for call in client.trade_calls], ["BTCUSDT"])
        self.assertEqual(second.request_weight, 30)
        self.assertEqual(second_client.order_calls, [])

    def test_live_order_priority_defers_backfill_before_any_rest_request(self) -> None:
        from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore
        from momentum_alpha.trade_data_sync import run_incremental_trade_data_sync

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            RuntimeSyncStateStore(path=path).request_control(
                key="live_order_priority",
                requested_at=now,
                reason="stop_repair",
            )
            client = _FakeSyncClient()
            result = run_incremental_trade_data_sync(
                client=client,
                runtime_db_path=path,
                now=now,
                logger=lambda _message: None,
            )

        self.assertTrue(result.live_priority_deferred)
        self.assertEqual(result.request_weight, 0)
        self.assertEqual(client.income_calls, [])
        self.assertEqual(client.order_calls, [])
        self.assertEqual(client.trade_calls, [])

    def test_quiet_round_only_fetches_combined_income_and_costs_30(self) -> None:
        from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore
        from momentum_alpha.trade_data_sync import run_incremental_trade_data_sync

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            client = _FakeSyncClient()
            result = run_incremental_trade_data_sync(
                client=client,
                runtime_db_path=path,
                now=now,
                logger=lambda _message: None,
            )
            cursor = RuntimeSyncStateStore(path=path).get_cursor(kind="income")

        self.assertEqual(result.request_weight, 30)
        self.assertEqual(len(client.income_calls), 1)
        self.assertIsNone(client.income_calls[0]["income_type"])
        self.assertEqual(client.order_calls, [])
        self.assertEqual(client.trade_calls, [])
        self.assertEqual(cursor, now)

    def test_five_dirty_symbols_cost_80_and_are_cleared(self) -> None:
        from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore
        from momentum_alpha.trade_data_sync import run_incremental_trade_data_sync

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        symbols = [f"S{index}USDT" for index in range(5)]
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            store = RuntimeSyncStateStore(path=path)
            for symbol in symbols:
                store.mark_dirty(symbol=symbol, reason="test", observed_at=now - timedelta(minutes=1))
            client = _FakeSyncClient()
            result = run_incremental_trade_data_sync(
                client=client,
                runtime_db_path=path,
                now=now,
                logger=lambda _message: None,
            )
            remaining = store.dirty_symbols()

        self.assertEqual(result.request_weight, 80)
        self.assertEqual([call["symbol"] for call in client.order_calls], symbols)
        self.assertEqual([call["symbol"] for call in client.trade_calls], symbols)
        self.assertEqual(set(result.synced_symbols), set(symbols))
        self.assertEqual(remaining, [])

    def test_cursors_apply_a_bounded_20_minute_overlap(self) -> None:
        from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore
        from momentum_alpha.trade_data_sync import run_incremental_trade_data_sync

        first_now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        second_now = first_now + timedelta(minutes=15)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            store = RuntimeSyncStateStore(path=path)
            store.mark_dirty(symbol="BTCUSDT", reason="first", observed_at=first_now)
            run_incremental_trade_data_sync(
                client=_FakeSyncClient(),
                runtime_db_path=path,
                now=first_now,
                logger=lambda _message: None,
            )
            store.mark_dirty(symbol="BTCUSDT", reason="second", observed_at=second_now)
            client = _FakeSyncClient()
            run_incremental_trade_data_sync(
                client=client,
                runtime_db_path=path,
                now=second_now,
                logger=lambda _message: None,
            )

        expected_start_ms = int((first_now - timedelta(minutes=20)).timestamp() * 1000)
        self.assertEqual(client.income_calls[0]["start_time_ms"], expected_start_ms)
        self.assertEqual(client.order_calls[0]["start_time_ms"], expected_start_ms)
        self.assertEqual(client.trade_calls[0]["start_time_ms"], expected_start_ms)

    def test_new_symbol_after_bootstrap_uses_dirty_overlap_not_36_hours(self) -> None:
        from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore
        from momentum_alpha.trade_data_sync import run_incremental_trade_data_sync

        bootstrap_now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        dirty_at = bootstrap_now + timedelta(hours=2)
        sync_now = dirty_at + timedelta(minutes=5)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            run_incremental_trade_data_sync(
                client=_FakeSyncClient(),
                runtime_db_path=path,
                now=bootstrap_now,
                logger=lambda _message: None,
            )
            RuntimeSyncStateStore(path=path).mark_dirty(
                symbol="NEWUSDT",
                reason="order_trade_update",
                observed_at=dirty_at,
            )
            client = _FakeSyncClient()
            result = run_incremental_trade_data_sync(
                client=client,
                runtime_db_path=path,
                now=sync_now,
                logger=lambda _message: None,
            )

        expected_start_ms = int((dirty_at - timedelta(minutes=20)).timestamp() * 1000)
        self.assertEqual(result.request_weight, 40)
        self.assertEqual(client.order_calls[0]["start_time_ms"], expected_start_ms)
        self.assertEqual(client.trade_calls[0]["start_time_ms"], expected_start_ms)

    def test_valid_48_hour_cursor_is_caught_up_incrementally(self) -> None:
        from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore
        from momentum_alpha.trade_data_sync import run_incremental_trade_data_sync

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        cursor_at = now - timedelta(hours=48)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            store = RuntimeSyncStateStore(path=path)
            store.save_cursor(kind="sync_bootstrap", cursor_at=cursor_at, updated_at=cursor_at)
            store.save_cursor(kind="income", cursor_at=cursor_at, updated_at=cursor_at)
            store.save_cursor(kind="orders", symbol="BTCUSDT", cursor_at=cursor_at, updated_at=cursor_at)
            store.save_cursor(kind="trades", symbol="BTCUSDT", cursor_at=cursor_at, updated_at=cursor_at)
            store.mark_dirty(symbol="BTCUSDT", reason="account_update", observed_at=now)
            client = _FakeSyncClient()
            run_incremental_trade_data_sync(
                client=client,
                runtime_db_path=path,
                now=now,
                logger=lambda _message: None,
            )

        expected_start_ms = int((cursor_at - timedelta(minutes=20)).timestamp() * 1000)
        self.assertEqual(client.income_calls[0]["start_time_ms"], expected_start_ms)
        self.assertEqual(client.order_calls[0]["start_time_ms"], expected_start_ms)
        self.assertEqual(client.trade_calls[0]["start_time_ms"], expected_start_ms)

    def test_manual_repair_deferred_symbol_keeps_36_hour_window(self) -> None:
        from momentum_alpha.trade_data_sync import run_incremental_trade_data_sync

        first_now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        symbols = [f"S{index}USDT" for index in range(8)]
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            first_client = _FakeSyncClient()
            first = run_incremental_trade_data_sync(
                client=first_client,
                runtime_db_path=path,
                now=first_now,
                logger=lambda _message: None,
                full_repair=True,
                repair_symbols=symbols,
            )
            second_now = first_now + timedelta(minutes=15)
            second_client = _FakeSyncClient()
            second = run_incremental_trade_data_sync(
                client=second_client,
                runtime_db_path=path,
                now=second_now,
                logger=lambda _message: None,
            )

        self.assertEqual(first.request_weight, 100)
        self.assertEqual(first.deferred_symbols, ("S7USDT",))
        self.assertEqual(second.request_weight, 40)
        self.assertEqual(second_client.order_calls[0]["symbol"], "S7USDT")
        expected_start_ms = int((second_now - timedelta(hours=36)).timestamp() * 1000)
        self.assertEqual(second_client.order_calls[0]["start_time_ms"], expected_start_ms)
        self.assertEqual(second_client.trade_calls[0]["start_time_ms"], expected_start_ms)

    def test_429_aborts_before_the_next_dirty_symbol(self) -> None:
        from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore
        from momentum_alpha.trade_data_sync import run_incremental_trade_data_sync

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            store = RuntimeSyncStateStore(path=path)
            store.mark_dirty(symbol="BTCUSDT", reason="test", observed_at=now)
            store.mark_dirty(symbol="ETHUSDT", reason="test", observed_at=now)
            client = _FakeSyncClient()
            client.order_error = _RateLimitError("too many requests")
            result = run_incremental_trade_data_sync(
                client=client,
                runtime_db_path=path,
                now=now,
                logger=lambda _message: None,
            )
            remaining = store.dirty_symbols()

        self.assertTrue(result.rate_limited)
        self.assertEqual(result.request_weight, 35)
        self.assertEqual(len(client.order_calls), 1)
        self.assertEqual(client.trade_calls, [])
        self.assertEqual({item.symbol for item in remaining}, {"BTCUSDT", "ETHUSDT"})

    def test_replayed_trade_is_unique_by_symbol_and_trade_id(self) -> None:
        from momentum_alpha.runtime_store import fetch_recent_trade_fills
        from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore
        from momentum_alpha.trade_data_sync import run_incremental_trade_data_sync

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        trade = {
            "symbol": "BTCUSDT",
            "id": 9001,
            "orderId": 101,
            "side": "BUY",
            "price": "100",
            "qty": "1",
            "realizedPnl": "0",
            "commission": "0.1",
            "commissionAsset": "USDT",
            "time": int((now - timedelta(minutes=1)).timestamp() * 1000),
        }
        order = {
            "symbol": "BTCUSDT",
            "orderId": 101,
            "clientOrderId": "ma_test",
            "status": "FILLED",
            "side": "BUY",
            "type": "MARKET",
            "updateTime": trade["time"],
        }
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            store = RuntimeSyncStateStore(path=path)
            client = _FakeSyncClient()
            client.orders["BTCUSDT"] = [order]
            client.trades["BTCUSDT"] = [trade]
            store.mark_dirty(symbol="BTCUSDT", reason="first", observed_at=now)
            first = run_incremental_trade_data_sync(
                client=client,
                runtime_db_path=path,
                now=now,
                logger=lambda _message: None,
            )
            store.mark_dirty(symbol="BTCUSDT", reason="replay", observed_at=now + timedelta(minutes=1))
            second = run_incremental_trade_data_sync(
                client=client,
                runtime_db_path=path,
                now=now + timedelta(minutes=1),
                logger=lambda _message: None,
            )
            fills = fetch_recent_trade_fills(path=path, limit=10)

        self.assertEqual(first.trades_inserted, 1)
        self.assertEqual(second.trades_inserted, 0)
        self.assertEqual(len(fills), 1)


if __name__ == "__main__":
    unittest.main()
