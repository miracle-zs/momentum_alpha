# Daily Repeat Base Filter And Shadow Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permit only one valid base signal per symbol per UTC day, persist every later valid signal as a replayable `base_entry_skipped` record, and provide an offline command that reconstructs the filtered base, add-ons, stop updates, and exit.

**Architecture:** Extend the existing immutable strategy decision/state flow with poll-owned daily base-signal maps and explicit skipped-base decisions. Keep live execution unaware of virtual positions. Build the counterfactual as a separate read-only replay pipeline with injected kline loading, deterministic one-minute simulation, CSV/Markdown artifacts, and CLI wiring.

**Tech Stack:** Python 3 standard library, dataclasses, Decimal, SQLite, unittest, Binance USD-M public kline API, existing runtime store/sizing/CLI patterns.

---

## File Structure

### Live behavior

- Modify `src/momentum_alpha/models.py`
  - Add daily base-signal state fields and `SkippedBaseEntry`.
  - Extend minute/tick decisions with daily state outputs and skipped entries.
- Modify `src/momentum_alpha/trace_ids.py`
  - Add deterministic shadow opportunity IDs.
- Modify `src/momentum_alpha/strategy.py`
  - Apply the daily-repeat veto after all existing base checks pass.
- Modify `src/momentum_alpha/runtime.py`
  - Reset daily state on UTC day change and persist decision-produced maps.
- Modify `src/momentum_alpha/strategy_state_codec.py`
  - Serialize and deserialize daily maps backward compatibly.
- Modify `src/momentum_alpha/reconciliation.py`
  - Initialize restored strategy state with empty daily maps.
- Modify `src/momentum_alpha/poll_worker_core_live.py`
  - Restore, merge, persist, and log daily state and skipped-base decisions.
- Modify `src/momentum_alpha/poll_worker_core_state.py`
  - Preserve poll-owned daily fields during atomic state writes.
- Modify `src/momentum_alpha/runtime_state_store.py`
  - Preserve daily fields in generic merge saves.
- Modify `src/momentum_alpha/stream_worker_core.py`
  - Preserve existing daily fields during user-stream writes.
- Modify `src/momentum_alpha/stream_worker_loop.py`
  - Include daily maps when prewarming/saving stream state.

### Offline replay

- Create `src/momentum_alpha/skipped_base_replay_data.py`
  - Load seeds and leader history from SQLite.
  - Fetch/cache Binance one-minute klines through a proxy.
- Create `src/momentum_alpha/skipped_base_replay.py`
  - Own replay dataclasses, deterministic simulation, overlap handling, and report generation.
- Create `src/momentum_alpha/skipped_base_replay_output.py`
  - Write summary, leg, event CSVs and `summary.md`.
- Modify `src/momentum_alpha/cli_parser.py`
  - Add `replay-skipped-base`.
- Modify `src/momentum_alpha/cli.py`
  - Inject/export the replay entry point.
- Modify `src/momentum_alpha/cli_commands.py`
  - Pass the replay function into command handlers.
- Modify `src/momentum_alpha/cli_commands_ops.py`
  - Dispatch the new read-only command.
- Modify `src/momentum_alpha/main.py`
  - Preserve compatibility exports.

### Tests

- Modify `tests/test_strategy.py`
- Modify `tests/test_runtime.py`
- Modify `tests/test_strategy_state_codec.py`
- Modify `tests/test_poll_worker.py`
- Modify `tests/test_stream_worker_split.py`
- Modify `tests/test_main.py`
- Modify `tests/test_cli.py`
- Create `tests/test_skipped_base_replay_data.py`
- Create `tests/test_skipped_base_replay.py`
- Create `tests/test_skipped_base_replay_output.py`

---

### Task 1: Extend Strategy And Persisted State Models

**Files:**
- Modify: `src/momentum_alpha/models.py`
- Modify: `src/momentum_alpha/strategy_state_codec.py`
- Modify: `src/momentum_alpha/runtime_state_store.py`
- Test: `tests/test_strategy_state_codec.py`
- Test: `tests/test_runtime_store.py`

- [ ] **Step 1: Write failing codec tests for the new daily maps**

Extend `test_round_trip_strategy_state` with:

```python
state = StoredStrategyState(
    current_day="2026-06-12",
    previous_leader_symbol="BTCUSDT",
    daily_base_signal_times={
        "BTCUSDT": "2026-06-12T02:03:00+00:00",
    },
    daily_base_signal_counts={"BTCUSDT": 3},
    # existing fixture fields remain unchanged
)

self.assertEqual(
    restored.daily_base_signal_times,
    {"BTCUSDT": "2026-06-12T02:03:00+00:00"},
)
self.assertEqual(restored.daily_base_signal_counts, {"BTCUSDT": 3})
```

Add a backward-compatibility test:

```python
def test_deserialize_legacy_state_defaults_daily_base_maps(self) -> None:
    restored = deserialize_strategy_state(
        {
            "current_day": "2026-06-12",
            "previous_leader_symbol": None,
            "positions": {},
        }
    )

    self.assertEqual(restored.daily_base_signal_times, {})
    self.assertEqual(restored.daily_base_signal_counts, {})
```

- [ ] **Step 2: Write a failing merge-save test**

In `tests/test_runtime_store.py`, save an existing state with populated daily
maps, call `merge_save` with stream-owned fields only, and assert the maps are
unchanged:

