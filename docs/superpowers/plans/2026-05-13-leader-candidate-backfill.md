# Leader Candidate Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local sidecar analytics database at `local_analytics/leader_candidates.db` that can be populated from existing runtime snapshots and Binance historical klines.

**Architecture:** Keep production runtime data and local analytics data separate. `var/runtime.db` remains a replaceable server mirror; the new analytics modules own schema, reads, and writes for `local_analytics/leader_candidates.db`. CLI backfill commands read runtime data or Binance klines and write ranked top-N rows into the sidecar database.

**Tech Stack:** Python 3.12, stdlib `sqlite3`, stdlib `unittest`, existing Binance REST client, existing CLI command dispatch.

---

## File Structure

- Modify: `.gitignore`
  - Add `local_analytics/` so generated sidecar databases are never committed.
- Create: `src/momentum_alpha/analytics_schema.py`
  - Bootstrap and connect to the sidecar analytics database.
- Create: `src/momentum_alpha/analytics_writes_candidates.py`
  - Bulk upsert leader candidate rows with deterministic source precedence.
- Create: `src/momentum_alpha/analytics_reads_candidates.py`
  - Read candidate rows for tests and future diagnostics.
- Create: `src/momentum_alpha/cli_backfill_candidates.py`
  - Replay candidate rows from `var/runtime.db`.
  - Reconstruct leader candidates from Binance klines.
- Modify: `src/momentum_alpha/cli_parser.py`
  - Add `backfill-leader-candidates`.
- Modify: `src/momentum_alpha/cli_commands_ops.py`
  - Add command handler for replay and kline modes.
- Modify: `src/momentum_alpha/cli_commands.py`
  - Pass backfill function through command dispatch.
- Modify: `src/momentum_alpha/cli.py`
  - Import and expose the new backfill function for injectable CLI tests.
- Create: `tests/test_analytics_candidates.py`
  - Schema, write/read, replay, and kline reconstruction tests.
- Modify: `tests/test_cli.py`
  - Export smoke test for the new module.
- Modify: `tests/test_main.py`
  - CLI parser and command dispatch tests.

## Task 1: Sidecar Schema And Candidate Persistence

**Files:**
- Modify: `.gitignore`
- Create: `src/momentum_alpha/analytics_schema.py`
- Create: `src/momentum_alpha/analytics_writes_candidates.py`
- Create: `src/momentum_alpha/analytics_reads_candidates.py`
- Create: `tests/test_analytics_candidates.py`

- [ ] **Step 1: Add failing schema and persistence tests**

Create `tests/test_analytics_candidates.py` with:

```python
import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class AnalyticsCandidateTests(unittest.TestCase):
    def test_bootstrap_creates_leader_candidate_table_and_indexes(self) -> None:
        from momentum_alpha.analytics_schema import bootstrap_leader_candidates_db

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            bootstrap_leader_candidates_db(path=db_path)

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
                indexes = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
                    )
                }
            finally:
                connection.close()

        self.assertIn("leader_candidate_snapshots", tables)
        self.assertIn("idx_leader_candidate_snapshots_unique", indexes)
        self.assertIn("idx_leader_candidate_snapshots_rank_time", indexes)
        self.assertIn("idx_leader_candidate_snapshots_symbol_time", indexes)

    def test_insert_and_fetch_leader_candidate_snapshots(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.analytics_writes_candidates import insert_leader_candidate_snapshots_bulk

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            timestamp = datetime(2026, 5, 1, 1, 5, tzinfo=timezone.utc)
            inserted = insert_leader_candidate_snapshots_bulk(
                path=db_path,
                rows=[
                    {
                        "timestamp": timestamp,
                        "source": "position-snapshot-replay",
                        "symbol": "AAAUSDT",
                        "rank": 1,
                        "daily_open_price": "100",
                        "latest_price": "112",
                        "daily_change_pct": "0.12",
                        "previous_hour_low": "105",
                        "current_hour_low": "108",
                        "leader_gap_pct": "0.03",
                        "payload": {"symbol": "AAAUSDT", "rank": 1},
                    },
                    {
                        "timestamp": timestamp,
                        "source": "position-snapshot-replay",
                        "symbol": "BBBUSDT",
                        "rank": 2,
                        "daily_open_price": "200",
                        "latest_price": "218",
                        "daily_change_pct": "0.09",
                        "previous_hour_low": "210",
                        "current_hour_low": "214",
                        "leader_gap_pct": None,
                        "payload": {"symbol": "BBBUSDT", "rank": 2},
                    },
                ],
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=db_path,
                window_start=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 1, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 2)
        self.assertEqual([row["symbol"] for row in rows], ["AAAUSDT", "BBBUSDT"])
        self.assertEqual(rows[0]["source"], "position-snapshot-replay")
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["payload"]["symbol"], "AAAUSDT")

    def test_kline_backfill_rows_replace_replay_rows_but_replay_does_not_replace_kline_rows(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.analytics_writes_candidates import insert_leader_candidate_snapshots_bulk

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            timestamp = datetime(2026, 5, 1, 1, 5, tzinfo=timezone.utc)
            base_row = {
                "timestamp": timestamp,
                "symbol": "AAAUSDT",
                "rank": 1,
                "daily_open_price": "100",
                "latest_price": "112",
                "daily_change_pct": "0.12",
                "previous_hour_low": "105",
                "current_hour_low": "108",
                "leader_gap_pct": "0.03",
                "payload": {},
            }
            insert_leader_candidate_snapshots_bulk(
                path=db_path,
                rows=[{**base_row, "source": "position-snapshot-replay", "latest_price": "112"}],
            )
            insert_leader_candidate_snapshots_bulk(
                path=db_path,
                rows=[{**base_row, "source": "kline-backfill", "latest_price": "113"}],
            )
            insert_leader_candidate_snapshots_bulk(
                path=db_path,
                rows=[{**base_row, "source": "position-snapshot-replay", "latest_price": "111"}],
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=db_path,
                window_start=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 1, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "kline-backfill")
        self.assertEqual(rows[0]["latest_price"], "113")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_analytics_candidates -v
```

