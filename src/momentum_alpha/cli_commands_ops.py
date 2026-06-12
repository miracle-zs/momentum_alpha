from __future__ import annotations

import os
from pathlib import Path

from momentum_alpha.dashboard import run_dashboard_server
from momentum_alpha.leader_opportunity_diagnostics import diagnose_opportunities
from momentum_alpha.runtime_store import prune_runtime_db, rebuild_trade_analytics
from momentum_alpha.skipped_base_replay import replay_skipped_bases

from .cli_backfill import backfill_account_flows
from .cli_backfill import backfill_binance_user_trades
from .cli_backfill_candidates import backfill_leader_candidates
from .cli_env import (
    _build_client_from_factory,
    _parse_cli_datetime,
    _require_runtime_db_path,
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
        income_types=args.income_types,
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


def backfill_leader_candidates_command(
    *,
    parser,
    args,
    client_factory,
    backfill_leader_candidates_fn=backfill_leader_candidates,
) -> int:
    runtime_settings = load_runtime_settings_from_env()
    use_testnet = args.testnet or runtime_settings["use_testnet"]
    leader_candidates_db_path = Path(os.path.abspath(args.leader_candidates_db_file))
    if args.replay_position_snapshots:
        runtime_db_path = _require_runtime_db_path(
            parser=parser,
            command=args.command,
            explicit_path=args.runtime_db_file,
        )
        inserted = backfill_leader_candidates_fn(
            runtime_db_path=runtime_db_path,
            leader_candidates_db_path=leader_candidates_db_path,
            replay_position_snapshots=True,
            logger=print,
        )
    else:
        client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
        if args.start_time is None or args.end_time is None:
            parser.error("backfill-leader-candidates requires --start-time and --end-time unless --replay-position-snapshots is set")
        inserted = backfill_leader_candidates_fn(
            runtime_db_path=(
                Path(os.path.abspath(args.runtime_db_file)) if args.runtime_db_file else None
            ),
            leader_candidates_db_path=leader_candidates_db_path,
            replay_position_snapshots=False,
            client=client,
            start_time=_parse_cli_datetime(args.start_time),
            end_time=_parse_cli_datetime(args.end_time),
            symbols=args.symbols,
            interval=args.interval,
            top_n=args.top_n,
            logger=print,
        )
    print(f"backfilled_leader_candidates={inserted}")
    return 0


def diagnose_opportunities_command(
    *,
    parser,
    args,
    client_factory,
    diagnose_opportunities_fn=diagnose_opportunities,
) -> int:
    runtime_db_path = _require_runtime_db_path(
        parser=parser,
        command=args.command,
        explicit_path=args.runtime_db_file,
    )
    report = diagnose_opportunities_fn(
        runtime_db_path=runtime_db_path,
        leader_candidates_db_path=Path(os.path.abspath(args.leader_candidates_db_file)),
        output_file=Path(os.path.abspath(args.output_file)),
        start_time=_parse_cli_datetime(args.start_time) if args.start_time else None,
        end_time=_parse_cli_datetime(args.end_time) if args.end_time else None,
        symbols=args.symbols,
        min_peak_change_pct=args.min_peak_change_pct,
        logger=print,
    )
    return 0 if report.rows else 1


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


def replay_skipped_base_command(
    *,
    parser,
    args,
    replay_skipped_bases_fn=replay_skipped_bases,
) -> int:
    runtime_db_path = _require_runtime_db_path(
        parser=parser,
        command=args.command,
        explicit_path=args.runtime_db_file,
    )
    output_dir = Path(os.path.abspath(args.output_dir))
    report = replay_skipped_bases_fn(
        runtime_db_path=runtime_db_path,
        output_dir=output_dir,
        start_time=_parse_cli_datetime(args.start_time) if args.start_time else None,
        end_time=_parse_cli_datetime(args.end_time) if args.end_time else None,
        symbols=args.symbols,
        proxy=args.proxy,
        taker_fee_rate=args.taker_fee_rate,
        refresh_klines=args.refresh_klines,
    )
    print(f"replay_seed_count={report.seed_count}")
    print(f"replay_independent_count={len(report.opportunities)}")
    print(f"replay_overlap_count={len(report.overlaps)}")
    print(f"replay_output_dir={output_dir}")
    return 1 if report.had_fetch_errors else 0


def prune_runtime_db_command(
    *,
    parser,
    args,
    now_provider,
    prune_runtime_db_fn=prune_runtime_db,
) -> int:
    runtime_db_path = _require_runtime_db_path(
        parser=parser,
        command=args.command,
        explicit_path=args.runtime_db_file,
    )
    summary = prune_runtime_db_fn(
        path=runtime_db_path,
        now=now_provider(),
        audit_retention_days=args.audit_retention_days,
        snapshot_retention_days=args.snapshot_retention_days,
    )
    print(f"audit_cutoff={summary['audit_cutoff']}")
    print(f"snapshot_cutoff={summary['snapshot_cutoff']}")
    print(f"audit_events_deleted={summary['audit_events_deleted']}")
    print(f"position_snapshots_deleted={summary['position_snapshots_deleted']}")
    print(f"account_snapshots_deleted={summary['account_snapshots_deleted']}")
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
    backfill_leader_candidates_fn=backfill_leader_candidates,
    diagnose_opportunities_fn=diagnose_opportunities,
    replay_skipped_bases_fn=replay_skipped_bases,
    rebuild_trade_analytics_fn=rebuild_trade_analytics,
    prune_runtime_db_fn=prune_runtime_db,
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
    if args.command == "backfill-leader-candidates":
        return backfill_leader_candidates_command(
            parser=parser,
            args=args,
            client_factory=client_factory,
            backfill_leader_candidates_fn=backfill_leader_candidates_fn,
        )
    if args.command == "diagnose-opportunities":
        return diagnose_opportunities_command(
            parser=parser,
            args=args,
            client_factory=client_factory,
            diagnose_opportunities_fn=diagnose_opportunities_fn,
        )
    if args.command == "replay-skipped-base":
        return replay_skipped_base_command(
            parser=parser,
            args=args,
            replay_skipped_bases_fn=replay_skipped_bases_fn,
        )
    if args.command == "rebuild-trade-analytics":
        return rebuild_trade_analytics_command(
            parser=parser,
            args=args,
            rebuild_trade_analytics_fn=rebuild_trade_analytics_fn,
        )
    if args.command == "prune-runtime-db":
        return prune_runtime_db_command(
            parser=parser,
            args=args,
            now_provider=now_provider,
            prune_runtime_db_fn=prune_runtime_db_fn,
        )
    if args.command == "dashboard":
        return dashboard_command(
            parser=parser,
            args=args,
            now_provider=now_provider,
            run_dashboard_fn=run_dashboard_fn,
        )
    return None
