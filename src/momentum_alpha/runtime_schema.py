from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    source TEXT,
    decision_id TEXT,
    intent_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp
    ON audit_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_event_type_timestamp
    ON audit_events(event_type, timestamp DESC);

CREATE TABLE IF NOT EXISTS signal_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    decision_id TEXT,
    intent_id TEXT,
    decision_type TEXT NOT NULL,
    symbol TEXT,
    previous_leader_symbol TEXT,
    next_leader_symbol TEXT,
    position_count INTEGER,
    order_status_count INTEGER,
    broker_response_count INTEGER,
    stop_replacement_count INTEGER,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signal_decisions_timestamp
    ON signal_decisions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_decisions_decision_type_timestamp
    ON signal_decisions(decision_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_decisions_next_leader_timestamp
    ON signal_decisions(next_leader_symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS broker_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    symbol TEXT,
    action_type TEXT NOT NULL,
    order_type TEXT,
    order_id TEXT,
    client_order_id TEXT,
    client_algo_id TEXT,
    decision_id TEXT,
    intent_id TEXT,
    order_status TEXT,
    side TEXT,
    quantity REAL,
    price REAL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_broker_orders_timestamp
    ON broker_orders(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_broker_orders_action_type_timestamp
    ON broker_orders(action_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_broker_orders_symbol_timestamp
    ON broker_orders(symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS trade_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    symbol TEXT,
    order_id TEXT,
    trade_id TEXT,
    client_order_id TEXT,
    decision_id TEXT,
    intent_id TEXT,
    order_status TEXT,
    execution_type TEXT,
    side TEXT,
    order_type TEXT,
    quantity TEXT,
    cumulative_quantity TEXT,
    average_price TEXT,
    last_price TEXT,
    realized_pnl TEXT,
    commission TEXT,
    commission_asset TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_fills_timestamp
    ON trade_fills(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trade_fills_symbol_timestamp
    ON trade_fills(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trade_fills_trade_id
    ON trade_fills(trade_id);

CREATE TABLE IF NOT EXISTS algo_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    symbol TEXT,
    algo_id TEXT,
    client_algo_id TEXT,
    decision_id TEXT,
    intent_id TEXT,
    algo_status TEXT,
    side TEXT,
    order_type TEXT,
    trigger_price TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_algo_orders_timestamp
    ON algo_orders(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_algo_orders_symbol_timestamp
    ON algo_orders(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_algo_orders_algo_id
    ON algo_orders(algo_id);

CREATE TABLE IF NOT EXISTS account_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    reason TEXT,
    asset TEXT,
    wallet_balance TEXT,
    cross_wallet_balance TEXT,
    balance_change TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_flows_timestamp
    ON account_flows(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_account_flows_reason_timestamp
    ON account_flows(reason, timestamp DESC);

CREATE TABLE IF NOT EXISTS trade_round_trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_trip_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT NOT NULL,
    entry_fill_count INTEGER NOT NULL,
    exit_fill_count INTEGER NOT NULL,
    total_entry_quantity TEXT,
    total_exit_quantity TEXT,
    weighted_avg_entry_price TEXT,
    weighted_avg_exit_price TEXT,
    realized_pnl TEXT,
    commission TEXT,
    net_pnl TEXT,
    exit_reason TEXT,
    duration_seconds INTEGER,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_round_trips_closed_at
    ON trade_round_trips(closed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trade_round_trips_symbol_closed_at
    ON trade_round_trips(symbol, closed_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_round_trips_round_trip_id
    ON trade_round_trips(round_trip_id);

CREATE TABLE IF NOT EXISTS daily_review_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    trade_count INTEGER NOT NULL,
    actual_total_pnl TEXT NOT NULL,
    counterfactual_total_pnl TEXT NOT NULL,
    pnl_delta TEXT NOT NULL,
    replayed_add_on_count INTEGER NOT NULL,
    stop_budget_usdt TEXT NOT NULL,
    entry_start_hour_utc INTEGER NOT NULL,
    entry_end_hour_utc INTEGER NOT NULL,
    warning_json TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_review_reports_report_date
    ON daily_review_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_daily_review_reports_generated_at
    ON daily_review_reports(generated_at DESC);

CREATE TABLE IF NOT EXISTS stop_exit_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    round_trip_id TEXT NOT NULL,
    trigger_price TEXT,
    average_exit_price TEXT,
    slippage_abs TEXT,
    slippage_pct TEXT,
    exit_quantity TEXT,
    realized_pnl TEXT,
    commission TEXT,
    net_pnl TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stop_exit_summaries_timestamp
    ON stop_exit_summaries(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_stop_exit_summaries_symbol_timestamp
    ON stop_exit_summaries(symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS position_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    leader_symbol TEXT,
    decision_id TEXT,
    intent_id TEXT,
    position_count INTEGER NOT NULL,
    order_status_count INTEGER NOT NULL,
    symbol_count INTEGER,
    submit_orders INTEGER,
    restore_positions INTEGER,
    execute_stop_replacements INTEGER,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_timestamp
    ON position_snapshots(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_leader_timestamp
    ON position_snapshots(leader_symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    decision_id TEXT,
    intent_id TEXT,
    wallet_balance TEXT,
    available_balance TEXT,
    equity TEXT,
    unrealized_pnl TEXT,
    position_count INTEGER NOT NULL,
    open_order_count INTEGER NOT NULL,
    leader_symbol TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_snapshots_timestamp
    ON account_snapshots(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_account_snapshots_leader_timestamp
    ON account_snapshots(leader_symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS notification_statuses (
    status_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_state (
    id INTEGER PRIMARY KEY,
    payload_json TEXT NOT NULL
);
"""


@contextmanager
def _connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        yield connection
        connection.commit()
    finally:
        connection.close()


def _ensure_columns(*, connection: sqlite3.Connection, table_name: str, column_definitions: tuple[str, ...]) -> None:
    existing_columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}
    for column_definition in column_definitions:
        column_name = column_definition.split()[0]
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")


def _migrate_runtime_db(connection: sqlite3.Connection) -> None:
    columns_by_table = {
        "audit_events": ("decision_id TEXT", "intent_id TEXT"),
        "signal_decisions": ("decision_id TEXT", "intent_id TEXT"),
        "broker_orders": ("client_algo_id TEXT", "decision_id TEXT", "intent_id TEXT"),
        "trade_fills": ("decision_id TEXT", "intent_id TEXT"),
        "algo_orders": ("decision_id TEXT", "intent_id TEXT"),
        "position_snapshots": ("decision_id TEXT", "intent_id TEXT"),
        "account_snapshots": ("decision_id TEXT", "intent_id TEXT"),
    }
    for table_name, column_definitions in columns_by_table.items():
        _ensure_columns(connection=connection, table_name=table_name, column_definitions=column_definitions)

    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_decision_id
            ON audit_events(decision_id);
        CREATE INDEX IF NOT EXISTS idx_audit_events_intent_id
            ON audit_events(intent_id);

        CREATE INDEX IF NOT EXISTS idx_signal_decisions_decision_id
            ON signal_decisions(decision_id);
        CREATE INDEX IF NOT EXISTS idx_signal_decisions_intent_id
            ON signal_decisions(intent_id);

        CREATE INDEX IF NOT EXISTS idx_broker_orders_decision_id
            ON broker_orders(decision_id);
        CREATE INDEX IF NOT EXISTS idx_broker_orders_intent_id
            ON broker_orders(intent_id);
        CREATE INDEX IF NOT EXISTS idx_broker_orders_client_order_id
            ON broker_orders(client_order_id);
        CREATE INDEX IF NOT EXISTS idx_broker_orders_client_algo_id
            ON broker_orders(client_algo_id);

        CREATE INDEX IF NOT EXISTS idx_trade_fills_decision_id
            ON trade_fills(decision_id);
        CREATE INDEX IF NOT EXISTS idx_trade_fills_intent_id
            ON trade_fills(intent_id);
        CREATE INDEX IF NOT EXISTS idx_trade_fills_client_order_id
            ON trade_fills(client_order_id);

        CREATE INDEX IF NOT EXISTS idx_algo_orders_decision_id
            ON algo_orders(decision_id);
        CREATE INDEX IF NOT EXISTS idx_algo_orders_intent_id
            ON algo_orders(intent_id);
        CREATE INDEX IF NOT EXISTS idx_algo_orders_client_algo_id
            ON algo_orders(client_algo_id);

        CREATE INDEX IF NOT EXISTS idx_position_snapshots_decision_id
            ON position_snapshots(decision_id);
        CREATE INDEX IF NOT EXISTS idx_position_snapshots_intent_id
            ON position_snapshots(intent_id);

        CREATE INDEX IF NOT EXISTS idx_account_snapshots_decision_id
            ON account_snapshots(decision_id);
        CREATE INDEX IF NOT EXISTS idx_account_snapshots_intent_id
            ON account_snapshots(intent_id);
        """
    )


def bootstrap_runtime_db(*, path: Path) -> None:
    with _connect(path) as connection:
        connection.executescript(SCHEMA)
        _migrate_runtime_db(connection)
