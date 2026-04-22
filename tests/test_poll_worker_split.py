import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class PollWorkerSplitTests(unittest.TestCase):
    def test_poll_worker_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import poll_worker_core, poll_worker_core_execution, poll_worker_core_live, poll_worker_core_state, poll_worker_loop

        self.assertTrue(callable(poll_worker_core.run_once))
        self.assertTrue(callable(poll_worker_core.run_once_live))
        self.assertTrue(callable(poll_worker_loop.run_forever))
        self.assertTrue(hasattr(poll_worker_core, "RunOnceResult"))
        self.assertTrue(callable(poll_worker_core_state._save_strategy_state))
        self.assertTrue(callable(poll_worker_core_execution.build_runtime_from_snapshots))
        self.assertTrue(callable(poll_worker_core_execution.run_once))
        self.assertTrue(callable(poll_worker_core_live.run_once_live))


if __name__ == "__main__":
    unittest.main()
