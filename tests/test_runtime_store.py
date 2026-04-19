import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeStoreTests(unittest.TestCase):
    def test_bootstrap_and_insert_audit_event(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_audit_event_counts,
            fetch_recent_audit_events,
            insert_audit_event,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_audit_event(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
                event_type="tick_result",
                payload={"symbol_count": 538, "leader": "INUSDT"},
                source="poll",
            )

            events = fetch_recent_audit_events(path=db_path, limit=10)
            counts = fetch_audit_event_counts(path=db_path, limit=10)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "tick_result")
            self.assertEqual(events[0]["payload"]["leader"], "INUSDT")
            self.assertEqual(events[0]["source"], "poll")
            self.assertEqual(counts, {"tick_result": 1})

    def test_fetch_recent_audit_events_returns_newest_first(self) -> None:
        from momentum_alpha.runtime_store import bootstrap_runtime_db, fetch_recent_audit_events, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_audit_event(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
                event_type="poll_tick",
                payload={"symbol_count": 538},
            )
            insert_audit_event(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc),
                event_type="user_stream_worker_start",
                payload={"position_count": 0},
            )

            events = fetch_recent_audit_events(path=db_path, limit=10)
            self.assertEqual([event["event_type"] for event in events], ["user_stream_worker_start", "poll_tick"])

    def test_bootstrap_runtime_db_is_idempotent(self) -> None:
        from momentum_alpha.runtime_store import bootstrap_runtime_db

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            bootstrap_runtime_db(path=db_path)
            self.assertTrue(db_path.exists())

    def test_bootstrap_creates_structured_tables(self) -> None:
        from momentum_alpha.runtime_store import bootstrap_runtime_db

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            import sqlite3

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
                    "signal_decisions",
                    "broker_orders",
                    "trade_fills",
                    "position_snapshots",
                    "account_snapshots",
                }.issubset(tables)
            )

    def test_structured_inserts_preserve_summary_fields(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_recent_account_flows,
            fetch_recent_account_snapshots,
            fetch_recent_algo_orders,
            fetch_recent_broker_orders,
            fetch_recent_position_snapshots,
            fetch_recent_signal_decisions,
            fetch_recent_stop_exit_summaries,
            fetch_recent_trade_fills,
            fetch_recent_trade_round_trips,
            insert_account_flow,
            insert_account_snapshot,
            insert_algo_order,
            insert_broker_order,
            insert_position_snapshot,
            insert_signal_decision,
            insert_stop_exit_summary,
            insert_trade_fill,
            insert_trade_round_trip,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            first_timestamp = datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc)
            second_timestamp = datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc)

            insert_signal_decision(
                path=db_path,
                timestamp=first_timestamp,
                source="poll",
                decision_type="base_entry",
                symbol="BLESSUSDT",
                previous_leader_symbol="ONUSDT",
                next_leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=0,
                payload={
                    "note": "leader switch",
                    "latest_price": "0.1234",
                    "daily_change_pct": "0.42",
                    "leader_gap_pct": "0.08",
                },
            )
            insert_algo_order(
                path=db_path,
                timestamp=second_timestamp,
                source="poll",
                symbol="BLESSUSDT",
                algo_id="algo-1",
                client_algo_id="abc-123-stop",
                algo_status="NEW",
                side="SELL",
                order_type="STOP_MARKET",
                trigger_price="0.1200",
                payload={"workingType": "CONTRACT_PRICE"},
            )
            insert_broker_order(
                path=db_path,
                timestamp=second_timestamp,
                source="poll",
                symbol="BLESSUSDT",
                action_type="submit",
                order_status="FILLED",
                side="BUY",
                order_id="12345",
                client_order_id="abc-123",
                payload={"filled_qty": "1.25"},
            )
            insert_trade_fill(
                path=db_path,
                timestamp=second_timestamp,
                source="user-stream",
                symbol="BLESSUSDT",
                order_id="12345",
                trade_id="67890",
                client_order_id="abc-123",
                order_status="FILLED",
                execution_type="TRADE",
                side="BUY",
                order_type="MARKET",
                quantity="1.25",
                cumulative_quantity="1.25",
                average_price="0.1234",
                last_price="0.1235",
                realized_pnl="5.67",
                commission="0.01",
                commission_asset="USDT",
                payload={"maker": False},
            )
            insert_account_flow(
                path=db_path,
                timestamp=second_timestamp,
                source="user-stream",
                reason="FUNDING_FEE",
                asset="USDT",
                wallet_balance="1234.56",
                cross_wallet_balance="1200.00",
                balance_change="-0.12",
                payload={"event_type": "ACCOUNT_UPDATE"},
            )
            insert_trade_round_trip(
                path=db_path,
                round_trip_id="BLESSUSDT:1",
                symbol="BLESSUSDT",
                opened_at=first_timestamp,
                closed_at=second_timestamp,
                entry_fill_count=1,
                exit_fill_count=1,
                total_entry_quantity="1.25",
                total_exit_quantity="1.25",
                weighted_avg_entry_price="0.1234",
                weighted_avg_exit_price="0.1210",
                realized_pnl="-3.00",
                commission="0.01",
                net_pnl="-3.01",
                exit_reason="stop_loss",
                duration_seconds=60,
                payload={"stop_triggered": True},
            )
            insert_stop_exit_summary(
                path=db_path,
                timestamp=second_timestamp,
                symbol="BLESSUSDT",
                round_trip_id="BLESSUSDT:1",
                trigger_price="0.1220",
                average_exit_price="0.1210",
                slippage_abs="0.0010",
                slippage_pct="0.819672",
                exit_quantity="1.25",
                realized_pnl="-3.00",
                commission="0.01",
                net_pnl="-3.01",
                payload={"stop_triggered": True},
            )
            insert_position_snapshot(
                path=db_path,
                timestamp=second_timestamp,
                source="poll",
                leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=2,
                symbol_count=538,
                submit_orders=True,
                restore_positions=True,
                execute_stop_replacements=False,
                payload={"mode": "LIVE"},
            )
            insert_account_snapshot(
                path=db_path,
                timestamp=second_timestamp,
                source="poll",
                wallet_balance="1234.56",
                available_balance="1200.00",
                equity="1260.12",
                unrealized_pnl="25.56",
                position_count=1,
                open_order_count=2,
                leader_symbol="BLESSUSDT",
                payload={"account_alias": "primary"},
            )

            signal_decisions = fetch_recent_signal_decisions(path=db_path, limit=10)
            algo_orders = fetch_recent_algo_orders(path=db_path, limit=10)
            broker_orders = fetch_recent_broker_orders(path=db_path, limit=10)
            trade_fills = fetch_recent_trade_fills(path=db_path, limit=10)
            account_flows = fetch_recent_account_flows(path=db_path, limit=10)
            round_trips = fetch_recent_trade_round_trips(path=db_path, limit=10)
            stop_exits = fetch_recent_stop_exit_summaries(path=db_path, limit=10)
            snapshots = fetch_recent_position_snapshots(path=db_path, limit=10)
            account_snapshots = fetch_recent_account_snapshots(path=db_path, limit=10)

            self.assertEqual(signal_decisions[0]["decision_type"], "base_entry")
            self.assertEqual(signal_decisions[0]["previous_leader_symbol"], "ONUSDT")
            self.assertEqual(signal_decisions[0]["next_leader_symbol"], "BLESSUSDT")
            self.assertEqual(signal_decisions[0]["payload"]["note"], "leader switch")
            self.assertEqual(signal_decisions[0]["payload"]["leader_gap_pct"], "0.08")
            self.assertEqual(algo_orders[0]["algo_id"], "algo-1")
            self.assertEqual(algo_orders[0]["trigger_price"], "0.1200")
            self.assertEqual(broker_orders[0]["action_type"], "submit")
            self.assertEqual(broker_orders[0]["order_status"], "FILLED")
            self.assertEqual(broker_orders[0]["payload"]["filled_qty"], "1.25")
            self.assertEqual(trade_fills[0]["symbol"], "BLESSUSDT")
            self.assertEqual(trade_fills[0]["trade_id"], "67890")
            self.assertEqual(trade_fills[0]["quantity"], "1.25")
            self.assertEqual(trade_fills[0]["average_price"], "0.1234")
            self.assertEqual(trade_fills[0]["realized_pnl"], "5.67")
            self.assertEqual(trade_fills[0]["commission_asset"], "USDT")
            self.assertEqual(trade_fills[0]["payload"]["maker"], False)
            self.assertEqual(account_flows[0]["reason"], "FUNDING_FEE")
            self.assertEqual(account_flows[0]["balance_change"], "-0.12")
            self.assertEqual(round_trips[0]["round_trip_id"], "BLESSUSDT:1")
            self.assertEqual(round_trips[0]["exit_reason"], "stop_loss")
            self.assertEqual(stop_exits[0]["round_trip_id"], "BLESSUSDT:1")
            self.assertEqual(stop_exits[0]["slippage_abs"], "0.0010")
            self.assertEqual(snapshots[0]["leader_symbol"], "BLESSUSDT")
            self.assertTrue(snapshots[0]["submit_orders"])
            self.assertEqual(snapshots[0]["symbol_count"], 538)
            self.assertEqual(account_snapshots[0]["wallet_balance"], "1234.56")
            self.assertEqual(account_snapshots[0]["equity"], "1260.12")
            self.assertEqual(account_snapshots[0]["open_order_count"], 2)
            self.assertEqual(account_snapshots[0]["payload"]["account_alias"], "primary")

    def test_fetch_account_snapshots_for_range_keeps_latest_point_per_bucket(self) -> None:
        from momentum_alpha.runtime_store import fetch_account_snapshots_for_range, insert_account_snapshot

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
            points = [
                (now - timedelta(days=10) + timedelta(minutes=10), "old-same-day-older"),
                (now - timedelta(days=10) + timedelta(minutes=20), "old-day-latest"),
                (now - timedelta(minutes=2), "recent-older"),
                (now - timedelta(minutes=1), "recent-latest"),
            ]
            for timestamp, wallet_balance in points:
                insert_account_snapshot(
                    path=db_path,
                    timestamp=timestamp,
                    source="poll",
                    wallet_balance=wallet_balance,
                    available_balance="0",
                    equity="0",
                    unrealized_pnl="0",
                    position_count=0,
                    open_order_count=0,
                    leader_symbol=None,
                    payload={},
                )

            snapshots = fetch_account_snapshots_for_range(path=db_path, now=now, range_key="ALL")

            self.assertEqual(
                [snapshot["wallet_balance"] for snapshot in snapshots],
                ["recent-latest", "old-day-latest"],
            )

    def test_fetch_account_snapshots_for_range_uses_window_specific_density(self) -> None:
        from momentum_alpha.runtime_store import fetch_account_snapshots_for_range, insert_account_snapshot

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
            for idx in range(0, 48 * 12):
                timestamp = now - timedelta(minutes=idx * 5)
                insert_account_snapshot(
                    path=db_path,
                    timestamp=timestamp,
                    source="poll",
                    wallet_balance=str(idx),
                    available_balance="0",
                    equity="0",
                    unrealized_pnl="0",
                    position_count=0,
                    open_order_count=0,
                    leader_symbol=None,
                    payload={},
                )

            one_day = fetch_account_snapshots_for_range(path=db_path, now=now, range_key="1D")
            one_week = fetch_account_snapshots_for_range(path=db_path, now=now, range_key="1W")

            self.assertLessEqual(len(one_day), 290)
            self.assertLessEqual(len(one_week), 50)
            self.assertLess(
                datetime.fromisoformat(one_week[-1]["timestamp"]),
                datetime.fromisoformat(one_day[-1]["timestamp"]),
            )

    def test_dashboard_helpers_return_leader_history_and_pulse_points(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_event_pulse_points,
            fetch_leader_history,
            insert_broker_order,
            insert_position_snapshot,
            insert_signal_decision,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            insert_position_snapshot(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
                source="poll",
                leader_symbol="ONUSDT",
                position_count=0,
                order_status_count=0,
                symbol_count=538,
                submit_orders=True,
                restore_positions=True,
                execute_stop_replacements=True,
                payload={},
            )
            insert_signal_decision(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc),
                source="poll",
                decision_type="base_entry",
                symbol="BLESSUSDT",
                previous_leader_symbol="ONUSDT",
                next_leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=0,
                payload={},
            )
            insert_broker_order(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc),
                source="poll",
                symbol="BLESSUSDT",
                action_type="submit",
                order_status="NEW",
                side="BUY",
                payload={},
            )
            insert_position_snapshot(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 2, tzinfo=timezone.utc),
                source="poll",
                leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=1,
                symbol_count=538,
                submit_orders=True,
                restore_positions=True,
                execute_stop_replacements=False,
                payload={},
            )

            leader_history = fetch_leader_history(path=db_path, limit=10)
            pulse_points = fetch_event_pulse_points(
                path=db_path,
                now=datetime(2026, 4, 15, 8, 5, tzinfo=timezone.utc),
                since_minutes=10,
                bucket_minutes=1,
                limit=10,
            )

            self.assertEqual([row["symbol"] for row in leader_history], ["BLESSUSDT", "ONUSDT"])
            self.assertEqual([row["bucket"] for row in pulse_points[-3:]], [
                "2026-04-15T08:00:00+00:00",
                "2026-04-15T08:01:00+00:00",
                "2026-04-15T08:02:00+00:00",
            ])

    def test_rebuild_trade_analytics_marks_algo_triggered_market_sell_as_stop_loss(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_recent_stop_exit_summaries,
            fetch_recent_trade_round_trips,
            insert_algo_order,
            insert_trade_fill,
            rebuild_trade_analytics,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            opened_at = datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc)
            closed_at = datetime(2026, 4, 15, 8, 5, tzinfo=timezone.utc)

            insert_trade_fill(
                path=db_path,
                timestamp=opened_at,
                source="user-stream",
                symbol="PIPPINUSDT",
                order_id="1001",
                trade_id="2001",
                client_order_id="ma_260415080000_PIPPINUSDT_b00e",
                order_status="FILLED",
                execution_type="TRADE",
                side="BUY",
                order_type="MARKET",
                quantity="100",
                cumulative_quantity="100",
                average_price="0.035",
                last_price="0.035",
                realized_pnl="0",
                commission="0.001",
                commission_asset="USDT",
                payload={},
            )
            insert_algo_order(
                path=db_path,
                timestamp=closed_at,
                source="user-stream",
                symbol="PIPPINUSDT",
                algo_id="3001",
                client_algo_id="ma_260415080000_PIPPINUSDT_b00s",
                algo_status="TRIGGERED",
                side="SELL",
                order_type="STOP_MARKET",
                trigger_price="0.0341",
                payload={},
            )
            insert_trade_fill(
                path=db_path,
                timestamp=closed_at,
                source="user-stream",
                symbol="PIPPINUSDT",
                order_id="1002",
                trade_id="2002",
                client_order_id="ma_260415080000_PIPPINUSDT_b00s",
                order_status="FILLED",
                execution_type="TRADE",
                side="SELL",
                order_type="MARKET",
                quantity="100",
                cumulative_quantity="100",
                average_price="0.034",
                last_price="0.034",
                realized_pnl="-0.1",
                commission="0.001",
                commission_asset="USDT",
                payload={},
            )

            rebuild_trade_analytics(path=db_path)

            round_trips = fetch_recent_trade_round_trips(path=db_path, limit=10)
            stop_exits = fetch_recent_stop_exit_summaries(path=db_path, limit=10)

            self.assertEqual(round_trips[0]["symbol"], "PIPPINUSDT")
            self.assertEqual(round_trips[0]["exit_reason"], "stop_loss")
            self.assertEqual(stop_exits[0]["symbol"], "PIPPINUSDT")
            self.assertEqual(stop_exits[0]["trigger_price"], "0.0341")

    def test_rebuild_trade_analytics_persists_leg_analytics_with_missing_stop_data(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_recent_trade_round_trips,
            fetch_recent_stop_exit_summaries,
            insert_algo_order,
            insert_trade_fill,
            rebuild_trade_analytics,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            opened_at = datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc)
            add_on_time = datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc)
            closed_at = datetime(2026, 4, 15, 8, 5, tzinfo=timezone.utc)

            insert_trade_fill(
                path=db_path,
                timestamp=opened_at,
                source="user-stream",
                symbol="LUMAUSDT",
                order_id="9001",
                trade_id="9101",
                client_order_id="ma_260415080000_LUMA_b00e",
                order_status="FILLED",
                execution_type="TRADE",
                side="BUY",
                order_type="MARKET",
                quantity="2",
                cumulative_quantity="2",
                average_price="10",
                last_price="10",
                realized_pnl="0",
                commission="0.10",
                commission_asset="USDT",
                payload={},
            )
            insert_algo_order(
                path=db_path,
                timestamp=opened_at,
                source="user-stream",
                symbol="LUMAUSDT",
                algo_id="8001",
                client_algo_id="ma_260415080000_LUMA_b00s",
                algo_status="NEW",
                side="SELL",
                order_type="STOP_MARKET",
                trigger_price="9.5",
                payload={},
            )
            insert_trade_fill(
                path=db_path,
                timestamp=add_on_time,
                source="user-stream",
                symbol="LUMAUSDT",
                order_id="9002",
                trade_id="9102",
                client_order_id="ma_260415080000_LUMA_a01e",
                order_status="FILLED",
                execution_type="TRADE",
                side="BUY",
                order_type="MARKET",
                quantity="3",
                cumulative_quantity="3",
                average_price="11",
                last_price="11",
                realized_pnl="0",
                commission="0.15",
                commission_asset="USDT",
                payload={},
            )
            insert_algo_order(
                path=db_path,
                timestamp=add_on_time,
                source="user-stream",
                symbol="LUMAUSDT",
                algo_id="8002",
                client_algo_id="ma_260415080001_LUMA_a01s",
                algo_status="NEW",
                side="SELL",
                order_type="STOP_MARKET",
                trigger_price="",
                payload={},
            )
            insert_trade_fill(
                path=db_path,
                timestamp=closed_at,
                source="user-stream",
                symbol="LUMAUSDT",
                order_id="9003",
                trade_id="9103",
                client_order_id="ma_260415080000_LUMA_b00s",
                order_status="FILLED",
                execution_type="TRADE",
                side="SELL",
                order_type="STOP_MARKET",
                quantity="5",
                cumulative_quantity="5",
                average_price="8",
                last_price="8",
                realized_pnl="-10",
                commission="0.25",
                commission_asset="USDT",
                payload={},
            )

            rebuild_trade_analytics(path=db_path)

            round_trips = fetch_recent_trade_round_trips(path=db_path, limit=10)
            stop_exits = fetch_recent_stop_exit_summaries(path=db_path, limit=10)
            payload = round_trips[0]["payload"]

            self.assertEqual(payload["leg_count"], 2)
            self.assertEqual(payload["add_on_leg_count"], 1)
            self.assertEqual(payload["base_leg_risk"], "1.0")
            self.assertIsNone(payload["peak_cumulative_risk"])
            self.assertEqual(len(payload["legs"]), 2)
            self.assertEqual(payload["legs"][0]["leg_index"], 1)
            self.assertEqual(payload["legs"][0]["leg_type"], "base")
            self.assertEqual(payload["legs"][0]["stop_price_at_entry"], "9.5")
            self.assertEqual(payload["legs"][0]["leg_risk"], "1.0")
            self.assertEqual(payload["legs"][0]["cumulative_risk_after_leg"], "1.0")
            self.assertEqual(payload["legs"][0]["gross_pnl_contribution"], "-4.0")
            self.assertEqual(payload["legs"][0]["fee_share"], "0.200")
            self.assertEqual(payload["legs"][0]["net_pnl_contribution"], "-4.200")
            self.assertEqual(payload["legs"][1]["leg_index"], 2)
            self.assertEqual(payload["legs"][1]["leg_type"], "add_on")
            self.assertIsNone(payload["legs"][1]["stop_price_at_entry"])
            self.assertIsNone(payload["legs"][1]["leg_risk"])
            self.assertIsNone(payload["legs"][1]["cumulative_risk_after_leg"])
            self.assertEqual(payload["legs"][1]["gross_pnl_contribution"], "-6.0")
            self.assertEqual(payload["legs"][1]["fee_share"], "0.300")
            self.assertEqual(payload["legs"][1]["net_pnl_contribution"], "-6.300")
            self.assertEqual(stop_exits[0]["trigger_price"], "9.5")

    def test_rebuild_trade_analytics_keeps_trade_visible_when_stop_price_is_missing(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_recent_trade_round_trips,
            insert_algo_order,
            insert_trade_fill,
            rebuild_trade_analytics,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            opened_at = datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc)
            closed_at = datetime(2026, 4, 19, 1, 20, tzinfo=timezone.utc)

            insert_trade_fill(
                path=db_path,
                timestamp=opened_at,
                source="user-stream",
                symbol="ETHUSDT",
                order_id="10",
                trade_id="210",
                client_order_id="manual-entry",
                order_status="FILLED",
                execution_type="TRADE",
                side="BUY",
                order_type="MARKET",
                quantity="1",
                cumulative_quantity="1",
                average_price="200",
                last_price="200",
                realized_pnl="0",
                commission="0.2",
                commission_asset="USDT",
                payload={},
            )
            insert_algo_order(
                path=db_path,
                timestamp=opened_at,
                source="user-stream",
                symbol="ETHUSDT",
                algo_id="310",
                client_algo_id="ma_260419010000_ETHUSDT_b00s",
                algo_status="NEW",
                side="SELL",
                order_type="STOP_MARKET",
                trigger_price="not-a-number",
                payload={},
            )
            insert_trade_fill(
                path=db_path,
                timestamp=closed_at,
                source="user-stream",
                symbol="ETHUSDT",
                order_id="11",
                trade_id="211",
                client_order_id="manual-exit",
                order_status="FILLED",
                execution_type="TRADE",
                side="SELL",
                order_type="MARKET",
                quantity="1",
                cumulative_quantity="1",
                average_price="210",
                last_price="210",
                realized_pnl="10",
                commission="0.3",
                commission_asset="USDT",
                payload={},
            )

            rebuild_trade_analytics(path=db_path)
            round_trips = fetch_recent_trade_round_trips(path=db_path, limit=10)

            self.assertEqual(len(round_trips), 1)
            payload = round_trips[0]["payload"]
            self.assertEqual(round_trips[0]["symbol"], "ETHUSDT")
            self.assertEqual(round_trips[0]["exit_reason"], "sell")
            self.assertEqual(payload["leg_count"], 1)
            self.assertEqual(payload["add_on_leg_count"], 0)
            self.assertIsNone(payload["base_leg_risk"])
            self.assertIsNone(payload["peak_cumulative_risk"])
            self.assertIsNone(payload["legs"][0]["stop_price_at_entry"])
            self.assertIsNone(payload["legs"][0]["leg_risk"])
            self.assertIsNone(payload["legs"][0]["cumulative_risk_after_leg"])

    def test_fetch_trade_round_trips_for_range_returns_newest_first_with_payload(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_trade_round_trips_for_range,
            insert_trade_round_trip,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            now = datetime(2026, 4, 15, 8, 30, tzinfo=timezone.utc)
            older_inside_range = datetime(2026, 4, 15, 7, 5, tzinfo=timezone.utc)
            newer_inside_range = datetime(2026, 4, 15, 8, 10, tzinfo=timezone.utc)
            outside_range = datetime(2026, 4, 14, 7, 0, tzinfo=timezone.utc)

            insert_trade_round_trip(
                path=db_path,
                round_trip_id="AAAUSDT:old",
                symbol="AAAUSDT",
                opened_at=older_inside_range,
                closed_at=older_inside_range,
                entry_fill_count=1,
                exit_fill_count=1,
                payload={"legs": [{"side": "BUY", "price": "1.01"}], "note": "older"},
            )
            insert_trade_round_trip(
                path=db_path,
                round_trip_id="AAAUSDT:new",
                symbol="AAAUSDT",
                opened_at=newer_inside_range,
                closed_at=newer_inside_range,
                entry_fill_count=2,
                exit_fill_count=1,
                payload={"legs": [{"side": "BUY", "price": "1.05"}], "note": "newer"},
            )
            insert_trade_round_trip(
                path=db_path,
                round_trip_id="AAAUSDT:tie",
                symbol="AAAUSDT",
                opened_at=newer_inside_range,
                closed_at=newer_inside_range,
                entry_fill_count=3,
                exit_fill_count=1,
                payload={"legs": [{"side": "BUY", "price": "1.08"}], "note": "tie"},
            )
            insert_trade_round_trip(
                path=db_path,
                round_trip_id="AAAUSDT:outside",
                symbol="AAAUSDT",
                opened_at=outside_range,
                closed_at=outside_range,
                entry_fill_count=1,
                exit_fill_count=1,
                payload={"legs": [{"side": "BUY", "price": "0.99"}], "note": "outside"},
            )

            round_trips = fetch_trade_round_trips_for_range(path=db_path, now=now, range_key="1D")

            self.assertEqual([row["round_trip_id"] for row in round_trips], ["AAAUSDT:tie", "AAAUSDT:new", "AAAUSDT:old"])
            self.assertEqual(round_trips[0]["payload"], {"legs": [{"side": "BUY", "price": "1.08"}], "note": "tie"})
            self.assertEqual(round_trips[1]["payload"], {"legs": [{"side": "BUY", "price": "1.05"}], "note": "newer"})
            self.assertEqual(round_trips[2]["payload"], {"legs": [{"side": "BUY", "price": "1.01"}], "note": "older"})

    def test_runtime_state_store_round_trips_strategy_state(self) -> None:
        from datetime import datetime, timezone
        from decimal import Decimal

        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.runtime_store import RuntimeStateStore
        from momentum_alpha.state_store import StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            store = RuntimeStateStore(path=db_path)
            state = StoredStrategyState(
                current_day="2026-04-15",
                previous_leader_symbol="BTCUSDT",
                positions={
                    "ETHUSDT": Position(
                        symbol="ETHUSDT",
                        stop_price=Decimal("106"),
                        legs=(
                            PositionLeg(
                                "ETHUSDT",
                                Decimal("2"),
                                Decimal("108"),
                                Decimal("106"),
                                datetime(2026, 4, 15, 1, 5, tzinfo=timezone.utc),
                                "stream_fill",
                            ),
                        ),
                    )
                },
                processed_event_ids={"evt-1": "2026-04-15T01:00:00+00:00"},
                order_statuses={"101": {"symbol": "ETHUSDT", "status": "NEW"}},
                recent_stop_loss_exits={"ETHUSDT": "2026-04-15T01:05:00+00:00"},
            )

            store.save(state)
            loaded = store.load()

            self.assertEqual(loaded.previous_leader_symbol, "BTCUSDT")
            self.assertEqual(loaded.positions["ETHUSDT"].total_quantity, Decimal("2"))
            self.assertEqual(loaded.processed_event_ids, {"evt-1": "2026-04-15T01:00:00+00:00"})
            self.assertEqual(loaded.order_statuses["101"]["status"], "NEW")
            self.assertEqual(loaded.recent_stop_loss_exits["ETHUSDT"], "2026-04-15T01:05:00+00:00")

    def test_runtime_state_store_merge_save_preserves_existing_fields(self) -> None:
        from momentum_alpha.runtime_store import RuntimeStateStore
        from momentum_alpha.state_store import StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            store = RuntimeStateStore(path=db_path)
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BTCUSDT",
                    processed_event_ids={"evt-1": "2026-04-15T01:00:00+00:00"},
                    order_statuses={"101": {"symbol": "BTCUSDT", "status": "NEW"}},
                    recent_stop_loss_exits={"BTCUSDT": "2026-04-15T01:05:00+00:00"},
                )
            )

            store.merge_save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="SOLUSDT",
                )
            )
            loaded = store.load()

            self.assertEqual(loaded.previous_leader_symbol, "SOLUSDT")
            self.assertEqual(loaded.processed_event_ids, {"evt-1": "2026-04-15T01:00:00+00:00"})
            self.assertEqual(loaded.order_statuses["101"]["status"], "NEW")
            self.assertEqual(loaded.recent_stop_loss_exits["BTCUSDT"], "2026-04-15T01:05:00+00:00")
