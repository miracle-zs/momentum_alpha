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
