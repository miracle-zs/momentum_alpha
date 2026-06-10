# Base Entry False-Breakout Filter Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible analysis that searches conservative base-entry veto rules while preserving all historical 100 USDT winners and at least 98% of 50 USDT tail PnL.

**Architecture:** A standalone analysis module loads matched live trades, computes point-in-time features from completed Binance 1-minute candles, evaluates single and cross-family conjunction rules, and writes auditable CSV and Markdown reports. Pure feature and acceptance functions are covered by focused unit tests; no live strategy code is changed.

**Tech Stack:** Python standard library, SQLite, Binance USD-M public klines, existing analysis helpers, `unittest`.

---

### Task 1: Point-In-Time Feature Engine

**Files:**
- Create: `scripts/analyze_base_filter_research.py`
- Create: `tests/test_analyze_base_filter_research.py`

- [ ] **Step 1: Write failing tests for completed-candle slicing and feature values**

Add tests with synthetic one-minute klines proving that the candle containing
the signal timestamp is excluded and that returns, efficiency ratio, pullback,
close location, wick fraction, volume ratio, trade-count ratio, taker-buy
share, realized volatility, and ATR are calculated from prior completed
candles.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_analyze_base_filter_research -v
```

Expected: failure because the analysis module does not exist.

- [ ] **Step 3: Implement the feature engine**

Create pure helpers:

```python
def completed_candles_before(klines: list, signal_time: datetime) -> list[dict]: ...
def compute_features(candles: list[dict], trade: dict) -> dict[str, float | str]: ...
```

Use only candles whose close time is strictly before the signal timestamp.
Return blank values when history is insufficient instead of silently using a
shorter window.

- [ ] **Step 4: Run the focused tests**

Run:

```bash
python3 -m unittest tests.test_analyze_base_filter_research -v
```

Expected: all feature tests pass.

### Task 2: Candidate Rule Search

**Files:**
- Modify: `scripts/analyze_base_filter_research.py`
- Modify: `tests/test_analyze_base_filter_research.py`

- [ ] **Step 1: Write failing tests for rule evaluation and tail constraints**

Cover:

```python
def evaluate_condition(row: dict, condition: Condition) -> bool: ...
def summarize_candidate(rows: list[dict], conditions: tuple[Condition, ...]) -> dict: ...
def passes_tail_constraints(summary: dict) -> bool: ...
```

Tests must prove conjunction semantics, all 100 USDT winners retained, 98% tail
PnL retention, unmatched PnL inclusion, add-on accounting, and recent/weekly
deltas.

- [ ] **Step 2: Run tests and verify failure**

Run the same focused `unittest` command and expect missing-function failures.

- [ ] **Step 3: Implement coarse threshold grids and candidate evaluation**

Generate weak-state conditions from fixed grids:

- path efficiency and positive-minute share;
- day-high distance, rolling-high distance, pullback, close location, upper
  wick;
- quote-volume ratio, trade-count ratio, taker-buy share;
- stop distance, realized-volatility-normalized return, and range expansion.

Evaluate singles, cross-family pairs, and cross-family triples. A candidate
filters a trade only when every condition is true.

- [ ] **Step 4: Run tests**

Expected: all rule-search tests pass.

### Task 3: Data Loading And Full Research Run

**Files:**
- Modify: `scripts/analyze_base_filter_research.py`
- Create at runtime: `var/analysis/base_filter_research_20260610/*`

- [ ] **Step 1: Add cache loading and proxy-backed fetch**

Seed the new cache from both existing 1-minute caches. Fetch missing signal-day
klines through `http://127.0.0.1:7897`, with bounded concurrency, retries, and
incremental cache writes.

- [ ] **Step 2: Build the 692-row feature table**

Join each matched base signal to its completed one-minute history and recorded
trade/add-on outcome. Fail the run if any trade is missing required signal-day
market data.

- [ ] **Step 3: Search and rank candidates**

Write:

- `feature_table.csv`
- `single_condition_results.csv`
- `combined_veto_results.csv`
- `passing_candidates.csv`
- `candidate_trade_detail.csv`

Rank only candidates that satisfy the tail constraints and improve total PnL.

- [ ] **Step 4: Generate the narrative report**

Write `summary.md` with feature distribution diagnostics, preferred rule,
simpler fallback, long-tail audit, weekly deltas, largest trade impacts, and an
explicit no-deploy conclusion when stability is insufficient.

### Task 4: Verification

**Files:**
- Verify: `scripts/analyze_base_filter_research.py`
- Verify: `tests/test_analyze_base_filter_research.py`
- Verify: `var/analysis/base_filter_research_20260610/*`

- [ ] **Step 1: Run syntax and unit tests**

```bash
python3 -m py_compile scripts/analyze_base_filter_research.py
python3 -m unittest tests.test_analyze_base_filter_research -v
```

- [ ] **Step 2: Run the complete analysis from cache**

```bash
python3 scripts/analyze_base_filter_research.py \
  --db var/runtime.db \
  --output-dir var/analysis/base_filter_research_20260610 \
  --proxy http://127.0.0.1:7897
```

Expected: exit zero without network access after the cache has been populated.

- [ ] **Step 3: Validate artifact invariants**

Assert:

- exactly 692 feature rows;
- no future candle is used;
- every passing candidate retains all eight 100 USDT winners;
- every passing candidate retains at least 98% of 50 USDT tail PnL;
- preferred and fallback candidate detail rows reconcile to their summaries.

- [ ] **Step 4: Review the result for overfitting**

Reject a recommendation when most improvement comes from one trade or one week,
or when the rule is unnecessarily complex relative to its fallback.
