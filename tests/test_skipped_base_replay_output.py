from __future__ import annotations

import csv
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class SkippedBaseReplayOutputTests(unittest.TestCase):
    @staticmethod
    def _result(*, shadow_id: str, net_pnl: Decimal | None, status: str):
        from momentum_alpha.skipped_base_replay import (
            ShadowLegResult,
            ShadowReplayEvent,
            ShadowReplayResult,
        )

        signal_at = datetime(2026, 6, 12, 1, 5, tzinfo=timezone.utc)
        is_closed = status == "closed"
        leg = ShadowLegResult(
            shadow_opportunity_id=shadow_id,
            leg_type="base",
            sequence=0,
            opened_at=signal_at,
            entry_price=Decimal("110"),
            stop_at_entry=Decimal("100"),
            quantity=Decimal("1"),
            risk_budget=Decimal("10"),
            entry_fee=Decimal("0.055"),
            closed_at=signal_at + timedelta(hours=1) if is_closed else None,
            exit_price=Decimal("120") if is_closed else None,
            gross_pnl=Decimal("10") if is_closed else None,
            net_contribution=net_pnl,
        )
        event_type = "stop_exit" if is_closed else "open_at_cutoff"
        return ShadowReplayResult(
            shadow_opportunity_id=shadow_id,
            symbol="AAAUSDT",
            base_signal_at=signal_at,
            base_signal_sequence=2,
            first_base_signal_at=signal_at - timedelta(hours=1),
            status=status,
            base_entry_price=Decimal("110"),
            initial_stop_price=Decimal("100"),
            base_quantity=Decimal("1"),
            add_on_count=2 if shadow_id == "winner" else 0,
            skipped_add_on_count=1,
            exit_at=signal_at + timedelta(hours=1) if is_closed else None,
            exit_price=Decimal("120") if is_closed else None,
            duration_minutes=Decimal("60"),
            gross_pnl=Decimal("10") if is_closed else None,
            entry_fees=Decimal("0.055"),
            exit_fees=Decimal("0.06") if is_closed else None,
            net_pnl=net_pnl,
            mark_price_at_cutoff=Decimal("115") if not is_closed else None,
            mark_to_market_net_pnl=Decimal("4.8") if not is_closed else None,
            legs=(leg,),
            events=(
                ShadowReplayEvent(
                    shadow_opportunity_id=shadow_id,
                    symbol="AAAUSDT",
                    timestamp=signal_at + timedelta(hours=1),
                    event_type=event_type,
                    price=Decimal("120") if is_closed else Decimal("115"),
                ),
            ),
            warnings=("sample_warning",) if not is_closed else (),
        )

    def test_writes_stable_csvs_and_markdown_summary(self) -> None:
        from momentum_alpha.skipped_base_replay import ShadowOverlap, ShadowReplayReport
        from momentum_alpha.skipped_base_replay_output import write_replay_artifacts

        winner = self._result(shadow_id="winner", net_pnl=Decimal("9.885"), status="closed")
        loser = replace(
            self._result(shadow_id="loser", net_pnl=Decimal("-10.105"), status="closed"),
            gross_pnl=Decimal("-10"),
        )
        open_result = self._result(shadow_id="open", net_pnl=None, status="open")
        report = ShadowReplayReport(
            seed_count=4,
            opportunities=(winner, loser, open_result),
            overlaps=(
                ShadowOverlap(
                    shadow_opportunity_id="overlap",
                    symbol="AAAUSDT",
                    signal_at=winner.base_signal_at + timedelta(minutes=1),
                    active_shadow_opportunity_id="winner",
                ),
            ),
            warnings=("report_warning",),
        )

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            paths = write_replay_artifacts(report=report, output_dir=output_dir)
            with paths["summary_csv"].open(newline="", encoding="utf-8") as handle:
                summary_rows = list(csv.DictReader(handle))
            with paths["events_csv"].open(newline="", encoding="utf-8") as handle:
                event_rows = list(csv.DictReader(handle))
            markdown = paths["summary_md"].read_text(encoding="utf-8")

        self.assertEqual(summary_rows[0]["status"], "closed")
        self.assertEqual(summary_rows[0]["add_on_count"], "2")
        self.assertIn("open_at_cutoff", [row["event_type"] for row in event_rows])
        self.assertIn("overlap_existing_shadow", [row["event_type"] for row in event_rows])
        self.assertIn("Seed count: 4", markdown)
        self.assertIn("Realized net PnL: -0.220", markdown)
        self.assertIn("Open mark-to-market net PnL: 4.8", markdown)
        self.assertIn("Win rate: 50.00%", markdown)
        self.assertIn("PnL by base signal sequence", markdown)
        self.assertIn("PnL by ISO week", markdown)
        self.assertIn("report_warning", markdown)

    def test_empty_report_still_writes_headers(self) -> None:
        from momentum_alpha.skipped_base_replay import ShadowReplayReport
        from momentum_alpha.skipped_base_replay_output import write_replay_artifacts

        with TemporaryDirectory() as tmpdir:
            paths = write_replay_artifacts(
                report=ShadowReplayReport(
                    seed_count=0,
                    opportunities=(),
                    overlaps=(),
                    warnings=(),
                ),
                output_dir=Path(tmpdir),
            )
            lines = paths["summary_csv"].read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 1)
        self.assertIn("shadow_opportunity_id", lines[0])


if __name__ == "__main__":
    unittest.main()