```python
self.assertEqual(
    restored.daily_base_signal_times,
    {"ETHUSDT": "2026-06-12T03:05:00+00:00"},
)
self.assertEqual(restored.daily_base_signal_counts, {"ETHUSDT": 2})
```

- [ ] **Step 3: Run the tests and verify the expected failures**

Run:

```bash
python3 -m unittest \
  tests.test_strategy_state_codec \
  tests.test_runtime_store
```

Expected: failures because `StoredStrategyState` and serialization do not yet
support the daily maps.

- [ ] **Step 4: Add the state and decision dataclasses**

In `src/momentum_alpha/models.py`, add:

```python
@dataclass(frozen=True)
class SkippedBaseEntry:
    symbol: str
    stop_price: Decimal
    reason: str
    base_signal_sequence: int
    first_base_signal_at: datetime
    shadow_opportunity_id: str
```

Extend `StrategyState`:

```python
daily_base_signal_times: dict[str, datetime] = field(default_factory=dict)
daily_base_signal_counts: dict[str, int] = field(default_factory=dict)
```

Extend `MinuteCloseDecision` and `TickDecision` with defaults so existing test
fixtures remain source compatible:

```python
skipped_base_entries: list[SkippedBaseEntry] = field(default_factory=list)
new_daily_base_signal_times: dict[str, datetime] = field(default_factory=dict)
new_daily_base_signal_counts: dict[str, int] = field(default_factory=dict)
```

- [ ] **Step 5: Extend stored state serialization**

In `src/momentum_alpha/strategy_state_codec.py`, add fields to
`StoredStrategyState`:

```python
daily_base_signal_times: dict[str, str] | None = None
daily_base_signal_counts: dict[str, int] | None = None
```

Serialize with empty-map defaults:

```python
"daily_base_signal_times": dict(state.daily_base_signal_times or {}),
"daily_base_signal_counts": dict(state.daily_base_signal_counts or {}),
```

Deserialize legacy payloads with:

```python
daily_base_signal_times=dict(payload.get("daily_base_signal_times", {})),
daily_base_signal_counts={
    str(symbol): int(count)
    for symbol, count in payload.get("daily_base_signal_counts", {}).items()
},
```

- [ ] **Step 6: Preserve the fields in `RuntimeStateStore.merge_save`**

Add both fields to the merge constructor, using the same `state value or
existing value` ownership pattern as `positions` and `order_statuses`.

- [ ] **Step 7: Run the state tests**

Run:

```bash
python3 -m unittest \
  tests.test_strategy_state_codec \
  tests.test_runtime_store
```

Expected: PASS.

- [ ] **Step 8: Commit the state model change**

```bash
git add \
  src/momentum_alpha/models.py \
  src/momentum_alpha/strategy_state_codec.py \
  src/momentum_alpha/runtime_state_store.py \
  tests/test_strategy_state_codec.py \
  tests/test_runtime_store.py
git commit -m "feat: persist daily base signal state"
```

---

### Task 2: Implement The Daily Repeat Base Veto

**Files:**
- Modify: `src/momentum_alpha/trace_ids.py`
- Modify: `src/momentum_alpha/strategy.py`
- Modify: `src/momentum_alpha/runtime.py`
- Test: `tests/test_strategy.py`
- Test: `tests/test_runtime.py`

- [ ] **Step 1: Write failing strategy tests**

Add a helper fixture that makes `ETHUSDT` the new valid leader. Then add:

```python
def test_first_valid_base_signal_consumes_daily_opportunity(self) -> None:
    state = StrategyState(
        current_day=now.date(),
        previous_leader_symbol="BTCUSDT",
        daily_base_signal_times={},
        daily_base_signal_counts={},
    )

    result = evaluate_minute_close(now=now, state=state, market=market)

    self.assertEqual([item.symbol for item in result.base_entries], ["ETHUSDT"])
    self.assertEqual(result.skipped_base_entries, [])
    self.assertEqual(result.new_daily_base_signal_times["ETHUSDT"], now)
    self.assertEqual(result.new_daily_base_signal_counts["ETHUSDT"], 1)
```

```python
def test_second_valid_base_signal_is_filtered(self) -> None:
    first_at = datetime(2026, 6, 12, 2, 5, tzinfo=timezone.utc)
    state = StrategyState(
        current_day=now.date(),
        previous_leader_symbol="BTCUSDT",
        daily_base_signal_times={"ETHUSDT": first_at},
        daily_base_signal_counts={"ETHUSDT": 1},
    )

    result = evaluate_minute_close(now=now, state=state, market=market)

    self.assertEqual(result.base_entries, [])
    self.assertEqual(result.blocked_reason, "daily_repeat_base")
    self.assertEqual(result.skipped_base_entries[0].base_signal_sequence, 2)
    self.assertEqual(result.skipped_base_entries[0].first_base_signal_at, first_at)
    self.assertEqual(result.new_daily_base_signal_counts["ETHUSDT"], 2)
```

Add tests proving:

- cooldown/missing candle/invalid stop do not mutate either map;
- a different symbol can consume its own first opportunity;
- the shadow ID is deterministic for the same timestamp, symbol, and sequence.

- [ ] **Step 2: Write a failing runtime UTC rollover test**

In `tests/test_runtime.py`:

