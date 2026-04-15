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
                "o": {"s": "BTCUSDT", "X": "FILLED", "x": "TRADE"},
            }
        )
        self.assertEqual(event.event_type, "ORDER_TRADE_UPDATE")
        self.assertEqual(event.symbol, "BTCUSDT")
        self.assertEqual(event.order_status, "FILLED")
        self.assertEqual(event.execution_type, "TRADE")

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
