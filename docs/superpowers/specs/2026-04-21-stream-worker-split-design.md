# Stream Worker Split Design

**Date**: 2026-04-21
**Status**: Proposed

## Overview

Refactor `src/momentum_alpha/stream_worker.py` into two focused modules:

- `src/momentum_alpha/stream_worker_core.py`
- `src/momentum_alpha/stream_worker_loop.py`

The goal is to separate event-processing and persistence logic from reconnect and lifecycle orchestration, while preserving the current public entrypoint and behavior.

The existing `stream_worker.py` file remains a compatibility facade. It should continue to expose `run_user_stream` and the helper names that current tests and call sites patch through the module namespace.

The facade also stays the monkeypatch boundary. Its wrapper should forward the module-bound helper callables into the new implementation so patches against `momentum_alpha.stream_worker.*` continue to affect runtime behavior.

## Confirmed User Decision

The split is locked to the recommended 2-file boundary:

- core logic in `stream_worker_core.py`
- loop/orchestration logic in `stream_worker_loop.py`

No third state module should be introduced in this refactor.

## Problem Statement

`stream_worker.py` currently mixes several concerns in one file:

- event de-duplication
- trade-fill, algo-order, and account-flow persistence
- user-stream state merging
- prewarming from REST state
- stream client construction
- reconnect/backoff loop management

That makes the file harder to reason about and harder to test in isolation. It also makes the public `stream_worker` module a less stable boundary, because unrelated changes to the reconnect loop can accidentally disturb event processing and state persistence.

## Goals

1. Keep `run_user_stream` working with the same inputs and outputs.
2. Preserve the current event semantics, state semantics, and audit behavior.
3. Preserve the current `stream_worker` module namespace for existing monkeypatch-based tests.
4. Preserve current monkeypatch behavior for the helper names already patched in `tests/test_main.py`.
5. Split the code so event processing can be tested without the reconnect loop, and the loop can be tested without the low-level persistence details.
6. Avoid changing any database schema or runtime store format.

## Non-Goals

This design does not introduce:

- a new websocket transport implementation
- a new user-stream protocol
- a new persistence schema
- a new CLI surface
- a new public API beyond the existing facade
- a third split module

## Approaches Considered

### Approach A: Keep `stream_worker.py` Monolithic

Pros:

- Lowest short-term change surface
- No import churn
- No facade work

Cons:

- The file stays mixed across persistence, state, and reconnect logic
- Event handling remains harder to test independently
- The module continues to grow around a single public entrypoint

This is not recommended.

### Approach B: Split Into `stream_worker_core.py` and `stream_worker_loop.py`

Pros:

- Clean separation between event processing and orchestration
- Minimal import churn
- Fits the current codebase pattern of compatibility facades
- Keeps the refactor small enough to land safely

Cons:

- The facade must keep some imported helper names for compatibility with existing tests
- Some logic will still be nested inside closures because the behavior is stateful

This is the recommended approach.

### Approach C: Split Into Three Modules

Pros:

- Even tighter separation of state handling and event processing

Cons:

- More files than the current complexity justifies
- More coordination overhead for a relatively small module
- Higher chance of over-splitting without real payoff

This is not recommended for the current refactor.

## Recommended Architecture

Keep `stream_worker.py` as a facade and move the implementation into two modules:

- `stream_worker_core.py`: event handling, state merging, state persistence helpers
- `stream_worker_loop.py`: runtime setup, prewarm, reconnect loop, and the public `run_user_stream`

The facade should continue to import and expose the names that existing tests patch directly, including helper functions from `momentum_alpha.user_stream` and write helpers from `momentum_alpha.runtime_store`.

The loop and core modules should not look back into `momentum_alpha.stream_worker` for their dependencies. Instead, the facade should pass its bound callables into the new implementation explicitly. That keeps patching effective and makes the split easy to test.

## Compatibility Surface

Keep these names importable from `momentum_alpha.stream_worker`:

