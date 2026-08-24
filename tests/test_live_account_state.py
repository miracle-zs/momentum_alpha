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


class _AccountClient:
    def __init__(self) -> None:
        self.position_mode_calls = 0
        self.account_calls = 0
        self.position_risk_calls = 0
        self.open_order_calls: list[str | None] = []
        self.open_algo_order_calls: list[str | None] = []
        self.open_orders: list[dict] = []
        self.positions: list[dict] = [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "1",
                "entryPrice": "100",
                "positionSide": "BOTH",
            }
        ]

    def fetch_position_mode(self):
        self.position_mode_calls += 1
        return {"dualSidePosition": False}

    def fetch_account_info(self):
        self.account_calls += 1
        return {"positions": self.positions}

    def fetch_position_risk(self):
        self.position_risk_calls += 1
        return self.positions

    def fetch_open_orders(self, *, symbol=None):
        self.open_order_calls.append(symbol)
        return self.open_orders

    def fetch_open_algo_orders(self, *, symbol=None):
        self.open_algo_order_calls.append(symbol)
        return []


class LiveAccountStateTests(unittest.TestCase):
    def test_unchanged_stream_projection_does_not_erase_fresh_symbol_validation(self) -> None:
        from momentum_alpha.live_account_state import LiveAccountStateCache
        from momentum_alpha.strategy_state_codec import StoredStrategyState

        client = _AccountClient()
        client.open_orders = [
            {
                "symbol": "BTCUSDT",
                "orderId": 101,
                "status": "NEW",
                "side": "SELL",
                "type": "STOP_MARKET",
                "stopPrice": "90",
                "origQty": "1",
            }
        ]
        cache = LiveAccountStateCache(client=client)
        now = datetime(2026, 8, 24, 6, 1, tzinfo=timezone.utc)
        stored = StoredStrategyState(
            current_day=now.date().isoformat(),
            previous_leader_symbol=None,
            order_statuses={},
        )

        first = cache.snapshot(
            now=now,
            stored_state=stored,
            restore_positions=True,
            submit_orders=True,
        )
        second = cache.snapshot(
            now=now + timedelta(seconds=30),
            stored_state=stored,
            restore_positions=True,
            submit_orders=True,
        )

        self.assertEqual(len(first.open_orders), 1)
        self.assertEqual(len(second.open_orders), 1)

    def test_poll_startup_uses_symbol_queries_and_normal_minutes_stay_under_20(self) -> None:
        from momentum_alpha.live_account_state import LiveAccountStateCache

        client = _AccountClient()
        cache = LiveAccountStateCache(client=client)
        first_now = datetime(2026, 8, 24, 6, 1, tzinfo=timezone.utc)

        first = cache.snapshot(
            now=first_now,
            stored_state=None,
            restore_positions=True,
            submit_orders=True,
        )
        second = cache.snapshot(
            now=first_now + timedelta(minutes=1),
            stored_state=None,
            restore_positions=True,
            submit_orders=True,
        )
        third = cache.snapshot(
            now=first_now + timedelta(minutes=2),
            stored_state=None,
            restore_positions=True,
            submit_orders=True,
        )

        self.assertEqual(first.request_weight, 42)
        self.assertTrue(first.full_sync)
        self.assertLessEqual(second.request_weight, 20)
        self.assertLessEqual(third.request_weight, 20)
        self.assertEqual(client.position_mode_calls, 1)
        self.assertEqual(client.position_risk_calls, 1)
        self.assertNotIn(None, client.open_order_calls)
        self.assertNotIn(None, client.open_algo_order_calls)
        self.assertEqual(client.open_order_calls[0], "BTCUSDT")
        self.assertEqual(client.open_algo_order_calls[0], "BTCUSDT")

    def test_account_slice_reserves_two_weight_for_market_ticker(self) -> None:
        from momentum_alpha.live_account_state import LiveAccountStateCache

        client = _AccountClient()
        client.positions = [
            {
                "symbol": f"S{index}USDT",
                "positionAmt": "1",
                "entryPrice": "100",
                "positionSide": "BOTH",
            }
            for index in range(20)
        ]
        cache = LiveAccountStateCache(client=client)
        now = datetime(2026, 8, 24, 6, 1, tzinfo=timezone.utc)
        cache.snapshot(
            now=now,
            stored_state=None,
            restore_positions=True,
            submit_orders=True,
        )
        validation = cache.snapshot(
            now=now + timedelta(minutes=4),
            stored_state=None,
            restore_positions=True,
            submit_orders=True,
        )

        self.assertEqual(validation.request_weight, 18)
        self.assertEqual(validation.request_weight + 2, 20)

    def test_manual_position_mode_refresh_is_consumed_once(self) -> None:
        from momentum_alpha.live_account_state import LiveAccountStateCache
        from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore

        now = datetime(2026, 8, 24, 6, 1, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            client = _AccountClient()
            cache = LiveAccountStateCache(client=client, runtime_db_path=path)
            cache.snapshot(now=now, stored_state=None, restore_positions=False, submit_orders=True)
            RuntimeSyncStateStore(path=path).request_control(
                key="position_mode_refresh",
                requested_at=now + timedelta(seconds=1),
                reason="test",
            )
            refreshed = cache.snapshot(
                now=now + timedelta(minutes=1),
                stored_state=None,
                restore_positions=False,
                submit_orders=True,
            )
            requests = RuntimeSyncStateStore(path=path).control_requests()

        self.assertEqual(refreshed.request_weight, 35)
        self.assertEqual(client.position_mode_calls, 2)
        self.assertEqual(requests, [])

    def test_post_order_refresh_updates_account_once_and_reports_cumulative_weight(self) -> None:
        from momentum_alpha.live_account_state import LiveAccountStateCache

        client = _AccountClient()
        cache = LiveAccountStateCache(client=client)
        now = datetime(2026, 8, 24, 6, 1, tzinfo=timezone.utc)
        initial = cache.snapshot(
            now=now,
            stored_state=None,
            restore_positions=True,
            submit_orders=True,
        )
        refreshed = cache.refresh_symbols(
            symbols={"BTCUSDT"},
            now=now + timedelta(seconds=10),
            stored_state=None,
            refresh_account=True,
        )

        self.assertEqual(initial.request_weight, 42)
        self.assertEqual(refreshed.request_weight, 49)
        self.assertEqual(client.account_calls, 2)


if __name__ == "__main__":
    unittest.main()
