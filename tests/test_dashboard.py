import json
import os
import subprocess
import sys
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardTests(unittest.TestCase):
    def _build_tabbed_snapshot(self) -> dict:
        return {
            "health": {"overall_status": "OK", "items": [{"name": "poll", "status": "OK", "message": "fresh"}]},
            "runtime": {
                "previous_leader_symbol": "BTCUSDT",
                "position_count": 1,
                "order_status_count": 1,
                "latest_tick_result_timestamp": "2026-04-17T01:00:00+00:00",
                "latest_position_snapshot": {
                    "payload": {
                        "positions": {
                            "BTCUSDT": {
                                "symbol": "BTCUSDT",
                                "stop_price": "81000",
                                "latest_price": "83500",
                                "legs": [
                                    {
                                        "symbol": "BTCUSDT",
                                        "quantity": "0.01",
                                        "entry_price": "82000",
                                        "stop_price": "81000",
                                        "opened_at": "2026-04-17T00:30:00+00:00",
                                        "leg_type": "base",
                                    }
                                ],
                            }
                        },
                        "market_context": {"candidates": []},
                    }
                },
                "latest_account_snapshot": {
                    "wallet_balance": "1000.00",
                    "available_balance": "820.00",
                    "equity": "1080.00",
                    "unrealized_pnl": "20.00",
                    "position_count": 1,
                    "open_order_count": 1,
                },
                "latest_signal_decision": {
                    "decision_type": "base_entry",
                    "symbol": "BTCUSDT",
                    "timestamp": "2026-04-17T01:00:00+00:00",
                    "payload": {"blocked_reason": "risk_limit"},
                },
            },
            "recent_account_snapshots": [
                {
                    "timestamp": "2026-04-17T00:00:00+00:00",
                    "wallet_balance": "1000.00",
                    "available_balance": "950.00",
                    "equity": "1000.00",
                    "unrealized_pnl": "0.00",
                    "position_count": 0,
                    "open_order_count": 0,
                },
                {
                    "timestamp": "2026-04-17T01:00:00+00:00",
                    "wallet_balance": "1000.00",
                    "available_balance": "820.00",
                    "equity": "1080.00",
                    "unrealized_pnl": "20.00",
                    "position_count": 1,
                    "open_order_count": 1,
                },
            ],
            "recent_trade_round_trips": [
                {
                    "round_trip_id": "BTCUSDT:1",
                    "symbol": "BTCUSDT",
                    "opened_at": "2026-04-17T00:20:00+00:00",
                    "closed_at": "2026-04-17T00:50:00+00:00",
                    "net_pnl": "25.00",
                    "commission": "0.30",
                    "duration_seconds": 1800,
                }
            ],
            "recent_stop_exit_summaries": [
                {
                    "timestamp": "2026-04-17T00:51:00+00:00",
                    "symbol": "BTCUSDT",
                    "trigger_price": "81000.00",
                    "average_exit_price": "80920.00",
                    "slippage_pct": "0.10",
                    "commission": "0.05",
                    "net_pnl": "-8.00",
                }
            ],
            "recent_trade_fills": [
                {
                    "timestamp": "2026-04-17T00:40:00+00:00",
                    "trade_id": "fill-1",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "quantity": "0.01",
                    "average_price": "82000",
                    "commission": "0.02",
                    "order_status": "FILLED",
                }
            ],
            "recent_signal_decisions": [
                {"timestamp": "2026-04-17T01:00:00+00:00", "payload": {"blocked_reason": "risk_limit"}}
            ],
            "recent_events": [
                {
                    "timestamp": "2026-04-17T01:00:00+00:00",
                    "event_type": "tick_result",
                    "payload": {"symbol": "BTCUSDT"},
                    "source": "poll",
                }
            ],
            "recent_broker_orders": [],
            "event_counts": {"tick_result": 1},
            "source_counts": {"poll": 1},
            "leader_history": [{"timestamp": "2026-04-17T01:00:00+00:00", "symbol": "BTCUSDT"}],
            "pulse_points": [],
            "warnings": [],
            "strategy_config": {"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": False, "submit_orders": True},
        }

    def test_normalize_dashboard_tab_defaults_to_overview(self) -> None:
        from momentum_alpha.dashboard import normalize_dashboard_tab

        self.assertEqual(normalize_dashboard_tab(None), "overview")
        self.assertEqual(normalize_dashboard_tab(""), "overview")
        self.assertEqual(normalize_dashboard_tab("unknown"), "overview")

    def test_normalize_dashboard_tab_accepts_known_tabs(self) -> None:
        from momentum_alpha.dashboard import normalize_dashboard_tab

        self.assertEqual(normalize_dashboard_tab("overview"), "overview")
        self.assertEqual(normalize_dashboard_tab("execution"), "execution")
        self.assertEqual(normalize_dashboard_tab("performance"), "performance")
        self.assertEqual(normalize_dashboard_tab("system"), "system")

    def test_render_dashboard_html_defaults_to_overview_tab_and_renders_query_param_links(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(self._build_tabbed_snapshot())

        self.assertIn('?tab=overview', html)
        self.assertIn('?tab=execution', html)
        self.assertIn('?tab=performance', html)
        self.assertIn('?tab=system', html)
        self.assertIn('dashboard-tab is-active', html)
        self.assertIn('data-dashboard-tab-content="overview"', html)
        self.assertIn("LIVE OVERVIEW", html)
        self.assertIn("POSITION SUMMARY", html)
        self.assertIn("HOME COMMAND", html)
        self.assertIn("NEXT ACTIONS", html)
        self.assertNotIn("ACCOUNT OVERVIEW", html)
        self.assertNotIn("STOP SLIPPAGE ANALYSIS", html)
        self.assertNotIn("SYSTEM OPERATIONS", html)

    def test_render_dashboard_html_renders_execution_tab_without_overview_sections(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(self._build_tabbed_snapshot(), active_tab="execution")

        self.assertIn('data-dashboard-tab-content="execution"', html)
        self.assertIn("Execution Summary", html)
        self.assertIn("Recent Fills", html)
        self.assertIn("STOP SLIPPAGE ANALYSIS", html)
        self.assertNotIn("LIVE OVERVIEW", html)
        self.assertNotIn("ACTIVE POSITIONS", html)
        self.assertNotIn("SYSTEM OPERATIONS", html)

    def test_render_dashboard_html_execution_tab_surfaces_order_flow_diagnostics(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        snapshot = self._build_tabbed_snapshot()
        snapshot["recent_broker_orders"] = [
            {
                "timestamp": "2026-04-17T00:41:00+00:00",
                "symbol": "BTCUSDT",
                "action_type": "replace_stop_order",
                "order_type": "STOP_MARKET",
                "side": "SELL",
                "order_status": "NEW",
            }
        ]
        snapshot["recent_algo_orders"] = [
            {
                "timestamp": "2026-04-17T00:41:10+00:00",
                "symbol": "BTCUSDT",
                "algo_id": "77",
                "algo_status": "WORKING",
                "order_type": "STOP_MARKET",
                "trigger_price": "81000",
            }
        ]
        snapshot["recent_trade_fills"] = [
            {
                "timestamp": "2026-04-17T00:42:00+00:00",
                "trade_id": "fill-2",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": "0.01",
                "average_price": "82100",
                "commission": "0.02",
                "order_status": "FILLED",
                "order_type": "MARKET",
            }
        ]
        snapshot["recent_stop_exit_summaries"] = [
            {
                "timestamp": "2026-04-17T00:50:00+00:00",
                "symbol": "BTCUSDT",
                "trigger_price": "81000",
                "average_exit_price": "80950",
                "slippage_pct": "0.06",
                "net_pnl": "-8.00",
            }
        ]

        html = render_dashboard_html(snapshot, active_tab="execution")

        self.assertIn("ORDER FLOW", html)
        self.assertIn("Latest Broker Action", html)
        self.assertIn("replace_stop_order", html)
        self.assertIn("Latest Stop Order", html)
        self.assertIn("WORKING", html)
        self.assertIn("Latest Fill", html)
        self.assertIn("fill-2", html)
        self.assertIn("Latest Stop Exit", html)
        self.assertIn("80950", html)

    def test_render_dashboard_html_moves_full_account_metrics_to_performance_tab(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        overview_html = render_dashboard_html(self._build_tabbed_snapshot())
        performance_html = render_dashboard_html(self._build_tabbed_snapshot(), active_tab="performance")

        self.assertIn("HOME COMMAND", overview_html)
        self.assertNotIn("ACCOUNT OVERVIEW", overview_html)
        self.assertIn("ACCOUNT METRICS", performance_html)
        self.assertIn("ACCOUNT OVERVIEW", performance_html)
        self.assertIn("data-account-range=\"1D\"", performance_html)
        self.assertIn("data-account-metric=\"equity\"", performance_html)

    def test_format_timestamp_for_display_uses_utc_plus_8(self) -> None:
        from momentum_alpha.dashboard import format_timestamp_for_display

        self.assertEqual(
            format_timestamp_for_display("2026-04-15T08:52:00.734144+00:00"),
            "2026-04-15 16:52:00",
        )

    def test_load_dashboard_snapshot_combines_health_state_and_recent_audit(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot
        from momentum_alpha.models import Position
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"

            poll_log_file.write_text("tick 2026-04-15T06:00:00+00:00\n", encoding="utf-8")
            user_stream_log_file.write_text("listen_key=abc\n", encoding="utf-8")

            # Save state to runtime database
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="INUSDT",
                    positions={
                        "ETHUSDT": Position(symbol="ETHUSDT", stop_price=Decimal("95"), legs=())
                    },
                    order_statuses={"123": {"symbol": "ETHUSDT", "status": "NEW"}},
                )
            )

            insert_audit_event(
                path=runtime_db_file,
                timestamp=now,
                event_type="poll_tick",
                payload={"symbol_count": 538, "rate_limited_until": None},
                source="poll",
            )

            for path in (poll_log_file, user_stream_log_file):
                os.utime(path, (now.timestamp(), now.timestamp()))

            snapshot = load_dashboard_snapshot(
                now=now,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                runtime_db_file=runtime_db_file,
                recent_limit=10,
            )

            self.assertEqual(snapshot["health"]["overall_status"], "OK")
            self.assertEqual(snapshot["runtime"]["previous_leader_symbol"], "INUSDT")
            self.assertIn("event_counts", snapshot)

    def test_load_dashboard_snapshot_reports_missing_state_as_warning(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"

            for path in (poll_log_file, user_stream_log_file):
                path.write_text("x\n", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            snapshot = load_dashboard_snapshot(
                now=now,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                runtime_db_file=runtime_db_file,
                recent_limit=5,
            )

            self.assertEqual(snapshot["health"]["overall_status"], "FAIL")
            self.assertEqual(snapshot["runtime"]["previous_leader_symbol"], None)
            self.assertEqual(snapshot["runtime"]["position_count"], 0)

    def test_render_dashboard_html_includes_health_runtime_and_recent_events(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        snapshot = {
            "health": {
                "overall_status": "OK",
                "items": [{"name": "strategy_state", "status": "OK", "message": "fresh"}],
            },
            "runtime": {
                "previous_leader_symbol": "INUSDT",
                "position_count": 1,
                "order_status_count": 2,
                "latest_tick_timestamp": "2026-04-15T06:59:00+00:00",
                "latest_tick_result_timestamp": "2026-04-15T06:59:01+00:00",
                "latest_poll_worker_start_timestamp": "2026-04-15T06:58:00+00:00",
                "latest_user_stream_start_timestamp": "2026-04-15T06:58:05+00:00",
            },
            "recent_events": [
                {
                    "timestamp": "2026-04-15T06:59:01+00:00",
                    "event_type": "tick_result",
                    "payload": {"symbol_count": 538},
                    "source": "poll",
                }
            ],
            "event_counts": {"poll_tick": 12, "tick_result": 12, "user_stream_event": 3},
            "source_counts": {"poll": 24, "user-stream": 3},
            "leader_history": [{"timestamp": "2026-04-15T06:59:01+00:00", "symbol": "INUSDT"}],
            "pulse_points": [{"bucket": "2026-04-15T06:59:00+00:00", "event_count": 3}],
            "warnings": [],
        }
        overview_html = render_dashboard_html(snapshot)
        system_html = render_dashboard_html(snapshot, active_tab="system")

        self.assertIn("Momentum Alpha", overview_html)
        self.assertIn("交易监控面板", overview_html)
        self.assertIn("OK", overview_html)
        self.assertIn("INUSDT", overview_html)
        self.assertIn("setInterval(refreshDashboard, 5000)", overview_html)
        self.assertIn("window.location.pathname", overview_html)
        self.assertIn("app", overview_html)
        self.assertIn("metric", overview_html)
        self.assertIn("POSITION SUMMARY", overview_html)
        self.assertIn("HOME COMMAND", overview_html)
        self.assertIn("LIVE OVERVIEW", overview_html)
        self.assertIn("LEADER ROTATION", overview_html)
        self.assertIn("SYSTEM HEALTH", overview_html)
        self.assertNotIn("EXECUTION QUALITY", overview_html)
        self.assertNotIn("RECENT EVENTS", overview_html)
        self.assertIn("tick_result", system_html)
        self.assertIn("RECENT EVENTS", system_html)
        self.assertIn("2026-04-15 14:59:01", system_html)

    def test_render_dashboard_html_system_tab_surfaces_operational_diagnostics(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        snapshot = self._build_tabbed_snapshot()
        snapshot["health"] = {
            "overall_status": "DEGRADED",
            "items": [{"name": "poll", "status": "WARN", "message": "lagging"}],
        }
        snapshot["runtime"]["latest_tick_result_timestamp"] = "2026-04-17T01:05:00+00:00"
        snapshot["recent_events"] = [
            {
                "timestamp": "2026-04-17T01:05:00+00:00",
                "event_type": "tick_result",
                "payload": {"symbol": "BTCUSDT"},
                "source": "poll",
            }
        ]
        snapshot["source_counts"] = {"poll": 3, "user-stream": 1}
        snapshot["warnings"] = ["state file missing path=/tmp/runtime.json", "audit file invalid path=/tmp/audit.log"]

        html = render_dashboard_html(snapshot, active_tab="system")

        self.assertIn("SYSTEM DIAGNOSTICS", html)
        self.assertIn("Health Status", html)
        self.assertIn("DEGRADED", html)
        self.assertIn("Data Freshness", html)
        self.assertIn("2026-04-17 09:05:00", html)
        self.assertIn("Warning Count", html)
        self.assertIn(">2<", html)
        self.assertIn("Primary Source", html)
        self.assertIn("poll · 3", html)
        self.assertIn("ACTIVE WARNINGS", html)
        self.assertIn("state file missing path=/tmp/runtime.json", html)

    def test_render_dashboard_html_rebuilds_layout_around_trader_priorities(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        overview_html = render_dashboard_html(
            {
                "health": {
                    "overall_status": "OK",
                    "items": [{"name": "strategy_state", "status": "OK", "message": "fresh"}],
                },
                "runtime": {
                    "previous_leader_symbol": "INUSDT",
                    "position_count": 1,
                    "order_status_count": 2,
                    "latest_tick_timestamp": "2026-04-15T06:59:00+00:00",
                    "latest_tick_result_timestamp": "2026-04-15T06:59:01+00:00",
                    "latest_poll_worker_start_timestamp": "2026-04-15T06:58:00+00:00",
                    "latest_user_stream_start_timestamp": "2026-04-15T06:58:05+00:00",
                    "latest_signal_decision": {
                        "timestamp": "2026-04-15T06:59:01+00:00",
                        "decision_type": "base_entry",
                        "symbol": "INUSDT",
                        "payload": {"blocked_reason": None},
                    },
                    "latest_position_snapshot": {
                        "payload": {
                            "positions": {
                                "INUSDT": {
                                    "symbol": "INUSDT",
                                    "opened_at": "2026-04-15T06:40:00+00:00",
                                    "stop_price": "0.90",
                                    "legs": [
                                        {
                                            "symbol": "INUSDT",
                                            "quantity": "100",
                                            "entry_price": "1.00",
                                            "opened_at": "2026-04-15T06:40:00+00:00",
                                            "leg_type": "base",
                                        }
                                    ],
                                }
                            }
                        }
                    },
                    "latest_account_snapshot": {
                        "wallet_balance": "1000.00",
                        "available_balance": "780.00",
                        "equity": "1080.00",
                        "unrealized_pnl": "30.00",
                        "position_count": 1,
                        "open_order_count": 2,
                        "leader_symbol": "INUSDT",
                    },
                },
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-15T00:00:00+00:00",
                        "wallet_balance": "1000.00",
                        "available_balance": "900.00",
                        "equity": "1000.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                        "leader_symbol": "AAAUSDT",
                    },
                    {
                        "timestamp": "2026-04-15T06:59:00+00:00",
                        "wallet_balance": "1000.00",
                        "available_balance": "780.00",
                        "equity": "1080.00",
                        "unrealized_pnl": "30.00",
                        "position_count": 1,
                        "open_order_count": 2,
                        "leader_symbol": "INUSDT",
                    },
                ],
                "recent_trade_round_trips": [
                    {"closed_at": "2026-04-15T05:20:00+00:00", "net_pnl": "40.00", "duration_seconds": 600},
                    {"closed_at": "2026-04-15T06:10:00+00:00", "net_pnl": "-10.00", "duration_seconds": 300},
                ],
                "recent_stop_exit_summaries": [
                    {"timestamp": "2026-04-15T06:15:00+00:00", "slippage_pct": "1.50", "commission": "0.50"}
                ],
                "recent_signal_decisions": [
                    {
                        "timestamp": "2026-04-15T06:59:01+00:00",
                        "decision_type": "base_entry",
                        "symbol": "INUSDT",
                        "payload": {"blocked_reason": "risk_limit"},
                    }
                ],
                "leader_history": [
                    {"timestamp": "2026-04-15T06:00:00+00:00", "symbol": "AAAUSDT"},
                    {"timestamp": "2026-04-15T06:30:00+00:00", "symbol": "INUSDT"},
                ],
                "recent_events": [
                    {
                        "timestamp": "2026-04-15T06:59:01+00:00",
                        "event_type": "tick_result",
                        "payload": {"symbol_count": 538},
                        "source": "poll",
                    }
                ],
                "event_counts": {"poll_tick": 12, "tick_result": 12, "user_stream_event": 3},
                "source_counts": {"poll": 24, "user-stream": 3},
                "pulse_points": [{"bucket": "2026-04-15T06:59:00+00:00", "event_count": 3}],
                "warnings": [],
            }
        )

        for label in (
            "EQUITY",
            "TODAY NET PNL",
            "OPEN RISK / EQUITY",
            "SYSTEM HEALTH",
            "POSITION SUMMARY",
            "LIVE OVERVIEW",
        ):
            self.assertIn(label, overview_html)

        self.assertNotIn("EXECUTION QUALITY", overview_html)
        self.assertNotIn("STRATEGY PERFORMANCE", overview_html)
        self.assertNotIn("SYSTEM OPERATIONS", overview_html)
        self.assertLess(overview_html.index("LIVE OVERVIEW"), overview_html.index("POSITION SUMMARY"))

    def test_render_dashboard_html_refocuses_overview_as_home_entry(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(self._build_tabbed_snapshot())

        self.assertIn("HOME COMMAND", html)
        self.assertIn("POSITION SUMMARY", html)
        self.assertIn("ACTIVE POSITIONS", html)
        self.assertIn("NEXT ACTIONS", html)
        self.assertIn("Execution", html)
        self.assertIn("Performance", html)
        self.assertIn("System", html)
        self.assertNotIn("ACCOUNT SNAPSHOT", html)

    def test_render_dashboard_html_overview_surfaces_live_position_cockpit(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(self._build_tabbed_snapshot())

        self.assertIn("ACTIVE POSITIONS", html)
        self.assertIn("BTCUSDT", html)
        self.assertIn("81000", html)
        self.assertIn("MTM", html)
        self.assertIn("15.00", html)
        self.assertIn("PnL %", html)
        self.assertIn("Distance", html)
        self.assertIn("R Multiple", html)

    def test_render_dashboard_html_home_command_uses_computed_mtm_pnl(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(self._build_tabbed_snapshot())

        self.assertIn("MTM</div><div class='home-command-value'>+15.00", html)

    def test_render_dashboard_html_surfaces_execution_mode_in_global_header(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        live_html = render_dashboard_html(
            self._build_tabbed_snapshot(),
            strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": False, "submit_orders": True},
        )
        dry_run_html = render_dashboard_html(
            self._build_tabbed_snapshot(),
            strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": True, "submit_orders": False},
        )

        self.assertIn("PROD LIVE", live_html)
        self.assertIn("TESTNET DRY RUN", dry_run_html)

    def test_refresh_preserves_server_data_freshness_timestamp(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(self._build_tabbed_snapshot())

        self.assertIn("Last update <strong id='last-updated-text'>2026-04-17 09:00:00</strong>", html)
        self.assertNotIn("updateLastRefreshTimestamp();", html)

    def test_render_dashboard_html_marks_live_price_dependent_metrics_unavailable(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "INUSDT",
                    "position_count": 1,
                    "order_status_count": 0,
                    "latest_account_snapshot": {
                        "wallet_balance": "1000.00",
                        "available_balance": "850.00",
                        "equity": "1000.00",
                        "unrealized_pnl": None,
                        "position_count": 1,
                        "open_order_count": 0,
                        "leader_symbol": "INUSDT",
                    },
                    "latest_position_snapshot": {
                        "payload": {
                            "positions": {
                                "INUSDT": {
                                    "symbol": "INUSDT",
                                    "opened_at": "2026-04-15T06:40:00+00:00",
                                    "stop_price": "0.90",
                                    "legs": [
                                        {
                                            "symbol": "INUSDT",
                                            "quantity": "100",
                                            "entry_price": "1.00",
                                            "opened_at": "2026-04-15T06:40:00+00:00",
                                            "leg_type": "base",
                                        }
                                    ],
                                }
                            }
                        }
                    },
                },
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-15T06:59:00+00:00",
                        "wallet_balance": "1000.00",
                        "available_balance": "850.00",
                        "equity": "1000.00",
                        "unrealized_pnl": None,
                        "position_count": 1,
                        "open_order_count": 0,
                        "leader_symbol": "INUSDT",
                    }
                ],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
                "recent_events": [],
                "event_counts": {},
                "source_counts": {},
                "pulse_points": [],
                "warnings": [],
            }
        )

        self.assertNotIn("waiting for live price data", html)
        self.assertIn("n/a", html)

    def test_render_dashboard_html_uses_snapshot_strategy_config_without_explicit_argument(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "INUSDT",
                    "position_count": 0,
                    "order_status_count": 0,
                    "latest_account_snapshot": {
                        "wallet_balance": "1000.00",
                        "available_balance": "850.00",
                        "equity": "1000.00",
                    },
                },
                "recent_account_snapshots": [],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
                "recent_events": [],
                "event_counts": {},
                "source_counts": {},
                "pulse_points": [],
                "warnings": [],
                "strategy_config": {
                    "stop_budget_usdt": "25",
                    "entry_window": "02:00-18:00 UTC",
                    "testnet": True,
                    "submit_orders": False,
                },
            },
            active_tab="system",
        )

        self.assertIn("SYSTEM OPERATIONS", html)
        self.assertIn("Stop Budget", html)
        self.assertIn("25", html)
        self.assertIn("02:00-18:00 UTC", html)
        self.assertIn("Yes", html)
        self.assertIn("Submit Orders", html)
        self.assertIn("No", html)

    def test_render_dashboard_html_top_cards_fall_back_to_runtime_latest_account_snapshot(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "INUSDT",
                    "position_count": 0,
                    "order_status_count": 0,
                    "latest_account_snapshot": {
                        "wallet_balance": "1000.00",
                        "available_balance": "850.00",
                        "equity": "1000.00",
                        "unrealized_pnl": "5.00",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                },
                "recent_account_snapshots": [],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
                "recent_events": [],
                "event_counts": {},
                "source_counts": {},
                "pulse_points": [],
                "warnings": [],
            }
        )

        self.assertIn("EQUITY", html)
        self.assertIn("1,000.00", html)
        self.assertIn("Available Balance", html)
        self.assertIn("850.00", html)
        self.assertIn("Capital Pressure", html)
        self.assertIn("Margin Usage", html)
        self.assertIn("15.00%", html)

    def test_build_trader_summary_metrics_limits_today_net_pnl_to_display_calendar_day(self) -> None:
        from momentum_alpha.dashboard import build_trader_summary_metrics

        metrics = build_trader_summary_metrics(
            snapshot={
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-15T15:30:00+00:00",
                        "wallet_balance": "1000.00",
                        "available_balance": "900.00",
                        "equity": "1000.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                    {
                        "timestamp": "2026-04-15T16:30:00+00:00",
                        "wallet_balance": "1010.00",
                        "available_balance": "910.00",
                        "equity": "1010.00",
                        "unrealized_pnl": "10.00",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                    {
                        "timestamp": "2026-04-16T02:00:00+00:00",
                        "wallet_balance": "1035.00",
                        "available_balance": "935.00",
                        "equity": "1035.00",
                        "unrealized_pnl": "35.00",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                ],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
            },
            position_details=[],
            range_key="1D",
        )

        self.assertEqual(metrics["account"]["today_net_pnl"], 25.0)

    def test_build_trader_summary_metrics_anchors_today_net_pnl_to_newest_display_day_across_accounts_and_round_trips(self) -> None:
        from momentum_alpha.dashboard import build_trader_summary_metrics

        metrics = build_trader_summary_metrics(
            snapshot={
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-15T13:30:00+00:00",
                        "wallet_balance": "1000.00",
                        "available_balance": "900.00",
                        "equity": "1000.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                    {
                        "timestamp": "2026-04-15T14:30:00+00:00",
                        "wallet_balance": "1010.00",
                        "available_balance": "910.00",
                        "equity": "1010.00",
                        "unrealized_pnl": "10.00",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                ],
                "recent_trade_round_trips": [
                    {"closed_at": "2026-04-15T16:30:00+00:00", "net_pnl": "35.00"},
                ],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
            },
            position_details=[],
            range_key="1D",
        )

        self.assertEqual(metrics["account"]["today_net_pnl"], 35.0)

    def test_build_trader_summary_metrics_prefers_fresher_same_day_round_trips_over_stale_account_delta(self) -> None:
        from momentum_alpha.dashboard import build_trader_summary_metrics

        metrics = build_trader_summary_metrics(
            snapshot={
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-15T16:05:00+00:00",
                        "wallet_balance": "1000.00",
                        "available_balance": "900.00",
                        "equity": "1000.00",
                        "adjusted_equity": "1000.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                    {
                        "timestamp": "2026-04-15T16:20:00+00:00",
                        "wallet_balance": "1010.00",
                        "available_balance": "910.00",
                        "equity": "1010.00",
                        "adjusted_equity": "1010.00",
                        "unrealized_pnl": "10.00",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                ],
                "recent_trade_round_trips": [
                    {"closed_at": "2026-04-15T16:45:00+00:00", "net_pnl": "35.00"},
                ],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
            },
            position_details=[],
            range_key="1D",
        )

        self.assertEqual(metrics["account"]["today_net_pnl"], 35.0)

    def test_build_dashboard_response_json_serializes_snapshot(self) -> None:
        from momentum_alpha.dashboard import build_dashboard_response_json

        payload = build_dashboard_response_json(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {"previous_leader_symbol": "INUSDT"},
                "recent_events": [],
                "event_counts": dict(Counter(["poll_tick", "tick_result"])),
                "warnings": [],
            }
        )

        self.assertIn('"overall_status": "OK"', payload)
        self.assertIn('"previous_leader_symbol": "INUSDT"', payload)
        self.assertIn('"event_counts"', payload)

    def test_build_trader_summary_metrics_computes_account_risk_and_execution_stats(self) -> None:
        from momentum_alpha.dashboard import build_trader_summary_metrics

        metrics = build_trader_summary_metrics(
            snapshot={
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-16T00:00:00+00:00",
                        "wallet_balance": "1000.00",
                        "available_balance": "900.00",
                        "equity": "1000.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                        "leader_symbol": "AAAUSDT",
                    },
                    {
                        "timestamp": "2026-04-16T01:00:00+00:00",
                        "wallet_balance": "1030.00",
                        "available_balance": "780.00",
                        "equity": "1080.00",
                        "unrealized_pnl": "30.00",
                        "position_count": 2,
                        "open_order_count": 1,
                        "leader_symbol": "BBBUSDT",
                    },
                ],
                "recent_trade_round_trips": [
                    {"closed_at": "2026-04-16T00:20:00+00:00", "net_pnl": "40.00", "duration_seconds": 600, "commission": "0.25"},
                    {"closed_at": "2026-04-16T00:40:00+00:00", "net_pnl": "-10.00", "duration_seconds": 300, "commission": "0.20"},
                    {"closed_at": "2026-04-16T00:50:00+00:00", "net_pnl": "20.00", "duration_seconds": 900, "commission": "0.30"},
                ],
                "recent_stop_exit_summaries": [
                    {"timestamp": "2026-04-16T00:35:00+00:00", "slippage_pct": "1.50", "commission": "0.50"},
                    {"timestamp": "2026-04-16T00:45:00+00:00", "slippage_pct": "2.50", "commission": "0.75"},
                ],
                "recent_signal_decisions": [
                    {"timestamp": "2026-04-16T00:10:00+00:00", "payload": {"blocked_reason": "risk_limit"}},
                    {"timestamp": "2026-04-16T00:30:00+00:00", "payload": {"blocked_reason": "risk_limit"}},
                    {"timestamp": "2026-04-16T00:55:00+00:00", "payload": {"blocked_reason": "invalid_stop_price"}},
                ],
                "leader_history": [
                    {"timestamp": "2026-04-16T00:00:00+00:00", "symbol": "AAAUSDT"},
                    {"timestamp": "2026-04-16T00:15:00+00:00", "symbol": "BBBUSDT"},
                    {"timestamp": "2026-04-16T00:40:00+00:00", "symbol": "CCCUSDT"},
                ],
            },
            position_details=[
                {"symbol": "AAAUSDT", "risk": "50.00"},
                {"symbol": "BBBUSDT", "risk": "25.00"},
            ],
            range_key="1D",
        )

        self.assertEqual(metrics["account"]["today_net_pnl"], 80.0)
        self.assertEqual(metrics["account"]["margin_usage_pct"], 27.77777777777778)
        self.assertEqual(metrics["account"]["open_risk"], 75.0)
        self.assertEqual(metrics["account"]["open_risk_pct"], 6.944444444444445)
        self.assertEqual(metrics["performance"]["win_rate"], 2 / 3)
        self.assertEqual(metrics["performance"]["profit_factor"], 6.0)
        self.assertEqual(metrics["performance"]["current_streak"]["label"], "W1")
        self.assertEqual(metrics["performance"]["avg_win"], 30.0)
        self.assertEqual(metrics["performance"]["avg_loss"], -10.0)
        self.assertEqual(metrics["performance"]["expectancy"], 50.0 / 3.0)
        self.assertEqual(metrics["performance"]["avg_hold_time_seconds"], 600.0)
        self.assertEqual(metrics["execution"]["avg_slippage_pct"], 2.0)
        self.assertEqual(metrics["execution"]["max_slippage_pct"], 2.5)
        self.assertEqual(metrics["execution"]["fee_total"], 0.75)
        self.assertEqual(metrics["signals"]["blocked_reason_counts"]["risk_limit"], 2)
        self.assertEqual(metrics["signals"]["rotation_count"], 2)

    def test_build_trader_summary_metrics_returns_none_or_empty_values_when_data_missing(self) -> None:
        from momentum_alpha.dashboard import build_trader_summary_metrics

        metrics = build_trader_summary_metrics(
            snapshot={
                "recent_account_snapshots": [],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
            },
            position_details=[],
            range_key="1D",
        )

        self.assertIsNone(metrics["account"]["today_net_pnl"])
        self.assertIsNone(metrics["account"]["margin_usage_pct"])
        self.assertEqual(metrics["signals"]["blocked_reason_counts"], {})
        self.assertEqual(metrics["signals"]["rotation_count"], 0)

    def test_build_trader_summary_metrics_prefers_adjusted_equity_over_raw_equity_change(self) -> None:
        from momentum_alpha.dashboard import build_trader_summary_metrics

        metrics = build_trader_summary_metrics(
            snapshot={
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-16T00:00:00+00:00",
                        "wallet_balance": "1000.00",
                        "available_balance": "900.00",
                        "equity": "1000.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                        "leader_symbol": "AAAUSDT",
                    },
                    {
                        "timestamp": "2026-04-16T01:00:00+00:00",
                        "wallet_balance": "1100.00",
                        "available_balance": "1000.00",
                        "equity": "1100.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                        "leader_symbol": "AAAUSDT",
                    },
                ],
                "recent_account_flows": [
                    {
                        "timestamp": "2026-04-16T00:30:00+00:00",
                        "reason": "DEPOSIT",
                        "balance_change": "100.00",
                    }
                ],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
            },
            position_details=[],
            range_key="1D",
        )

        self.assertEqual(metrics["account"]["today_net_pnl"], 0.0)

    def test_build_trader_summary_metrics_falls_back_to_round_trip_pnl_when_account_history_is_missing(self) -> None:
        from momentum_alpha.dashboard import build_trader_summary_metrics

        metrics = build_trader_summary_metrics(
            snapshot={
                "recent_account_snapshots": [],
                "recent_trade_round_trips": [
                    {"closed_at": "2026-04-16T00:20:00+00:00", "net_pnl": "40.00"},
                    {"closed_at": "2026-04-16T00:40:00+00:00", "net_pnl": "-5.00"},
                ],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
            },
            position_details=[],
            range_key="1D",
        )

        self.assertEqual(metrics["account"]["today_net_pnl"], 35.0)

    def test_load_dashboard_snapshot_prefers_sqlite_runtime_store(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot
        from momentum_alpha.runtime_store import (
            RuntimeStateStore,
            StoredStrategyState,
            bootstrap_runtime_db,
            insert_audit_event,
            insert_position_snapshot,
            insert_signal_decision,
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"

            for path in (poll_log_file, user_stream_log_file):
                path.write_text("", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            # Save strategy state to database
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BLESSUSDT")
            )

            insert_signal_decision(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 58, 59, tzinfo=timezone.utc),
                source="poll",
                decision_type="base_entry",
                symbol="BLESSUSDT",
                previous_leader_symbol="INUSDT",
                next_leader_symbol="BLESSUSDT",
                payload={},
            )
            insert_position_snapshot(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 1, tzinfo=timezone.utc),
                source="poll",
                leader_symbol="BLESSUSDT",
                position_count=2,
                order_status_count=3,
                symbol_count=538,
                payload={},
            )
            insert_audit_event(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, tzinfo=timezone.utc),
                event_type="poll_tick",
                payload={"symbol_count": 538},
                source="poll",
            )
            insert_audit_event(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 2, tzinfo=timezone.utc),
                event_type="user_stream_worker_start",
                payload={"position_count": 0},
                source="user-stream",
            )

            snapshot = load_dashboard_snapshot(
                now=now,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                runtime_db_file=runtime_db_file,
                recent_limit=10,
            )

            self.assertEqual(snapshot["event_counts"]["poll_tick"], 1)
            self.assertEqual(snapshot["recent_events"][0]["event_type"], "user_stream_worker_start")
            self.assertEqual(snapshot["source_counts"]["poll"], 1)
            self.assertEqual(snapshot["source_counts"]["user-stream"], 1)
            self.assertEqual(snapshot["runtime"]["previous_leader_symbol"], "BLESSUSDT")
            self.assertEqual(snapshot["runtime"]["position_count"], 2)
            self.assertEqual(snapshot["runtime"]["order_status_count"], 3)

    def test_load_dashboard_snapshot_uses_sqlite_runtime_summary_when_state_file_missing(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot
        from momentum_alpha.runtime_store import RuntimeStateStore, insert_position_snapshot, insert_signal_decision
        from momentum_alpha.state_store import StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"

            for path in (poll_log_file, user_stream_log_file):
                path.write_text("", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            insert_signal_decision(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, tzinfo=timezone.utc),
                source="poll",
                decision_type="no_action",
                symbol="BLESSUSDT",
                previous_leader_symbol="ONUSDT",
                next_leader_symbol="BLESSUSDT",
                payload={"blocked_reason": "invalid_stop_price"},
            )
            insert_position_snapshot(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 1, tzinfo=timezone.utc),
                source="poll",
                leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=4,
                symbol_count=538,
                payload={},
            )
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BLESSUSDT",
                    processed_event_ids=["evt-1"],
                    order_statuses={"101": {"symbol": "BLESSUSDT", "status": "NEW"}},
                )
            )

            snapshot = load_dashboard_snapshot(
                now=now,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                runtime_db_file=runtime_db_file,
                recent_limit=10,
            )

            self.assertEqual(snapshot["runtime"]["previous_leader_symbol"], "BLESSUSDT")
            self.assertEqual(snapshot["runtime"]["position_count"], 1)
            self.assertEqual(snapshot["runtime"]["order_status_count"], 4)

    def test_load_dashboard_snapshot_includes_structured_runtime_summaries(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot
        from momentum_alpha.runtime_store import (
            RuntimeStateStore,
            StoredStrategyState,
            insert_account_snapshot,
            insert_broker_order,
            insert_position_snapshot,
            insert_signal_decision,
            insert_trade_fill,
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"

            for path in (poll_log_file, user_stream_log_file):
                path.write_text("", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BLESSUSDT")
            )

            insert_signal_decision(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, tzinfo=timezone.utc),
                symbol="BLESSUSDT",
                decision_type="no_action",
                previous_leader_symbol="ONUSDT",
                next_leader_symbol="BLESSUSDT",
                payload={"blocked_reason": "invalid_stop_price"},
                source="poll",
            )
            insert_broker_order(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 1, tzinfo=timezone.utc),
                symbol="BLESSUSDT",
                action_type="submit_entry",
                order_type="MARKET",
                status="NEW",
                payload={"quantity": "5"},
                source="poll",
            )
            insert_trade_fill(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 1, tzinfo=timezone.utc),
                source="user-stream",
                symbol="BLESSUSDT",
                order_id="1001",
                trade_id="2002",
                client_order_id="ma_foo",
                order_status="FILLED",
                execution_type="TRADE",
                side="BUY",
                order_type="MARKET",
                quantity="5",
                cumulative_quantity="5",
                average_price="0.1234",
                last_price="0.1234",
                realized_pnl="1.23",
                commission="0.01",
                commission_asset="USDT",
                payload={"maker": False},
            )
            insert_position_snapshot(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 2, tzinfo=timezone.utc),
                previous_leader_symbol="BLESSUSDT",
                position_count=1,
                order_status_count=2,
                symbol_count=538,
                payload={"positions": ["BLESSUSDT"]},
                source="poll",
            )
            insert_account_snapshot(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, 3, tzinfo=timezone.utc),
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

            snapshot = load_dashboard_snapshot(
                now=now,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                runtime_db_file=runtime_db_file,
                recent_limit=10,
            )

            self.assertEqual(snapshot["runtime"]["latest_signal_decision"]["decision_type"], "no_action")
            self.assertEqual(snapshot["runtime"]["latest_signal_decision"]["symbol"], "BLESSUSDT")
            self.assertEqual(snapshot["runtime"]["latest_signal_decision"]["payload"]["blocked_reason"], "invalid_stop_price")
            self.assertEqual(snapshot["runtime"]["latest_broker_order"]["action_type"], "submit_entry")
            self.assertEqual(snapshot["runtime"]["latest_position_snapshot"]["position_count"], 1)
            self.assertEqual(snapshot["runtime"]["latest_account_snapshot"]["wallet_balance"], "1234.56")
            self.assertEqual(snapshot["runtime"]["latest_account_snapshot"]["equity"], "1260.12")
            self.assertEqual(snapshot["recent_signal_decisions"][0]["symbol"], "BLESSUSDT")
            self.assertEqual(snapshot["recent_broker_orders"][0]["order_type"], "MARKET")
            self.assertEqual(snapshot["recent_trade_fills"][0]["trade_id"], "2002")
            self.assertEqual(snapshot["recent_account_snapshots"][0]["payload"]["account_alias"], "primary")

    def test_dashboard_api_helpers_split_summary_timeseries_and_tables(self) -> None:
        from momentum_alpha.dashboard import (
            build_dashboard_summary_payload,
            build_dashboard_tables_payload,
            build_dashboard_timeseries_payload,
        )

        snapshot = {
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "BLESSUSDT",
                "position_count": 1,
                "order_status_count": 2,
                "latest_tick_timestamp": "2026-04-15T08:49:00+00:00",
                "latest_signal_decision": {"decision_type": "base_entry", "symbol": "BLESSUSDT"},
                "latest_account_snapshot": {
                    "wallet_balance": "1234.56",
                    "available_balance": "1200.00",
                    "equity": "1260.12",
                    "unrealized_pnl": "25.56",
                    "position_count": 1,
                    "open_order_count": 2,
                },
            },
            "event_counts": {"poll_tick": 3},
            "source_counts": {"poll": 3},
            "leader_history": [{"timestamp": "2026-04-15T08:49:00+00:00", "symbol": "BLESSUSDT"}],
            "pulse_points": [{"bucket": "2026-04-15T08:49:00+00:00", "event_count": 3}],
            "recent_signal_decisions": [{"timestamp": "2026-04-15T08:49:00+00:00", "decision_type": "base_entry"}],
            "recent_broker_orders": [{"timestamp": "2026-04-15T08:49:01+00:00", "action_type": "submit_order"}],
            "recent_trade_fills": [{"timestamp": "2026-04-15T08:49:01+00:00", "trade_id": "2002", "symbol": "BLESSUSDT"}],
            "recent_trade_round_trips": [{"round_trip_id": "PLAYUSDT:1", "symbol": "PLAYUSDT", "net_pnl": "-43.85"}],
            "recent_stop_exit_summaries": [{"timestamp": "2026-04-15T08:49:02+00:00", "symbol": "PLAYUSDT", "slippage_pct": "4.99"}],
            "recent_position_snapshots": [{"timestamp": "2026-04-15T08:49:00+00:00", "leader_symbol": "BLESSUSDT"}],
            "recent_account_snapshots": [
                {
                    "timestamp": "2026-04-15T08:48:00+00:00",
                    "wallet_balance": "1230.00",
                    "available_balance": "1190.00",
                    "equity": "1250.00",
                    "unrealized_pnl": "20.00",
                    "position_count": 1,
                    "open_order_count": 1,
                    "leader_symbol": "ONUSDT",
                },
                {
                    "timestamp": "2026-04-15T08:49:00+00:00",
                    "wallet_balance": "1234.56",
                    "available_balance": "1200.00",
                    "equity": "1260.12",
                    "unrealized_pnl": "25.56",
                    "position_count": 1,
                    "open_order_count": 2,
                    "leader_symbol": "BLESSUSDT",
                },
            ],
            "recent_account_flows": [
                {
                    "timestamp": "2026-04-15T08:48:30+00:00",
                    "reason": "DEPOSIT",
                    "asset": "USDT",
                    "balance_change": "100.00",
                }
            ],
            "recent_events": [{"timestamp": "2026-04-15T08:49:00+00:00", "event_type": "poll_tick"}],
            "warnings": [],
        }

        summary = build_dashboard_summary_payload(snapshot)
        timeseries = build_dashboard_timeseries_payload(snapshot)
        tables = build_dashboard_tables_payload(snapshot)

        self.assertEqual(summary["account"]["wallet_balance"], 1234.56)
        self.assertEqual(summary["runtime"]["previous_leader_symbol"], "BLESSUSDT")
        self.assertEqual(timeseries["account"][0]["timestamp"], "2026-04-15T08:48:00+00:00")
        self.assertEqual(timeseries["account"][1]["equity"], 1260.12)
        self.assertEqual(timeseries["account"][0]["adjusted_equity"], 1250.00)
        self.assertEqual(timeseries["account"][1]["adjusted_equity"], 1160.12)
        self.assertEqual(tables["recent_signal_decisions"][0]["decision_type"], "base_entry")
        self.assertEqual(tables["recent_trade_fills"][0]["trade_id"], "2002")
        self.assertEqual(tables["recent_trade_round_trips"][0]["round_trip_id"], "PLAYUSDT:1")
        self.assertEqual(tables["recent_stop_exit_summaries"][0]["symbol"], "PLAYUSDT")
        self.assertEqual(tables["recent_account_snapshots"][1]["leader_symbol"], "BLESSUSDT")

    def test_load_dashboard_snapshot_uses_runtime_db_when_audit_file_missing(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"

            for path in (poll_log_file, user_stream_log_file):
                path.write_text("", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="ONUSDT")
            )

            insert_audit_event(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 58, tzinfo=timezone.utc),
                event_type="poll_worker_start",
                payload={"symbol_count": 538},
                source="poll",
            )
            insert_audit_event(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 15, 6, 59, tzinfo=timezone.utc),
                event_type="tick_result",
                payload={"next_previous_leader_symbol": "ONUSDT"},
                source="poll",
            )

            snapshot = load_dashboard_snapshot(
                now=now,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                runtime_db_file=runtime_db_file,
                recent_limit=10,
            )

            self.assertEqual(snapshot["health"]["overall_status"], "OK")
            self.assertEqual(snapshot["event_counts"]["poll_worker_start"], 1)
            self.assertEqual(snapshot["source_counts"]["poll"], 2)
            self.assertEqual(snapshot["leader_history"][0]["symbol"], "ONUSDT")

    def test_build_position_details_extracts_legs_from_payload(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        position_snapshot = {
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "stop_price": "81000",
                        "legs": [
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.01",
                                "entry_price": "82000",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T09:15:00+00:00",
                                "leg_type": "base"
                            },
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.005",
                                "entry_price": "82500",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T10:00:00+00:00",
                                "leg_type": "add_on"
                            }
                        ]
                    }
                }
            }
        }

        details = build_position_details(position_snapshot)

        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["symbol"], "BTCUSDT")
        self.assertEqual(details[0]["total_quantity"], "0.015")
        self.assertEqual(details[0]["entry_price"], "82166.67")
        self.assertEqual(details[0]["stop_price"], "81000")
        self.assertAlmostEqual(float(details[0]["risk"]), 17.50, places=2)

    def test_build_position_details_includes_richer_diagnostics(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        position_snapshot = {
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "opened_at": "2026-04-15T08:00:00+00:00",
                        "stop_price": "81000",
                        "legs": [
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.01",
                                "entry_price": "82000",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T09:15:00+00:00",
                                "leg_type": "base",
                            },
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.005",
                                "entry_price": "82500",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T10:00:00+00:00",
                                "leg_type": "add_on",
                            },
                        ],
                    }
                }
            }
        }

        details = build_position_details(position_snapshot, equity_value="1000")

        self.assertEqual(details[0]["leg_count"], 2)
        self.assertEqual(details[0]["opened_at"], "2026-04-15T08:00:00+00:00")
        self.assertEqual(details[0]["risk_pct_of_equity"], "1.75")
        self.assertIsNone(details[0]["mtm_pnl"])
        self.assertIsNone(details[0]["distance_to_stop_pct"])

    def test_build_position_details_treats_nonpositive_stop_price_as_unavailable(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        position_snapshot = {
            "payload": {
                "positions": {
                    "BASEUSDT": {
                        "symbol": "BASEUSDT",
                        "side": "LONG",
                        "total_quantity": "100",
                        "weighted_avg_entry_price": "10",
                        "stop_price": "0",
                        "latest_price": "12",
                        "legs": [],
                    }
                }
            }
        }

        details = build_position_details(position_snapshot, equity_value="1000")

        self.assertIsNone(details[0]["stop_price"])
        self.assertIsNone(details[0]["risk"])
        self.assertIsNone(details[0]["risk_pct_of_equity"])
        self.assertIsNone(details[0]["distance_to_stop_pct"])
        self.assertIsNone(details[0]["r_multiple"])
        self.assertEqual(details[0]["latest_price"], 12.0)
        self.assertEqual(details[0]["mtm_pnl"], 200.0)
        self.assertEqual(details[0]["pnl_pct"], 20.0)
        self.assertEqual(details[0]["notional_exposure"], 1200.0)

    def test_build_position_details_computes_live_price_diagnostics(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        position_snapshot = {
            "payload": {
                "positions": {
                    "BASEUSDT": {
                        "symbol": "BASEUSDT",
                        "side": "LONG",
                        "total_quantity": "100",
                        "weighted_avg_entry_price": "10",
                        "stop_price": "9",
                        "latest_price": "12",
                        "legs": [],
                    }
                }
            }
        }

        details = build_position_details(position_snapshot, equity_value="1000")

        self.assertEqual(details[0]["latest_price"], 12.0)
        self.assertEqual(details[0]["mtm_pnl"], 200.0)
        self.assertEqual(details[0]["pnl_pct"], 20.0)
        self.assertAlmostEqual(details[0]["distance_to_stop_pct"], 25.0)
        self.assertEqual(details[0]["notional_exposure"], 1200.0)
        self.assertEqual(details[0]["r_multiple"], 2.0)

    def test_format_metric_uses_unsigned_zero_for_signed_zero(self) -> None:
        from momentum_alpha.dashboard import _format_metric

        self.assertEqual(_format_metric(0.0, signed=True), "0.00")
        self.assertEqual(_format_metric(-0.0, signed=True), "0.00")

    def test_format_metric_preserves_near_zero_non_zero_values(self) -> None:
        from momentum_alpha.dashboard import _format_metric

        self.assertEqual(_format_metric(-0.0001, signed=True), "-0.00")
        self.assertEqual(_format_metric(0.0049, signed=True), "+0.00")

    def test_render_dashboard_html_formats_actual_zero_values_without_signed_zero(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "INUSDT",
                    "position_count": 0,
                    "order_status_count": 0,
                    "latest_account_snapshot": {
                        "wallet_balance": "1000.00",
                        "available_balance": "900.00",
                        "equity": "1000.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                        "leader_symbol": "INUSDT",
                    },
                },
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-15T06:00:00+00:00",
                        "wallet_balance": "1000.00",
                        "available_balance": "900.00",
                        "equity": "1000.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                        "leader_symbol": "INUSDT",
                    }
                ],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
                "recent_events": [],
                "event_counts": {},
                "source_counts": {},
                "pulse_points": [],
                "warnings": [],
            }
        )

        self.assertIn("numericValue === 0", html)
        self.assertNotIn("value >= 0 ? '+' : ''", html)

        start = html.index("function formatAccountValue")
        end = html.index("function formatAccountWindowTimestamp", start)
        formatter_source = html[start:end].strip()
        script = f"""
const formatAccountValue = {formatter_source}
const cases = [
  formatAccountValue(0, true),
  formatAccountValue(-0, true),
  formatAccountValue(-0.0001, true),
  formatAccountValue(0.0049, true),
  formatAccountValue(0, true, '%'),
];
console.log(JSON.stringify(cases));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            json.loads(completed.stdout.strip()),
            ["0.00", "0.00", "-0.00", "+0.00", "0.00%"],
        )

    def test_build_position_details_uses_earliest_leg_opened_at_when_position_timestamp_missing(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        position_snapshot = {
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "stop_price": "81000",
                        "legs": [
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.005",
                                "entry_price": "82500",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T10:00:00+00:00",
                                "leg_type": "add_on",
                            },
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.01",
                                "entry_price": "82000",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T09:15:00+00:00",
                                "leg_type": "base",
                            },
                        ],
                    }
                }
            }
        }

        details = build_position_details(position_snapshot, equity_value="1000")

        self.assertEqual(details[0]["opened_at"], "2026-04-15T09:15:00+00:00")

    def test_build_position_details_returns_empty_list_for_missing_payload(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        details = build_position_details({})
        self.assertEqual(details, [])

        details = build_position_details({"payload": {}})
        self.assertEqual(details, [])

    def test_build_position_details_returns_empty_list_for_non_mapping_positions(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        details = build_position_details({"payload": {"positions": ["BTCUSDT"]}})
        self.assertEqual(details, [])

    def test_build_position_details_renders_stop_dependent_fields_as_unavailable_when_stop_missing(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        position_snapshot = {
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "legs": [
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.01",
                                "entry_price": "82000",
                                "opened_at": "2026-04-15T09:15:00+00:00",
                                "leg_type": "base",
                            }
                        ],
                    }
                }
            }
        }

        details = build_position_details(position_snapshot, equity_value="1000")

        self.assertEqual(details[0]["stop_price"], None)
        self.assertEqual(details[0]["risk"], None)
        self.assertEqual(details[0]["risk_pct_of_equity"], None)

    def test_build_position_details_degrades_safely_for_malformed_nested_legs(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        malformed_details = build_position_details({
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "stop_price": "81000",
                        "legs": "invalid",
                    }
                }
            }
        })
        self.assertEqual(malformed_details, [])

        mixed_details = build_position_details({
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "stop_price": "81000",
                        "legs": [
                            None,
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.01",
                                "entry_price": "82000",
                                "opened_at": "2026-04-15T09:15:00+00:00",
                                "leg_type": "base",
                            },
                        ],
                    }
                }
            }
        }, equity_value="1000")

        self.assertEqual(len(mixed_details), 1)
        self.assertEqual(mixed_details[0]["symbol"], "BTCUSDT")
        self.assertEqual(mixed_details[0]["leg_count"], 1)

    def test_render_trade_history_table_generates_html_rows(self) -> None:
        from momentum_alpha.dashboard import render_trade_history_table

        orders = [
            {
                "timestamp": "2026-04-15T09:15:23+00:00",
                "symbol": "BTCUSDT",
                "trade_id": "1",
                "side": "BUY",
                "quantity": "0.015",
                "last_price": "82166.5",
                "commission": "0.12",
                "order_status": "FILLED",
            },
            {
                "timestamp": "2026-04-15T08:30:15+00:00",
                "symbol": "ETHUSDT",
                "trade_id": "2",
                "side": "SELL",
                "quantity": "0.12",
                "last_price": "3010.2",
                "commission": "0.03",
                "order_status": "FILLED",
            },
        ]

        html = render_trade_history_table(orders)

        self.assertIn("BTCUSDT", html)
        self.assertIn("ETHUSDT", html)
        # Timestamps should be converted to UTC+8 (Asia/Shanghai)
        # 09:15:23 UTC -> 17:15:23 UTC+8
        # 08:30:15 UTC -> 16:30:15 UTC+8
        self.assertIn("17:15:23", html)
        self.assertIn("16:30:15", html)
        self.assertIn("0.015", html)
        self.assertIn("0.12", html)
        self.assertIn("82,166.50", html)
        self.assertIn("3,010.20", html)
        self.assertIn("0.03", html)
        self.assertIn("FILLED", html)

    def test_render_dashboard_html_uses_explicit_headers_and_trimmed_precision(self) -> None:
        from momentum_alpha.dashboard import render_closed_trades_table, render_stop_slippage_table

        stop_html = render_stop_slippage_table(
            [
                {
                    "symbol": "KOMAUSDT",
                    "trigger_price": "0.011133889229651234",
                    "average_exit_price": "0.0098",
                    "slippage_pct": "-11.52678424",
                    "net_pnl": "-12.3456789",
                }
            ]
        )
        round_trip_html = render_closed_trades_table(
            [
                {
                    "symbol": "ORDIUSDT",
                    "round_trip_id": "ORDIUSDT:1",
                    "opened_at": "2026-04-17T11:41:01+08:00",
                    "closed_at": "2026-04-17T19:00:52+08:00",
                    "exit_reason": "sell",
                    "net_pnl": "73.12954018",
                }
            ]
        )

        self.assertIn("SYMBOL", stop_html)
        self.assertIn("STOP", stop_html)
        self.assertIn("EXEC", stop_html)
        self.assertIn("SLIP %", stop_html)
        self.assertIn("PNL", stop_html)
        self.assertIn("0.011134", stop_html)
        self.assertNotIn("0.011133889229651234", stop_html)
        self.assertIn("-11.53%", stop_html)
        self.assertIn("-12.35", stop_html)
        self.assertIn("SYMBOL", round_trip_html)
        self.assertIn("OPEN", round_trip_html)
        self.assertIn("CLOSE", round_trip_html)
        self.assertIn("EXIT", round_trip_html)
        self.assertIn("PNL", round_trip_html)
        self.assertIn("73.13", round_trip_html)
        self.assertNotIn("73.12954018", round_trip_html)

    def test_render_dashboard_html_trade_history_prefers_trade_fills(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html({
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "BTCUSDT",
                "position_count": 0,
                "order_status_count": 0,
                "latest_position_snapshot": {"payload": {}},
                "latest_account_snapshot": {"wallet_balance": "1000", "equity": "1000"},
                "latest_signal_decision": {},
            },
            "recent_broker_orders": [
                {"timestamp": "2026-04-15T09:15:23+00:00", "action_type": "stream_order_update", "symbol": "-", "order_status": "TRIGGERED"}
            ],
            "recent_trade_fills": [
                {"timestamp": "2026-04-15T09:15:23+00:00", "trade_id": "1", "symbol": "BTCUSDT", "side": "BUY", "quantity": "0.015", "last_price": "82166.5", "commission": "0.12", "order_status": "FILLED"}
            ],
            "recent_account_snapshots": [],
            "recent_events": [],
            "event_counts": {},
            "source_counts": {},
            "leader_history": [],
            "pulse_points": [],
            "warnings": [],
        }, strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": False, "submit_orders": True}, active_tab="execution")

        self.assertIn("BTCUSDT", html)
        fills_section = html[html.index("Recent Fills"):html.index("STOP SLIPPAGE ANALYSIS")]
        self.assertNotIn("stream_order_update", fills_section)

    def test_render_trade_history_table_shows_empty_message(self) -> None:
        from momentum_alpha.dashboard import render_trade_history_table

        html = render_trade_history_table([])
        self.assertIn("No trades", html)

    def test_build_strategy_config_extracts_from_runtime_config(self) -> None:
        from momentum_alpha.dashboard import build_strategy_config

        config = build_strategy_config(
            stop_budget_usdt="10",
            entry_start_hour_utc=1,
            entry_end_hour_utc=23,
            testnet=True,
            submit_orders=False,
        )

        self.assertEqual(config["stop_budget_usdt"], "10")
        self.assertEqual(config["entry_window"], "01:00-23:00 UTC")
        self.assertEqual(config["testnet"], True)
        self.assertEqual(config["submit_orders"], False)

    def test_render_position_cards_generates_html(self) -> None:
        from momentum_alpha.dashboard import render_position_cards

        positions = [
            {
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "total_quantity": "0.015",
                "entry_price": "82166.67",
                "stop_price": "81000",
                "risk": "17.50",
                "latest_price": "83000",
                "notional_exposure": "1245.00",
                "mtm_pnl": "12.50",
                "pnl_pct": "1.00",
                "distance_to_stop_pct": "2.00",
                "r_multiple": "0.25",
                "legs": [
                    {"type": "base", "time": "2026-04-15T09:15:00+00:00"},
                    {"type": "add_on", "time": "2026-04-15T10:00:00+00:00"},
                ],
            }
        ]

        html = render_position_cards(positions)

        self.assertIn("BTCUSDT", html)
        self.assertIn("LONG", html)
        self.assertIn("0.015", html)
        self.assertIn("82166.67", html)
        self.assertIn("81000", html)
        self.assertIn("17.50", html)
        self.assertIn("83000", html)
        self.assertIn("12.50", html)
        self.assertIn("1.00", html)
        self.assertIn("Notional", html)
        self.assertIn("1245.00", html)
        self.assertIn("Distance", html)
        self.assertIn("2.00", html)
        self.assertIn("R Multiple", html)
        self.assertIn("0.25", html)
        self.assertIn("base", html)
        self.assertIn("add_on", html)

    def test_render_position_cards_orders_by_risk_and_shows_unavailable_metrics(self) -> None:
        from momentum_alpha.dashboard import render_position_cards

        positions = [
            {
                "symbol": "LOWUSDT",
                "direction": "LONG",
                "total_quantity": "1",
                "entry_price": "10",
                "stop_price": "9",
                "risk": "2.00",
                "risk_pct_of_equity": "0.20",
                "leg_count": 1,
                "opened_at": "2026-04-15T08:00:00+00:00",
                "mtm_pnl": None,
                "distance_to_stop_pct": None,
                "legs": [{"type": "base", "time": "2026-04-15T08:00:00+00:00"}],
            },
            {
                "symbol": "HIGHUSDT",
                "direction": "LONG",
                "total_quantity": "1",
                "entry_price": "20",
                "stop_price": "18",
                "risk": "20.00",
                "risk_pct_of_equity": "2.00",
                "leg_count": 2,
                "opened_at": "2026-04-15T09:00:00+00:00",
                "mtm_pnl": None,
                "distance_to_stop_pct": None,
                "legs": [{"type": "base", "time": "2026-04-15T09:00:00+00:00"}],
            },
        ]

        html = render_position_cards(positions)

        self.assertLess(html.index("HIGHUSDT"), html.index("LOWUSDT"))
        self.assertIn("Risk %", html)
        self.assertIn("Legs", html)
        self.assertIn("Opened", html)
        self.assertIn("MTM", html)
        self.assertIn("n/a", html)
        self.assertNotIn("waiting for live price data", html)

    def test_render_position_cards_shows_empty_message(self) -> None:
        from momentum_alpha.dashboard import render_position_cards

        html = render_position_cards([])
        self.assertIn("No positions", html)

    def test_render_dashboard_html_includes_closed_trades_and_stop_slippage_sections(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        snapshot = {
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "PLAYUSDT",
                "position_count": 1,
                "order_status_count": 0,
                "latest_position_snapshot": {"payload": {}},
                "latest_account_snapshot": {"wallet_balance": "1000", "equity": "1000"},
                "latest_signal_decision": {},
            },
            "recent_broker_orders": [],
            "recent_trade_round_trips": [
                {
                    "round_trip_id": "PLAYUSDT:1",
                    "symbol": "PLAYUSDT",
                    "opened_at": "2026-04-15T20:48:00+00:00",
                    "closed_at": "2026-04-15T21:18:19+00:00",
                    "net_pnl": "-43.85",
                    "exit_reason": "stop_loss",
                }
            ],
            "recent_stop_exit_summaries": [
                {
                    "timestamp": "2026-04-15T21:18:19+00:00",
                    "symbol": "PLAYUSDT",
                    "trigger_price": "0.17687",
                    "average_exit_price": "0.16804",
                    "slippage_pct": "4.99",
                    "net_pnl": "-43.85",
                }
            ],
            "recent_account_snapshots": [],
            "recent_events": [],
            "event_counts": {},
            "source_counts": {},
            "leader_history": [],
            "pulse_points": [],
            "warnings": [],
        }
        performance_html = render_dashboard_html(
            snapshot,
            strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": False, "submit_orders": True},
            active_tab="performance",
        )
        execution_html = render_dashboard_html(
            snapshot,
            strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": False, "submit_orders": True},
            active_tab="execution",
        )

        self.assertIn("STRATEGY PERFORMANCE", performance_html)
        self.assertIn("PLAYUSDT:1", performance_html)
        self.assertIn("STOP SLIPPAGE ANALYSIS", execution_html)
        self.assertIn("0.17687", execution_html)

    def test_render_dashboard_tab_bar_uses_relative_tab_links(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_tab_bar

        html = render_dashboard_tab_bar("overview")

        self.assertIn('href="?tab=overview"', html)
        self.assertIn('href="?tab=execution"', html)
        self.assertNotIn('href="/?tab=overview"', html)

    def test_render_dashboard_html_includes_positions_section(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        snapshot = {
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "BTCUSDT",
                "position_count": 1,
                "order_status_count": 2,
                "latest_position_snapshot": {
                    "payload": {
                        "positions": {
                            "BTCUSDT": {
                                "symbol": "BTCUSDT",
                                "stop_price": "81000",
                                "legs": [{"symbol": "BTCUSDT", "quantity": "0.01", "entry_price": "82000", "stop_price": "81000", "opened_at": "2026-04-15T09:15:00+00:00", "leg_type": "base"}]
                            }
                        }
                    }
                },
                "latest_account_snapshot": {"wallet_balance": "1000", "equity": "1000"},
                "latest_signal_decision": {},
            },
            "recent_broker_orders": [],
            "recent_account_snapshots": [],
            "recent_events": [],
            "event_counts": {},
            "source_counts": {},
            "leader_history": [],
            "pulse_points": [],
            "warnings": [],
        }
        overview_html = render_dashboard_html(
            snapshot,
            strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": True, "submit_orders": False},
        )
        system_html = render_dashboard_html(
            snapshot,
            strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": True, "submit_orders": False},
            active_tab="system",
        )

        self.assertIn("POSITION SUMMARY", overview_html)
        self.assertNotIn("EXECUTION QUALITY", overview_html)
        self.assertIn("SYSTEM OPERATIONS", system_html)
        self.assertIn("Stop Budget", system_html)
        self.assertIn("10", system_html)

    def test_render_dashboard_html_shows_risk_pct_when_equity_is_available(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html({
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "BTCUSDT",
                "position_count": 1,
                "order_status_count": 0,
                "latest_position_snapshot": {
                    "payload": {
                        "positions": {
                            "BTCUSDT": {
                                "symbol": "BTCUSDT",
                                "stop_price": "81000",
                                "legs": [
                                    {
                                        "symbol": "BTCUSDT",
                                        "quantity": "0.01",
                                        "entry_price": "82000",
                                        "stop_price": "81000",
                                        "opened_at": "2026-04-15T09:15:00+00:00",
                                        "leg_type": "base",
                                    }
                                ],
                            }
                        }
                    }
                },
                "latest_account_snapshot": {"wallet_balance": "1000", "equity": "1000"},
                "latest_signal_decision": {},
            },
            "recent_broker_orders": [],
            "recent_account_snapshots": [],
            "recent_events": [],
            "event_counts": {},
            "source_counts": {},
            "leader_history": [],
            "pulse_points": [],
            "warnings": [],
        }, strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": True, "submit_orders": False})

        self.assertIn("Risk %", html)
        self.assertIn("1.00%", html)
        self.assertNotIn("Risk %</span><span class='metric-value'>n/a", html)

    def test_load_dashboard_snapshot_loads_extended_account_history_from_runtime_db(self) -> None:
        from momentum_alpha.dashboard import load_dashboard_snapshot
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_account_snapshot

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 16, 2, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"

            for path in (poll_log_file, user_stream_log_file):
                path.write_text("", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="PLAYUSDT")
            )

            start = datetime(2026, 4, 15, 0, 0, tzinfo=timezone.utc)
            for idx in range(64):
                insert_account_snapshot(
                    path=runtime_db_file,
                    timestamp=start + timedelta(minutes=idx),
                    source="poll",
                    wallet_balance=str(100 + idx),
                    available_balance=str(90 + idx),
                    equity=str(110 + idx),
                    unrealized_pnl=str(idx),
                    position_count=1,
                    open_order_count=1,
                    leader_symbol="PLAYUSDT",
                    payload={},
                )

            snapshot = load_dashboard_snapshot(
                now=now,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                runtime_db_file=runtime_db_file,
                recent_limit=10,
            )

            self.assertEqual(len(snapshot["recent_account_snapshots"]), 64)
            self.assertEqual(snapshot["recent_account_snapshots"][0]["wallet_balance"], "163")
            self.assertEqual(snapshot["recent_account_snapshots"][-1]["wallet_balance"], "100")

    def test_render_dashboard_html_redesigns_account_metrics_as_single_interactive_panel(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "PLAYUSDT",
                    "position_count": 1,
                    "order_status_count": 0,
                    "latest_position_snapshot": {"payload": {}},
                    "latest_account_snapshot": {
                        "wallet_balance": "62.52",
                        "available_balance": "58.00",
                        "equity": "59.58",
                        "unrealized_pnl": "-2.94",
                        "position_count": 1,
                        "open_order_count": 0,
                    },
                    "latest_signal_decision": {},
                },
                "recent_broker_orders": [],
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-15T18:00:00+00:00",
                        "wallet_balance": "100.00",
                        "available_balance": "95.00",
                        "equity": "100.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                        "leader_symbol": "PLAYUSDT",
                    },
                    {
                        "timestamp": "2026-04-16T02:00:00+00:00",
                        "wallet_balance": "62.52",
                        "available_balance": "58.00",
                        "equity": "59.58",
                        "unrealized_pnl": "-2.94",
                        "position_count": 1,
                        "open_order_count": 0,
                        "leader_symbol": "PLAYUSDT",
                    },
                ],
                "recent_events": [],
                "event_counts": {},
                "source_counts": {},
                "leader_history": [],
                "pulse_points": [],
                "warnings": [],
            },
            strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": False, "submit_orders": True},
            active_tab="performance",
        )

        self.assertIn("ACCOUNT METRICS", html)
        self.assertIn("ACCOUNT OVERVIEW", html)
        self.assertIn("PEAK EQUITY", html)
        self.assertIn("CURRENT DRAWDOWN", html)
        for range_key in ("1H", "1D", "1W", "1M", "1Y", "ALL"):
            self.assertIn(f"data-account-range=\"{range_key}\"", html)
        self.assertIn("data-account-range=\"ALL\"", html)
        self.assertIn("data-account-metric=\"equity\"", html)
        self.assertIn("data-account-metric=\"adjusted_equity\"", html)
        self.assertIn("data-account-metric=\"wallet_balance\"", html)
        self.assertIn("data-account-metric=\"unrealized_pnl\"", html)
        self.assertIn("ADJUSTED EQUITY", html)
        self.assertIn("accountMetricsData", html)

    def test_account_overview_js_supports_requested_range_windows(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(self._build_tabbed_snapshot(), active_tab="performance")

        self.assertIn("'1H': 1", html)
        self.assertIn("'1D': 24", html)
        self.assertIn("'1W': 24 * 7", html)
        self.assertIn("'1M': 24 * 30", html)
        self.assertIn("'1Y': 24 * 365", html)
        self.assertIn("localStorage.getItem('dashboard.account.range') || '1D'", html)

    def test_filter_rows_for_range_supports_requested_windows(self) -> None:
        from momentum_alpha.dashboard import _filter_rows_for_range

        rows = [
            {"timestamp": "2026-01-01T00:00:00+00:00", "value": "old"},
            {"timestamp": "2026-04-10T00:00:00+00:00", "value": "week"},
            {"timestamp": "2026-04-17T00:00:00+00:00", "value": "latest"},
        ]

        self.assertEqual(
            [row["value"] for row in _filter_rows_for_range(rows, timestamp_key="timestamp", range_key="1W")],
            ["week", "latest"],
        )
        self.assertEqual(
            [row["value"] for row in _filter_rows_for_range(rows, timestamp_key="timestamp", range_key="1D")],
            ["latest"],
        )
        self.assertEqual(
            [row["value"] for row in _filter_rows_for_range(rows, timestamp_key="timestamp", range_key="1Y")],
            ["old", "week", "latest"],
        )

    def test_render_dashboard_html_account_overview_js_preserves_missing_unrealized_pnl(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "BLESSUSDT",
                    "position_count": 1,
                    "order_status_count": 0,
                    "latest_account_snapshot": {
                        "wallet_balance": "1234.56",
                        "available_balance": "1200.00",
                        "equity": "1260.12",
                        "unrealized_pnl": None,
                        "position_count": 1,
                        "open_order_count": 0,
                    },
                },
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-15T08:48:00+00:00",
                        "wallet_balance": "1230.00",
                        "available_balance": "1190.00",
                        "equity": "1250.00",
                        "unrealized_pnl": None,
                        "position_count": 1,
                        "open_order_count": 0,
                        "leader_symbol": "BLESSUSDT",
                    },
                    {
                        "timestamp": "2026-04-15T08:49:00+00:00",
                        "wallet_balance": "1234.56",
                        "available_balance": "1200.00",
                        "equity": "1260.12",
                        "unrealized_pnl": None,
                        "position_count": 1,
                        "open_order_count": 0,
                        "leader_symbol": "BLESSUSDT",
                    },
                ],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
                "recent_events": [],
                "event_counts": {},
                "source_counts": {},
                "pulse_points": [],
                "warnings": [],
            }
        )

        self.assertIn("formatAccountValue(last.unrealized_pnl, true)", html)
        self.assertIn("unrealized_pnl: computeDelta(first.unrealized_pnl, last.unrealized_pnl)", html)
        self.assertNotIn("Number(last.unrealized_pnl ?? 0)", html)
        self.assertNotIn("Number(first.unrealized_pnl ?? 0)", html)

    def test_render_dashboard_html_chart_js_preserves_missing_metric_values(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "BLESSUSDT",
                    "position_count": 1,
                    "order_status_count": 0,
                    "latest_account_snapshot": {
                        "wallet_balance": "1234.56",
                        "available_balance": "1200.00",
                        "equity": "1260.12",
                        "unrealized_pnl": None,
                        "position_count": 1,
                        "open_order_count": 0,
                    },
                },
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-15T08:48:00+00:00",
                        "wallet_balance": "1230.00",
                        "available_balance": "1190.00",
                        "equity": "1250.00",
                        "unrealized_pnl": None,
                        "position_count": 1,
                        "open_order_count": 0,
                        "leader_symbol": "BLESSUSDT",
                    },
                    {
                        "timestamp": "2026-04-15T08:49:00+00:00",
                        "wallet_balance": "1234.56",
                        "available_balance": "1200.00",
                        "equity": "1260.12",
                        "unrealized_pnl": None,
                        "position_count": 1,
                        "open_order_count": 0,
                        "leader_symbol": "BLESSUSDT",
                    },
                ],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_signal_decisions": [],
                "leader_history": [],
                "recent_events": [],
                "event_counts": {},
                "source_counts": {},
                "pulse_points": [],
                "warnings": [],
            }
        )

        self.assertIn("const values = points.map((point) => point[metric])", html)
        self.assertIn("filter((value) => value !== null && value !== undefined && !Number.isNaN(value))", html)
        self.assertIn("return `<div class=\"chart-empty\"><span class=\"chart-empty-icon\">◎</span><span>waiting for visible metric data</span></div>`;", html)
        self.assertNotIn("Number(point[metric] ?? 0)", html)

    def test_render_dashboard_html_surfaces_execution_performance_and_signal_aggregates(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        snapshot = {
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "CCCUSDT",
                "position_count": 1,
                "order_status_count": 0,
                "latest_position_snapshot": {"payload": {}},
                "latest_account_snapshot": {
                    "wallet_balance": "1030.00",
                    "available_balance": "780.00",
                    "equity": "1080.00",
                    "unrealized_pnl": "30.00",
                    "position_count": 1,
                    "open_order_count": 0,
                },
                "latest_signal_decision": {
                    "decision_type": "base_entry",
                    "symbol": "CCCUSDT",
                    "timestamp": "2026-04-16T00:55:00+00:00",
                    "payload": {"blocked_reason": "risk_limit"},
                },
            },
            "recent_account_snapshots": [
                {
                    "timestamp": "2026-04-16T00:00:00+00:00",
                    "wallet_balance": "1000.00",
                    "available_balance": "900.00",
                    "equity": "1000.00",
                    "unrealized_pnl": "0.00",
                    "position_count": 0,
                    "open_order_count": 0,
                    "leader_symbol": "AAAUSDT",
                },
                {
                    "timestamp": "2026-04-16T01:00:00+00:00",
                    "wallet_balance": "1030.00",
                    "available_balance": "780.00",
                    "equity": "1080.00",
                    "unrealized_pnl": "30.00",
                    "position_count": 1,
                    "open_order_count": 0,
                    "leader_symbol": "CCCUSDT",
                },
            ],
            "recent_trade_round_trips": [
                {
                    "round_trip_id": "AAAUSDT:1",
                    "symbol": "AAAUSDT",
                    "opened_at": "2026-04-16T00:10:00+00:00",
                    "closed_at": "2026-04-16T00:20:00+00:00",
                    "net_pnl": "40.00",
                    "commission": "0.25",
                    "duration_seconds": 600,
                },
                {
                    "round_trip_id": "BBBUSDT:1",
                    "symbol": "BBBUSDT",
                    "opened_at": "2026-04-16T00:30:00+00:00",
                    "closed_at": "2026-04-16T00:35:00+00:00",
                    "net_pnl": "-10.00",
                    "commission": "0.20",
                    "duration_seconds": 300,
                },
                {
                    "round_trip_id": "CCCUSDT:1",
                    "symbol": "CCCUSDT",
                    "opened_at": "2026-04-16T00:40:00+00:00",
                    "closed_at": "2026-04-16T00:55:00+00:00",
                    "net_pnl": "20.00",
                    "commission": "0.30",
                    "duration_seconds": 900,
                },
            ],
            "recent_stop_exit_summaries": [
                {"timestamp": "2026-04-16T00:35:00+00:00", "symbol": "BBBUSDT", "slippage_pct": "1.50", "commission": "0.20"},
                {"timestamp": "2026-04-16T00:45:00+00:00", "symbol": "CCCUSDT", "slippage_pct": "2.50", "commission": "0.30"},
            ],
            "recent_trade_fills": [
                {"timestamp": "2026-04-16T00:45:00+00:00", "trade_id": "1", "symbol": "CCCUSDT", "side": "BUY", "quantity": "10", "last_price": "1.23", "commission": "0.01", "order_status": "FILLED"}
            ],
            "recent_signal_decisions": [
                {"timestamp": "2026-04-16T00:10:00+00:00", "payload": {"blocked_reason": "risk_limit"}},
                {"timestamp": "2026-04-16T00:30:00+00:00", "payload": {"blocked_reason": "risk_limit"}},
                {"timestamp": "2026-04-16T00:55:00+00:00", "payload": {"blocked_reason": "invalid_stop_price"}},
            ],
            "leader_history": [
                {"timestamp": "2026-04-16T00:00:00+00:00", "symbol": "AAAUSDT"},
                {"timestamp": "2026-04-16T00:15:00+00:00", "symbol": "BBBUSDT"},
                {"timestamp": "2026-04-16T00:40:00+00:00", "symbol": "CCCUSDT"},
            ],
            "recent_events": [],
            "recent_broker_orders": [],
            "event_counts": {},
            "source_counts": {},
            "pulse_points": [],
            "warnings": [],
            "strategy_config": {"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": False, "submit_orders": True},
        }
        overview_html = render_dashboard_html(snapshot)
        execution_html = render_dashboard_html(snapshot, active_tab="execution")
        performance_html = render_dashboard_html(snapshot, active_tab="performance")

        self.assertIn("Rotation Count", overview_html)
        self.assertIn("Blocked Reasons", overview_html)
        self.assertIn("risk_limit: 2", overview_html)
        self.assertIn("invalid_stop_price: 1", overview_html)
        self.assertIn("signal-breakdown", overview_html)
        self.assertIn("signal-breakdown-item", overview_html)
        self.assertIn("signal-breakdown-label", overview_html)
        self.assertIn("signal-breakdown-count", overview_html)

        self.assertIn("Avg Slippage", execution_html)
        self.assertIn("Max Slippage", execution_html)
        self.assertIn("Stop Exits", execution_html)
        self.assertIn("Fee Total", execution_html)
        self.assertIn("2.00%", execution_html)
        self.assertIn("0.75", execution_html)

        self.assertIn("Avg Win", performance_html)
        self.assertIn("Avg Loss", performance_html)
        self.assertIn("Expectancy", performance_html)
        self.assertIn("Avg Hold", performance_html)
        self.assertIn("30.00", performance_html)
        self.assertIn("-10.00", performance_html)
        self.assertIn("16.67", performance_html)
        self.assertIn("10m 00s", performance_html)

    def test_render_dashboard_html_falls_back_to_stop_prices_for_slippage_summary_and_compacts_empty_blocked_state(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        snapshot = {
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "BASEUSDT",
                "position_count": 0,
                "order_status_count": 0,
                "latest_position_snapshot": {"payload": {}},
                "latest_account_snapshot": {
                    "wallet_balance": "1000.00",
                    "available_balance": "900.00",
                    "equity": "1000.00",
                    "unrealized_pnl": "0.00",
                    "position_count": 0,
                    "open_order_count": 0,
                },
                "latest_signal_decision": {
                    "decision_type": "no_action",
                    "symbol": "BASEUSDT",
                    "timestamp": "2026-04-17T00:04:00+00:00",
                    "payload": {},
                },
            },
            "recent_account_snapshots": [
                {
                    "timestamp": "2026-04-17T00:00:00+00:00",
                    "wallet_balance": "1000.00",
                    "available_balance": "900.00",
                    "equity": "1000.00",
                    "unrealized_pnl": "0.00",
                    "position_count": 0,
                    "open_order_count": 0,
                }
            ],
            "recent_trade_round_trips": [],
            "recent_stop_exit_summaries": [
                {"timestamp": "2026-04-15T00:35:00+00:00", "symbol": "BBBUSDT", "trigger_price": "10.0", "average_exit_price": "9.85", "commission": "0.20", "net_pnl": "-10.00"},
                {"timestamp": "2026-04-15T00:45:00+00:00", "symbol": "CCCUSDT", "trigger_price": "20.0", "average_exit_price": "19.50", "commission": "0.30", "net_pnl": "-20.00"},
            ],
            "recent_trade_fills": [],
            "recent_signal_decisions": [],
            "leader_history": [],
            "recent_events": [],
            "recent_broker_orders": [],
            "event_counts": {},
            "source_counts": {},
            "pulse_points": [],
            "warnings": [],
        }
        overview_html = render_dashboard_html(snapshot)
        execution_html = render_dashboard_html(snapshot, active_tab="execution")

        self.assertIn("2.00%", execution_html)
        self.assertIn("2.50%", execution_html)
        self.assertIn("No blocked signals", overview_html)
        blocked_section = overview_html[overview_html.index("Blocked Reasons"):overview_html.index("RISK &amp; DEPLOYMENT", overview_html.index("Blocked Reasons"))]
        self.assertNotIn('class="decision-value"', blocked_section)

    def test_render_dashboard_html_surfaces_rotation_summary_and_risk_state(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "BASEUSDT",
                    "position_count": 2,
                    "order_status_count": 0,
                    "latest_position_snapshot": {
                        "payload": {
                            "market_context": {"candidates": []},
                            "positions": {
                                "BASEUSDT": {
                                    "symbol": "BASEUSDT",
                                    "weighted_avg_entry_price": "0.17",
                                    "total_quantity": "31119",
                                    "stop_price": "0.15",
                                    "risk": "482.94",
                                },
                                "ORDIUSDT": {
                                    "symbol": "ORDIUSDT",
                                    "weighted_avg_entry_price": "7.04",
                                    "total_quantity": "62.6",
                                    "stop_price": "6.10",
                                    "risk": "440.76",
                                },
                            },
                        }
                    },
                    "latest_account_snapshot": {
                        "equity": "1367.35",
                        "available_balance": "401.78",
                        "wallet_balance": "952.03",
                        "unrealized_pnl": "415.32",
                        "position_count": 2,
                        "open_order_count": 0,
                    },
                    "latest_signal_decision": {
                        "decision_type": "no_action",
                        "symbol": "BASEUSDT",
                        "timestamp": "2026-04-17T00:04:00+00:00",
                        "payload": {},
                    },
                },
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-16T00:00:00+00:00",
                        "equity": "1000",
                        "wallet_balance": "1000",
                        "adjusted_equity": "1000",
                        "unrealized_pnl": "0",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                    {
                        "timestamp": "2026-04-17T00:00:00+00:00",
                        "equity": "1367.35",
                        "wallet_balance": "952.03",
                        "adjusted_equity": "1367.35",
                        "unrealized_pnl": "415.32",
                        "position_count": 2,
                        "open_order_count": 0,
                    },
                ],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_trade_fills": [],
                "recent_signal_decisions": [],
                "leader_history": [
                    {"timestamp": "2026-04-17T00:01:00+00:00", "symbol": "BASEUSDT"},
                    {"timestamp": "2026-04-17T00:02:00+00:00", "symbol": "ORDIUSDT"},
                    {"timestamp": "2026-04-17T00:03:00+00:00", "symbol": "BASEUSDT"},
                ],
                "recent_events": [],
                "recent_broker_orders": [],
                "event_counts": {},
                "source_counts": {},
                "pulse_points": [],
                "warnings": [],
                "strategy_config": {"submit_orders": True},
            }
        )

        self.assertIn("Recent Sequence", html)
        self.assertIn("BASEUSDT → ORDIUSDT → BASEUSDT", html)
        self.assertIn("metric warning", html)
        self.assertIn("No blocked signals", html)

    def test_render_dashboard_html_refreshes_in_place_and_persists_account_controls(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "BASEUSDT",
                    "position_count": 1,
                    "order_status_count": 0,
                    "latest_position_snapshot": {"payload": {}},
                    "latest_account_snapshot": {
                        "equity": "1100.00",
                        "available_balance": "840.00",
                        "wallet_balance": "1060.00",
                        "unrealized_pnl": "40.00",
                        "position_count": 1,
                        "open_order_count": 1,
                    },
                    "latest_signal_decision": {},
                },
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-17T00:00:00+00:00",
                        "equity": "1000.00",
                        "wallet_balance": "1000.00",
                        "available_balance": "930.00",
                        "unrealized_pnl": "0.00",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                    {
                        "timestamp": "2026-04-17T01:00:00+00:00",
                        "equity": "1100.00",
                        "wallet_balance": "1060.00",
                        "available_balance": "840.00",
                        "unrealized_pnl": "40.00",
                        "position_count": 1,
                        "open_order_count": 1,
                    },
                ],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_trade_fills": [],
                "recent_signal_decisions": [],
                "leader_history": [],
                "recent_events": [],
                "recent_broker_orders": [],
                "event_counts": {},
                "source_counts": {},
                "pulse_points": [],
                "warnings": [],
            }
        )

        self.assertNotIn("window.location.reload()", html)
        self.assertIn("new DOMParser()", html)
        self.assertIn("localStorage.getItem('dashboard.account.metric')", html)
        self.assertIn("localStorage.getItem('dashboard.account.range')", html)
        self.assertIn("window.location.search", html)
        self.assertIn("document.getElementById('manual-refresh-button')", html)
        self.assertIn("replaceSectionFromDocument", html)
        self.assertIn("data-dashboard-tab-content=\"overview\"", html)

    def test_render_dashboard_html_prioritizes_live_overview_and_compacts_position_cards(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "BTCUSDT",
                    "position_count": 1,
                    "order_status_count": 1,
                    "latest_position_snapshot": {
                        "payload": {
                            "positions": {
                                "BTCUSDT": {
                                    "symbol": "BTCUSDT",
                                    "stop_price": "81000",
                                    "latest_price": "83500",
                                    "legs": [
                                        {
                                            "symbol": "BTCUSDT",
                                            "quantity": "0.01",
                                            "entry_price": "82000",
                                            "stop_price": "81000",
                                            "opened_at": "2026-04-15T09:15:00+00:00",
                                            "leg_type": "base",
                                        }
                                    ],
                                }
                            }
                        }
                    },
                    "latest_account_snapshot": {
                        "wallet_balance": "1000",
                        "available_balance": "750",
                        "equity": "1080",
                        "unrealized_pnl": "15",
                    },
                    "latest_signal_decision": {
                        "decision_type": "base_entry",
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-04-15T10:00:00+00:00",
                        "payload": {},
                    },
                },
                "recent_account_snapshots": [
                    {
                        "timestamp": "2026-04-15T00:00:00+00:00",
                        "wallet_balance": "1000",
                        "available_balance": "900",
                        "equity": "1000",
                        "unrealized_pnl": "0",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                    {
                        "timestamp": "2026-04-15T10:00:00+00:00",
                        "wallet_balance": "1000",
                        "available_balance": "750",
                        "equity": "1080",
                        "unrealized_pnl": "15",
                        "position_count": 1,
                        "open_order_count": 1,
                    },
                ],
                "recent_broker_orders": [],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_trade_fills": [],
                "recent_signal_decisions": [],
                "recent_events": [],
                "event_counts": {},
                "source_counts": {},
                "leader_history": [{"timestamp": "2026-04-15T10:00:00+00:00", "symbol": "BTCUSDT"}],
                "pulse_points": [],
                "warnings": [],
            },
            strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": True, "submit_orders": False},
        )

        self.assertIn("LIVE OVERVIEW", html)
        self.assertIn("RISK &amp; DEPLOYMENT", html)
        self.assertIn("ACTIVE SIGNAL", html)
        self.assertIn("POSITION SUMMARY", html)
        self.assertIn("SYSTEM HEALTH", html)
        self.assertIn("MANUAL REFRESH", html)
        self.assertIn("Last update", html)
        self.assertIn("ACTIVE POSITIONS", html)
        self.assertIn("Distance", html)
        self.assertIn("Notional", html)

    def test_render_dashboard_html_supports_collapsible_sections_and_refresh_failure_state(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "FAIL", "items": [{"name": "poll", "status": "FAIL", "message": "stale"}]},
                "runtime": {
                    "previous_leader_symbol": "ETHUSDT",
                    "position_count": 0,
                    "order_status_count": 0,
                    "latest_signal_decision": {},
                    "latest_account_snapshot": {
                        "wallet_balance": "1000",
                        "available_balance": "1000",
                        "equity": "1000",
                        "unrealized_pnl": "0",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                },
                "recent_account_snapshots": [],
                "recent_trade_round_trips": [],
                "recent_stop_exit_summaries": [],
                "recent_trade_fills": [],
                "recent_signal_decisions": [],
                "recent_events": [],
                "event_counts": {},
                "source_counts": {},
                "leader_history": [],
                "pulse_points": [],
                "warnings": [],
            }
        )

        self.assertIn("section-toggle", html)
        self.assertIn("data-section-toggle", html)
        self.assertIn("collapsed-sections", html)
        self.assertIn("refresh-indicator error", html)
        self.assertIn("setRefreshIndicatorState('error'", html)
        self.assertIn("Unable to refresh", html)

    def test_render_dashboard_html_mobile_layout_uses_record_cards_and_scroll_fallbacks(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html(
            {
                "health": {"overall_status": "OK", "items": []},
                "runtime": {
                    "previous_leader_symbol": "SOLUSDT",
                    "position_count": 0,
                    "order_status_count": 0,
                    "latest_signal_decision": {},
                    "latest_account_snapshot": {
                        "wallet_balance": "1000",
                        "available_balance": "920",
                        "equity": "1010",
                        "unrealized_pnl": "10",
                        "position_count": 0,
                        "open_order_count": 0,
                    },
                },
                "recent_account_snapshots": [],
                "recent_trade_round_trips": [
                    {"round_trip_id": "SOLUSDT:1", "symbol": "SOLUSDT", "opened_at": "2026-04-15T09:00:00+00:00", "closed_at": "2026-04-15T10:00:00+00:00", "net_pnl": "12.00", "exit_reason": "signal_flip"}
                ],
                "recent_stop_exit_summaries": [
                    {"symbol": "SOLUSDT", "trigger_price": "120.00", "average_exit_price": "119.50", "slippage_pct": "0.42", "net_pnl": "-3.50"}
                ],
                "recent_trade_fills": [
                    {"timestamp": "2026-04-15T09:30:00+00:00", "symbol": "SOLUSDT", "side": "BUY", "quantity": "1.25", "average_price": "120.55", "commission": "0.10", "order_status": "FILLED"}
                ],
                "recent_signal_decisions": [],
                "recent_events": [],
                "event_counts": {},
                "source_counts": {},
                "leader_history": [],
                "pulse_points": [],
                "warnings": [],
            }
        )

        self.assertIn("analytics-card-list", html)
        self.assertIn("trade-card-list", html)
        self.assertIn("table-scroll", html)
        self.assertIn(".analytics-table.desktop-only", html)
        self.assertIn(".analytics-card-list.mobile-only", html)
        self.assertIn(".trade-history.desktop-only", html)
        self.assertIn(".trade-card-list.mobile-only", html)

    def test_build_account_metrics_panel_surfaces_large_jump_note(self) -> None:
        from momentum_alpha.dashboard import _build_account_metrics_panel

        html = _build_account_metrics_panel(
            [
                {
                    "timestamp": "2026-04-16T00:00:00+00:00",
                    "equity": "100.00",
                    "wallet_balance": "100.00",
                    "adjusted_equity": "100.00",
                    "unrealized_pnl": "0.00",
                    "position_count": 0,
                    "open_order_count": 0,
                },
                {
                    "timestamp": "2026-04-16T01:00:00+00:00",
                    "equity": "1000.00",
                    "wallet_balance": "1000.00",
                    "adjusted_equity": "1000.00",
                    "unrealized_pnl": "0.00",
                    "position_count": 0,
                    "open_order_count": 0,
                },
            ]
        )

        self.assertIn("Large equity jump detected", html)
