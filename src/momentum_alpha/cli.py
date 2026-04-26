from __future__ import annotations

from datetime import datetime, timezone

from momentum_alpha.logging_config import configure_logging

from momentum_alpha.binance_client import BINANCE_TESTNET_FAPI_BASE_URL, BinanceRestClient
from momentum_alpha.broker import BinanceBroker
from momentum_alpha.dashboard import run_dashboard_server
from momentum_alpha.poll_worker import run_forever
from momentum_alpha.runtime_store import prune_runtime_db, rebuild_trade_analytics
from momentum_alpha.stream_worker import run_user_stream

from .cli_backfill import _account_flow_exists, backfill_account_flows, backfill_binance_user_trades
from .cli_commands import run_cli_command
from .cli_env import (
    _build_audit_recorder,
    _build_client_from_factory,
    _build_runtime_state_store,
    _parse_cli_datetime,
    _require_runtime_db_path,
    load_credentials_from_env,
    load_runtime_settings_from_env,
    resolve_runtime_db_path,
)
from .cli_parser import build_cli_parser


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
    backfill_binance_user_trades_fn=None,
    rebuild_trade_analytics_fn=None,
    prune_runtime_db_fn=None,
) -> int:
    configure_logging()
    parser = build_cli_parser()
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
    backfill_account_flows_fn = backfill_account_flows_fn or backfill_account_flows
    backfill_binance_user_trades_fn = backfill_binance_user_trades_fn or backfill_binance_user_trades
    rebuild_trade_analytics_fn = rebuild_trade_analytics_fn or rebuild_trade_analytics
    prune_runtime_db_fn = prune_runtime_db_fn or prune_runtime_db

    run_dashboard_fn = run_dashboard_fn or run_dashboard_server

    return run_cli_command(
        parser=parser,
        args=args,
        client_factory=client_factory,
        broker_factory=broker_factory,
        now_provider=now_provider,
        run_forever_fn=run_forever_fn,
        run_user_stream_fn=run_user_stream_fn,
        run_dashboard_fn=run_dashboard_fn,
        backfill_account_flows_fn=backfill_account_flows_fn,
        backfill_binance_user_trades_fn=backfill_binance_user_trades_fn,
        rebuild_trade_analytics_fn=rebuild_trade_analytics_fn,
        prune_runtime_db_fn=prune_runtime_db_fn,
    )


__all__ = [
    "cli_main",
    "resolve_runtime_db_path",
    "_require_runtime_db_path",
    "_build_audit_recorder",
    "_build_runtime_state_store",
    "_parse_cli_datetime",
    "_build_client_from_factory",
    "load_credentials_from_env",
    "load_runtime_settings_from_env",
    "_account_flow_exists",
    "backfill_account_flows",
    "backfill_binance_user_trades",
    "build_cli_parser",
]
