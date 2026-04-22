from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from momentum_alpha.daily_review import build_daily_review_report
from momentum_alpha.health import build_runtime_health_report
from momentum_alpha.runtime_store import insert_daily_review_report, summarize_audit_events

from .cli_env import _parse_cli_datetime, _require_runtime_db_path


def healthcheck_command(
    *,
    parser,
    args,
    now_provider,
    build_runtime_health_report_fn=build_runtime_health_report,
) -> int:
    report = build_runtime_health_report_fn(
        now=now_provider(),
        runtime_db_file=Path(os.path.abspath(args.runtime_db_file)),
        max_state_age_seconds=args.max_state_age_seconds,
        max_poll_event_age_seconds=args.max_poll_event_age_seconds,
        max_user_stream_event_age_seconds=args.max_user_stream_event_age_seconds,
        max_runtime_db_age_seconds=args.max_runtime_db_age_seconds,
    )
    print(f"overall={report.overall_status}")
    for item in report.items:
        print(f"{item.name} status={item.status} {item.message}")
    return 0 if report.overall_status == "OK" else 1


def audit_report_command(
    *,
    parser,
    args,
    now_provider,
    summarize_audit_events_fn=summarize_audit_events,
) -> int:
    summary = summarize_audit_events_fn(
        path=Path(os.path.abspath(args.runtime_db_file)),
        now=now_provider(),
        since_minutes=args.since_minutes,
        limit=args.limit,
    )
    print(f"total_events={summary['total_events']}")
    for event_type, count in summary["counts"].items():
        print(f"{event_type}={count}")
    for event in summary["recent_events"]:
        print(f"recent timestamp={event['timestamp']} event_type={event['event_type']} payload={event['payload']}")
    return 0


def daily_review_report_command(
    *,
    parser,
    args,
    now_provider,
    build_daily_review_report_fn=build_daily_review_report,
    insert_daily_review_report_fn=insert_daily_review_report,
) -> int:
    runtime_db_path = _require_runtime_db_path(
        parser=parser,
        command=args.command,
        explicit_path=args.runtime_db_file,
    )
    report = build_daily_review_report_fn(
        path=runtime_db_path,
        now=now_provider(),
        stop_budget_usdt=Decimal(args.stop_budget_usdt),
        entry_start_hour_utc=args.entry_start_hour_utc,
        entry_end_hour_utc=args.entry_end_hour_utc,
    )
    insert_daily_review_report_fn(
        path=runtime_db_path,
        report_date=report.report_date,
        window_start=report.window_start,
        window_end=report.window_end,
        generated_at=report.generated_at,
        status=report.status,
        trade_count=report.trade_count,
        actual_total_pnl=report.actual_total_pnl,
        counterfactual_total_pnl=report.counterfactual_total_pnl,
        pnl_delta=report.pnl_delta,
        replayed_add_on_count=report.replayed_add_on_count,
        stop_budget_usdt=report.stop_budget_usdt,
        entry_start_hour_utc=report.entry_start_hour_utc,
        entry_end_hour_utc=report.entry_end_hour_utc,
        warnings=list(report.warnings),
        payload={
            "rows": [row.__dict__ for row in report.rows],
            "strategy_config": {
                "stop_budget_usdt": report.stop_budget_usdt,
                "entry_window": f"{report.entry_start_hour_utc:02d}:00-{report.entry_end_hour_utc:02d}:00 UTC",
            },
        },
    )
    print(f"report_date={report.report_date}")
    print(f"trade_count={report.trade_count}")
    print(f"actual_total_pnl={report.actual_total_pnl}")
    print(f"counterfactual_total_pnl={report.counterfactual_total_pnl}")
    return 0


def run_reporting_commands(
    *,
    parser,
    args,
    now_provider,
    build_runtime_health_report_fn=build_runtime_health_report,
    summarize_audit_events_fn=summarize_audit_events,
    build_daily_review_report_fn=build_daily_review_report,
    insert_daily_review_report_fn=insert_daily_review_report,
    **_unused,
) -> int | None:
    if args.command == "healthcheck":
        return healthcheck_command(
            parser=parser,
            args=args,
            now_provider=now_provider,
            build_runtime_health_report_fn=build_runtime_health_report_fn,
        )
    if args.command == "audit-report":
        return audit_report_command(
            parser=parser,
            args=args,
            now_provider=now_provider,
            summarize_audit_events_fn=summarize_audit_events_fn,
        )
    if args.command == "daily-review-report":
        return daily_review_report_command(
            parser=parser,
            args=args,
            now_provider=now_provider,
            build_daily_review_report_fn=build_daily_review_report_fn,
            insert_daily_review_report_fn=insert_daily_review_report_fn,
        )
    return None
