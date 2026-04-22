from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path


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

        self.assertEqual(series, [{"timestamp": "2026-04-15T08:48:00+00:00", "peak_risk": 10.0}])

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

        self.assertEqual(payload["position_risk"], [{"timestamp": "2026-04-15T08:48:00+00:00", "peak_risk": 10.0}])

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