Expected: fail with `ModuleNotFoundError: No module named 'momentum_alpha.analytics_schema'`.

- [ ] **Step 3: Add `.gitignore` coverage**

Append this line to `.gitignore`:

```gitignore
local_analytics/
```

- [ ] **Step 4: Create `analytics_schema.py`**

Create `src/momentum_alpha/analytics_schema.py`:

```python
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
```

- [ ] **Step 5: Create `analytics_writes_candidates.py`**

Create `src/momentum_alpha/analytics_writes_candidates.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from momentum_alpha.analytics_schema import bootstrap_leader_candidates_db, connect_leader_candidates_db


def _as_utc_iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def _text_or_none(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _json_dumps(value: dict | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def insert_leader_candidate_snapshots_bulk(*, path: Path, rows: Iterable[dict]) -> int:
    materialized_rows = list(rows)
    if not materialized_rows:
        bootstrap_leader_candidates_db(path=path)
        return 0
    bootstrap_leader_candidates_db(path=path)
    inserted = 0
    with connect_leader_candidates_db(path) as connection:
        for row in materialized_rows:
            connection.execute(
                """
                INSERT INTO leader_candidate_snapshots(
                    timestamp,
                    source,
                    symbol,
                    rank,
                    daily_open_price,
                    latest_price,
                    daily_change_pct,
                    previous_hour_low,
                    current_hour_low,
                    leader_gap_pct,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(timestamp, symbol) DO UPDATE SET
                    source = excluded.source,
                    rank = excluded.rank,
                    daily_open_price = excluded.daily_open_price,
                    latest_price = excluded.latest_price,
                    daily_change_pct = excluded.daily_change_pct,
                    previous_hour_low = excluded.previous_hour_low,
                    current_hour_low = excluded.current_hour_low,
                    leader_gap_pct = excluded.leader_gap_pct,
                    payload_json = excluded.payload_json
                WHERE excluded.source = 'kline-backfill'
                   OR leader_candidate_snapshots.source != 'kline-backfill'
                """,
                (
                    _as_utc_iso(row["timestamp"]),
                    str(row["source"]),
                    str(row["symbol"]).upper(),
                    int(row["rank"]),
                    _text_or_none(row.get("daily_open_price")),
                    _text_or_none(row.get("latest_price")),
                    _text_or_none(row.get("daily_change_pct")),
                    _text_or_none(row.get("previous_hour_low")),
                    _text_or_none(row.get("current_hour_low")),
                    _text_or_none(row.get("leader_gap_pct")),
                    _json_dumps(row.get("payload")),
                ),
            )
            if connection.total_changes > inserted:
                inserted += 1
    return inserted
```

- [ ] **Step 6: Create `analytics_reads_candidates.py`**

