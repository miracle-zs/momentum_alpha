from __future__ import annotations

from momentum_alpha.cli import (
    _account_flow_exists,
    _build_audit_recorder,
    _build_client_from_factory,
    _build_runtime_state_store,
    _parse_cli_datetime,
    _require_runtime_db_path,
    backfill_account_flows,
    backfill_binance_user_trades,
    cli_main,
    load_credentials_from_env,
    load_runtime_settings_from_env,
    resolve_runtime_db_path,
)
from momentum_alpha.market_data import (
    LiveMarketDataCache,
    _build_live_snapshots,
    _current_hour_window_ms,
    _fetch_current_hour_klines,
    _fetch_daily_open_klines,
    _fetch_previous_hour_klines,
    _previous_closed_hour_window_ms,
    _resolve_symbols,
    _utc_midnight_window_ms,
)
from momentum_alpha.poll_worker import (
    RunOnceResult,
    _save_strategy_state,
    build_runtime_from_snapshots,
    run_forever,
    run_once,
    run_once_live,
)
from momentum_alpha.runtime_store import rebuild_trade_analytics
from momentum_alpha.stream_worker import (
    _prune_processed_event_ids,
    _save_user_stream_strategy_state,
    run_user_stream,
)
from momentum_alpha.telemetry import (
    _build_market_context_payloads,
    _build_snapshot_market_context_payload,
    _record_account_snapshot,
    _record_broker_orders,
    _record_position_snapshot,
    _record_signal_decision,
)


if __name__ == "__main__":
    raise SystemExit(cli_main())