- `run_user_stream`
- `_prune_processed_event_ids`
- `_save_user_stream_strategy_state`
- `BinanceUserStreamClient`
- `apply_user_stream_event_to_state`
- `extract_account_flows`
- `extract_algo_order_event`
- `extract_algo_order_status_update`
- `extract_order_status_update`
- `extract_trade_fill`
- `user_stream_event_id`
- `insert_account_flow`
- `insert_algo_order`
- `insert_trade_fill`
- `AuditRecorder`
- `_record_broker_orders`
- `_record_position_snapshot`
- `RuntimeStateStore`
- `StoredStrategyState`
- `MAX_PROCESSED_EVENT_ID_AGE_HOURS`
- `restore_state`
- `StrategyState`

## Core Module Boundary

`stream_worker_core.py` should own the logic that is tied to a single parsed user-stream event and the current worker state.

It should contain:

- `_prune_processed_event_ids`
- `_save_user_stream_strategy_state`
- a helper for building the per-event handler logic
- the event-processing function that receives a parsed event and updates state, order status, audit rows, and runtime persistence

The core module should:

- accept a parsed event object
- de-duplicate by event id
- persist trade fills, algo orders, and account flows
- update `order_statuses`
- apply the event to `StrategyState`
- persist the merged state back to `RuntimeStateStore`
- record the position snapshot audit event

The core module should not:

- create the websocket client
- manage reconnect backoff
- own the outer `while True` loop
- decide how many times to retry a failed stream connection
- assemble the initial runtime state from the stored snapshot

## Loop Module Boundary

`stream_worker_loop.py` should own the long-lived worker lifecycle.

It should:

- load initial state from `RuntimeStateStore`
- assemble the in-memory `StrategyState`, `processed_event_ids`, and `order_statuses` from the stored snapshot
- build `AuditRecorder`
- prewarm positions and tracked order status from REST before each connection attempt
- construct the stream client via the injected factory
- call the core event handler
- handle reconnects and sleep backoff on stream failure

The loop module should not duplicate the per-event persistence logic. It should delegate that work to the core module.

## Data Flow

1. `run_user_stream` is called with a REST client, optional `RuntimeStateStore`, optional runtime DB path, and injected factories.
2. The loop module loads stored state and seeds an in-memory `StrategyState`.
3. Before each connection attempt, the loop module prewarms current positions and open order snapshots from REST.
4. The core module builds an event handler that receives parsed `UserStreamEvent` objects.
5. Each event is processed once:
   - write audit rows
   - write trade fill rows when present
   - write algo order rows when present
   - write account flow rows when present
   - update the tracked order-status map
   - apply the event to the strategy state
   - save the merged strategy snapshot
   - record a position snapshot
6. If the websocket runner exits successfully, the worker returns `0`.
7. If the websocket runner raises, the loop module logs the failure, sleeps with bounded backoff, and reconnects.

## Error Handling

The refactor should preserve current fail-soft behavior:

- trade-fill insert failures are logged and do not stop the worker
- algo-order insert failures are logged and do not stop the worker
- account-flow insert failures are logged and do not stop the worker
- prewarm failures for optional open-algo-order fetching should be ignored
- reconnect failures should continue to back off and retry

The split should not introduce new fatal paths in the event handler.

## Testing

The refactor should preserve the existing `stream_worker`-facing tests and add a small split-specific smoke test.

Expected coverage:

- `tests/test_stream_worker_split.py` to verify the new modules import and expose the expected entrypoint boundary
- `tests/test_stream_worker.py` to continue verifying `run_user_stream`
- `tests/test_main.py` to keep working with monkeypatch targets such as `momentum_alpha.stream_worker.extract_trade_fill`

Verification should include:

- focused stream-worker tests
- `python -m unittest discover -s tests -v`
- `git diff --check`

## Compatibility Notes

The following compatibility behavior must remain intact:

- `momentum_alpha.stream_worker.run_user_stream` stays importable
- existing monkeypatch targets on `momentum_alpha.stream_worker` continue to resolve
- those monkeypatch targets must still affect the runtime path taken by `run_user_stream`
- no change to `user_stream_worker_start` or `user_stream_event` audit event names
- no change to the persisted `StoredStrategyState` structure

## Outcome

After the split, `stream_worker.py` should read as a thin facade, `stream_worker_core.py` should hold the event-processing machinery, and `stream_worker_loop.py` should hold the connection lifecycle. The refactor should reduce coupling without changing runtime behavior.