Create `src/momentum_alpha/analytics_reads_candidates.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from momentum_alpha.analytics_schema import connect_leader_candidates_db


def _as_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _json_loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _row_to_dict(row) -> dict:
    return {
        "timestamp": row[0],
        "source": row[1],
        "symbol": row[2],
        "rank": row[3],
        "daily_open_price": row[4],
        "latest_price": row[5],
        "daily_change_pct": row[6],
        "previous_hour_low": row[7],
        "current_hour_low": row[8],
        "leader_gap_pct": row[9],
        "payload": _json_loads(row[10]),
    }


def fetch_leader_candidate_snapshots_for_window(
    *,
    path: Path,
    window_start: datetime,
    window_end: datetime,
) -> list[dict]:
    if not path.exists():
        return []
    with connect_leader_candidates_db(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                symbol,
                rank,
                daily_open_price,
                latest_price,
                daily_change_pct,
                previous_hour_low,
                current_hour_low,
                leader_gap_pct,
                payload_json
            FROM leader_candidate_snapshots
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC, rank ASC, symbol ASC
            """,
            (_as_utc_iso(window_start), _as_utc_iso(window_end)),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def fetch_top_leader_candidates_for_window(
    *,
    path: Path,
    window_start: datetime,
    window_end: datetime,
    top_n: int,
) -> list[dict]:
    if not path.exists():
        return []
    with connect_leader_candidates_db(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                symbol,
                rank,
                daily_open_price,
                latest_price,
                daily_change_pct,
                previous_hour_low,
                current_hour_low,
                leader_gap_pct,
                payload_json
            FROM leader_candidate_snapshots
            WHERE timestamp >= ? AND timestamp < ? AND rank <= ?
            ORDER BY timestamp ASC, rank ASC, symbol ASC
            """,
            (_as_utc_iso(window_start), _as_utc_iso(window_end), top_n),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]
```

- [ ] **Step 7: Run tests to verify persistence passes**

Run:

```bash
python3 -m unittest tests.test_analytics_candidates -v
```

Expected: pass all tests in `AnalyticsCandidateTests`.

- [ ] **Step 8: Commit**

```bash
git add .gitignore src/momentum_alpha/analytics_schema.py src/momentum_alpha/analytics_writes_candidates.py src/momentum_alpha/analytics_reads_candidates.py tests/test_analytics_candidates.py
git commit -m "feat: add leader candidate analytics store"
```

## Task 2: Replay Existing Runtime Position Snapshot Candidates

**Files:**
- Modify: `src/momentum_alpha/cli_backfill_candidates.py`
- Modify: `tests/test_analytics_candidates.py`

- [ ] **Step 1: Add failing replay tests**

Append to `AnalyticsCandidateTests` in `tests/test_analytics_candidates.py`:

```python
    def test_replay_position_snapshot_candidates_expands_runtime_candidates(self) -> None:
        from momentum_alpha.cli_backfill_candidates import replay_position_snapshot_candidates
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.runtime_store import insert_position_snapshot

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            analytics_db_path = Path(tmpdir) / "leader_candidates.db"
            timestamp = datetime(2026, 5, 1, 1, 5, tzinfo=timezone.utc)
            insert_position_snapshot(
                path=runtime_db_path,
                timestamp=timestamp,
                source="poll",
                leader_symbol="AAAUSDT",
                position_count=0,
                order_status_count=0,
                payload={
                    "market_context": {
                        "leader_symbol": "AAAUSDT",
                        "leader_gap_pct": "0.03",
                        "candidates": [
                            {
                                "symbol": "AAAUSDT",
                                "daily_open_price": "100",
                                "latest_price": "112",
                                "daily_change_pct": "0.12",
                                "previous_hour_low": "105",
                                "current_hour_low": "108",
                                "leader_gap_pct": "0.03",
                            },
                            {
                                "symbol": "BBBUSDT",
                                "daily_open_price": "200",
                                "latest_price": "218",
                                "daily_change_pct": "0.09",
                                "previous_hour_low": "210",
                                "current_hour_low": "214",
                            },
                        ],
                    }
                },
            )

            inserted = replay_position_snapshot_candidates(
                runtime_db_path=runtime_db_path,
                leader_candidates_db_path=analytics_db_path,
                logger=lambda message: None,
            )
            inserted_again = replay_position_snapshot_candidates(
                runtime_db_path=runtime_db_path,
                leader_candidates_db_path=analytics_db_path,
                logger=lambda message: None,
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=analytics_db_path,
                window_start=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 1, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 2)
        self.assertEqual(inserted_again, 2)
        self.assertEqual([(row["symbol"], row["rank"]) for row in rows], [("AAAUSDT", 1), ("BBBUSDT", 2)])
        self.assertEqual(rows[0]["source"], "position-snapshot-replay")
        self.assertEqual(rows[0]["leader_gap_pct"], "0.03")

    def test_replay_position_snapshot_candidates_skips_malformed_candidates(self) -> None:
        from momentum_alpha.cli_backfill_candidates import replay_position_snapshot_candidates
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.runtime_store import insert_position_snapshot

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            analytics_db_path = Path(tmpdir) / "leader_candidates.db"
            timestamp = datetime(2026, 5, 1, 1, 5, tzinfo=timezone.utc)
            insert_position_snapshot(
                path=runtime_db_path,
                timestamp=timestamp,
                source="poll",
                leader_symbol="AAAUSDT",
                position_count=0,
                order_status_count=0,
                payload={"market_context": {"candidates": [{"latest_price": "112"}, {"symbol": "AAAUSDT", "latest_price": "112"}]}},
            )

            inserted = replay_position_snapshot_candidates(
                runtime_db_path=runtime_db_path,
                leader_candidates_db_path=analytics_db_path,
                logger=lambda message: None,
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=analytics_db_path,
                window_start=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 1, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 1)
        self.assertEqual([row["symbol"] for row in rows], ["AAAUSDT"])
```

