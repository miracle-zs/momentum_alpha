from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class StreamDirtySyncTests(unittest.TestCase):
    def _context(self, now):
        from momentum_alpha.models import StrategyState
        from momentum_alpha.stream_worker_core import UserStreamWorkerContext

        return UserStreamWorkerContext(
            state=StrategyState(current_day=now.date(), previous_leader_symbol=None),
            processed_event_ids={},
            order_statuses={},
        )

    def test_order_and_position_events_mark_dirty_symbols(self) -> None:
        from momentum_alpha.stream_worker_core import build_user_stream_event_handler
        from momentum_alpha.user_stream import UserStreamEvent

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        dirty = []
        handler = build_user_stream_event_handler(
            logger=lambda _message: None,
            runtime_state_store=None,
            audit_recorder=None,
            now_provider=lambda: now,
            context=self._context(now),
            mark_dirty_symbol_fn=lambda symbol, reason, observed_at: dirty.append(
                (symbol, reason, observed_at)
            ),
        )

        handler(
            UserStreamEvent(
                event_type="ORDER_TRADE_UPDATE",
                payload={},
                symbol="BTCUSDT",
                event_time=now,
            )
        )
        handler(
            UserStreamEvent(
                event_type="ACCOUNT_UPDATE",
                payload={"a": {"P": [{"s": "ETHUSDT"}, {"s": "SOLUSDT"}]}},
                event_time=now,
            )
        )

        self.assertEqual(
            {(symbol, reason) for symbol, reason, _ in dirty},
            {
                ("BTCUSDT", "order_trade_update"),
                ("ETHUSDT", "account_update"),
                ("SOLUSDT", "account_update"),
            },
        )

    def test_account_config_event_requests_position_mode_refresh(self) -> None:
        from momentum_alpha.stream_worker_core import build_user_stream_event_handler
        from momentum_alpha.user_stream import UserStreamEvent

        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        controls = []
        handler = build_user_stream_event_handler(
            logger=lambda _message: None,
            runtime_state_store=None,
            audit_recorder=None,
            now_provider=lambda: now,
            context=self._context(now),
            request_runtime_control_fn=lambda key, requested_at, reason: controls.append(
                (key, requested_at, reason)
            ),
        )

        handler(
            UserStreamEvent(
                event_type="ACCOUNT_CONFIG_UPDATE",
                payload={"ac": {"s": "BTCUSDT"}},
                event_time=now,
            )
        )

        self.assertEqual(
            controls,
            [("position_mode_refresh", now, "user_stream_account_config_update")],
        )


if __name__ == "__main__":
    unittest.main()
