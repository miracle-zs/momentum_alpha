from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


LEADER_CANDIDATES_SCHEMA = """
CREATE TABLE IF NOT EXISTS leader_candidate_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    symbol TEXT NOT NULL,
    rank INTEGER NOT NULL,
    daily_open_price TEXT,
    latest_price TEXT,
    daily_change_pct TEXT,
    previous_hour_low TEXT,
    current_hour_low TEXT,
    leader_gap_pct TEXT,
    payload_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leader_candidate_snapshots_unique
    ON leader_candidate_snapshots(timestamp, symbol);
CREATE INDEX IF NOT EXISTS idx_leader_candidate_snapshots_rank_time
    ON leader_candidate_snapshots(rank, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_leader_candidate_snapshots_symbol_time
    ON leader_candidate_snapshots(symbol, timestamp DESC);
"""


@contextmanager
def connect_leader_candidates_db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        yield connection
        connection.commit()
    finally:
        connection.close()


def bootstrap_leader_candidates_db(*, path: Path) -> None:
    with connect_leader_candidates_db(path) as connection:
        connection.executescript(LEADER_CANDIDATES_SCHEMA)
