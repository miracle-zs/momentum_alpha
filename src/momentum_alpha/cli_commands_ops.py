from __future__ import annotations

import os
from pathlib import Path

from momentum_alpha.dashboard import run_dashboard_server
from momentum_alpha.runtime_store import rebuild_trade_analytics

from .cli_backfill import backfill_account_flows
from .cli_backfill import backfill_binance_user_trades
from .cli_env import (
    _build_client_from_factory,
    _parse_cli_datetime,
    load_runtime_settings_from_env,
    resolve_runtime_db_path,
)


def backfill_account_flows_command(
    *,
    parser,
    args,
    client_factory,
    backfill_account_flows_fn=backfill_account_flows,
) -> int:
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


def backfill_binance_trades_command(
    *,
    parser,
    args,
    client_factory,
    backfill_binance_user_trades_fn=backfill_binance_user_trades,
    rebuild_trade_analytics_fn=rebuild_trade_analytics,
) -> int:
    runtime_settings = load_runtime_settings_from_env()
    use_testnet = args.testnet or runtime_settings["use_testnet"]
    client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
    runtime_db_path = Path(os.path.abspath(args.runtime_db_file))
    inserted = backfill_binance_user_trades_fn(
        client=client,
        runtime_db_path=runtime_db_path,
        start_time=_parse_cli_datetime(args.start_time),
        end_time=_parse_cli_datetime(args.end_time),
        symbols=args.symbols,
        logger=print,
    )
    print(f"backfilled_binance_trades={inserted}")
    if not args.skip_rebuild:
        rebuild_trade_analytics_fn(path=runtime_db_path)
        print("trade-analytics-rebuilt")
    return 0


def rebuild_trade_analytics_command(
    *,
    parser,
    args,
    rebuild_trade_analytics_fn=rebuild_trade_analytics,
) -> int:
    runtime_db_path = Path(os.path.abspath(args.runtime_db_file))
    rebuild_trade_analytics_fn(path=runtime_db_path)
    print("trade-analytics-rebuilt")
    return 0


def dashboard_command(
    *,
    parser,
    args,
    now_provider,
    run_dashboard_fn=run_dashboard_server,
) -> int:
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


def run_ops_commands(
    *,
    parser,
    args,
    client_factory,
    now_provider,
    run_dashboard_fn=run_dashboard_server,
    backfill_account_flows_fn=backfill_account_flows,
    backfill_binance_user_trades_fn=backfill_binance_user_trades,
    rebuild_trade_analytics_fn=rebuild_trade_analytics,
    **_unused,
) -> int | None:
    if args.command == "backfill-account-flows":
        return backfill_account_flows_command(
            parser=parser,
            args=args,
            client_factory=client_factory,
            backfill_account_flows_fn=backfill_account_flows_fn,
        )
    if args.command == "backfill-binance-trades":
        return backfill_binance_trades_command(
            parser=parser,
            args=args,
            client_factory=client_factory,
            backfill_binance_user_trades_fn=backfill_binance_user_trades_fn,
            rebuild_trade_analytics_fn=rebuild_trade_analytics_fn,
        )
    if args.command == "rebuild-trade-analytics":
        return rebuild_trade_analytics_command(
            parser=parser,
            args=args,
            rebuild_trade_analytics_fn=rebuild_trade_analytics_fn,
        )
    if args.command == "dashboard":
        return dashboard_command(
            parser=parser,
            args=args,
            now_provider=now_provider,
            run_dashboard_fn=run_dashboard_fn,
        )
    return None
