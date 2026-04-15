import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class PackageImportTests(unittest.TestCase):
    def test_package_imports(self) -> None:
        import momentum_alpha

        self.assertTrue(momentum_alpha.__all__)
