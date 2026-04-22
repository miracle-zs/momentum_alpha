import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeStoreSplitTests(unittest.TestCase):
    def test_runtime_state_store_split_module_exports_key_entrypoints(self) -> None:
        from momentum_alpha import runtime_state_store, runtime_store

        self.assertTrue(hasattr(runtime_state_store, "RuntimeStateStore"))
        self.assertTrue(hasattr(runtime_state_store, "_json_dumps"))
        self.assertTrue(hasattr(runtime_store, "RuntimeStateStore"))
        self.assertTrue(hasattr(runtime_store, "MAX_PROCESSED_EVENT_ID_AGE_HOURS"))
        self.assertIs(runtime_store.RuntimeStateStore, runtime_state_store.RuntimeStateStore)