```python
def test_runtime_resets_daily_base_state_on_utc_day_change(self) -> None:
    state = StrategyState(
        current_day=date(2026, 6, 11),
        previous_leader_symbol="ETHUSDT",
        daily_base_signal_times={
            "BTCUSDT": datetime(2026, 6, 11, 4, 0, tzinfo=timezone.utc),
        },
        daily_base_signal_counts={"BTCUSDT": 2},
    )

    result = process_runtime_tick(
        runtime=runtime,
        state=state,
        now=datetime(2026, 6, 12, 1, 1, tzinfo=timezone.utc),
    )

    self.assertEqual(result.next_state.current_day, date(2026, 6, 12))
    self.assertEqual(result.next_state.daily_base_signal_counts["BTCUSDT"], 1)
```

The market fixture should make BTC the first valid signal of the new day.

- [ ] **Step 3: Run the tests and verify they fail**

Run:

```bash
python3 -m unittest tests.test_strategy tests.test_runtime
```

Expected: failures because repeat filtering and state propagation do not exist.

- [ ] **Step 4: Add the stable shadow ID helper**

In `src/momentum_alpha/trace_ids.py`:

```python
def build_shadow_opportunity_id(
    *,
    symbol: str,
    signal_at: datetime,
    sequence: int,
) -> str:
    resolved = signal_at.astimezone(timezone.utc)
    symbol_token = "".join(ch for ch in symbol.upper() if ch.isalnum())[-12:] or "UNKNOWN"
    return f"shadow_{resolved.strftime('%y%m%d%H%M%S')}_{symbol_token}_{sequence:02d}"
```

- [ ] **Step 5: Apply the veto only after existing validation passes**

In `evaluate_minute_close`:

1. Copy the maps at function start.
2. Preserve them unchanged for every existing blocked path.
3. When `can_enter` is true:

```python
sequence = daily_counts.get(leader, 0) + 1
daily_counts[leader] = sequence
first_signal_at = daily_times.get(leader)
if first_signal_at is None:
    daily_times[leader] = now
    entries.append(
        EntryIntent(symbol=leader, stop_price=stop_price, leg_type="base")
    )
else:
    blocked_reason = "daily_repeat_base"
    skipped_base_entries.append(
        SkippedBaseEntry(
            symbol=leader,
            stop_price=stop_price,
            reason=blocked_reason,
            base_signal_sequence=sequence,
            first_base_signal_at=first_signal_at,
            shadow_opportunity_id=build_shadow_opportunity_id(
                symbol=leader,
                signal_at=now,
                sequence=sequence,
            ),
        )
    )
```

Return both copied maps and skipped entries in the minute decision.

- [ ] **Step 6: Propagate minute outputs through `process_clock_tick`**

Copy `skipped_base_entries`, `new_daily_base_signal_times`, and
`new_daily_base_signal_counts` into `TickDecision`. Do not alter hour-close
add-on behavior.

- [ ] **Step 7: Normalize UTC day state in `process_runtime_tick`**

Before calling `process_clock_tick`:

```python
normalized_state = state
if state.current_day != now.date():
    normalized_state = replace(
        state,
        current_day=now.date(),
        daily_base_signal_times={},
        daily_base_signal_counts={},
    )
```

Build `next_state` from `normalized_state`, including the decision's daily
maps.

- [ ] **Step 8: Run strategy/runtime tests**

Run:

```bash
python3 -m unittest tests.test_strategy tests.test_runtime
```

Expected: PASS.

- [ ] **Step 9: Commit the strategy behavior**

```bash
git add \
  src/momentum_alpha/trace_ids.py \
  src/momentum_alpha/strategy.py \
  src/momentum_alpha/runtime.py \
  tests/test_strategy.py \
  tests/test_runtime.py
git commit -m "feat: filter repeated daily base signals"
```

---

### Task 3: Preserve Daily State Across Poll And Stream Processes

**Files:**
- Modify: `src/momentum_alpha/reconciliation.py`
- Modify: `src/momentum_alpha/poll_worker_core_live.py`
- Modify: `src/momentum_alpha/poll_worker_core_state.py`
- Modify: `src/momentum_alpha/stream_worker_core.py`
- Modify: `src/momentum_alpha/stream_worker_loop.py`
- Test: `tests/test_poll_worker.py`
- Test: `tests/test_stream_worker_split.py`
- Test: `tests/test_reconciliation.py`

- [ ] **Step 1: Write failing poll restore/persist tests**

Add a test that stores:

```python
StoredStrategyState(
    current_day="2026-06-12",
    previous_leader_symbol="BTCUSDT",
    daily_base_signal_times={
        "ETHUSDT": "2026-06-12T02:00:00+00:00",
    },
    daily_base_signal_counts={"ETHUSDT": 1},
)
```

Run `run_once_live` after a leader cycle would otherwise re-enter ETH and
assert:

```python
self.assertEqual(result.runtime_result.decision.base_entries, [])
self.assertEqual(
    result.runtime_result.decision.skipped_base_entries[0].symbol,
    "ETHUSDT",
)
```

Add another test using a broker that records a base submission failure. Assert
the saved state still contains the first signal timestamp/count.

- [ ] **Step 2: Write failing atomic merge tests**

In `tests/test_stream_worker_split.py`, prove a user-stream save preserves
existing daily maps even when the incoming `StoredStrategyState` omits them.

Also prove `_save_strategy_state` preserves stream-owned fields while replacing
the daily maps with the poll result for the current day.

- [ ] **Step 3: Run the focused tests and verify failures**

Run:

```bash
python3 -m unittest \
  tests.test_poll_worker \
  tests.test_stream_worker_split \
  tests.test_reconciliation
```

Expected: failures showing daily state is not restored or preserved.

