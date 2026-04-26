from __future__ import annotations

from momentum_alpha.daily_review import build_daily_review_report
from momentum_alpha.health import build_runtime_health_report
from momentum_alpha.runtime_store import insert_daily_review_report, summarize_audit_events

from .cli_commands_live import run_live_commands
from .cli_commands_ops import run_ops_commands
from .cli_commands_reports import run_reporting_commands


def run_cli_command(
    *,
    parser,
    args,
    client_factory,
    broker_factory,
    now_provider,
    run_forever_fn,
    run_user_stream_fn,
    run_dashboard_fn,
    backfill_account_flows_fn,
    backfill_binance_user_trades_fn,
    rebuild_trade_analytics_fn,
    prune_runtime_db_fn,
) -> int:
    dispatch_kwargs = {
        "parser": parser,
        "args": args,
        "client_factory": client_factory,
        "broker_factory": broker_factory,
        "now_provider": now_provider,
        "run_forever_fn": run_forever_fn,
        "run_user_stream_fn": run_user_stream_fn,
        "run_dashboard_fn": run_dashboard_fn,
        "backfill_account_flows_fn": backfill_account_flows_fn,
        "backfill_binance_user_trades_fn": backfill_binance_user_trades_fn,
        "rebuild_trade_analytics_fn": rebuild_trade_analytics_fn,
        "prune_runtime_db_fn": prune_runtime_db_fn,
        "build_runtime_health_report_fn": build_runtime_health_report,
        "summarize_audit_events_fn": summarize_audit_events,
        "build_daily_review_report_fn": build_daily_review_report,
        "insert_daily_review_report_fn": insert_daily_review_report,
    }

    for handler in (run_live_commands, run_reporting_commands, run_ops_commands):
        result = handler(**dispatch_kwargs)
        if result is not None:
            return result
    return 1


__all__ = [
    "run_cli_command",
    "run_live_commands",
    "run_reporting_commands",
    "run_ops_commands",
    "build_runtime_health_report",
    "summarize_audit_events",
    "build_daily_review_report",
    "insert_daily_review_report",
]
