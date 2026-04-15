# Binance Leader Rotation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python trading engine for the Binance leader-rotation strategy with deterministic domain logic, Binance filter-aware order sizing, and test coverage for core state transitions.

**Architecture:** The implementation starts with a pure domain layer that consumes minute-close and hour-close events and emits trading intents. Binance-specific rounding and order payload generation are isolated in a thin adapter layer so the core logic stays reusable for backtest and live execution.

**Tech Stack:** Python 3.13, standard library `dataclasses` and `decimal`, `unittest`, Binance USDⓈ-M Futures REST/WebSocket integration later

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/momentum_alpha/__init__.py`
- Create: `tests/__init__.py`

**Step 1: Write the failing test**

```python
def test_package_imports():
    import momentum_alpha
    assert momentum_alpha.__all__
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_package -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create the package root and export public modules.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_package -v`
Expected: PASS

### Task 2: Binance Filter Normalization

**Files:**
- Create: `src/momentum_alpha/binance_filters.py`
- Test: `tests/test_binance_filters.py`

**Step 1: Write the failing test**

```python
def test_rounds_quantity_down_to_step_size():
    filters = SymbolFilters(step_size="0.1", min_qty="1", tick_size="0.01")
    assert filters.normalize_quantity("1.29") == Decimal("1.2")
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_binance_filters -v`
Expected: FAIL because `SymbolFilters` does not exist

**Step 3: Write minimal implementation**

Implement filter parsing, quantity normalization, price normalization, and validity checks.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_binance_filters -v`
Expected: PASS

### Task 3: Pure Strategy Models

**Files:**
- Create: `src/momentum_alpha/models.py`
- Test: `tests/test_models.py`

**Step 1: Write the failing test**

```python
def test_leg_risk_uses_entry_minus_stop():
    leg = PositionLeg(...)
    assert leg.stop_risk == Decimal("10")
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_models -v`
Expected: FAIL because the model does not exist

**Step 3: Write minimal implementation**

Implement market snapshot, position leg, aggregate position, and strategy event models.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_models -v`
Expected: PASS

### Task 4: Minute-Close Base Entry Logic

**Files:**
- Create: `src/momentum_alpha/strategy.py`
- Test: `tests/test_strategy.py`

**Step 1: Write the failing test**

```python
def test_opens_base_entry_when_leader_changes_and_symbol_not_held():
    result = evaluate_minute_close(...)
    assert result.base_entries == ["ETHUSDT"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_strategy -v`
Expected: FAIL because strategy evaluation does not exist

**Step 3: Write minimal implementation**

Implement leader selection, entry window enforcement, previous leader comparison, and duplicate-position blocking.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_strategy -v`
Expected: PASS

### Task 5: Hourly Add-On Logic

**Files:**
- Modify: `src/momentum_alpha/strategy.py`
- Modify: `src/momentum_alpha/models.py`
- Test: `tests/test_strategy.py`

**Step 1: Write the failing test**

```python
def test_hour_close_updates_stops_and_adds_one_leg_per_open_symbol():
    result = evaluate_hour_close(...)
    assert result.add_on_entries == ["BTCUSDT", "ETHUSDT"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_strategy -v`
Expected: FAIL because hour-close behavior is missing

**Step 3: Write minimal implementation**

Implement stop promotion, hourly sequencing, and add-on decision generation.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_strategy -v`
Expected: PASS

### Task 6: Order Sizing and Intent Payloads

**Files:**
- Create: `src/momentum_alpha/sizing.py`
- Modify: `src/momentum_alpha/strategy.py`
- Test: `tests/test_sizing.py`

**Step 1: Write the failing test**

```python
def test_sizes_entry_from_fixed_stop_loss_budget():
    quantity = size_from_stop_budget("110", "100", "10")
    assert quantity == Decimal("0.1")
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_sizing -v`
Expected: FAIL because the sizing helper is missing

**Step 3: Write minimal implementation**

Implement fixed stop-budget sizing and filter-aware quantity normalization.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_sizing -v`
Expected: PASS

### Task 7: Integration-Level Strategy Scenarios

**Files:**
- Modify: `tests/test_strategy.py`

**Step 1: Write the failing test**

```python
def test_hour_boundary_processes_base_entry_before_add_on():
    result = process_clock_tick(...)
    assert result.base_entries[0].symbol == "SOLUSDT"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_strategy -v`
Expected: FAIL because sequencing coverage is incomplete

**Step 3: Write minimal implementation**

Refine the strategy orchestration to process minute-close entries before hourly add-ons.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_strategy -v`
Expected: PASS

### Task 8: Runtime Skeleton

**Files:**
- Create: `src/momentum_alpha/runtime.py`
- Create: `src/momentum_alpha/config.py`
- Test: `tests/test_runtime.py`

**Step 1: Write the failing test**

```python
def test_runtime_builds_symbol_state_from_snapshots():
    runtime = build_runtime(...)
    assert runtime.symbols
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_runtime -v`
Expected: FAIL because runtime assembly does not exist

**Step 3: Write minimal implementation**

Create configuration and a minimal in-memory runtime skeleton without live network calls.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_runtime -v`
Expected: PASS

### Task 9: Full Verification

**Files:**
- Test: `tests/test_package.py`
- Test: `tests/test_binance_filters.py`
- Test: `tests/test_models.py`
- Test: `tests/test_strategy.py`
- Test: `tests/test_sizing.py`
- Test: `tests/test_runtime.py`

**Step 1: Run the full suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS

**Step 2: Review behavior against the design**

Manually compare tests and implementation with `docs/plans/2026-04-14-binance-leader-rotation-design.md`.

**Step 3: Commit**

```bash
git add .
git commit -m "feat: implement leader rotation strategy core"
```