- [ ] **Step 4: Restore daily state in `run_once_live`**

Load `StoredStrategyState` once near the beginning of `run_once_live`, then:

- retain its previous leader when needed;
- when `stored_state.current_day == now.date().isoformat()`, convert
  `daily_base_signal_times` to `datetime` and copy counts into the restored
  `StrategyState`;
- when the stored day differs, provide empty daily maps.

Do this for both restored-position and no-position paths so restart behavior
does not depend on `--restore-positions`.

- [ ] **Step 5: Persist the daily fields from `next_state`**

When building `merged_state` in `poll_worker_core_live.py`, include:

```python
daily_base_signal_times={
    symbol: timestamp.isoformat()
    for symbol, timestamp
    in result.runtime_result.next_state.daily_base_signal_times.items()
},
daily_base_signal_counts=dict(
    result.runtime_result.next_state.daily_base_signal_counts
),
```

- [ ] **Step 6: Preserve ownership in atomic save helpers**

In `_save_strategy_state`, copy the incoming poll-owned daily fields.

In `_save_user_stream_strategy_state`, preserve the existing state's daily
fields instead of taking values from the user-stream state:

```python
daily_base_signal_times=(
    dict(existing.daily_base_signal_times or {})
    if existing is not None
    else {}
),
daily_base_signal_counts=(
    dict(existing.daily_base_signal_counts or {})
    if existing is not None
    else {}
),
```

Update both stream save call sites to carry the fields for completeness, while
keeping the atomic updater authoritative.

- [ ] **Step 7: Initialize restored states explicitly**

In `reconciliation.restore_state`, construct `StrategyState` with empty daily
maps. This is explicit documentation of restored account positions versus
poll-owned signal history.

- [ ] **Step 8: Run focused process tests**

Run:

```bash
python3 -m unittest \
  tests.test_poll_worker \
  tests.test_stream_worker_split \
  tests.test_reconciliation
```

Expected: PASS.

- [ ] **Step 9: Commit process persistence**

```bash
git add \
  src/momentum_alpha/reconciliation.py \
  src/momentum_alpha/poll_worker_core_live.py \
  src/momentum_alpha/poll_worker_core_state.py \
  src/momentum_alpha/stream_worker_core.py \
  src/momentum_alpha/stream_worker_loop.py \
  tests/test_poll_worker.py \
  tests/test_stream_worker_split.py \
  tests/test_reconciliation.py
git commit -m "feat: preserve daily base limits across workers"
```

---

### Task 4: Persist Complete `base_entry_skipped` Telemetry

**Files:**
- Modify: `src/momentum_alpha/poll_worker_core_live.py`
- Test: `tests/test_main.py`
- Test: `tests/test_telemetry.py`

- [ ] **Step 1: Write a failing telemetry integration test**

Create a runtime DB with stored daily state for `ETHUSDT`, run a tick that
produces:

- a skipped repeated ETH base; and
- a stop update or skipped add-on for another held symbol on the same hour
  boundary.

Fetch recent signal decisions and assert both records exist:

```python
decision_types = [row["decision_type"] for row in decisions]
self.assertIn("base_entry_skipped", decision_types)
self.assertIn("add_on_skipped", decision_types)
```

Assert the skipped payload contains:

```python
self.assertEqual(payload["blocked_reason"], "daily_repeat_base")
self.assertEqual(payload["base_signal_sequence"], 2)
self.assertEqual(payload["first_base_signal_at"], first_at.isoformat())
self.assertEqual(payload["stop_budget_usdt"], "10")
self.assertEqual(payload["latest_price"], "120")
self.assertEqual(payload["stop_price"], "110")
self.assertEqual(payload["step_size"], "0.001")
self.assertIn("shadow_opportunity_id", payload)
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
python3 -m unittest tests.test_main tests.test_telemetry
```

Expected: failure because skipped-base decisions are not yet recorded.

- [ ] **Step 3: Add skipped-base signal records**

In `run_once_live`, extend `signal_records` independently of normal entries:

```python
signal_records.extend(
    (
        "base_entry_skipped",
        skipped.symbol,
        skipped.shadow_opportunity_id,
        {
            "leg_type": "base",
            "blocked_reason": skipped.reason,
            "base_signal_sequence": skipped.base_signal_sequence,
            "first_base_signal_at": skipped.first_base_signal_at.isoformat(),
            "shadow_opportunity_id": skipped.shadow_opportunity_id,
            "stop_price": str(skipped.stop_price),
            "stop_budget_usdt": str(StrategyConfig().stop_budget_usdt),
            **{
                key: value
                for key, value in market_payloads.get(skipped.symbol, {}).items()
                if value is not None
            },
        },
    )
    for skipped in result.runtime_result.decision.skipped_base_entries
)
```

Import `StrategyConfig` and assign
`stop_budget_usdt = StrategyConfig().stop_budget_usdt` once before building
signal records so the payload does not duplicate a literal.

- [ ] **Step 4: Add operational summary fields**

Include:

```python
"skipped_base_symbols": [
    item.symbol
    for item in result.runtime_result.decision.skipped_base_entries
],
```

in both `tick_result` and position snapshot payloads.

- [ ] **Step 5: Verify signal coexistence**

Keep the current `if not signal_records` fallback. Because skipped-base rows are
added to the common list, they are not lost when add-on or stop-update rows
exist on the same tick.

- [ ] **Step 6: Run telemetry tests**

Run:

```bash
python3 -m unittest tests.test_main tests.test_telemetry
```

