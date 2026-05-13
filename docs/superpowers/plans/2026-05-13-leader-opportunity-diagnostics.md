# Leader Opportunity Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `diagnose-opportunities` command that replays historical leader runs, matches them to runtime execution data, and writes a CSV review report under `local_analytics/`.

**Architecture:** Keep the opportunity engine in one focused module so the replay logic can be tested without the CLI. The CLI layer should only parse args, resolve paths, and forward to the engine. Runtime data stays read-only; the only artifact written is a CSV file in `local_analytics/`.

**Tech Stack:** Python 3.12, stdlib `csv`, `dataclasses`, `decimal`, `statistics`, existing SQLite-backed runtime read helpers, `unittest`.

---

## File Structure

- Create: `src/momentum_alpha/leader_opportunity_diagnostics.py`
  - Build contiguous leader runs from `local_analytics/leader_candidates.db`.
  - Join runtime `signal_decisions`, `position_snapshots`, and `trade_round_trips`.
  - Write the CSV report and produce summary lines.
- Create: `tests/test_leader_opportunity_diagnostics.py`
  - Grouping, matching, miss-reason, CSV-writing, and missing-path coverage.
- Modify: `src/momentum_alpha/cli_parser.py`
  - Add `diagnose-opportunities`.
- Modify: `src/momentum_alpha/cli_commands_ops.py`
  - Add the command wrapper and route it through the ops dispatcher.
- Modify: `src/momentum_alpha/cli_commands.py`
  - Pass the new callable through command dispatch.
- Modify: `src/momentum_alpha/cli.py`
  - Import and re-export the new command function for injectable tests.
- Modify: `src/momentum_alpha/main.py`
  - Re-export the new command function so the top-level entry module stays consistent.
- Modify: `tests/test_cli.py`
  - Export smoke test for the new module and CLI entrypoint.
- Modify: `tests/test_main.py`
  - Parser and command dispatch tests for `diagnose-opportunities`.

## Task 1: Build The Opportunity Replay Engine

**Files:**
- Create: `src/momentum_alpha/leader_opportunity_diagnostics.py`
- Create: `tests/test_leader_opportunity_diagnostics.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_leader_opportunity_diagnostics.py` with four focused cases:

Each test should create isolated files with:

```python
with TemporaryDirectory() as tmpdir:
    runtime_db_path = Path(tmpdir) / "runtime.db"
    leader_candidates_db_path = Path(tmpdir) / "leader_candidates.db"
    csv_path = Path(tmpdir) / "opportunity_diagnostics.csv"
```

