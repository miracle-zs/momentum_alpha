from __future__ import annotations

import logging
import sys
import unittest
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class LoggingConfigTests(unittest.TestCase):
    def test_configure_logging_routes_messages_to_stream(self) -> None:
        from momentum_alpha.logging_config import configure_logging

        stream = StringIO()
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        try:
            configure_logging(level="INFO", stream=stream)
            logging.getLogger("momentum_alpha.test").info("hello")
            self.assertIn("hello", stream.getvalue())
            self.assertEqual(logging.getLogger().level, logging.INFO)
        finally:
            root.handlers = old_handlers
            root.setLevel(old_level)

