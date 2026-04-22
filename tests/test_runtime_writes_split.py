import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeWritesSplitTests(unittest.TestCase):
    def test_runtime_writes_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import runtime_writes
        from momentum_alpha import (
            runtime_writes_common,
            runtime_writes_events_audit,
            runtime_writes_events_decisions,
            runtime_writes_events_flows,
            runtime_writes_events_orders,
            runtime_writes_events,
            runtime_writes_history,
            runtime_writes_notifications,
            runtime_writes_snapshots,
        )

        self.assertTrue(callable(runtime_writes.save_notification_status))
        self.assertTrue(callable(runtime_writes.insert_audit_event))
        self.assertTrue(callable(runtime_writes.insert_trade_round_trip))
        self.assertTrue(callable(runtime_writes.insert_position_snapshot))
        self.assertTrue(callable(runtime_writes_common._json_dumps))
        self.assertTrue(callable(runtime_writes_common._as_utc_iso))
        self.assertTrue(callable(runtime_writes_notifications.save_notification_status))
        self.assertTrue(callable(runtime_writes_events_audit.insert_audit_event))
        self.assertTrue(callable(runtime_writes_events_decisions.insert_signal_decision))
        self.assertTrue(callable(runtime_writes_events.insert_broker_order))
        self.assertTrue(callable(runtime_writes_events.insert_trade_fill))
        self.assertTrue(callable(runtime_writes_events_orders.insert_algo_order))
        self.assertTrue(callable(runtime_writes_events_flows.insert_account_flow))
        self.assertTrue(callable(runtime_writes_history.insert_daily_review_report))
        self.assertTrue(callable(runtime_writes_history.insert_stop_exit_summary))
        self.assertTrue(callable(runtime_writes_snapshots.insert_account_snapshot))


if __name__ == "__main__":
    unittest.main()
