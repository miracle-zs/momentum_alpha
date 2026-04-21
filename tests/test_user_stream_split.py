import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class UserStreamSplitTests(unittest.TestCase):
    def test_user_stream_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import user_stream_client, user_stream_events, user_stream_state

        self.assertTrue(callable(user_stream_events.parse_user_stream_event))
        self.assertTrue(callable(user_stream_state.apply_user_stream_event_to_state))
        self.assertTrue(callable(user_stream_client.BinanceUserStreamClient))


if __name__ == "__main__":
    unittest.main()
