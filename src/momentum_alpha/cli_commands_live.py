from __future__ import annotations

from momentum_alpha.poll_worker import run_forever as _default_run_forever, run_once_live as _default_run_once_live
from momentum_alpha.stream_worker import run_user_stream as _default_run_user_stream

from .cli_env import (
    _build_audit_recorder,
    _build_client_from_factory,
    _build_runtime_state_store,
    load_runtime_settings_from_env,
    _require_runtime_db_path,
)


def run_once_live_command(
    *,
    parser,
    args,
    client_factory,
    broker_factory,
    now_provider,
) -> int:
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

    result = _default_run_once_live(
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


def poll_command(
    *,
    parser,
    args,
    client_factory,
    broker_factory,
    now_provider,
    run_forever_fn=_default_run_forever,
) -> int:
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


def user_stream_command(
    *,
    parser,
    args,
    client_factory,
    broker_factory,
    now_provider,
    run_user_stream_fn=_default_run_user_stream,
) -> int:
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


def run_live_commands(
    *,
    parser,
    args,
    client_factory,
    broker_factory,
    now_provider,
    run_forever_fn=_default_run_forever,
    run_user_stream_fn=_default_run_user_stream,
    **_unused,
) -> int | None:
    if args.command == "run-once-live":
        return run_once_live_command(
            parser=parser,
            args=args,
            client_factory=client_factory,
            broker_factory=broker_factory,
            now_provider=now_provider,
        )
    if args.command == "poll":
        return poll_command(
            parser=parser,
            args=args,
            client_factory=client_factory,
            broker_factory=broker_factory,
            now_provider=now_provider,
            run_forever_fn=run_forever_fn,
        )
    if args.command == "user-stream":
        return user_stream_command(
            parser=parser,
            args=args,
            client_factory=client_factory,
            broker_factory=broker_factory,
            now_provider=now_provider,
            run_user_stream_fn=run_user_stream_fn,
        )
    return None
