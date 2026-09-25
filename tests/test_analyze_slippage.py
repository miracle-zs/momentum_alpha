from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from momentum_alpha.runtime_schema import bootstrap_runtime_db, _connect
import analyze_slippage


class AnalyzeSlippageTests(unittest.TestCase):
    def test_compute_distribution_empty(self) -> None:
        dist = analyze_slippage.compute_distribution([], [])
        self.assertEqual(dist.count, 0)
        self.assertEqual(dist.mean_bps, 0.0)
        self.assertEqual(dist.total_slippage_usd, 0.0)

    def test_compute_distribution_values(self) -> None:
        bps = [10.0, 20.0, 30.0, -5.0, 0.0]
        usd = [1.0, 2.0, 3.0, -0.5, 0.0]
        dist = analyze_slippage.compute_distribution(bps, usd)
        self.assertEqual(dist.count, 5)
        self.assertEqual(dist.mean_bps, 11.0)
        self.assertEqual(dist.median_bps, 10.0)
        self.assertEqual(dist.max_adverse_bps, 30.0)
        self.assertEqual(dist.max_favorable_bps, -5.0)
        self.assertEqual(dist.adverse_count, 3)
        self.assertEqual(dist.favorable_count, 1)
        self.assertEqual(dist.zero_count, 1)
        self.assertEqual(dist.total_slippage_usd, 5.5)

    def test_load_entry_and_exit_slippage_from_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)

            with _connect(db_path) as conn:
                # 1. Insert signal decision
                conn.execute(
                    """
                    INSERT INTO signal_decisions(
                        timestamp, source, decision_id, intent_id, decision_type, symbol, payload_json
                    ) VALUES (
                        '2026-04-15T10:00:00+00:00', 'poll', 'dec-1', 'intent-btc-1', 'base_entry', 'BTCUSDT',
                        ?
                    )
                    """,
                    (json.dumps({"latest_price": "100.0", "leg_type": "base"}),),
                )

                # 2. Insert trade fill for entry (bought at 100.20 -> 20 bps slippage)
                conn.execute(
                    """
                    INSERT INTO trade_fills(
                        timestamp, source, symbol, order_id, trade_id, client_order_id, intent_id,
                        order_status, execution_type, side, order_type, quantity, average_price, payload_json
                    ) VALUES (
                        '2026-04-15T10:00:01+00:00', 'user-stream', 'BTCUSDT', 'ord-1', 'trd-1', 'intent-btc-1e', 'intent-btc-1',
                        'FILLED', 'TRADE', 'BUY', 'MARKET', '2.0', '100.20', '{}'
                    )
                    """
                )

                # 3. Insert stop exit summary (trigger 95.0, average exit 94.5 -> 50 bps adverse slippage)
                conn.execute(
                    """
                    INSERT INTO stop_exit_summaries(
                        timestamp, symbol, round_trip_id, trigger_price, average_exit_price,
                        slippage_abs, slippage_pct, exit_quantity, realized_pnl, commission, net_pnl, payload_json
                    ) VALUES (
                        '2026-04-15T10:30:00+00:00', 'BTCUSDT', 'rt-1', '95.0', '94.5',
                        '0.5', '0.5263', '2.0', '-11.4', '0.2', '-11.6', '{}'
                    )
                    """
                )

            # Analyze
            entries = analyze_slippage.load_entry_slippage(db_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].symbol, "BTCUSDT")
            self.assertEqual(entries[0].leg_type, "base")
            self.assertEqual(entries[0].decision_price, 100.0)
            self.assertEqual(entries[0].fill_price, 100.2)
            self.assertAlmostEqual(entries[0].slippage_bps, 20.0, places=1)
            self.assertAlmostEqual(entries[0].slippage_usd, 0.4, places=2)

            exits = analyze_slippage.load_exit_slippage(db_path)
            self.assertEqual(len(exits), 1)
            self.assertEqual(exits[0].symbol, "BTCUSDT")
            self.assertEqual(exits[0].trigger_price, 95.0)
            self.assertEqual(exits[0].average_exit_price, 94.5)
            self.assertAlmostEqual(exits[0].slippage_bps, 52.63, places=1)
            self.assertAlmostEqual(exits[0].slippage_usd, 1.0, places=2)

            # Build report
            report = analyze_slippage.build_analysis_report(entries, exits)
            self.assertEqual(report["entry_summary"]["count"], 1)
            self.assertEqual(report["exit_summary"]["count"], 1)
            self.assertEqual(report["base_leg_summary"]["count"], 1)
            self.assertEqual(report["add_on_leg_summary"]["count"], 0)

            # Test export CSV and JSON
            output_dir = Path(tmpdir) / "output"
            analyze_slippage.export_csv(output_dir, entries, exits, report)
            self.assertTrue((output_dir / "entry_slippage.csv").exists())
            self.assertTrue((output_dir / "exit_slippage.csv").exists())
            self.assertTrue((output_dir / "slippage_summary.json").exists())


if __name__ == "__main__":
    unittest.main()
