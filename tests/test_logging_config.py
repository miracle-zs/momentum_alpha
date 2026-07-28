from __future__ import annotations

import json
import logging
import re
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

    def test_json_logging_includes_utc_timestamp(self) -> None:
        from momentum_alpha.logging_config import configure_logging

        stream = StringIO()
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        try:
            configure_logging(level="INFO", log_format="json", stream=stream)
            logging.getLogger("momentum_alpha.test").info("hello")
            payload = json.loads(stream.getvalue())

            self.assertEqual(payload["message"], "hello")
            self.assertRegex(payload["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
        finally:
            root.handlers = old_handlers
            root.setLevel(old_level)

    def test_kv_logging_prefixes_utc_timestamp(self) -> None:
        from momentum_alpha.logging_config import configure_logging

        stream = StringIO()
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        try:
            configure_logging(level="INFO", log_format="kv", stream=stream)
            logging.getLogger("momentum_alpha.test").info("hello")

            self.assertIsNotNone(
                re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z hello\n$", stream.getvalue())
            )
        finally:
            root.handlers = old_handlers
            root.setLevel(old_level)