```python
class LeaderOpportunityDiagnosticsTests(unittest.TestCase):
    def test_build_leader_opportunity_diagnostics_groups_contiguous_rank1_rows(self) -> None:
        from momentum_alpha.leader_opportunity_diagnostics import build_leader_opportunity_diagnostics

        # Seed AAA -> BBB -> AAA rank-1 rows in the sidecar DB.
        # Seed one overlapping AAA round trip in the runtime DB.
        report = build_leader_opportunity_diagnostics(
            runtime_db_path=runtime_db_path,
            leader_candidates_db_path=leader_candidates_db_path,
            start_time=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 1, 1, 20, tzinfo=timezone.utc),
        )

        self.assertEqual([row["symbol"] for row in report.rows], ["AAAUSDT", "BBBUSDT", "AAAUSDT"])
        self.assertEqual(report.rows[0]["trade_status"], "matched_closed_round_trip")
        self.assertEqual(report.rows[0]["capture_rate"], "1")

    def test_build_leader_opportunity_diagnostics_uses_blocked_reason_for_miss(self) -> None:
        from momentum_alpha.leader_opportunity_diagnostics import build_leader_opportunity_diagnostics

        # Seed one CCC leader run, one signal decision with payload {"blocked_reason": "invalid_stop_price"},
        # and no matching closed round trip.
        report = build_leader_opportunity_diagnostics(
            runtime_db_path=runtime_db_path,
            leader_candidates_db_path=leader_candidates_db_path,
            start_time=datetime(2026, 5, 1, 2, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 1, 2, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(report.rows[0]["trade_status"], "missed")
        self.assertEqual(report.rows[0]["miss_reason"], "invalid_stop_price")

    def test_write_opportunity_diagnostics_csv_writes_header_and_rows(self) -> None:
        from momentum_alpha.leader_opportunity_diagnostics import write_opportunity_diagnostics_csv

        write_opportunity_diagnostics_csv(
            path=csv_path,
            rows=[
                {
                    "run_id": "1",
                    "symbol": "AAAUSDT",
                    "run_start": "2026-05-01T01:00:00+00:00",
                    "run_end": "2026-05-01T01:10:00+00:00",
                    "run_minutes": "10",
                    "snapshot_count": "2",
                    "start_daily_change_pct": "0.10",
                    "peak_daily_change_pct": "0.20",
                    "peak_timestamp": "2026-05-01T01:05:00+00:00",
                    "leader_gap_pct_start": "0.05",
                    "trade_status": "matched_closed_round_trip",
                    "signal_decision_id": "dec-1",
                    "decision_type": "base_entry",
                    "matched_round_trip_id": "rt-1",
                    "entered_at": "2026-05-01T01:02:00+00:00",
                    "exit_at": "2026-05-01T01:09:00+00:00",
                    "entry_price": "100",
                    "exit_price": "120",
                    "realized_pnl": "18",
                    "net_pnl": "17",
                    "peak_return_pct": "0.20",
                    "realized_return_pct": "0.20",
                    "capture_rate": "1",
                    "miss_reason": "",
                    "notes": "matched on closed round trip",
                }
            ],
        )

        text = csv_path.read_text(encoding="utf-8")
        self.assertIn("run_id,symbol,run_start,run_end", text.splitlines()[0])
        self.assertIn("AAAUSDT", text)

    def test_build_leader_opportunity_diagnostics_raises_for_missing_runtime_db(self) -> None:
        from momentum_alpha.leader_opportunity_diagnostics import build_leader_opportunity_diagnostics

        with self.assertRaises(FileNotFoundError):
            build_leader_opportunity_diagnostics(
                runtime_db_path=Path("/tmp/missing-runtime.db"),
                leader_candidates_db_path=leader_candidates_db_path,
            )
```

Use the existing helpers already in the codebase to seed data:

- `insert_leader_candidate_snapshots_bulk` from `momentum_alpha.analytics_writes_candidates`
- `insert_signal_decision` from `momentum_alpha.runtime_writes`
- `insert_position_snapshot` from `momentum_alpha.runtime_writes`
- `insert_trade_round_trip` from `momentum_alpha.runtime_writes`

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_leader_opportunity_diagnostics -v
```

Expected: fail with `ModuleNotFoundError: No module named 'momentum_alpha.leader_opportunity_diagnostics'`.

- [ ] **Step 3: Implement the replay engine and CSV writer**

Create `src/momentum_alpha/leader_opportunity_diagnostics.py` with this public surface:

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

@dataclass(frozen=True)
class OpportunityDiagnosticsReport:
    rows: list[dict]
    warnings: list[str]
    total_runs: int
    captured_runs: int
    missed_runs: int
    open_at_cutoff_runs: int
    median_entry_delay_minutes: Decimal | None
    average_capture_rate: Decimal | None
    matched_net_pnl: Decimal | None
    miss_reason_counts: list[tuple[str, int]]

def build_leader_opportunity_diagnostics(
    *,
    runtime_db_path: Path,
    leader_candidates_db_path: Path,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    symbols: list[str] | tuple[str, ...] | None = None,
    min_peak_change_pct: Decimal = Decimal("0"),
) -> OpportunityDiagnosticsReport:

def write_opportunity_diagnostics_csv(*, path: Path, rows: list[dict]) -> None:

def diagnose_opportunities(
    *,
    runtime_db_path: Path,
    leader_candidates_db_path: Path,
    output_file: Path,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    symbols: list[str] | tuple[str, ...] | None = None,
    min_peak_change_pct: Decimal = Decimal("0"),
    logger=print,
) -> OpportunityDiagnosticsReport:
```

