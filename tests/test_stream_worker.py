from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class StreamWorkerTests(unittest.TestCase):
    def test_stream_worker_exports_run_user_stream(self) -> None:
        from momentum_alpha.stream_worker import run_user_stream

        self.assertTrue(callable(run_user_stream))
