from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from momentum_alpha.daily_review import build_daily_review_report
from momentum_alpha.health import build_runtime_health_report
from momentum_alpha.runtime_store import insert_daily_review_report, summarize_audit_events

from .cli_env import (
    _build_audit_recorder,
    _build_client_from_factory,
    _build_runtime_state_store,
    _parse_cli_datetime,
    _require_runtime_db_path,
    load_runtime_settings_from_env,
    resolve_runtime_db_path,
)


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
    rebuild_trade_analytics_fn,
) -> int:
    if args.command == "run-once-live":
        runtime_settings = load_runtime_settings_from_env()
        use_testnet = args.testnet or runtime_settings["use_testnet"]
        client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
        broker = broker_factory(client)
        runtime_db_path = _require_runtime_db_path(
            parser=parser,
            command=args.command,
            explicit_path=args.runtime_db_file,
        )
        runtime_state_store = _build_runtime_state_store(runtime_db_path=runtime_db_path)
        audit_recorder = _build_audit_recorder(
            runtime_db_path=runtime_db_path,
            source="run-once-live",
            error_logger=print,
        )
        mode = "LIVE" if args.submit_orders else "DRY_RUN"
        from momentum_alpha.poll_worker import run_once_live as _run_once_live

        result = _run_once_live(
            symbols=args.symbols,
            now=now_provider(),
            previous_leader_symbol=args.previous_leader,
            client=client,
            broker=broker,
            submit_orders=args.submit_orders,
            runtime_state_store=runtime_state_store,
            audit_recorder=audit_recorder,
        )
        entry_symbols = [order["symbol"] for order in result.execution_plan.entry_orders]
        print(f"mode={mode}")
        print(f"testnet={use_testnet}")
        print(f"entry_orders={entry_symbols}")
        print(f"broker_responses={len(result.broker_responses)}")
        return 0

    if args.command == "poll":
        runtime_settings = load_runtime_settings_from_env()
        use_testnet = args.testnet or runtime_settings["use_testnet"]
        runtime_db_path = _require_runtime_db_path(
            parser=parser,
            command=args.command,
            explicit_path=args.runtime_db_file,
        )
        runtime_state_store = _build_runtime_state_store(runtime_db_path=runtime_db_path)
        audit_recorder = _build_audit_recorder(
            runtime_db_path=runtime_db_path,
            source="poll",
            error_logger=print,
        )
        mode = "LIVE" if args.submit_orders else "DRY_RUN"
        print(
            "starting poll "
            f"mode={mode} symbols={args.symbols or 'AUTO'} "
            f"testnet={use_testnet} "
            f"restore_positions={args.restore_positions} "
            f"execute_stop_replacements={args.execute_stop_replacements} "
            f"max_ticks={args.max_ticks}"
        )
        return run_forever_fn(
            symbols=args.symbols,
            previous_leader_symbol=args.previous_leader,
            submit_orders=args.submit_orders,
            runtime_state_store=runtime_state_store,
            client_factory=lambda: _build_client_from_factory(client_factory=client_factory, testnet=use_testnet),
            broker_factory=broker_factory,
            now_provider=now_provider,
            restore_positions=args.restore_positions,
            execute_stop_replacements=args.execute_stop_replacements,
            max_ticks=args.max_ticks,
            audit_recorder=audit_recorder,
        )

    if args.command == "user-stream":
        runtime_settings = load_runtime_settings_from_env()
        use_testnet = args.testnet or runtime_settings["use_testnet"]
        client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
        runtime_db_path = _require_runtime_db_path(
            parser=parser,
            command=args.command,
            explicit_path=args.runtime_db_file,
        )
        runtime_state_store = _build_runtime_state_store(runtime_db_path=runtime_db_path)
        print(f"starting user-stream testnet={use_testnet}")
        return run_user_stream_fn(
            client=client,
            testnet=use_testnet,
            logger=print,
            runtime_state_store=runtime_state_store,
            runtime_db_path=runtime_db_path,
        )

    if args.command == "healthcheck":
        report = build_runtime_health_report(
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

    if args.command == "audit-report":
        summary = summarize_audit_events(
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

    if args.command == "daily-review-report":
        runtime_db_path = _require_runtime_db_path(
            parser=parser,
            command=args.command,
            explicit_path=args.runtime_db_file,
        )
        report = build_daily_review_report(
            path=runtime_db_path,
            now=now_provider(),
            stop_budget_usdt=Decimal(args.stop_budget_usdt),
            entry_start_hour_utc=args.entry_start_hour_utc,
            entry_end_hour_utc=args.entry_end_hour_utc,
        )
        insert_daily_review_report(
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

    if args.command == "backfill-account-flows":
        runtime_settings = load_runtime_settings_from_env()
        use_testnet = args.testnet or runtime_settings["use_testnet"]
        client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
        inserted = backfill_account_flows_fn(
            client=client,
            runtime_db_path=Path(os.path.abspath(args.runtime_db_file)),
            start_time=_parse_cli_datetime(args.start_time),
            end_time=_parse_cli_datetime(args.end_time),
            logger=print,
        )
        print(f"backfilled_account_flows={inserted}")
        return 0

    if args.command == "rebuild-trade-analytics":
        runtime_db_path = Path(os.path.abspath(args.runtime_db_file))
        rebuild_trade_analytics_fn(path=runtime_db_path)
        print("trade-analytics-rebuilt")
        return 0

    if args.command == "dashboard":
        runtime_settings = load_runtime_settings_from_env()
        submit_orders_env = os.environ.get("SUBMIT_ORDERS", "").strip().lower() in {"1", "true", "yes", "on"}
        runtime_db_path = resolve_runtime_db_path(explicit_path=args.runtime_db_file)
        return run_dashboard_fn(
            host=args.host,
            port=args.port,
            poll_log_file=Path(os.path.abspath(args.poll_log_file)) if args.poll_log_file else None,
            user_stream_log_file=Path(os.path.abspath(args.user_stream_log_file)) if args.user_stream_log_file else None,
            runtime_db_file=runtime_db_path,
            now_provider=now_provider,
            stop_budget_usdt=os.environ.get("STOP_BUDGET_USDT", "10"),
            testnet=runtime_settings["use_testnet"],
            submit_orders=submit_orders_env,
        )

    return 1
