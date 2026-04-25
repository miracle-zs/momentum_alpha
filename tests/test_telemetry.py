from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class TelemetryTests(unittest.TestCase):
    def test_emit_structured_log_formats_key_value_pairs(self) -> None:
        from momentum_alpha.structured_log import emit_structured_log

        messages: list[str] = []

        emit_structured_log(
            messages.append,
            service="poll",
            event="tick",
            level="INFO",
            symbol="BTCUSDT",
            stale=False,
            count=2,
            payload={"b": 2, "a": 1},
        )

        self.assertEqual(
            messages[0],
            'service=poll level=INFO event=tick symbol=BTCUSDT stale=false count=2 payload={"a":1,"b":2}',
        )

    def test_build_market_context_payloads_sorts_leader_candidates(self) -> None:
        from momentum_alpha.telemetry import build_market_context_payloads

        payloads, leader_gap_pct = build_market_context_payloads(
            snapshots=[
                {
                    "symbol": "ETHUSDT",
                    "daily_open_price": Decimal("100"),
                    "latest_price": Decimal("104"),
                    "previous_hour_low": Decimal("99"),
                    "current_hour_low": Decimal("98"),
                },
                {
                    "symbol": "BTCUSDT",
                    "daily_open_price": Decimal("100"),
                    "latest_price": Decimal("105"),
                    "previous_hour_low": Decimal("97"),
                    "current_hour_low": Decimal("96"),
                },
            ]
        )

        self.assertEqual(payloads["BTCUSDT"]["daily_change_pct"], "0.05")
        self.assertEqual(payloads["BTCUSDT"]["leader_gap_pct"], "0.01")
        self.assertEqual(leader_gap_pct, Decimal("0.01"))

    def test_record_signal_decision_persists_structured_row(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.runtime_store import fetch_recent_signal_decisions
        from momentum_alpha.telemetry import record_signal_decision

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            recorder = AuditRecorder(runtime_db_path=db_path, source="test")

            record_signal_decision(
                audit_recorder=recorder,
                now=datetime(2026, 4, 21, 1, 0, tzinfo=timezone.utc),
                decision_type="base_entry",
                symbol="BTCUSDT",
                previous_leader_symbol="ETHUSDT",
                next_leader_symbol="BTCUSDT",
                position_count=1,
                order_status_count=2,
                broker_response_count=0,
                stop_replacement_count=0,
                payload={"stop_price": "100"},
            )

            rows = fetch_recent_signal_decisions(path=db_path, limit=1)

        self.assertEqual(rows[0]["decision_type"], "base_entry")
        self.assertEqual(rows[0]["symbol"], "BTCUSDT")
        self.assertEqual(rows[0]["payload"]["stop_price"], "100")

    def test_record_signal_decision_surfaces_db_write_failures(self) -> None:
        from unittest.mock import patch

        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.runtime_store import fetch_recent_audit_events
        from momentum_alpha.telemetry import record_signal_decision

        messages: list[str] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            recorder = AuditRecorder(runtime_db_path=db_path, source="poll", error_logger=messages.append)

            with patch("momentum_alpha.telemetry.insert_signal_decision", side_effect=RuntimeError("db down")):
                record_signal_decision(
                    audit_recorder=recorder,
                    now=datetime(2026, 4, 21, 1, 0, tzinfo=timezone.utc),
                    decision_id="dec_260421010000000000",
                    intent_id="ma_260421010000_BTCUSDT_b00",
                    decision_type="base_entry",
                    symbol="BTCUSDT",
                    previous_leader_symbol="ETHUSDT",
                    next_leader_symbol="BTCUSDT",
                    position_count=1,
                    order_status_count=2,
                    broker_response_count=0,
                    stop_replacement_count=0,
                    payload={"stop_price": "100"},
                )

            events = fetch_recent_audit_events(path=db_path, limit=10)

        self.assertEqual(events[0]["event_type"], "signal_decision_insert_error")
        self.assertEqual(events[0]["payload"]["error"], "db down")
        self.assertTrue(any("event=signal-decision-insert-error" in message for message in messages))