Expected: PASS.

- [ ] **Step 7: Commit telemetry**

```bash
git add \
  src/momentum_alpha/poll_worker_core_live.py \
  tests/test_main.py \
  tests/test_telemetry.py
git commit -m "feat: record skipped base replay seeds"
```

---

### Task 5: Build Runtime Seed And Leader Data Loading

**Files:**
- Create: `src/momentum_alpha/skipped_base_replay_data.py`
- Create: `tests/test_skipped_base_replay_data.py`

- [ ] **Step 1: Write failing SQLite loader tests**

Create a temporary runtime DB and insert:

- two `base_entry_skipped` rows;
- normal `base_entry`, `no_action`, and `add_on` rows containing leader data;
- two rows in the same minute with conflicting leaders.

Test:

```python
seeds, leaders, warnings, cutoff = load_replay_inputs(
    runtime_db_path=db_path,
    start_time=start,
    end_time=end,
    symbols={"AAAUSDT"},
)

self.assertEqual([seed.symbol for seed in seeds], ["AAAUSDT"])
self.assertEqual(seed.base_signal_sequence, 2)
self.assertEqual(
    leaders[datetime(2026, 6, 12, 3, 0, tzinfo=timezone.utc)],
    "AAAUSDT",
)
self.assertTrue(any("conflicting_leader" in item for item in warnings))
```

Add a malformed skipped payload and assert it becomes an unresolved seed with
warnings rather than aborting the load.

- [ ] **Step 2: Run loader tests and verify import failure**

Run:

```bash
python3 -m unittest tests.test_skipped_base_replay_data
```

Expected: import failure because the module does not exist.

- [ ] **Step 3: Define replay input dataclasses**

In `skipped_base_replay_data.py`:

```python
@dataclass(frozen=True)
class ReplaySeed:
    shadow_opportunity_id: str
    symbol: str
    signal_at: datetime
    base_signal_sequence: int
    first_base_signal_at: datetime
    latest_price: Decimal | None
    stop_price: Decimal | None
    stop_budget_usdt: Decimal | None
    step_size: Decimal | None
    min_qty: Decimal | None
    tick_size: Decimal | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReplayCandle:
    open_time: datetime
    close_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
```

- [ ] **Step 4: Implement read-only SQLite loading**

Query `signal_decisions` ordered by `timestamp, id`.

- Parse only `decision_type = base_entry_skipped` into seeds.
- Build a minute-floor leader map from every non-null
  `next_leader_symbol`.
- Use the last row in a minute on conflict and emit a warning.
- Derive the default cutoff from the latest signal-decision timestamp.
- Apply optional time and symbol filters in Python after parsing to keep the
  SQL simple and deterministic.

- [ ] **Step 5: Run loader tests**

Run:

```bash
python3 -m unittest tests.test_skipped_base_replay_data
```

Expected: PASS.

- [ ] **Step 6: Commit runtime data loading**

```bash
git add \
  src/momentum_alpha/skipped_base_replay_data.py \
  tests/test_skipped_base_replay_data.py
git commit -m "feat: load skipped base replay inputs"
```

---

### Task 6: Add Proxy-Aware Binance Kline Cache

**Files:**
- Modify: `src/momentum_alpha/skipped_base_replay_data.py`
- Modify: `tests/test_skipped_base_replay_data.py`

- [ ] **Step 1: Write failing cache/fetch tests**

Test injected HTTP behavior without network access:

```python
cache = BinanceKlineCache(
    cache_path=tmp_path / "binance_1m_cache.json",
    proxy="http://127.0.0.1:7897",
    request_json=fake_request_json,
)

candles = cache.load_range(
    symbol="AAAUSDT",
    start_time=start,
    end_time=end,
)

self.assertEqual(candles[0].close_price, Decimal("10.5"))
self.assertEqual(calls[0]["proxy"], "http://127.0.0.1:7897")
```

Add tests proving:

- cached symbol-days do not call HTTP again;
- `refresh=True` bypasses cached data;
- incomplete candles beyond `end_time` are excluded;
- a failed day raises a typed `KlineFetchError` while retaining successful
  cached days.

- [ ] **Step 2: Run tests and verify failures**

Run:

```bash
python3 -m unittest tests.test_skipped_base_replay_data
```

Expected: failures because the cache class is missing.

- [ ] **Step 3: Implement the default proxy request**

Use only the standard library:

```python
def request_json(*, url: str, proxy: str | None, timeout: float) -> object:
    handlers = []
    if proxy:
        handlers.append(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    opener = urllib.request.build_opener(*handlers)
    with opener.open(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))
```

Retry transient failures with short bounded backoff. Do not use credentials for
the public endpoint.

- [ ] **Step 4: Implement daily cache keys and range loading**

Use keys of the form:

```text
AAAUSDT:2026-06-12
```

Fetch:

```text
https://fapi.binance.com/fapi/v1/klines
```

with `interval=1m`, UTC day `startTime`, UTC day `endTime`, and `limit=1440`.
Write the JSON cache atomically through a temporary file in the same directory.

Convert cached Binance rows to `ReplayCandle` using `Decimal(str(value))`.

- [ ] **Step 5: Run cache tests**

Run:

```bash
python3 -m unittest tests.test_skipped_base_replay_data
```

Expected: PASS.

- [ ] **Step 6: Commit kline caching**

```bash
git add \
  src/momentum_alpha/skipped_base_replay_data.py \
  tests/test_skipped_base_replay_data.py
git commit -m "feat: cache proxy binance replay klines"
```

