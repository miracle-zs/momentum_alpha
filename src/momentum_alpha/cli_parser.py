from __future__ import annotations

import argparse
from decimal import Decimal


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="momentum_alpha")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_once_live_parser = subparsers.add_parser("run-once-live")
    run_once_live_parser.add_argument("--symbols", nargs="+")
    run_once_live_parser.add_argument("--previous-leader")
    run_once_live_parser.add_argument("--runtime-db-file")
    run_once_live_parser.add_argument("--testnet", action="store_true")
    run_once_live_parser.add_argument("--submit-orders", action="store_true")

    poll_parser = subparsers.add_parser("poll")
    poll_parser.add_argument("--symbols", nargs="+")
    poll_parser.add_argument("--previous-leader")
    poll_parser.add_argument("--runtime-db-file")
    poll_parser.add_argument("--testnet", action="store_true")
    poll_parser.add_argument("--submit-orders", action="store_true")
    poll_parser.add_argument("--restore-positions", action="store_true")
    poll_parser.add_argument("--execute-stop-replacements", action="store_true")
    poll_parser.add_argument("--max-ticks", type=int)

    user_stream_parser = subparsers.add_parser("user-stream")
    user_stream_parser.add_argument("--testnet", action="store_true")
    user_stream_parser.add_argument("--runtime-db-file")

    healthcheck_parser = subparsers.add_parser("healthcheck")
    healthcheck_parser.add_argument("--poll-log-file")
    healthcheck_parser.add_argument("--user-stream-log-file")
    healthcheck_parser.add_argument("--runtime-db-file", required=True)
    healthcheck_parser.add_argument("--max-state-age-seconds", type=int, default=3600)
    healthcheck_parser.add_argument("--max-poll-event-age-seconds", type=int, default=180)
    healthcheck_parser.add_argument("--max-user-stream-event-age-seconds", type=int, default=1800)
    healthcheck_parser.add_argument("--max-runtime-db-age-seconds", type=int, default=1800)

    audit_report_parser = subparsers.add_parser("audit-report")
    audit_report_parser.add_argument("--runtime-db-file", required=True)
    audit_report_parser.add_argument("--since-minutes", type=int, default=1440)
    audit_report_parser.add_argument("--limit", type=int, default=20)

    daily_review_parser = subparsers.add_parser("daily-review-report")
    daily_review_parser.add_argument("--runtime-db-file", required=True)
    daily_review_parser.add_argument("--stop-budget-usdt", default="10")
    daily_review_parser.add_argument("--entry-start-hour-utc", type=int, default=1)
    daily_review_parser.add_argument("--entry-end-hour-utc", type=int, default=23)
    daily_review_parser.add_argument(
        "--replay-filtered-bases",
        action="store_true",
        help="Replay Base candidates blocked by the live Base veto and store counterfactual outcomes.",
    )

    backfill_account_flows_parser = subparsers.add_parser("backfill-account-flows")
    backfill_account_flows_parser.add_argument("--runtime-db-file", required=True)
    backfill_account_flows_parser.add_argument("--start-time", required=True)
    backfill_account_flows_parser.add_argument("--end-time", required=True)
    backfill_account_flows_parser.add_argument("--income-types", nargs="+", default=["TRANSFER"])
    backfill_account_flows_parser.add_argument("--testnet", action="store_true")

    backfill_binance_trades_parser = subparsers.add_parser("backfill-binance-trades")
    backfill_binance_trades_parser.add_argument("--runtime-db-file", required=True)
    backfill_binance_trades_parser.add_argument("--start-time", required=True)
    backfill_binance_trades_parser.add_argument("--end-time", required=True)
    backfill_binance_trades_parser.add_argument("--symbols", nargs="+")
    backfill_binance_trades_parser.add_argument("--testnet", action="store_true")
    backfill_binance_trades_parser.add_argument("--skip-rebuild", action="store_true")

    sync_trade_data_parser = subparsers.add_parser("sync-trade-data")
    sync_trade_data_parser.add_argument("--runtime-db-file", required=True)
    sync_trade_data_parser.add_argument("--testnet", action="store_true")
    sync_trade_data_parser.add_argument("--max-request-weight", type=int, default=100)
    sync_trade_data_parser.add_argument("--overlap-minutes", type=int, default=20)
    sync_trade_data_parser.add_argument("--full-repair", action="store_true")
    sync_trade_data_parser.add_argument("--symbols", nargs="+")

    request_live_resync_parser = subparsers.add_parser("request-live-resync")
    request_live_resync_parser.add_argument("--runtime-db-file", required=True)
    request_live_resync_parser.add_argument("--position-mode", action="store_true")
    request_live_resync_parser.add_argument("--orders", action="store_true")

    backfill_leader_candidates_parser = subparsers.add_parser("backfill-leader-candidates")
    backfill_leader_candidates_parser.add_argument("--runtime-db-file")
    backfill_leader_candidates_parser.add_argument(
        "--leader-candidates-db-file",
        default="./local_analytics/leader_candidates.db",
    )
    backfill_leader_candidates_parser.add_argument("--start-time")
    backfill_leader_candidates_parser.add_argument("--end-time")
    backfill_leader_candidates_parser.add_argument("--symbols", nargs="+")
    backfill_leader_candidates_parser.add_argument("--interval", default="5m")
    backfill_leader_candidates_parser.add_argument("--top-n", type=int, default=50)
    backfill_leader_candidates_parser.add_argument("--testnet", action="store_true")
    backfill_leader_candidates_parser.add_argument("--replay-position-snapshots", action="store_true")

    diagnose_opportunities_parser = subparsers.add_parser("diagnose-opportunities")
    diagnose_opportunities_parser.add_argument("--runtime-db-file", required=True)
    diagnose_opportunities_parser.add_argument(
        "--leader-candidates-db-file",
        default="./local_analytics/leader_candidates.db",
    )
    diagnose_opportunities_parser.add_argument(
        "--output-file",
        default="./local_analytics/opportunity_diagnostics.csv",
    )
    diagnose_opportunities_parser.add_argument("--start-time")
    diagnose_opportunities_parser.add_argument("--end-time")
    diagnose_opportunities_parser.add_argument("--symbols", nargs="+")
    diagnose_opportunities_parser.add_argument(
        "--min-peak-change-pct",
        type=Decimal,
        default=Decimal("0"),
    )

    replay_skipped_base_parser = subparsers.add_parser("replay-skipped-base")
    replay_skipped_base_parser.add_argument("--runtime-db-file", required=True)
    replay_skipped_base_parser.add_argument(
        "--output-dir",
        default="./local_analytics/skipped_base_replay",
    )
    replay_skipped_base_parser.add_argument("--start-time")
    replay_skipped_base_parser.add_argument("--end-time")
    replay_skipped_base_parser.add_argument("--symbols", nargs="+")
    replay_skipped_base_parser.add_argument(
        "--proxy",
        default="http://127.0.0.1:7897",
    )
    replay_skipped_base_parser.add_argument(
        "--taker-fee-rate",
        type=Decimal,
        default=Decimal("0.0005"),
    )
    replay_skipped_base_parser.add_argument("--refresh-klines", action="store_true")

    rebuild_trade_analytics_parser = subparsers.add_parser("rebuild-trade-analytics")
    rebuild_trade_analytics_parser.add_argument("--runtime-db-file", required=True)

    prune_runtime_db_parser = subparsers.add_parser("prune-runtime-db")
    prune_runtime_db_parser.add_argument("--runtime-db-file", required=True)
    prune_runtime_db_parser.add_argument("--audit-retention-days", type=int, default=30)
    prune_runtime_db_parser.add_argument("--snapshot-retention-days", type=int, default=7)

    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_parser.add_argument("--host", default="127.0.0.1")
    dashboard_parser.add_argument("--port", type=int, default=8080)
    dashboard_parser.add_argument("--poll-log-file")
    dashboard_parser.add_argument("--user-stream-log-file")
    dashboard_parser.add_argument("--runtime-db-file", required=True)

    return parser