`OpportunityDiagnosticsReport.summary_lines()` should emit:

- one line for `total_leader_runs`
- one line for `captured_runs`
- one line for `missed_runs`
- one line for `open_at_cutoff_runs`
- one line for `median_entry_delay_minutes` when available
- one line for `average_capture_rate` when available
- one line for `matched_net_pnl` when available
- one line per miss reason, sorted by count descending

Implementation details the module must follow:

- If `runtime_db_path` does not exist, raise `FileNotFoundError`.
- If `leader_candidates_db_path` is missing or no rank-1 rows survive filtering, return an empty report with a warning string.
- Read rank-1 leader candidate rows from `leader_candidates_db_path`.
- If `start_time` / `end_time` are omitted, analyze the full stored range by using a wide time window against the sidecar DB.
- Group contiguous rank-1 rows by symbol into one opportunity run.
- For each run, compute `run_start`, `run_end`, `run_minutes`, `snapshot_count`, `start_daily_change_pct`, `peak_daily_change_pct`, `peak_timestamp`, and `leader_gap_pct_start`.
- Query runtime rows once per analysis window with:
  - `fetch_signal_decisions_for_window`
  - `fetch_position_snapshots_for_range` or `fetch_position_snapshots_for_window`
  - `fetch_trade_round_trips_for_window`
- Match a closed round trip when the same symbol overlaps the run window.
- Mark `trade_status` as `matched_closed_round_trip`, `open_at_cutoff`, `missed`, or `unresolved`.
- Derive `miss_reason` from `payload["blocked_reason"]` first, then `decision_type`, then `open_at_cutoff`, then `no_matching_signal`.
- Compute `peak_return_pct`, `realized_return_pct`, and `capture_rate` only when the needed prices are available.
- Filter out runs whose `peak_daily_change_pct` is below `min_peak_change_pct`.
- Always write the CSV with a fixed column order and UTF-8 encoding.
- Return an `OpportunityDiagnosticsReport` whose `summary_lines()` method emits the compact terminal summary.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_leader_opportunity_diagnostics -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/leader_opportunity_diagnostics.py tests/test_leader_opportunity_diagnostics.py
git commit -m "feat: add leader opportunity diagnostics engine"
```

## Task 2: Wire The CLI Surface

**Files:**
- Modify: `src/momentum_alpha/cli_parser.py`
- Modify: `src/momentum_alpha/cli_commands_ops.py`
- Modify: `src/momentum_alpha/cli_commands.py`
- Modify: `src/momentum_alpha/cli.py`
- Modify: `src/momentum_alpha/main.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write the failing parser and dispatch tests**

Add these cases to the existing CLI tests:

```python
def test_cli_module_exports_diagnose_opportunities(self) -> None:
    from momentum_alpha import cli, leader_opportunity_diagnostics

    self.assertTrue(callable(cli.diagnose_opportunities))
    self.assertTrue(callable(leader_opportunity_diagnostics.diagnose_opportunities))

def test_cli_parser_supports_diagnose_opportunities_defaults(self) -> None:
    from momentum_alpha.cli_parser import build_cli_parser

    args = build_cli_parser().parse_args(
        ["diagnose-opportunities", "--runtime-db-file", "/tmp/runtime.db"]
    )
    self.assertEqual(args.command, "diagnose-opportunities")
    self.assertEqual(args.output_file, "./local_analytics/opportunity_diagnostics.csv")
    self.assertEqual(args.min_peak_change_pct, Decimal("0"))

def test_cli_main_supports_diagnose_opportunities_command(self) -> None:
    from momentum_alpha.main import cli_main

    calls = []

    class FakeReport:
        rows = [{"run_id": "1", "symbol": "AAAUSDT"}]
        warnings = []

        def summary_lines(self) -> list[str]:
            return ["total_leader_runs=1", "captured_runs=1"]

    def fake_diagnose_opportunities(**kwargs):
        calls.append(kwargs)
        return FakeReport()

    exit_code = cli_main(
        argv=[
            "diagnose-opportunities",
            "--runtime-db-file",
            "/tmp/runtime.db",
            "--leader-candidates-db-file",
            "/tmp/leader_candidates.db",
            "--output-file",
            "/tmp/opportunity_diagnostics.csv",
            "--start-time",
            "2026-05-01T00:00:00+00:00",
            "--end-time",
            "2026-05-02T00:00:00+00:00",
            "--symbols",
            "AAAUSDT",
            "BBBUSDT",
            "--min-peak-change-pct",
            "0.05",
        ],
        diagnose_opportunities_fn=fake_diagnose_opportunities,
    )

    self.assertEqual(exit_code, 0)
    self.assertEqual(calls[0]["runtime_db_path"], Path("/tmp/runtime.db"))
    self.assertEqual(calls[0]["leader_candidates_db_path"], Path("/tmp/leader_candidates.db"))
    self.assertEqual(calls[0]["output_file"], Path("/tmp/opportunity_diagnostics.csv"))
    self.assertEqual(calls[0]["symbols"], ["AAAUSDT", "BBBUSDT"])
    self.assertEqual(calls[0]["min_peak_change_pct"], Decimal("0.05"))
```