---

### Task 7: Implement The Deterministic Shadow Replay Engine

**Files:**
- Create: `src/momentum_alpha/skipped_base_replay.py`
- Create: `tests/test_skipped_base_replay.py`

- [ ] **Step 1: Write a failing base-sizing and stop-exit test**

Use:

- base entry `110`;
- stop `100`;
- risk budget `10`;
- quantity step `0.1`;
- one candle whose low crosses `100`.

Assert:

```python
self.assertEqual(result.status, "closed")
self.assertEqual(result.base_quantity, Decimal("1.0"))
self.assertEqual(result.exit_price, Decimal("100"))
self.assertEqual(result.add_on_count, 0)
self.assertEqual(
    result.net_pnl,
    Decimal("-10") - Decimal("110") * fee - Decimal("100") * fee,
)
```

- [ ] **Step 2: Write failing hourly stop/add-on tests**

Use candles spanning 01:00-03:00 and leader history at 02:00.

Assert:

- the 01:59 candle is checked against the old stop before the 02:00 update;
- the previous hour low becomes the new full-position stop;
- an add-on is created only when the symbol is top-1;
- add-on entry uses the completed 01:59 close;
- add-on quantity uses `size_from_stop_budget`;
- missing leader data records an event and does not add.

- [ ] **Step 3: Write failing multi-leg PnL and open-cutoff tests**

Cover:

- two add-ons followed by one stop closing every leg;
- entry fees for each leg and one exit fee on total quantity;
- per-leg gross/net contribution;
- an unclosed shadow with blank realized PnL and populated
  mark-to-market net PnL.

- [ ] **Step 4: Write a failing overlap test**

Provide two same-symbol seeds where the second occurs before the first shadow
exit. Assert:

```python
self.assertEqual(len(report.opportunities), 1)
self.assertEqual(len(report.overlaps), 1)
self.assertEqual(
    report.overlaps[0].active_shadow_opportunity_id,
    report.opportunities[0].shadow_opportunity_id,
)
```

Then provide a third seed after exit and assert it starts a second independent
opportunity.

- [ ] **Step 5: Run replay tests and verify import failure**

Run:

```bash
python3 -m unittest tests.test_skipped_base_replay
```

Expected: import failure because the replay module does not exist.

- [ ] **Step 6: Define replay result dataclasses**

Create:

```python
@dataclass(frozen=True)
class ShadowLegResult:
    shadow_opportunity_id: str
    leg_type: str
    sequence: int
    opened_at: datetime
    entry_price: Decimal
    stop_at_entry: Decimal
    quantity: Decimal
    risk_budget: Decimal
    entry_fee: Decimal
    closed_at: datetime | None
    exit_price: Decimal | None
    gross_pnl: Decimal | None
    net_contribution: Decimal | None


@dataclass(frozen=True)
class ShadowReplayResult:
    shadow_opportunity_id: str
    symbol: str
    base_signal_at: datetime
    base_signal_sequence: int
    first_base_signal_at: datetime
    status: str
    base_entry_price: Decimal | None
    initial_stop_price: Decimal | None
    base_quantity: Decimal | None
    add_on_count: int
    skipped_add_on_count: int
    exit_at: datetime | None
    exit_price: Decimal | None
    duration_minutes: Decimal | None
    gross_pnl: Decimal | None
    entry_fees: Decimal | None
    exit_fees: Decimal | None
    net_pnl: Decimal | None
    mark_price_at_cutoff: Decimal | None
    mark_to_market_net_pnl: Decimal | None
    legs: tuple[ShadowLegResult, ...]
    events: tuple[ShadowReplayEvent, ...]
    warnings: tuple[str, ...]
```

Define `ShadowReplayEvent`, `ShadowOverlap`, and `ShadowReplayReport` with
explicit typed fields used by the output schemas:

```python
@dataclass(frozen=True)
class ShadowReplayEvent:
    shadow_opportunity_id: str
    symbol: str
    timestamp: datetime
    event_type: str
    price: Decimal | None = None
    stop_price: Decimal | None = None
    quantity: Decimal | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ShadowOverlap:
    shadow_opportunity_id: str
    symbol: str
    signal_at: datetime
    active_shadow_opportunity_id: str
    status: str = "overlap_existing_shadow"


@dataclass(frozen=True)
class ShadowReplayReport:
    seed_count: int
    opportunities: tuple[ShadowReplayResult, ...]
    overlaps: tuple[ShadowOverlap, ...]
    warnings: tuple[str, ...]
    had_fetch_errors: bool = False
```

- [ ] **Step 7: Implement base construction**

Validate seed fields, build `SymbolFilters`, and call production
`size_from_stop_budget`. Return `unresolved` with events/warnings when sizing
inputs are unusable.

Charge:

```python
entry_fee = quantity * entry_price * taker_fee_rate
```

- [ ] **Step 8: Implement chronological candle processing**

For each completed candle at or after the signal minute:

1. Check `candle.low_price <= active_stop`.
2. If hit, close all legs at `active_stop` and stop.
3. If the candle closes immediately before a UTC hour boundary:
   - calculate the low of the just-completed hour;
   - update `active_stop`;
   - resolve leader at the exact boundary minute;
   - when leader matches, size/add a leg at `candle.close_price`.

Track hour candles explicitly so the previous-hour low is based on 60 complete
one-minute candles. If fewer than 60 candles are present, record
`missing_previous_hour_candles` and skip that boundary update/add-on.

