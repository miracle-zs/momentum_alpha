import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeReadsSplitTests(unittest.TestCase):
    def test_runtime_reads_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import runtime_reads_common, runtime_reads_events, runtime_reads_history

        self.assertTrue(callable(runtime_reads_events.fetch_recent_audit_events))
        self.assertTrue(callable(runtime_reads_events.fetch_recent_signal_decisions))
        self.assertTrue(callable(runtime_reads_history.fetch_recent_trade_round_trips))
        self.assertTrue(callable(runtime_reads_history.fetch_account_snapshots_for_range))
        self.assertTrue(callable(runtime_reads_common._json_loads))


if __name__ == "__main__":
    unittest.main()