- [ ] **Step 2: Run replay tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_analytics_candidates.AnalyticsCandidateTests.test_replay_position_snapshot_candidates_expands_runtime_candidates tests.test_analytics_candidates.AnalyticsCandidateTests.test_replay_position_snapshot_candidates_skips_malformed_candidates -v
```

Expected: fail with `ModuleNotFoundError: No module named 'momentum_alpha.cli_backfill_candidates'`.

- [ ] **Step 3: Create replay implementation**

Create `src/momentum_alpha/cli_backfill_candidates.py` with the replay code:

```python
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from momentum_alpha.analytics_writes_candidates import insert_leader_candidate_snapshots_bulk


DEFAULT_LEADER_CANDIDATES_DB_PATH = Path("local_analytics/leader_candidates.db")


def _json_loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _candidate_row_from_replay(*, timestamp: str, rank: int, candidate: dict) -> dict | None:
    symbol = candidate.get("symbol")
    if symbol in (None, ""):
        return None
    return {
        "timestamp": timestamp,
        "source": "position-snapshot-replay",
        "symbol": str(symbol).upper(),
        "rank": rank,
        "daily_open_price": candidate.get("daily_open_price"),
        "latest_price": candidate.get("latest_price"),
        "daily_change_pct": candidate.get("daily_change_pct"),
        "previous_hour_low": candidate.get("previous_hour_low"),
        "current_hour_low": candidate.get("current_hour_low"),
        "leader_gap_pct": candidate.get("leader_gap_pct"),
        "payload": dict(candidate),
    }


