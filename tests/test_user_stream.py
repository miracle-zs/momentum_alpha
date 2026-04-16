import sys
import unittest
from pathlib import Path
from datetime import date, datetime, timezone
from decimal import Decimal


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class UserStreamTests(unittest.TestCase):
    def test_build_stream_url_uses_testnet_when_enabled(self) -> None:
        from momentum_alpha.user_stream import BinanceUserStreamClient

        client = BinanceUserStreamClient(rest_client=object(), testnet=True)
        self.assertEqual(
            client.build_stream_url(listen_key="abc"),
            "wss://stream.binancefuture.com/ws/abc",
        )

    def test_parse_order_trade_update_event(self) -> None:
        from momentum_alpha.user_stream import parse_user_stream_event

        event = parse_user_stream_event(
            {
                "e": "ORDER_TRADE_UPDATE",
                "o": {
                    "s": "BTCUSDT",
                    "X": "FILLED",
                    "x": "TRADE",
                    "ap": "62500.5",
                    "z": "0.015",
                    "L": "62600.0",
                    "l": "0.005",
                    "rp": "12.34",
                    "n": "0.12",
                    "N": "USDT",
                    "i": 123,
                    "t": 456,
                    "c": "ma_entry",
                },
            }
        )
        self.assertEqual(event.event_type, "ORDER_TRADE_UPDATE")
        self.assertEqual(event.symbol, "BTCUSDT")
        self.assertEqual(event.order_status, "FILLED")
        self.assertEqual(event.execution_type, "TRADE")
        self.assertEqual(event.average_price, Decimal("62500.5"))
        self.assertEqual(event.filled_quantity, Decimal("0.015"))
        self.assertEqual(event.last_filled_price, Decimal("62600.0"))
        self.assertEqual(event.last_filled_quantity, Decimal("0.005"))
        self.assertEqual(event.realized_pnl, Decimal("12.34"))
        self.assertEqual(event.commission, Decimal("0.12"))
        self.assertEqual(event.commission_asset, "USDT")
        self.assertEqual(event.order_id, 123)
        self.assertEqual(event.trade_id, 456)
        self.assertEqual(event.client_order_id, "ma_entry")

    def test_parse_account_update_event(self) -> None:
        from momentum_alpha.user_stream import parse_user_stream_event

        event = parse_user_stream_event(
            {
                "e": "ACCOUNT_UPDATE",
                "a": {"m": "ORDER"},
            }
        )
        self.assertEqual(event.event_type, "ACCOUNT_UPDATE")
        self.assertIsNone(event.symbol)
        self.assertEqual(event.account_update_reason, "ORDER")

    def test_user_stream_event_id_distinguishes_non_trade_order_lifecycle_updates(self) -> None:
        from momentum_alpha.user_stream import parse_user_stream_event, user_stream_event_id

        new_event = parse_user_stream_event(
            {
                "e": "ORDER_TRADE_UPDATE",
                "T": 1776215100000,
                "o": {
                    "s": "ETHUSDT",
                    "i": 123,
                    "X": "NEW",
                    "x": "NEW",
                },
            }
        )
        canceled_event = parse_user_stream_event(
            {
                "e": "ORDER_TRADE_UPDATE",
                "T": 1776215160000,
                "o": {
                    "s": "ETHUSDT",
                    "i": 123,
                    "X": "CANCELED",
                    "x": "CANCELED",
                },
            }
        )
        self.assertNotEqual(user_stream_event_id(new_event), user_stream_event_id(canceled_event))

    def test_run_once_creates_listen_key_and_emits_event(self) -> None:
        from momentum_alpha.user_stream import BinanceUserStreamClient

        class FakeRestClient:
            def create_listen_key(self):
                return {"listenKey": "abc"}

        calls = []

        def fake_runner(*, url, on_message):
            calls.append(url)
            on_message('{"e":"ORDER_TRADE_UPDATE","o":{"s":"BTCUSDT","X":"FILLED"}}')

        events = []
        client = BinanceUserStreamClient(rest_client=FakeRestClient(), websocket_runner=fake_runner)
        listen_key = client.run_once(on_event=lambda event: events.append(event))
        self.assertEqual(listen_key, "abc")
        self.assertEqual(calls, ["wss://fstream.binance.com/ws/abc"])
        self.assertEqual(events[0].event_type, "ORDER_TRADE_UPDATE")

    def test_run_forever_closes_listen_key_after_runner_returns(self) -> None:
        from momentum_alpha.user_stream import BinanceUserStreamClient

        class FakeRestClient:
            def __init__(self) -> None:
                self.closed = []

            def create_listen_key(self):
                return {"listenKey": "abc"}

            def close_listen_key(self, *, listen_key):
                self.closed.append(listen_key)

        rest_client = FakeRestClient()

        def fake_runner(*, url, on_message):
            on_message('{"e":"ORDER_TRADE_UPDATE","o":{"s":"BTCUSDT","X":"FILLED","x":"TRADE"}}')

        events = []
        client = BinanceUserStreamClient(rest_client=rest_client, websocket_runner=fake_runner)
        listen_key = client.run_forever(on_event=lambda event: events.append(event))
        self.assertEqual(listen_key, "abc")
        self.assertEqual(rest_client.closed, ["abc"])
        self.assertEqual(events[0].order_status, "FILLED")

    def test_run_forever_starts_and_stops_keepalive_loop(self) -> None:
        from momentum_alpha.user_stream import BinanceUserStreamClient

        class FakeRestClient:
            def __init__(self) -> None:
                self.keepalives = []
                self.closed = []

            def create_listen_key(self):
                return {"listenKey": "abc"}

            def keepalive_listen_key(self, *, listen_key):
                self.keepalives.append(listen_key)

            def close_listen_key(self, *, listen_key):
                self.closed.append(listen_key)

        class FakeStopEvent:
            def __init__(self) -> None:
                self._set = False

            def is_set(self):
                return self._set

            def set(self):
                self._set = True

        stop_events = []

        def fake_stop_event_factory():
            event = FakeStopEvent()
            stop_events.append(event)
            return event

        keepalive_runs = []

        def fake_keepalive_runner(*, rest_client, listen_key, stop_event, interval_seconds):
            keepalive_runs.append((listen_key, interval_seconds, stop_event.is_set()))
            rest_client.keepalive_listen_key(listen_key=listen_key)
            self.assertFalse(stop_event.is_set())

        rest_client = FakeRestClient()

        def fake_runner(*, url, on_message):
            on_message('{"e":"ORDER_TRADE_UPDATE","o":{"s":"BTCUSDT","X":"FILLED","x":"TRADE"}}')

        client = BinanceUserStreamClient(
            rest_client=rest_client,
            websocket_runner=fake_runner,
            keepalive_runner=fake_keepalive_runner,
            stop_event_factory=fake_stop_event_factory,
        )
        listen_key = client.run_forever(on_event=lambda event: None)
        self.assertEqual(listen_key, "abc")
        self.assertEqual(rest_client.keepalives, ["abc"])
        self.assertEqual(rest_client.closed, ["abc"])
        self.assertEqual(len(keepalive_runs), 1)
        self.assertEqual(keepalive_runs[0][:2], ("abc", 30 * 60))
        self.assertTrue(stop_events[0].is_set())

    def test_apply_order_trade_update_buy_fill_adds_position(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.user_stream import apply_user_stream_event_to_state, parse_user_stream_event

        state = StrategyState(current_day=date(2026, 4, 15), previous_leader_symbol="BTCUSDT", positions={})
        event = parse_user_stream_event(
            {
                "e": "ORDER_TRADE_UPDATE",
                "T": 1776215100000,
                "o": {
                    "s": "ETHUSDT",
                    "S": "BUY",
                    "X": "FILLED",
                    "x": "TRADE",
                    "ot": "MARKET",
                    "ap": "108",
                    "z": "2",
                    "sp": "106",
                },
            }
        )
        updated = apply_user_stream_event_to_state(state=state, event=event)
        self.assertIn("ETHUSDT", updated.positions)
        self.assertEqual(updated.positions["ETHUSDT"].total_quantity, Decimal("2"))
        self.assertEqual(updated.positions["ETHUSDT"].stop_price, Decimal("106"))

    def test_apply_stop_market_sell_fill_removes_position(self) -> None:
        from momentum_alpha.models import Position, PositionLeg, StrategyState
        from momentum_alpha.user_stream import apply_user_stream_event_to_state, parse_user_stream_event

        opened_at = datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=date(2026, 4, 15),
            previous_leader_symbol="ETHUSDT",
            positions={
                "ETHUSDT": Position(
                    symbol="ETHUSDT",
                    stop_price=Decimal("106"),
                    legs=(PositionLeg("ETHUSDT", Decimal("2"), Decimal("108"), Decimal("106"), opened_at, "base"),),
                )
            },
        )
        event = parse_user_stream_event(
            {
                "e": "ORDER_TRADE_UPDATE",
                "T": 1776215160000,
                "o": {
                    "s": "ETHUSDT",
                    "S": "SELL",
                    "X": "FILLED",
                    "x": "TRADE",
                    "ot": "STOP_MARKET",
                    "ap": "106",
                    "z": "2",
                    "sp": "106",
                },
            }
        )
        updated = apply_user_stream_event_to_state(state=state, event=event)
        self.assertNotIn("ETHUSDT", updated.positions)
        self.assertEqual(
            updated.recent_stop_loss_exits["ETHUSDT"],
            datetime(2026, 4, 15, 1, 6, tzinfo=timezone.utc),
        )

    def test_apply_market_sell_fill_from_strategy_stop_removes_position(self) -> None:
        from momentum_alpha.models import Position, PositionLeg, StrategyState
        from momentum_alpha.user_stream import apply_user_stream_event_to_state, parse_user_stream_event

        opened_at = datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=date(2026, 4, 15),
            previous_leader_symbol="ETHUSDT",
            positions={
                "ETHUSDT": Position(
                    symbol="ETHUSDT",
                    stop_price=Decimal("106"),
                    legs=(PositionLeg("ETHUSDT", Decimal("2"), Decimal("108"), Decimal("106"), opened_at, "base"),),
                )
            },
        )
        event = parse_user_stream_event(
            {
                "e": "ORDER_TRADE_UPDATE",
                "T": 1776215160000,
                "o": {
                    "s": "ETHUSDT",
                    "c": "ma_260415010000_ETHUSDT_b00s",
                    "S": "SELL",
                    "X": "FILLED",
                    "x": "TRADE",
                    "ot": "MARKET",
                    "ap": "106",
                    "z": "2",
                    "sp": "0",
                },
            }
        )
        updated = apply_user_stream_event_to_state(state=state, event=event)
        self.assertNotIn("ETHUSDT", updated.positions)
        self.assertEqual(
            updated.recent_stop_loss_exits["ETHUSDT"],
            datetime(2026, 4, 15, 1, 6, tzinfo=timezone.utc),
        )

    def test_apply_account_update_flat_position_removes_position(self) -> None:
        from momentum_alpha.models import Position, PositionLeg, StrategyState
        from momentum_alpha.user_stream import apply_user_stream_event_to_state, parse_user_stream_event

        opened_at = datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=date(2026, 4, 15),
            previous_leader_symbol="ETHUSDT",
            positions={
                "ETHUSDT": Position(
                    symbol="ETHUSDT",
                    stop_price=Decimal("106"),
                    legs=(PositionLeg("ETHUSDT", Decimal("2"), Decimal("108"), Decimal("106"), opened_at, "base"),),
                )
            },
        )
        event = parse_user_stream_event(
            {
                "e": "ACCOUNT_UPDATE",
                "E": 1776215220000,
                "a": {
                    "m": "ORDER",
                    "P": [
                        {
                            "s": "ETHUSDT",
                            "pa": "0",
                            "ep": "0",
                        }
                    ],
                },
            }
        )
        updated = apply_user_stream_event_to_state(state=state, event=event)
        self.assertNotIn("ETHUSDT", updated.positions)

    def test_apply_account_update_positive_position_restores_missing_position(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.user_stream import apply_user_stream_event_to_state, parse_user_stream_event

        state = StrategyState(current_day=date(2026, 4, 15), previous_leader_symbol="BTCUSDT", positions={})
        event = parse_user_stream_event(
            {
                "e": "ACCOUNT_UPDATE",
                "E": 1776215220000,
                "a": {
                    "m": "ORDER",
                    "P": [
                        {
                            "s": "ETHUSDT",
                            "pa": "2",
                            "ep": "108",
                        }
                    ],
                },
            }
        )
        updated = apply_user_stream_event_to_state(state=state, event=event)
        self.assertIn("ETHUSDT", updated.positions)
        self.assertEqual(updated.positions["ETHUSDT"].total_quantity, Decimal("2"))
        self.assertEqual(updated.positions["ETHUSDT"].stop_price, Decimal("0"))
        self.assertEqual(updated.positions["ETHUSDT"].legs[0].leg_type, "account_update_restored")

    def test_apply_account_update_positive_position_syncs_existing_position_quantity_and_entry(self) -> None:
        from momentum_alpha.models import Position, PositionLeg, StrategyState
        from momentum_alpha.user_stream import apply_user_stream_event_to_state, parse_user_stream_event

        opened_at = datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=date(2026, 4, 15),
            previous_leader_symbol="ETHUSDT",
            positions={
                "ETHUSDT": Position(
                    symbol="ETHUSDT",
                    stop_price=Decimal("106"),
                    legs=(PositionLeg("ETHUSDT", Decimal("2"), Decimal("108"), Decimal("106"), opened_at, "base"),),
                )
            },
        )
        event = parse_user_stream_event(
            {
                "e": "ACCOUNT_UPDATE",
                "E": 1776215280000,
                "a": {
                    "m": "ORDER",
                    "P": [
                        {
                            "s": "ETHUSDT",
                            "pa": "3",
                            "ep": "109",
                        }
                    ],
                },
            }
        )
        updated = apply_user_stream_event_to_state(state=state, event=event)
        self.assertEqual(updated.positions["ETHUSDT"].total_quantity, Decimal("3"))
        self.assertEqual(updated.positions["ETHUSDT"].legs[0].entry_price, Decimal("109"))
        self.assertEqual(updated.positions["ETHUSDT"].legs[0].leg_type, "account_update_synced")
        self.assertEqual(updated.positions["ETHUSDT"].stop_price, Decimal("106"))

    def test_apply_account_update_restores_stop_price_from_known_stop_order(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.user_stream import apply_user_stream_event_to_state, parse_user_stream_event

        state = StrategyState(current_day=date(2026, 4, 15), previous_leader_symbol="BTCUSDT", positions={})
        event = parse_user_stream_event(
            {
                "e": "ACCOUNT_UPDATE",
                "E": 1776215220000,
                "a": {
                    "m": "ORDER",
                    "P": [
                        {
                            "s": "ETHUSDT",
                            "pa": "2",
                            "ep": "108",
                        }
                    ],
                },
            }
        )
        updated = apply_user_stream_event_to_state(
            state=state,
            event=event,
            order_statuses={
                "123": {
                    "symbol": "ETHUSDT",
                    "status": "NEW",
                    "side": "SELL",
                    "original_order_type": "STOP_MARKET",
                    "stop_price": "106",
                }
            },
        )
        self.assertEqual(updated.positions["ETHUSDT"].stop_price, Decimal("106"))
        self.assertEqual(updated.positions["ETHUSDT"].legs[0].stop_price, Decimal("106"))

    def test_apply_account_update_ignores_inactive_stop_order_when_restoring_stop_price(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.user_stream import apply_user_stream_event_to_state, parse_user_stream_event

        state = StrategyState(current_day=date(2026, 4, 15), previous_leader_symbol="BTCUSDT", positions={})
        event = parse_user_stream_event(
            {
                "e": "ACCOUNT_UPDATE",
                "E": 1776215220000,
                "a": {
                    "m": "ORDER",
                    "P": [
                        {
                            "s": "ETHUSDT",
                            "pa": "2",
                            "ep": "108",
                        }
                    ],
                },
            }
        )
        updated = apply_user_stream_event_to_state(
            state=state,
            event=event,
            order_statuses={
                "123": {
                    "symbol": "ETHUSDT",
                    "status": "CANCELED",
                    "side": "SELL",
                    "original_order_type": "STOP_MARKET",
                    "stop_price": "106",
                }
            },
        )
        self.assertEqual(updated.positions["ETHUSDT"].stop_price, Decimal("0"))

    def test_apply_account_update_prefers_active_stop_order_over_inactive_one(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.user_stream import apply_user_stream_event_to_state, parse_user_stream_event

        state = StrategyState(current_day=date(2026, 4, 15), previous_leader_symbol="BTCUSDT", positions={})
        event = parse_user_stream_event(
            {
                "e": "ACCOUNT_UPDATE",
                "E": 1776215220000,
                "a": {
                    "m": "ORDER",
                    "P": [
                        {
                            "s": "ETHUSDT",
                            "pa": "2",
                            "ep": "108",
                        }
                    ],
                },
            }
        )
        updated = apply_user_stream_event_to_state(
            state=state,
            event=event,
            order_statuses={
                "123": {
                    "symbol": "ETHUSDT",
                    "status": "CANCELED",
                    "side": "SELL",
                    "original_order_type": "STOP_MARKET",
                    "stop_price": "106",
                },
                "124": {
                    "symbol": "ETHUSDT",
                    "status": "NEW",
                    "side": "SELL",
                    "original_order_type": "STOP_MARKET",
                    "stop_price": "107",
                },
            },
        )
        self.assertEqual(updated.positions["ETHUSDT"].stop_price, Decimal("107"))

    def test_extract_order_status_update_returns_delete_signal_for_filled_stop_market_sell(self) -> None:
        from momentum_alpha.user_stream import extract_order_status_update, parse_user_stream_event

        event = parse_user_stream_event(
            {
                "e": "ORDER_TRADE_UPDATE",
                "T": 1776215160000,
                "o": {
                    "s": "ETHUSDT",
                    "i": 123,
                    "S": "SELL",
                    "X": "FILLED",
                    "x": "TRADE",
                    "ot": "STOP_MARKET",
                    "sp": "106",
                },
            }
        )
        self.assertEqual(extract_order_status_update(event), ("123", None))

    def test_parse_algo_update_event(self) -> None:
        from momentum_alpha.user_stream import parse_user_stream_event

        event = parse_user_stream_event(
            {
                "e": "ALGO_UPDATE",
                "E": 1776215100000,
                "s": "BTCUSDT",
                "algoId": 2000000786682809,
                "clientAlgoId": "ma_260415221700_BTCUSDT_b00s",
                "algoStatus": "NEW",
                "S": "SELL",
                "orderType": "STOP_MARKET",
                "triggerPrice": "61000.0",
            }
        )
        self.assertEqual(event.event_type, "ALGO_UPDATE")
        self.assertEqual(event.symbol, "BTCUSDT")
        self.assertEqual(event.algo_id, 2000000786682809)
        self.assertEqual(event.client_algo_id, "ma_260415221700_BTCUSDT_b00s")
        self.assertEqual(event.algo_status, "NEW")
        self.assertEqual(event.side, "SELL")
        self.assertEqual(event.trigger_price, Decimal("61000.0"))

    def test_extract_algo_order_status_update_returns_snapshot_for_new_order(self) -> None:
        from momentum_alpha.user_stream import extract_algo_order_status_update, parse_user_stream_event

        event = parse_user_stream_event(
            {
                "e": "ALGO_UPDATE",
                "E": 1776215100000,
                "s": "BTCUSDT",
                "algoId": 2000000786682809,
                "clientAlgoId": "ma_260415221700_BTCUSDT_b00s",
                "algoStatus": "NEW",
                "S": "SELL",
                "orderType": "STOP_MARKET",
                "triggerPrice": "61000.0",
            }
        )
        result = extract_algo_order_status_update(event)
        self.assertIsNotNone(result)
        key, snapshot = result
        self.assertEqual(key, "algo:2000000786682809")
        self.assertEqual(snapshot["symbol"], "BTCUSDT")
        self.assertEqual(snapshot["status"], "NEW")
        self.assertEqual(snapshot["side"], "SELL")
        self.assertEqual(snapshot["original_order_type"], "STOP_MARKET")
        self.assertEqual(snapshot["stop_price"], "61000.0")
        self.assertEqual(snapshot["client_order_id"], "ma_260415221700_BTCUSDT_b00s")

    def test_extract_algo_order_status_update_returns_delete_for_triggered_order(self) -> None:
        from momentum_alpha.user_stream import extract_algo_order_status_update, parse_user_stream_event

        event = parse_user_stream_event(
            {
                "e": "ALGO_UPDATE",
                "E": 1776215100000,
                "s": "BTCUSDT",
                "algoId": 2000000786682809,
                "algoStatus": "TRIGGERED",
                "S": "SELL",
            }
        )
        result = extract_algo_order_status_update(event)
        self.assertIsNotNone(result)
        key, snapshot = result
        self.assertEqual(key, "algo:2000000786682809")
        self.assertIsNone(snapshot)

    def test_resolve_stop_price_from_order_statuses_includes_algo_orders(self) -> None:
        from momentum_alpha.user_stream import resolve_stop_price_from_order_statuses

        order_statuses = {
            "123": {
                "symbol": "ETHUSDT",
                "status": "NEW",
                "side": "SELL",
                "original_order_type": "STOP_MARKET",
                "stop_price": "106",
            },
            "algo:2000000786682809": {
                "symbol": "BTCUSDT",
                "status": "NEW",
                "side": "SELL",
                "original_order_type": "STOP_MARKET",
                "stop_price": "61000",
                "client_order_id": "ma_260415221700_BTCUSDT_b00s",
            },
        }
        eth_stop = resolve_stop_price_from_order_statuses(symbol="ETHUSDT", order_statuses=order_statuses)
        btc_stop = resolve_stop_price_from_order_statuses(symbol="BTCUSDT", order_statuses=order_statuses)
        self.assertEqual(eth_stop, Decimal("106"))
        self.assertEqual(btc_stop, Decimal("61000"))

    def test_apply_account_update_restores_stop_price_from_algo_order(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.user_stream import apply_user_stream_event_to_state, parse_user_stream_event

        state = StrategyState(current_day=date(2026, 4, 15), previous_leader_symbol="BTCUSDT", positions={})
        event = parse_user_stream_event(
            {
                "e": "ACCOUNT_UPDATE",
                "E": 1776215220000,
                "a": {
                    "m": "ORDER",
                    "P": [
                        {
                            "s": "BTCUSDT",
                            "pa": "0.010",
                            "ep": "62000",
                        }
                    ],
                },
            }
        )
        updated = apply_user_stream_event_to_state(
            state=state,
            event=event,
            order_statuses={
                "algo:2000000786682809": {
                    "symbol": "BTCUSDT",
                    "status": "NEW",
                    "side": "SELL",
                    "original_order_type": "STOP_MARKET",
                    "stop_price": "61000",
                    "client_order_id": "ma_260415221700_BTCUSDT_b00s",
                }
            },
        )
        self.assertEqual(updated.positions["BTCUSDT"].stop_price, Decimal("61000"))
        self.assertEqual(updated.positions["BTCUSDT"].legs[0].stop_price, Decimal("61000"))
