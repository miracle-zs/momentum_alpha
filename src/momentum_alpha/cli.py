from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.binance_client import BINANCE_TESTNET_FAPI_BASE_URL, BinanceRestClient
from momentum_alpha.broker import BinanceBroker
from momentum_alpha.daily_review import build_daily_review_report
from momentum_alpha.dashboard import run_dashboard_server
from momentum_alpha.health import build_runtime_health_report
from momentum_alpha.poll_worker import run_forever, run_once_live
from momentum_alpha.runtime_store import (
    RuntimeStateStore,
    insert_account_flow,
    insert_daily_review_report,
    rebuild_trade_analytics,
    summarize_audit_events,
)
from momentum_alpha.stream_worker import run_user_stream


def resolve_runtime_db_path(*, explicit_path: str | None, default_dir: Path | None = None) -> Path | None:
    """Resolve the runtime database path.

    Priority:
    1. Explicit path provided
    2. RUNTIME_DB_FILE environment variable
    3. default_dir/runtime.db if default_dir is provided
    """
    if explicit_path:
        return Path(os.path.abspath(explicit_path))
    env_path = os.environ.get("RUNTIME_DB_FILE")
    if env_path:
        return Path(os.path.abspath(env_path))
    if default_dir is not None:
        return default_dir / "runtime.db"
    return None


def _require_runtime_db_path(*, parser: argparse.ArgumentParser, command: str, explicit_path: str | None) -> Path:
    runtime_db_path = resolve_runtime_db_path(explicit_path=explicit_path)
    if runtime_db_path is None:
        parser.error(f"{command} requires --runtime-db-file or RUNTIME_DB_FILE")
    return runtime_db_path


def _build_audit_recorder(
    *,
    runtime_db_path: Path | None,
    source: str | None = None,
    error_logger=None,
) -> AuditRecorder | None:
    if runtime_db_path is None:
        return None
    return AuditRecorder(runtime_db_path=runtime_db_path, source=source, error_logger=error_logger)


def _build_runtime_state_store(*, runtime_db_path: Path | None) -> RuntimeStateStore | None:
    """Build a RuntimeStateStore for state persistence."""
    if runtime_db_path is None:
        return None
    return RuntimeStateStore(path=runtime_db_path)


def load_credentials_from_env() -> tuple[str, str]:
    api_key = os.environ["BINANCE_API_KEY"]
    api_secret = os.environ["BINANCE_API_SECRET"]
    return api_key, api_secret


def load_runtime_settings_from_env() -> dict[str, bool]:
    raw_testnet = os.environ.get("BINANCE_USE_TESTNET", "")
    return {"use_testnet": raw_testnet.strip().lower() in {"1", "true", "yes", "on"}}


def _parse_cli_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _account_flow_exists(
    *,
    runtime_db_path: Path,
    timestamp: datetime,
    reason: str | None,
    asset: str | None,
    balance_change: str | None,
) -> bool:
    if not runtime_db_path.exists():
        return False
    connection = sqlite3.connect(runtime_db_path)
    try:
        row = connection.execute(
            """
            SELECT 1
            FROM account_flows
            WHERE timestamp = ?
              AND COALESCE(reason, '') = COALESCE(?, '')
              AND COALESCE(asset, '') = COALESCE(?, '')
              AND COALESCE(balance_change, '') = COALESCE(?, '')
            LIMIT 1
            """,
            (timestamp.astimezone(timezone.utc).isoformat(), reason, asset, balance_change),
        ).fetchone()
    finally:
        connection.close()
    return row is not None


def backfill_account_flows(
    *,
    client,
    runtime_db_path: Path,
    start_time: datetime,
    end_time: datetime,
    logger=print,
) -> int:
    inserted = 0
    window_start = start_time.astimezone(timezone.utc)
    end_time_utc = end_time.astimezone(timezone.utc)
    while window_start < end_time_utc:
        window_end = min(window_start + timedelta(days=7), end_time_utc)
        incomes = client.fetch_income_history(
            income_type="TRANSFER",
            start_time_ms=int(window_start.timestamp() * 1000),
            end_time_ms=int(window_end.timestamp() * 1000),
            limit=1000,
        )
        for income in incomes:
            timestamp_ms = income.get("time")
            if timestamp_ms in (None, ""):
                continue
            timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
            reason = str(income.get("info") or income.get("incomeType") or "").upper() or None
            asset = income.get("asset")
            balance_change = str(income.get("income")) if income.get("income") not in (None, "") else None
            if _account_flow_exists(
                runtime_db_path=runtime_db_path,
                timestamp=timestamp,
                reason=reason,
                asset=asset,
                balance_change=balance_change,
            ):
                continue
            insert_account_flow(
                path=runtime_db_path,
                timestamp=timestamp,
                source="backfill-income-history",
                reason=reason,
                asset=asset,
                balance_change=balance_change,
                payload=income,
            )
            inserted += 1
        logger(
            "backfill-account-flows "
            f"window_start={window_start.isoformat()} window_end={window_end.isoformat()} "
            f"fetched={len(incomes)} inserted={inserted}"
        )
        window_start = window_end
    return inserted


def _build_client_from_factory(*, client_factory, testnet: bool):
    try:
        return client_factory(testnet=testnet)
    except TypeError:
        return client_factory()


def cli_main(
    *,
    argv: list[str] | None = None,
    client_factory=None,
    broker_factory=None,
    now_provider=None,
    run_forever_fn=None,
    run_user_stream_fn=None,
    run_dashboard_fn=None,
    backfill_account_flows_fn=None,
    rebuild_trade_analytics_fn=None,
) -> int:
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
    backfill_account_flows_parser = subparsers.add_parser("backfill-account-flows")
    backfill_account_flows_parser.add_argument("--runtime-db-file", required=True)
    backfill_account_flows_parser.add_argument("--start-time", required=True)
    backfill_account_flows_parser.add_argument("--end-time", required=True)
    backfill_account_flows_parser.add_argument("--testnet", action="store_true")
    rebuild_trade_analytics_parser = subparsers.add_parser("rebuild-trade-analytics")
    rebuild_trade_analytics_parser.add_argument("--runtime-db-file", required=True)
    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_parser.add_argument("--host", default="127.0.0.1")
    dashboard_parser.add_argument("--port", type=int, default=8080)
    dashboard_parser.add_argument("--poll-log-file")
    dashboard_parser.add_argument("--user-stream-log-file")
    dashboard_parser.add_argument("--runtime-db-file", required=True)

    args = parser.parse_args(argv)

    def _default_client_factory(*, testnet: bool = False):
        api_key, api_secret = load_credentials_from_env()
        runtime_settings = load_runtime_settings_from_env()
        base_url = BINANCE_TESTNET_FAPI_BASE_URL if (testnet or runtime_settings["use_testnet"]) else None
        kwargs = {"api_key": api_key, "api_secret": api_secret}
        if base_url is not None:
            kwargs["base_url"] = base_url
        return BinanceRestClient(**kwargs)

    client_factory = client_factory or _default_client_factory
    broker_factory = broker_factory or (lambda client: BinanceBroker(client=client))
    now_provider = now_provider or (lambda: datetime.now(timezone.utc))
    run_forever_fn = run_forever_fn or run_forever
    run_user_stream_fn = run_user_stream_fn or run_user_stream
    run_dashboard_fn = run_dashboard_fn or run_dashboard_server
    backfill_account_flows_fn = backfill_account_flows_fn or backfill_account_flows
    rebuild_trade_analytics_fn = rebuild_trade_analytics_fn or rebuild_trade_analytics

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
        result = run_once_live(
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