- [ ] **Step 9: Calculate closed and open PnL**

Closed:

```python
gross_pnl = sum(
    leg.quantity * (exit_price - leg.entry_price)
    for leg in legs
)
entry_fees = sum(leg.entry_fee for leg in legs)
exit_fees = total_quantity * exit_price * taker_fee_rate
net_pnl = gross_pnl - entry_fees - exit_fees
```

Open-at-cutoff uses the same formula with the final candle close as mark price,
but stores it in `mark_to_market_net_pnl` and leaves `net_pnl` as `None`.

- [ ] **Step 10: Implement chronological per-symbol overlap handling**

Sort seeds by `(symbol, signal_at, shadow_opportunity_id)`. For each symbol:

- replay the first independent seed;
- compare the next seed to the active result's `exit_at`;
- suppress it as overlap when the prior result is unresolved/open or exits
  after the next seed;
- otherwise replay it independently.

- [ ] **Step 11: Run replay engine tests**

Run:

```bash
python3 -m unittest tests.test_skipped_base_replay
```

Expected: PASS.

- [ ] **Step 12: Commit the replay engine**

```bash
git add \
  src/momentum_alpha/skipped_base_replay.py \
  tests/test_skipped_base_replay.py
git commit -m "feat: replay skipped base shadow positions"
```

---

### Task 8: Write Replay CSV And Markdown Artifacts

**Files:**
- Create: `src/momentum_alpha/skipped_base_replay_output.py`
- Create: `tests/test_skipped_base_replay_output.py`

- [ ] **Step 1: Write failing artifact tests**

Build a report containing:

- one closed winner;
- one closed loser;
- one open position;
- one overlap;
- one warning.

Call:

```python
write_replay_artifacts(report=report, output_dir=output_dir)
```

Assert all files exist and verify key CSV fields:

```python
self.assertEqual(summary_rows[0]["status"], "closed")
self.assertEqual(summary_rows[0]["add_on_count"], "2")
self.assertEqual(event_rows[-1]["event_type"], "open_at_cutoff")
```

Assert `summary.md` contains:

- seed/independent/overlap counts;
- realized shadow net PnL;
- open mark-to-market PnL;
- win rate;
- top winner/loser;
- sequence and ISO-week sections;
- warnings.

- [ ] **Step 2: Run tests and verify import failure**

Run:

```bash
python3 -m unittest tests.test_skipped_base_replay_output
```

Expected: import failure because the output module does not exist.

- [ ] **Step 3: Implement stable CSV schemas**

Define explicit field lists rather than deriving headers from the first row.
Always write headers, including for empty reports.

Use an empty string for `None` Decimal/datetime values and `str(value)` for
precise numeric output.

- [ ] **Step 4: Implement Markdown aggregation**

Aggregate:

- closed win/loss counts and win rate;
- total realized net PnL;
- total open mark-to-market net PnL;
- base/add-on/skipped-add-on counts;
- sequence PnL;
- ISO-week PnL;
- five largest winners and losers;
- unique warnings.

- [ ] **Step 5: Run output tests**

Run:

```bash
python3 -m unittest tests.test_skipped_base_replay_output
```

Expected: PASS.

- [ ] **Step 6: Commit artifact generation**

```bash
git add \
  src/momentum_alpha/skipped_base_replay_output.py \
  tests/test_skipped_base_replay_output.py
git commit -m "feat: write skipped base replay reports"
```

---

### Task 9: Wire The Replay Orchestrator And CLI

**Files:**
- Modify: `src/momentum_alpha/skipped_base_replay.py`
- Modify: `src/momentum_alpha/cli_parser.py`
- Modify: `src/momentum_alpha/cli.py`
- Modify: `src/momentum_alpha/cli_commands.py`
- Modify: `src/momentum_alpha/cli_commands_ops.py`
- Modify: `src/momentum_alpha/main.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_skipped_base_replay.py`

- [ ] **Step 1: Write a failing orchestrator test**

Inject:

- a fake input loader;
- a fake kline cache;
- a temporary output directory.

Call:

```python
report = replay_skipped_bases(
    runtime_db_path=db_path,
    output_dir=output_dir,
    start_time=start,
    end_time=end,
    symbols=["AAAUSDT"],
    proxy="http://127.0.0.1:7897",
    taker_fee_rate=Decimal("0.0005"),
    refresh_klines=False,
    load_inputs_fn=fake_load_inputs,
    kline_cache_factory=fake_cache_factory,
)
```

Assert it loads every day needed for each seed through the cutoff, writes the
artifacts, and exposes `had_fetch_errors`.

- [ ] **Step 2: Write failing parser and CLI dispatch tests**

In `tests/test_cli.py`:

```python
args = build_cli_parser().parse_args(
    ["replay-skipped-base", "--runtime-db-file", "/tmp/runtime.db"]
)
self.assertEqual(args.output_dir, "./local_analytics/skipped_base_replay")
self.assertEqual(args.proxy, "http://127.0.0.1:7897")
self.assertEqual(args.taker_fee_rate, Decimal("0.0005"))
```

In `tests/test_main.py`, inject `replay_skipped_bases_fn`, invoke the full CLI,
and assert every parsed option is forwarded as the expected `Path`, datetime,
list, Decimal, and boolean.

- [ ] **Step 3: Run focused tests and verify failures**

Run:

```bash
python3 -m unittest \
  tests.test_cli \
  tests.test_main \
  tests.test_skipped_base_replay
```