def replay_position_snapshot_candidates(
    *,
    runtime_db_path: Path,
    leader_candidates_db_path: Path,
    logger=print,
) -> int:
    if not runtime_db_path.exists():
        logger(f"leader-candidate-replay runtime_db_missing path={runtime_db_path}")
        return 0
    connection = sqlite3.connect(runtime_db_path)
    try:
        rows = connection.execute(
            """
            SELECT timestamp, payload_json
            FROM position_snapshots
            WHERE json_type(payload_json, '$.market_context.candidates') IS NOT NULL
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
    finally:
        connection.close()

    candidate_rows: list[dict] = []
    for timestamp, payload_json in rows:
        payload = _json_loads(payload_json)
        candidates = ((payload.get("market_context") or {}).get("candidates") or [])
        if not isinstance(candidates, list):
            continue
        for rank, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                continue
            candidate_row = _candidate_row_from_replay(timestamp=timestamp, rank=rank, candidate=candidate)
            if candidate_row is not None:
                candidate_rows.append(candidate_row)

    inserted = insert_leader_candidate_snapshots_bulk(path=leader_candidates_db_path, rows=candidate_rows)
    logger(
        "leader-candidate-replay "
        f"runtime_db={runtime_db_path} analytics_db={leader_candidates_db_path} "
        f"snapshots={len(rows)} candidates={len(candidate_rows)} inserted={inserted}"
    )
    return inserted
```

The `Decimal`, `datetime`, `timedelta`, and `timezone` imports are used by Task 3, so keep them in the file.

- [ ] **Step 4: Run replay tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_analytics_candidates.AnalyticsCandidateTests.test_replay_position_snapshot_candidates_expands_runtime_candidates tests.test_analytics_candidates.AnalyticsCandidateTests.test_replay_position_snapshot_candidates_skips_malformed_candidates -v
```

Expected: pass both replay tests.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/cli_backfill_candidates.py tests/test_analytics_candidates.py
git commit -m "feat: replay leader candidates from runtime snapshots"
```

## Task 3: Kline-Based Historical Leader Candidate Reconstruction

**Files:**
- Modify: `src/momentum_alpha/cli_backfill_candidates.py`
- Modify: `tests/test_analytics_candidates.py`

- [ ] **Step 1: Add failing kline reconstruction tests**

Append to `AnalyticsCandidateTests`:

```python
    def test_backfill_leader_candidates_from_klines_ranks_top_n(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.cli_backfill_candidates import backfill_leader_candidates_from_klines

        class FakeClient:
            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                self.calls.append((symbol, interval, limit, start_time_ms, end_time_ms))
                data = {
                    "AAAUSDT": [
                        [1777593600000, "100", "102", "99", "100", "1"],
                        [1777593900000, "100", "112", "100", "111", "1"],
                        [1777594200000, "111", "115", "109", "114", "1"],
                    ],
                    "BBBUSDT": [
                        [1777593600000, "200", "202", "198", "200", "1"],
                        [1777593900000, "200", "225", "199", "224", "1"],
                        [1777594200000, "218", "219", "213", "214", "1"],
                    ],
                    "CCCUSDT": [
                        [1777593600000, "50", "51", "49", "50", "1"],
                        [1777593900000, "50", "52", "50", "52", "1"],
                        [1777594200000, "52", "53", "51", "53", "1"],
                    ],
                }
                return data[symbol]

            def __init__(self):
                self.calls = []

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            client = FakeClient()
            inserted = backfill_leader_candidates_from_klines(
                client=client,
                leader_candidates_db_path=db_path,
                start_time=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 5, 1, 0, 15, tzinfo=timezone.utc),
                symbols=["AAAUSDT", "BBBUSDT", "CCCUSDT"],
                interval="5m",
                top_n=2,
                logger=lambda message: None,
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=db_path,
                window_start=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 0, 15, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 6)
        by_timestamp = {}
        for row in rows:
            by_timestamp.setdefault(row["timestamp"], []).append(row)
        self.assertEqual(len(by_timestamp), 3)
        second_snapshot = by_timestamp["2026-05-01T00:05:00+00:00"]
        self.assertEqual([(row["symbol"], row["rank"]) for row in second_snapshot], [("BBBUSDT", 1), ("AAAUSDT", 2)])
        self.assertEqual(second_snapshot[0]["daily_change_pct"], "0.12")
        self.assertEqual(second_snapshot[0]["leader_gap_pct"], "0.01")
        self.assertEqual(second_snapshot[0]["previous_hour_low"], None)
        self.assertEqual(second_snapshot[0]["current_hour_low"], "198")

    def test_backfill_leader_candidates_from_klines_continues_after_symbol_failure(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.cli_backfill_candidates import backfill_leader_candidates_from_klines

        class PartialClient:
            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if symbol == "BADUSDT":
                    raise RuntimeError("fetch failed")
                return [
                    [1777593600000, "100", "102", "99", "100", "1"],
                    [1777593900000, "100", "112", "100", "112", "1"],
                ]

        messages = []
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            inserted = backfill_leader_candidates_from_klines(
                client=PartialClient(),
                leader_candidates_db_path=db_path,
                start_time=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 5, 1, 0, 10, tzinfo=timezone.utc),
                symbols=["BADUSDT", "AAAUSDT"],
                interval="5m",
                top_n=5,
                logger=messages.append,
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=db_path,
                window_start=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 0, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 2)
        self.assertEqual({row["symbol"] for row in rows}, {"AAAUSDT"})
        self.assertTrue(any("failed_symbols=1" in message for message in messages))
```

- [ ] **Step 2: Run kline tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_analytics_candidates.AnalyticsCandidateTests.test_backfill_leader_candidates_from_klines_ranks_top_n tests.test_analytics_candidates.AnalyticsCandidateTests.test_backfill_leader_candidates_from_klines_continues_after_symbol_failure -v
```

Expected: fail with `ImportError` for `backfill_leader_candidates_from_klines`.

- [ ] **Step 3: Add kline helper functions and reconstruction**

Append this implementation to `src/momentum_alpha/cli_backfill_candidates.py`:

```python

_INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
}


def _timestamp_ms(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


def _datetime_from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _fetch_symbol_klines(
    *,
    client,
    symbol: str,
    interval: str,
    start_time: datetime,
    end_time: datetime,
) -> list[list]:
    return client.fetch_klines(
        symbol=symbol,
        interval=interval,
        limit=1500,
        start_time_ms=_timestamp_ms(start_time),
        end_time_ms=_timestamp_ms(end_time),
    )


def _rows_for_symbol_klines(*, symbol: str, klines: list[list]) -> list[dict]:
    parsed = sorted(klines, key=lambda item: int(item[0]))
    if not parsed:
        return []
    daily_open_price = Decimal(str(parsed[0][1]))
    current_hour_start: datetime | None = None
    current_hour_low: Decimal | None = None
    completed_hour_lows: dict[datetime, Decimal] = {}
    rows: list[dict] = []

    for item in parsed:
        timestamp = _datetime_from_ms(int(item[0]))
        hour_start = datetime(timestamp.year, timestamp.month, timestamp.day, timestamp.hour, tzinfo=timezone.utc)
        low_price = Decimal(str(item[3]))
        close_price = Decimal(str(item[4]))
        if current_hour_start is None:
            current_hour_start = hour_start
            current_hour_low = low_price
        elif hour_start != current_hour_start:
            if current_hour_low is not None:
                completed_hour_lows[current_hour_start] = current_hour_low
            current_hour_start = hour_start
            current_hour_low = low_price
        else:
            current_hour_low = low_price if current_hour_low is None else min(current_hour_low, low_price)

        previous_hour_low = completed_hour_lows.get(hour_start - timedelta(hours=1))
        daily_change_pct = (close_price - daily_open_price) / daily_open_price if daily_open_price > 0 else Decimal("0")
        rows.append(
            {
                "timestamp": timestamp,
                "symbol": symbol,
                "daily_open_price": daily_open_price,
                "latest_price": close_price,
                "daily_change_pct": daily_change_pct,
                "previous_hour_low": previous_hour_low,
                "current_hour_low": current_hour_low,
            }
        )
    return rows


def _rank_candidate_rows(*, symbol_rows: list[dict], top_n: int) -> list[dict]:
    by_timestamp: dict[datetime, list[dict]] = {}
    for row in symbol_rows:
        by_timestamp.setdefault(row["timestamp"], []).append(row)

    ranked_rows: list[dict] = []
    for timestamp in sorted(by_timestamp):
        ordered = sorted(
            by_timestamp[timestamp],
            key=lambda item: (-item["daily_change_pct"], item["symbol"]),
        )[:top_n]
        leader_gap_pct = None
        if len(ordered) >= 2:
            leader_gap_pct = ordered[0]["daily_change_pct"] - ordered[1]["daily_change_pct"]
        for rank, row in enumerate(ordered, start=1):
            ranked_rows.append(
                {
                    "timestamp": timestamp,
                    "source": "kline-backfill",
                    "symbol": row["symbol"],
                    "rank": rank,
                    "daily_open_price": _decimal_text(row["daily_open_price"]),
                    "latest_price": _decimal_text(row["latest_price"]),
                    "daily_change_pct": _decimal_text(row["daily_change_pct"]),
                    "previous_hour_low": _decimal_text(row["previous_hour_low"]),
                    "current_hour_low": _decimal_text(row["current_hour_low"]),
                    "leader_gap_pct": _decimal_text(leader_gap_pct) if rank == 1 else None,
                    "payload": {
                        "symbol": row["symbol"],
                        "rank": rank,
                        "interval_source": "kline",
                    },
                }
            )
    return ranked_rows


def backfill_leader_candidates_from_klines(
    *,
    client,
    leader_candidates_db_path: Path,
    start_time: datetime,
    end_time: datetime,
    symbols: list[str] | tuple[str, ...],
    interval: str = "5m",
    top_n: int = 50,
    logger=print,
) -> int:
    if interval not in _INTERVAL_SECONDS:
        raise ValueError(f"unsupported interval: {interval}")
    normalized_symbols = sorted({symbol.upper() for symbol in symbols if symbol})
    symbol_rows: list[dict] = []
    failed_symbols: list[str] = []
    for symbol in normalized_symbols:
        try:
            klines = _fetch_symbol_klines(
                client=client,
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception:
            failed_symbols.append(symbol)
            continue
        symbol_rows.extend(_rows_for_symbol_klines(symbol=symbol, klines=klines))
    ranked_rows = _rank_candidate_rows(symbol_rows=symbol_rows, top_n=top_n)
    inserted = insert_leader_candidate_snapshots_bulk(path=leader_candidates_db_path, rows=ranked_rows)
    logger(
        "leader-candidate-kline-backfill "
        f"analytics_db={leader_candidates_db_path} symbols={len(normalized_symbols)} "
        f"failed_symbols={len(failed_symbols)} candidates={len(ranked_rows)} inserted={inserted}"
    )
    return inserted
```

- [ ] **Step 4: Run kline tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_analytics_candidates.AnalyticsCandidateTests.test_backfill_leader_candidates_from_klines_ranks_top_n tests.test_analytics_candidates.AnalyticsCandidateTests.test_backfill_leader_candidates_from_klines_continues_after_symbol_failure -v
```

Expected: pass both kline tests.

- [ ] **Step 5: Run all analytics candidate tests**

Run:

```bash
python3 -m unittest tests.test_analytics_candidates -v
```

Expected: pass all analytics candidate tests.

- [ ] **Step 6: Commit**

```bash
git add src/momentum_alpha/cli_backfill_candidates.py tests/test_analytics_candidates.py
git commit -m "feat: backfill leader candidates from klines"
```

## Task 4: CLI Parser And Command Dispatch

**Files:**
- Modify: `src/momentum_alpha/cli_parser.py`
- Modify: `src/momentum_alpha/cli_commands_ops.py`
- Modify: `src/momentum_alpha/cli_commands.py`
- Modify: `src/momentum_alpha/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add failing CLI tests**

Append to `tests/test_main.py` inside the existing test class:

```python
    def test_cli_main_replays_leader_candidates_to_sidecar_db(self) -> None:
        from momentum_alpha.main import cli_main

        calls = []

        def fake_backfill_leader_candidates(**kwargs):
            calls.append(kwargs)
            return 7

        exit_code = cli_main(
            argv=[
                "backfill-leader-candidates",
                "--runtime-db-file",
                "/tmp/runtime.db",
                "--leader-candidates-db-file",
                "/tmp/leader_candidates.db",
                "--replay-position-snapshots",
            ],
            backfill_leader_candidates_fn=fake_backfill_leader_candidates,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(str(calls[0]["runtime_db_path"]), "/tmp/runtime.db")
        self.assertEqual(str(calls[0]["leader_candidates_db_path"]), "/tmp/leader_candidates.db")
        self.assertTrue(calls[0]["replay_position_snapshots"])

    def test_cli_main_backfills_leader_candidates_from_klines(self) -> None:
        from momentum_alpha.main import cli_main

        calls = []

        class FakeClient:
            pass

        def fake_client_factory(*, testnet=False):
            return FakeClient()

        def fake_backfill_leader_candidates(**kwargs):
            calls.append(kwargs)
            return 11

        exit_code = cli_main(
            argv=[
                "backfill-leader-candidates",
                "--leader-candidates-db-file",
                "/tmp/leader_candidates.db",
                "--start-time",
                "2026-05-01T00:00:00+00:00",
                "--end-time",
                "2026-05-01T01:00:00+00:00",
                "--interval",
                "5m",
                "--top-n",
                "25",
                "--symbols",
                "AAAUSDT",
                "BBBUSDT",
            ],
            client_factory=fake_client_factory,
            backfill_leader_candidates_fn=fake_backfill_leader_candidates,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIsInstance(calls[0]["client"], FakeClient)
        self.assertEqual(str(calls[0]["leader_candidates_db_path"]), "/tmp/leader_candidates.db")
        self.assertEqual(calls[0]["interval"], "5m")
        self.assertEqual(calls[0]["top_n"], 25)
        self.assertEqual(calls[0]["symbols"], ["AAAUSDT", "BBBUSDT"])
```

Extend `tests/test_cli.py` export smoke test:

```python
        self.assertTrue(callable(cli_backfill.backfill_account_flows))
        from momentum_alpha import cli_backfill_candidates
        self.assertTrue(callable(cli_backfill_candidates.backfill_leader_candidates))
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_main.MainTests.test_cli_main_replays_leader_candidates_to_sidecar_db tests.test_main.MainTests.test_cli_main_backfills_leader_candidates_from_klines tests.test_cli -v
```

Expected: fail because `cli_main()` does not accept `backfill_leader_candidates_fn` and parser does not know `backfill-leader-candidates`.

- [ ] **Step 3: Add wrapper function in `cli_backfill_candidates.py`**

Append:

```python

def backfill_leader_candidates(
    *,
    leader_candidates_db_path: Path,
    runtime_db_path: Path | None = None,
    replay_position_snapshots: bool = False,
    client=None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    symbols: list[str] | tuple[str, ...] | None = None,
    interval: str = "5m",
    top_n: int = 50,
    logger=print,
) -> int:
    if replay_position_snapshots:
        if runtime_db_path is None:
            raise ValueError("runtime_db_path is required for replay")
        return replay_position_snapshot_candidates(
            runtime_db_path=runtime_db_path,
            leader_candidates_db_path=leader_candidates_db_path,
            logger=logger,
        )
    if client is None:
        raise ValueError("client is required for kline backfill")
    if start_time is None or end_time is None:
        raise ValueError("start_time and end_time are required for kline backfill")
    if not symbols:
        symbols = _resolve_backfill_symbols(client=client)
    return backfill_leader_candidates_from_klines(
        client=client,
        leader_candidates_db_path=leader_candidates_db_path,
        start_time=start_time,
        end_time=end_time,
        symbols=list(symbols),
        interval=interval,
        top_n=top_n,
        logger=logger,
    )


def _resolve_backfill_symbols(*, client) -> list[str]:
    from momentum_alpha.exchange_info import parse_exchange_info

    return sorted(parse_exchange_info(client.fetch_exchange_info()))
```

- [ ] **Step 4: Update `cli_parser.py`**

Add after `backfill_binance_trades_parser`:

```python
    backfill_leader_candidates_parser = subparsers.add_parser("backfill-leader-candidates")
    backfill_leader_candidates_parser.add_argument("--runtime-db-file")
    backfill_leader_candidates_parser.add_argument(
        "--leader-candidates-db-file",
        default="./local_analytics/leader_candidates.db",
    )
    backfill_leader_candidates_parser.add_argument("--start-time")
    backfill_leader_candidates_parser.add_argument("--end-time")
    backfill_leader_candidates_parser.add_argument("--symbols", nargs="+")
    backfill_leader_candidates_parser.add_argument("--interval", default="5m")
    backfill_leader_candidates_parser.add_argument("--top-n", type=int, default=50)
    backfill_leader_candidates_parser.add_argument("--testnet", action="store_true")
    backfill_leader_candidates_parser.add_argument("--replay-position-snapshots", action="store_true")
```

- [ ] **Step 5: Update `cli_commands_ops.py`**

Import the wrapper:

```python
from .cli_backfill_candidates import backfill_leader_candidates
```

Add command function:

```python
def backfill_leader_candidates_command(
    *,
    parser,
    args,
    client_factory,
    backfill_leader_candidates_fn=backfill_leader_candidates,
) -> int:
    runtime_settings = load_runtime_settings_from_env()
    use_testnet = args.testnet or runtime_settings["use_testnet"]
    client = None
    start_time = None
    end_time = None
    if not args.replay_position_snapshots:
        client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
        if args.start_time is None or args.end_time is None:
            parser.error("backfill-leader-candidates requires --start-time and --end-time unless --replay-position-snapshots is set")
        start_time = _parse_cli_datetime(args.start_time)
        end_time = _parse_cli_datetime(args.end_time)
    inserted = backfill_leader_candidates_fn(
        runtime_db_path=Path(os.path.abspath(args.runtime_db_file)) if args.runtime_db_file else None,
        leader_candidates_db_path=Path(os.path.abspath(args.leader_candidates_db_file)),
        replay_position_snapshots=args.replay_position_snapshots,
        client=client,
        start_time=start_time,
        end_time=end_time,
        symbols=args.symbols,
        interval=args.interval,
        top_n=args.top_n,
        logger=print,
    )
    print(f"backfilled_leader_candidates={inserted}")
    return 0
```

Add parameter to `run_ops_commands()`:

```python
    backfill_leader_candidates_fn=backfill_leader_candidates,
```

Add dispatch before `rebuild-trade-analytics`:

```python
    if args.command == "backfill-leader-candidates":
        return backfill_leader_candidates_command(
            parser=parser,
            args=args,
            client_factory=client_factory,
            backfill_leader_candidates_fn=backfill_leader_candidates_fn,
        )
```

- [ ] **Step 6: Update `cli_commands.py`**

Add `backfill_leader_candidates_fn` to `run_cli_command()` signature and `dispatch_kwargs`:

```python
    backfill_leader_candidates_fn,
```

```python
        "backfill_leader_candidates_fn": backfill_leader_candidates_fn,
```

- [ ] **Step 7: Update `cli.py`**

Import the wrapper:

```python
from .cli_backfill_candidates import backfill_leader_candidates
```

Add parameter to `cli_main()`:

```python
    backfill_leader_candidates_fn=None,
```

Initialize default:

```python
    backfill_leader_candidates_fn = backfill_leader_candidates_fn or backfill_leader_candidates
```

Pass through `run_cli_command()`:

```python
        backfill_leader_candidates_fn=backfill_leader_candidates_fn,
```

Add to `__all__`:

```python
    "backfill_leader_candidates",
```

- [ ] **Step 8: Run CLI tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_main.MainTests.test_cli_main_replays_leader_candidates_to_sidecar_db tests.test_main.MainTests.test_cli_main_backfills_leader_candidates_from_klines tests.test_cli -v
```

Expected: pass the new CLI tests and `tests.test_cli`.

- [ ] **Step 9: Commit**

```bash
git add src/momentum_alpha/cli_backfill_candidates.py src/momentum_alpha/cli_parser.py src/momentum_alpha/cli_commands_ops.py src/momentum_alpha/cli_commands.py src/momentum_alpha/cli.py tests/test_cli.py tests/test_main.py
git commit -m "feat: add leader candidate backfill cli"
```

## Task 5: Verification And Documentation Touch-Up

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a short README section**

Add under the existing backfill or dashboard operations section:

```markdown
## Local Leader Candidate Backfill

Leader candidate history is stored outside `var/` so local analytics survive replacing `var/` with a server copy.

Replay candidates already captured in runtime snapshots:

```bash
python3 -m momentum_alpha.main backfill-leader-candidates \
  --runtime-db-file ./var/runtime.db \
  --leader-candidates-db-file ./local_analytics/leader_candidates.db \
  --replay-position-snapshots
```

Rebuild ranked candidates from Binance historical klines:

```bash
python3 -m momentum_alpha.main backfill-leader-candidates \
  --leader-candidates-db-file ./local_analytics/leader_candidates.db \
  --start-time 2026-05-01T00:00:00+00:00 \
  --end-time 2026-05-02T00:00:00+00:00 \
  --interval 5m \
  --top-n 50
```
```

- [ ] **Step 2: Run targeted test suite**

Run:

```bash
python3 -m unittest tests.test_analytics_candidates tests.test_cli tests.test_main -v
```

Expected: pass all selected tests.

- [ ] **Step 3: Run full test suite**

Run:

```bash
python3 -m unittest
```

Expected: pass full test suite.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document leader candidate backfill"
```

## Self-Review

- Spec coverage: The plan covers the sidecar database, git ignore rule, replay from `var/runtime.db`, kline reconstruction, top-N persistence, idempotent source precedence, CLI integration, and local workflow documentation.
- Intentional deferral: optional server-side live persistence is not part of this implementation because the spec says to add it only after the local diagnostic workflow proves useful.
- Placeholder scan: no unresolved placeholder markers or unnamed implementation steps are present.
- Type consistency: paths use `Path`, timestamps use timezone-aware `datetime`, persisted decimal values use text, and CLI injection names match the planned dispatch signature.
