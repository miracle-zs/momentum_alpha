from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from momentum_alpha.daily_review import (
    DailyReviewWindow,
    build_daily_review_report,
    build_daily_review_window,
)
from momentum_alpha.filtered_base_review import build_filtered_base_review_report
from momentum_alpha.health import build_runtime_health_report
from momentum_alpha.runtime_store import (
    fetch_filtered_base_review_report_by_date,
    fetch_filtered_base_review_report_dates,
    fetch_signal_decisions_for_window,
    insert_daily_review_report,
    insert_filtered_base_review_report,
    summarize_audit_events,
)

from .cli_env import _parse_cli_datetime, _require_runtime_db_path


_FILTERED_REVIEW_REFRESH_MAX_AGE = timedelta(hours=48)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_report_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(str(value)))
    except (TypeError, ValueError):
        return None


def refresh_open_filtered_base_reports(
    *,
    path: Path,
    now: datetime,
    current_report_date: str,
    replay_output_dir: Path,
    replay_skipped_bases_fn,
    build_filtered_base_review_report_fn=build_filtered_base_review_report,
    insert_filtered_base_review_report_fn=insert_filtered_base_review_report,
) -> list[str]:
    """Finalize recent filtered reports whose replay was still open at cutoff.

    The report date/window remains unchanged; only the replay cutoff advances.
    This keeps the original daily review immutable while allowing a filtered
    counterfactual to settle after the day boundary.
    """

    now_utc = _as_utc(now)
    refreshed_dates: list[str] = []
    for report_date in fetch_filtered_base_review_report_dates(path=path):
        if report_date >= current_report_date:
            continue
        stored = fetch_filtered_base_review_report_by_date(
            path=path,
            report_date=report_date,
        )
        if stored is None:
            continue
        payload = stored.get("payload") or {}
        rows = payload.get("rows") or payload.get("filtered_base_rows") or []
        window_start = _parse_report_datetime(stored.get("window_start"))
        window_end = _parse_report_datetime(stored.get("window_end"))
        if window_start is None or window_end is None:
            continue
        signal_decisions = fetch_signal_decisions_for_window(
            path=path,
            window_start=window_start,
            window_end=window_end,
        )
        candidate_sample_ids = {
            str(
                (decision.get("payload") or {}).get("shadow_opportunity_id")
                or decision.get("intent_id")
                or ""
            )
            for decision in signal_decisions
            if decision.get("decision_type") == "base_entry_skipped"
            and str((decision.get("payload") or {}).get("blocked_reason") or "") == "base_veto"
        }
        stored_sample_ids = {
            str(row.get("sample_id") or row.get("shadow_opportunity_id") or "")
            for row in rows
        }
        needs_rebuild = not candidate_sample_ids.issubset(stored_sample_ids)
        open_rows = [
            row
            for row in rows
            if str(row.get("status") or "") in {"open", "pending_replay", "unresolved"}
        ]
        if not open_rows and not needs_rebuild:
            continue
        report_age = now_utc - window_end
        if report_age < timedelta(0) or report_age > _FILTERED_REVIEW_REFRESH_MAX_AGE:
            continue
        symbols = sorted(
            {
                str(decision.get("symbol") or "")
                for decision in signal_decisions
                if decision.get("decision_type") == "base_entry_skipped"
                and str((decision.get("payload") or {}).get("blocked_reason") or "") == "base_veto"
                and decision.get("symbol")
            }
        )
        if not symbols:
            continue
        replay_report = replay_skipped_bases_fn(
            runtime_db_path=path,
            output_dir=replay_output_dir / "historical" / report_date,
            start_time=window_start,
            seed_end_time=window_end,
            end_time=now_utc,
            symbols=symbols,
            proxy=os.environ.get("BINANCE_PROXY") or None,
            taker_fee_rate=Decimal(os.environ.get("TAKER_FEE_RATE", "0.0005")),
            refresh_klines=False,
            blocked_reasons={"base_veto"},
            independent_candidate_replay=False,
            enforce_daily_base_limit=True,
        )
        if bool(getattr(replay_report, "had_fetch_errors", False)):
            continue
        result_by_id = {
            str(getattr(result, "shadow_opportunity_id", "")): result
            for result in (getattr(replay_report, "opportunities", ()) or ())
            if getattr(result, "shadow_opportunity_id", None)
        }
        open_sample_ids = {
            str(row.get("sample_id") or row.get("shadow_opportunity_id") or "")
            for row in open_rows
        }
        if not open_sample_ids.issubset(result_by_id):
            continue
        if any(
            str(getattr(result_by_id[sample_id], "status", "")) not in {"closed", "open"}
            for sample_id in open_sample_ids
        ):
            continue
        refreshed_report = build_filtered_base_review_report_fn(
            path=path,
            now=now,
            replay_report=replay_report,
            review_window=DailyReviewWindow(
                report_date=report_date,
                window_start=window_start,
                window_end=window_end,
            ),
            replay_cutoff=now_utc,
        )
        refreshed_rows = {
            str(row.sample_id): row
            for row in refreshed_report.rows
        }
        if any(
            sample_id not in refreshed_rows
            or refreshed_rows[sample_id].status not in {"closed", "open"}
            for sample_id in open_sample_ids
        ):
            continue
        insert_filtered_base_review_report_fn(
            path=path,
            report_date=refreshed_report.report_date,
            window_start=refreshed_report.window_start,
            window_end=refreshed_report.window_end,
            generated_at=refreshed_report.generated_at,
            status=refreshed_report.status,
            warnings=list(refreshed_report.warnings),
            payload={
                "summary": refreshed_report.summary,
                "rows": [row.__dict__ for row in refreshed_report.rows],
            },
        )
        refreshed_dates.append(report_date)
    return refreshed_dates


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
    build_filtered_base_review_report_fn=build_filtered_base_review_report,
    insert_daily_review_report_fn=insert_daily_review_report,
    insert_filtered_base_review_report_fn=insert_filtered_base_review_report,
    replay_skipped_bases_fn=None,
) -> int:
    runtime_db_path = _require_runtime_db_path(
        parser=parser,
        command=args.command,
        explicit_path=args.runtime_db_file,
    )
    now = now_provider()
    replay_report = None
    if getattr(args, "replay_filtered_bases", False):
        if replay_skipped_bases_fn is None:
            parser.error("--replay-filtered-bases requires the skipped Base replay command")
        window = build_daily_review_window(now=now)
        replay_output_dir = Path(
            os.environ.get(
                "DAILY_REVIEW_REPLAY_OUTPUT_DIR",
                str(runtime_db_path.parent / "daily_review_replay"),
            )
        )
        replay_report = replay_skipped_bases_fn(
            runtime_db_path=runtime_db_path,
            output_dir=replay_output_dir,
            start_time=window.window_start,
            end_time=window.window_end,
            symbols=None,
            proxy=os.environ.get("BINANCE_PROXY") or None,
            taker_fee_rate=Decimal(os.environ.get("TAKER_FEE_RATE", "0.0005")),
            refresh_klines=False,
            blocked_reasons={"base_veto"},
            independent_candidate_replay=False,
            enforce_daily_base_limit=True,
        )

    report_kwargs = {
        "path": runtime_db_path,
        "now": now,
        "stop_budget_usdt": Decimal(args.stop_budget_usdt),
        "entry_start_hour_utc": args.entry_start_hour_utc,
        "entry_end_hour_utc": args.entry_end_hour_utc,
    }
    report = build_daily_review_report_fn(**report_kwargs)
    filtered_report = (
        build_filtered_base_review_report_fn(
            path=runtime_db_path,
            now=now,
            replay_report=replay_report,
        )
        if replay_report is not None
        else None
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
            "account_reconciliation": report.account_reconciliation.__dict__,
            "strategy_config": {
                "stop_budget_usdt": report.stop_budget_usdt,
                "entry_window": f"{report.entry_start_hour_utc:02d}:00-{report.entry_end_hour_utc:02d}:00 UTC",
            },
        },
    )
    if filtered_report is not None:
        insert_filtered_base_review_report_fn(
            path=runtime_db_path,
            report_date=filtered_report.report_date,
            window_start=filtered_report.window_start,
            window_end=filtered_report.window_end,
            generated_at=filtered_report.generated_at,
            status=filtered_report.status,
            warnings=list(filtered_report.warnings),
            payload={
                "summary": filtered_report.summary,
                "rows": [row.__dict__ for row in filtered_report.rows],
            },
        )
    refreshed_filtered_dates = (
        refresh_open_filtered_base_reports(
            path=runtime_db_path,
            now=now,
            current_report_date=(filtered_report.report_date if filtered_report is not None else report.report_date),
            replay_output_dir=replay_output_dir,
            replay_skipped_bases_fn=replay_skipped_bases_fn,
            build_filtered_base_review_report_fn=build_filtered_base_review_report_fn,
            insert_filtered_base_review_report_fn=insert_filtered_base_review_report_fn,
        )
        if filtered_report is not None and replay_skipped_bases_fn is not None
        else []
    )
    print(f"report_date={report.report_date}")
    print(f"trade_count={report.trade_count}")
    print(f"actual_total_pnl={report.actual_total_pnl}")
    print(f"counterfactual_total_pnl={report.counterfactual_total_pnl}")
    filtered_summary = filtered_report.summary if filtered_report is not None else {}
    print(f"filtered_base_candidates={filtered_summary.get('candidate_count', 0)}")
    print(f"filtered_base_strategy_pnl_delta={filtered_summary.get('strategy_pnl_delta', '0')}")
    print(f"filtered_base_refreshed_dates={','.join(refreshed_filtered_dates)}")
    print(f"account_income_total_pnl={report.account_reconciliation.income_total_pnl}")
    print(f"account_trade_vs_income_delta={report.account_reconciliation.trade_vs_income_delta}")
    return 0


def run_reporting_commands(
    *,
    parser,
    args,
    now_provider,
    build_runtime_health_report_fn=build_runtime_health_report,
    summarize_audit_events_fn=summarize_audit_events,
    build_daily_review_report_fn=build_daily_review_report,
    build_filtered_base_review_report_fn=build_filtered_base_review_report,
    insert_daily_review_report_fn=insert_daily_review_report,
    insert_filtered_base_review_report_fn=insert_filtered_base_review_report,
    replay_skipped_bases_fn=None,
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
            build_filtered_base_review_report_fn=build_filtered_base_review_report_fn,
            insert_daily_review_report_fn=insert_daily_review_report_fn,
            insert_filtered_base_review_report_fn=insert_filtered_base_review_report_fn,
            replay_skipped_bases_fn=replay_skipped_bases_fn,
        )
    return None