Expected: failures because the orchestrator and CLI surface do not exist.

- [ ] **Step 4: Implement `replay_skipped_bases`**

The function should:

1. fail fast when `runtime_db_path` is absent;
2. load seeds, leaders, warnings, and cutoff;
3. build/load cached klines for every seed symbol and required UTC date;
4. mark fetch-failed opportunities unresolved but continue others;
5. call the replay engine;
6. merge input/fetch warnings into the report;
7. write all artifacts;
8. return the report.

- [ ] **Step 5: Add parser arguments**

In `cli_parser.py`:

```python
replay_parser = subparsers.add_parser("replay-skipped-base")
replay_parser.add_argument("--runtime-db-file", required=True)
replay_parser.add_argument(
    "--output-dir",
    default="./local_analytics/skipped_base_replay",
)
replay_parser.add_argument("--start-time")
replay_parser.add_argument("--end-time")
replay_parser.add_argument("--symbols", nargs="+")
replay_parser.add_argument("--proxy", default="http://127.0.0.1:7897")
replay_parser.add_argument(
    "--taker-fee-rate",
    type=Decimal,
    default=Decimal("0.0005"),
)
replay_parser.add_argument("--refresh-klines", action="store_true")
```

- [ ] **Step 6: Wire dependency injection and command dispatch**

Add `replay_skipped_bases_fn` through:

- `cli_main`
- `run_cli_command`
- `run_ops_commands`

The command handler should return:

- `0` for a complete or empty replay;
- `1` when outputs were written but `report.had_fetch_errors` is true.

Print concise summary counters and output paths.

- [ ] **Step 7: Export compatibility entry points**

Import/export `replay_skipped_bases` from `cli.py` and `main.py` in the same
style as `diagnose_opportunities`.

- [ ] **Step 8: Run focused CLI tests**

Run:

```bash
python3 -m unittest \
  tests.test_cli \
  tests.test_main \
  tests.test_skipped_base_replay
```

Expected: PASS.

- [ ] **Step 9: Commit CLI integration**

```bash
git add \
  src/momentum_alpha/skipped_base_replay.py \
  src/momentum_alpha/cli_parser.py \
  src/momentum_alpha/cli.py \
  src/momentum_alpha/cli_commands.py \
  src/momentum_alpha/cli_commands_ops.py \
  src/momentum_alpha/main.py \
  tests/test_cli.py \
  tests/test_main.py \
  tests/test_skipped_base_replay.py
git commit -m "feat: add skipped base replay command"
```

---

### Task 10: Run Regression And Acceptance Verification

**Files:**
- Modify if required: `README.md`
- Modify if required: `docs/live-ops-checklist.md`

- [ ] **Step 1: Run all new focused tests**

Run:

```bash
python3 -m unittest \
  tests.test_strategy \
  tests.test_runtime \
  tests.test_strategy_state_codec \
  tests.test_runtime_store \
  tests.test_poll_worker \
  tests.test_stream_worker_split \
  tests.test_reconciliation \
  tests.test_telemetry \
  tests.test_skipped_base_replay_data \
  tests.test_skipped_base_replay \
  tests.test_skipped_base_replay_output \
  tests.test_cli \
  tests.test_main
```

Expected: PASS with zero failures/errors.

- [ ] **Step 2: Run the complete test suite**

Run:

```bash
python3 -m unittest discover -s tests
```

Expected: PASS with zero failures/errors.

- [ ] **Step 3: Run static syntax verification**

Run:

```bash
python3 -m compileall -q src tests
```

Expected: exit code `0`.

- [ ] **Step 4: Verify the CLI help**

Run:

```bash
PYTHONPATH=src python3 -m momentum_alpha.main replay-skipped-base --help
```

Expected: help includes runtime DB, output directory, date range, symbols,
proxy, fee rate, and refresh flags.

- [ ] **Step 5: Run a local empty-data smoke test**

Create a temporary bootstrapped runtime DB with no skipped seeds and run:

```bash
PYTHONPATH=src python3 -m momentum_alpha.main replay-skipped-base \
  --runtime-db-file /tmp/momentum-alpha-empty-replay.db \
  --output-dir /tmp/momentum-alpha-empty-replay
```

Expected:

- exit code `0`;
- all CSV files contain headers;
- `summary.md` reports zero seeds;
- no network request is made.

- [ ] **Step 6: Review the live acceptance criteria**

Confirm from tests and code:

- a valid first signal consumes the opportunity before broker submission;
- later valid signals create no execution-plan orders;
- restart state retains daily consumption;
- UTC rollover clears daily consumption;
- add-ons remain unchanged;
- every repeated signal produces a complete `base_entry_skipped` payload;
- shadow state exists only in offline modules.

- [ ] **Step 7: Add concise operator documentation**

Document:

```bash
PYTHONPATH=src python3 -m momentum_alpha.main replay-skipped-base \
  --runtime-db-file ./var/runtime.db \
  --output-dir ./local_analytics/skipped_base_replay \
  --proxy http://127.0.0.1:7897
```

State that results are one-minute counterfactual estimates and list the four
output files.

- [ ] **Step 8: Run documentation and diff checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended implementation, test, and
documentation files are modified.

- [ ] **Step 9: Commit final documentation or fixes**

```bash
git add README.md docs/live-ops-checklist.md
git commit -m "docs: explain skipped base replay workflow"
```

Skip this commit only if no documentation file required a change.
