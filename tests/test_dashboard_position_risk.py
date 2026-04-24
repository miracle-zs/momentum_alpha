from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DashboardPositionRiskTests(unittest.TestCase):
    def test_compute_position_risk_handles_long_and_short_books(self) -> None:
        from momentum_alpha.dashboard_position_risk import compute_position_risk

        long_position = {
            "side": "LONG",
            "legs": [
                {"quantity": "1", "entry_price": "100", "stop_price": "90"},
            ],
        }
        short_position = {
            "side": "SHORT",
            "legs": [
                {"quantity": "2", "entry_price": "100", "stop_price": "108"},
            ],
        }

        self.assertEqual(compute_position_risk(long_position), Decimal("10"))
        self.assertEqual(compute_position_risk(short_position), Decimal("16"))

    def test_compute_position_risk_clamps_negative_values_to_zero(self) -> None:
        from momentum_alpha.dashboard_position_risk import compute_position_risk

        long_position = {
            "side": "LONG",
            "legs": [
                {"quantity": "1", "entry_price": "100", "stop_price": "110"},
            ],
        }

        self.assertEqual(compute_position_risk(long_position), Decimal("0"))

    def test_compute_position_risk_ignores_zero_stop_legs(self) -> None:
        from momentum_alpha.dashboard_position_risk import compute_position_risk

        position = {
            "side": "LONG",
            "legs": [
                {"quantity": "1", "entry_price": "100", "stop_price": "0"},
            ],
        }

        self.assertIsNone(compute_position_risk(position))

    def test_build_position_risk_series_skips_incomplete_positions(self) -> None:
        from momentum_alpha.dashboard_position_risk import build_position_risk_series

        snapshots = [
            {
                "timestamp": "2026-04-15T08:48:00+00:00",
                "payload": {
                    "positions": {
                        "BTCUSDT": {
                            "side": "LONG",
                            "legs": [{"quantity": "1", "entry_price": "100", "stop_price": "90"}],
                        },
                        "BROKEN": {
                            "side": "LONG",
                            "legs": [{"quantity": "1", "entry_price": "100"}],
                        },
                    }
                },
            },
            {
                "timestamp": "2026-04-15T08:49:00+00:00",
                "payload": {"positions": {}},
            },
        ]

        series = build_position_risk_series(snapshots)

        self.assertEqual(series, [{"timestamp": "2026-04-15T08:48:00+00:00", "open_risk": 10.0}])

    def test_render_line_chart_svg_uses_a_non_flat_axis_for_single_open_risk_point(self) -> None:
        from momentum_alpha.dashboard_render_panels import _render_line_chart_svg

        svg = _render_line_chart_svg(
            points=[{"timestamp": "2026-04-15T08:48:00+00:00", "open_risk": 0.9}],
            value_key="open_risk",
            stroke="#ff5d73",
            fill="#ff5d73",
        )

        self.assertIn(">1.1<", svg)
        self.assertIn(">0.0<", svg)

    def test_render_line_chart_svg_uses_timestamp_spacing(self) -> None:
        from momentum_alpha.dashboard_render_panels import _render_line_chart_svg
        import re

        svg = _render_line_chart_svg(
            points=[
                {"timestamp": "2026-04-23T09:00:00+00:00", "equity": 100.0},
                {"timestamp": "2026-04-23T09:10:00+00:00", "equity": 110.0},
                {"timestamp": "2026-04-23T10:10:00+00:00", "equity": 120.0},
            ],
            value_key="equity",
            stroke="#4cc9f0",
            fill="#4cc9f0",
        )

        match = re.search(r"<polyline points='([^']+)'", svg)
        self.assertIsNotNone(match)
        x_values = [float(pair.split(",")[0]) for pair in match.group(1).split()]
        self.assertLess(x_values[1] - x_values[0], x_values[2] - x_values[1])

    def test_render_line_chart_svg_uses_integer_axis_for_position_count(self) -> None:
        from momentum_alpha.dashboard_render_panels import _render_line_chart_svg

        svg = _render_line_chart_svg(
            points=[
                {"timestamp": "2026-04-15T08:48:00+00:00", "position_count": 0},
                {"timestamp": "2026-04-15T08:49:00+00:00", "position_count": 1},
                {"timestamp": "2026-04-15T08:50:00+00:00", "position_count": 2},
            ],
            value_key="position_count",
            stroke="#36d98a",
            fill="#36d98a",
            integer_axis=True,
        )

        self.assertIn(">2<", svg)
        self.assertIn(">1<", svg)
        self.assertIn(">0<", svg)
        self.assertNotIn(">2.0<", svg)
        self.assertNotIn(">1.5<", svg)

    def test_build_live_core_lines_panel_renders_integer_position_count_axis(self) -> None:
        from momentum_alpha.dashboard_render_panels import _build_live_core_lines_panel

        html = _build_live_core_lines_panel(
            [
                {
                    "timestamp": "2026-04-15T08:48:00+00:00",
                    "equity": 100.0,
                    "margin_usage_pct": 0.0,
                    "position_count": 0,
                    "open_risk": 0.0,
                },
                {
                    "timestamp": "2026-04-15T08:49:00+00:00",
                    "equity": 101.0,
                    "margin_usage_pct": 0.2,
                    "position_count": 1,
                    "open_risk": 0.5,
                },
                {
                    "timestamp": "2026-04-15T08:50:00+00:00",
                    "equity": 102.0,
                    "margin_usage_pct": 0.4,
                    "position_count": 2,
                    "open_risk": 0.9,
                },
            ]
        )

        position_count_section = html.split("Position Count", 1)[1].split("Open Risk", 1)[0]
        self.assertIn(">2<", position_count_section)
        self.assertIn(">1<", position_count_section)
        self.assertIn(">0<", position_count_section)
        self.assertNotIn(">2.0<", position_count_section)
        self.assertNotIn(">1.5<", position_count_section)

    def test_build_dashboard_timeseries_payload_includes_position_risk(self) -> None:
        from momentum_alpha.dashboard import build_dashboard_timeseries_payload

        snapshot = {
            "recent_account_snapshots": [],
            "account_metric_flows": [],
            "leader_history": [],
            "pulse_points": [],
            "recent_position_snapshots": [
                {
                    "timestamp": "2026-04-15T08:48:00+00:00",
                    "payload": {
                        "positions": {
                            "BTCUSDT": {
                                "side": "LONG",
                                "legs": [{"quantity": "1", "entry_price": "100", "stop_price": "90"}],
                            }
                        }
                    },
                }
            ],
        }

        payload = build_dashboard_timeseries_payload(snapshot)

        self.assertEqual(payload["position_risk"], [{"timestamp": "2026-04-15T08:48:00+00:00", "open_risk": 10.0}])

    def test_build_dashboard_timeseries_payload_creates_shared_core_live_timeline(self) -> None:
        from momentum_alpha.dashboard import build_dashboard_timeseries_payload

        snapshot = {
            "recent_account_snapshots": [
                {
                    "timestamp": "2026-04-23T09:00:00+00:00",
                    "wallet_balance": "100.00",
                    "available_balance": "90.00",
                    "equity": "100.00",
                    "unrealized_pnl": "0.00",
                    "position_count": 1,
                    "open_order_count": 1,
                },
                {
                    "timestamp": "2026-04-23T09:05:00+00:00",
                    "wallet_balance": "102.00",
                    "available_balance": "92.00",
                    "equity": "102.00",
                    "unrealized_pnl": "2.00",
                    "position_count": 1,
                    "open_order_count": 1,
                },
            ],
            "recent_position_risk_snapshots": [
                {
                    "timestamp": "2026-04-23T09:02:00+00:00",
                    "payload": {
                        "positions": {
                            "BTCUSDT": {
                                "side": "LONG",
                                "legs": [
                                    {"quantity": "1", "entry_price": "100", "stop_price": "90"}
                                ],
                            }
                        }
                    },
                }
            ],
        }

        payload = build_dashboard_timeseries_payload(snapshot)

        self.assertEqual(
            [point["timestamp"] for point in payload["core_live_timeline"]],
            [
                "2026-04-23T09:00:00+00:00",
                "2026-04-23T09:02:00+00:00",
                "2026-04-23T09:05:00+00:00",
            ],
        )
        self.assertEqual(payload["core_live_timeline"][0]["open_risk"], None)
        self.assertEqual(payload["core_live_timeline"][1]["open_risk"], 10.0)
        self.assertEqual(payload["core_live_timeline"][2]["open_risk"], 10.0)
        self.assertEqual(payload["core_live_timeline"][1]["equity"], 100.0)
        self.assertEqual(payload["account"][0]["equity"], 100.0)
        self.assertEqual(payload["position_risk"][0]["open_risk"], 10.0)

    def test_load_dashboard_snapshot_includes_position_risk_when_poll_rows_do_not_have_positions(self) -> None:
        from momentum_alpha.dashboard import build_dashboard_timeseries_payload, load_dashboard_snapshot
        from momentum_alpha.runtime_store import bootstrap_runtime_db, insert_position_snapshot

        with TemporaryDirectory() as tmpdir:
            runtime_db_file = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=runtime_db_file)

            for minute in range(2, 10):
                insert_position_snapshot(
                    path=runtime_db_file,
                    timestamp=datetime(2026, 4, 21, 9, minute, tzinfo=timezone.utc),
                    source="poll",
                    leader_symbol="DENTUSDT",
                    position_count=0,
                    order_status_count=0,
                    symbol_count=537,
                    payload={
                        "event_type": "poll_tick",
                        "market_context": {"leader_symbol": "DENTUSDT"},
                    },
                )

            insert_position_snapshot(
                path=runtime_db_file,
                timestamp=datetime(2026, 4, 21, 8, 25, tzinfo=timezone.utc),
                source="user-stream",
                leader_symbol="RAVEUSDT",
                position_count=1,
                order_status_count=11,
                symbol_count=1,
                payload={
                    "event_type": "ACCOUNT_UPDATE",
                    "positions": {
                        "RAVEUSDT": {
                            "side": "LONG",
                            "legs": [
                                {"quantity": "1", "entry_price": "100", "stop_price": "90"},
                            ],
                        }
                    },
                },
            )

            snapshot = load_dashboard_snapshot(
                now=datetime(2026, 4, 21, 9, 15, tzinfo=timezone.utc),
                runtime_db_file=runtime_db_file,
            )
            payload = build_dashboard_timeseries_payload(snapshot)

        self.assertEqual(
            payload["position_risk"],
            [
                {"timestamp": "2026-04-21T08:25:00+00:00", "open_risk": 10.0},
                {"timestamp": "2026-04-21T09:09:00+00:00", "open_risk": 0.0},
            ],
        )

    def test_load_dashboard_snapshot_ranges_position_risk_history(self) -> None:
        from momentum_alpha.dashboard import build_dashboard_timeseries_payload, load_dashboard_snapshot
        from momentum_alpha.runtime_store import bootstrap_runtime_db, insert_position_snapshot

        with TemporaryDirectory() as tmpdir:
            runtime_db_file = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=runtime_db_file)

            for minute in range(10):
                insert_position_snapshot(
                    path=runtime_db_file,
                    timestamp=datetime(2026, 4, 21, 8, minute, tzinfo=timezone.utc),
                    source="user-stream",
                    leader_symbol="BTCUSDT",
                    position_count=1,
                    order_status_count=1,
                    symbol_count=1,
                    payload={
                        "event_type": "ACCOUNT_UPDATE",
                        "positions": {
                            "BTCUSDT": {
                                "side": "LONG",
                                "legs": [
                                    {"quantity": "1", "entry_price": "100", "stop_price": "90"},
                                ],
                            }
                        },
                    },
                )

            snapshot = load_dashboard_snapshot(
                now=datetime(2026, 4, 21, 9, 15, tzinfo=timezone.utc),
                runtime_db_file=runtime_db_file,
            )
            payload = build_dashboard_timeseries_payload(snapshot)

        self.assertEqual(
            [point["timestamp"] for point in payload["position_risk"]],
            [
                "2026-04-21T08:04:00+00:00",
                "2026-04-21T08:09:00+00:00",
            ],
        )
        self.assertTrue(all(point["open_risk"] > 0 for point in payload["position_risk"]))

    def test_build_position_details_uses_shared_risk_math(self) -> None:
        from momentum_alpha.dashboard_view_model import build_position_details

        position_snapshot = {
            "payload": {
                "positions": {
                    "ETHUSDT": {
                        "side": "SHORT",
                        "stop_price": "108",
                        "latest_price": "96",
                        "legs": [
                            {
                                "quantity": "2",
                                "entry_price": "100",
                                "stop_price": "108",
                                "opened_at": "2026-04-15T08:00:00+00:00",
                            }
                        ],
                    }
                }
            }
        }

        details = build_position_details(position_snapshot, equity_value="1000")

        self.assertEqual(details[0]["risk"], "16.00")