Also extend `test_main_module_exports_cli_and_worker_entrypoints` in `tests/test_main.py` so it asserts `callable(main.diagnose_opportunities)`.

The CLI wrapper test should also verify that a fake `client_factory` is never used, because this command is read-only and must not open a Binance client.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_cli tests.test_main -v
```

Expected: fail because `diagnose-opportunities` is not wired into the parser and the new injectable callable is not present on `cli_main()`.

- [ ] **Step 3: Implement the parser and command dispatch**

Update the CLI files so the new command is available end-to-end:

```python
# src/momentum_alpha/cli_parser.py
from decimal import Decimal

diagnose_opportunities_parser = subparsers.add_parser("diagnose-opportunities")
diagnose_opportunities_parser.add_argument("--runtime-db-file", required=True)
diagnose_opportunities_parser.add_argument(
    "--leader-candidates-db-file",
    default="./local_analytics/leader_candidates.db",
)
diagnose_opportunities_parser.add_argument(
    "--output-file",
    default="./local_analytics/opportunity_diagnostics.csv",
)
diagnose_opportunities_parser.add_argument("--start-time")
diagnose_opportunities_parser.add_argument("--end-time")
diagnose_opportunities_parser.add_argument("--symbols", nargs="+")
diagnose_opportunities_parser.add_argument("--min-peak-change-pct", type=Decimal, default=Decimal("0"))
```

```python
# src/momentum_alpha/cli_commands_ops.py
from .leader_opportunity_diagnostics import diagnose_opportunities

def diagnose_opportunities_command(
    *,
    parser,
    args,
    client_factory=None,
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
    for warning in report.warnings:
        print(warning)
    for line in report.summary_lines():
        print(line)
    print(f"opportunity_rows={len(report.rows)}")
    return 0 if report.rows else 1
```

Also thread the callable through:

- `run_ops_commands` in `cli_commands_ops.py`
- `run_cli_command` in `cli_commands.py`
- `cli_main` in `cli.py`
- `src/momentum_alpha/main.py` exports

The wrapper must accept `client_factory` in its signature for dispatch compatibility, but it must not use it.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_cli tests.test_main -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/cli_parser.py src/momentum_alpha/cli_commands_ops.py src/momentum_alpha/cli_commands.py src/momentum_alpha/cli.py src/momentum_alpha/main.py tests/test_cli.py tests/test_main.py
git commit -m "feat: wire leader opportunity diagnostics cli"
```

## Verification

After both tasks land, run the focused regression set:

```bash
python3 -m unittest tests.test_leader_opportunity_diagnostics tests.test_cli tests.test_main tests.test_analytics_candidates -v
```

This should confirm:

- the replay engine groups runs correctly,
- capture and miss cases are classified correctly,
- the CSV writer produces the expected output,
- the CLI parser and dispatcher route `diagnose-opportunities`,
- the existing leader candidate backfill tests still pass.
