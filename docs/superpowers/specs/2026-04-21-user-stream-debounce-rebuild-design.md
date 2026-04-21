# User Stream Debounced Rebuild Design

**Date**: 2026-04-21  
**Status**: Proposed

## Overview

Trigger `rebuild-trade-analytics` from the `user-stream` process after new `trade_fills` are written, with a **30-second debounce window**.

The goal is to keep `trade_round_trips` and the review-room summary close to real time without rebuilding on every individual fill. This is a correctness and freshness fix for the reporting pipeline, not a strategy change.

The debounce window means:

- the first new fill schedules a rebuild
- additional fills arriving within 30 seconds reuse the same pending rebuild
- once 30 seconds pass without a new fill, the rebuild runs once

## Confirmed User Decision

The user confirmed the following direction:

- use `user-stream` as the trigger point
- debounce window is `30s`
- do not use a standalone high-frequency timer as the primary mechanism

## Problem Statement

`trade_fills` is written continuously by `user-stream`, but `trade_round_trips` is only updated when `rebuild-trade-analytics` runs explicitly.

That leaves the dashboard and review views stale after later fills arrive. In practice, the summary can remain stuck on an earlier closed trade, even though newer fills already exist in the database.

The current behavior is acceptable for batch rebuilds, but not for operational review when the user expects the latest closed trade to be visible shortly after fills settle.

## Goals

1. Rebuild `trade_round_trips` automatically after new fills land in `trade_fills`.
2. Use a 30-second debounce so one trade split across multiple fills only triggers one rebuild.
3. Keep the rebuild asynchronous relative to fill persistence so `user-stream` does not block on analytics work.
4. Preserve current behavior for non-fill events.
5. Keep failure handling fail-soft: a rebuild failure should be logged and should not crash the user-stream worker.
6. Keep the existing manual `rebuild-trade-analytics` command working.

## Non-Goals

This design does not:

- change the trade reconstruction algorithm
- change the `trade_round_trips` schema
- change the dashboard rendering logic
- add a new timer-based polling service
- make `user-stream` depend on the dashboard

The only behavior change is when and how rebuilds are triggered.

## Approaches Considered

### Approach A: Trigger Rebuild Directly in the Fill Insert Path

Pros:

- simplest control flow
- minimal new surface area

Cons:

- risk of blocking fill processing
- repeated fills can cause repeated rebuilds
- hard to coalesce bursts cleanly

This is not recommended.

### Approach B: `user-stream` In-Process Debounced Rebuild Scheduler

Pros:

- event-driven
- near-real-time freshness
- coalesces bursts of fills into one rebuild
- keeps the rebuild trigger close to the source of truth

Cons:

- adds a small background scheduling mechanism inside the worker process
- rebuild state is process-local, so a worker restart can drop a pending scheduled rebuild

This is the recommended approach.

### Approach C: Add A Separate High-Frequency Rebuild Timer

Pros:

- easy to reason about
- independent of fill processing code

Cons:

- polling-based instead of event-driven
- still stale between timer ticks
- runs even when no new fills arrived

This is a fallback option, not the primary design.

## Recommended Architecture

Add a small debounce scheduler to the `user-stream` process.

The scheduler should:

1. receive a signal after `trade_fills` inserts succeed
2. remember whether a rebuild is already pending
3. push the rebuild deadline forward on every new fill during the debounce window
4. run `rebuild-trade-analytics` once the worker has been quiet for 30 seconds
5. clear the pending state after the rebuild completes or fails

The scheduler should be invoked only after fill persistence succeeds, so analytics rebuilds are based on committed data.

## Data Flow

1. `user-stream` receives a websocket event.
2. The worker extracts a `trade_fill`, if present.
3. The fill is written to `trade_fills`.
4. The worker notifies the debounce scheduler that a rebuild is needed.
5. If another fill arrives within 30 seconds, the scheduler delays execution and still keeps only one pending rebuild.
6. When the worker has been quiet for 30 seconds, the scheduler invokes the existing `rebuild-trade-analytics` logic.
7. The rebuild reconstructs `trade_round_trips` from the committed fills.

## Failure Handling

The scheduler should be conservative:

- if a fill insert fails, do not schedule a rebuild for that fill
- if the rebuild command fails, log the error and keep the worker alive
- if a second fill arrives while a rebuild is already running, mark that another rebuild is needed after the current one finishes
- if the process restarts, the pending in-memory debounce state can be lost; the next fill will reschedule a rebuild

The design should not try to persist the debounce timer state in SQLite. That would add complexity without clear value for this use case.

## Testing

The implementation should add tests for:

1. multiple fills inside 30 seconds result in one rebuild call
2. a fill after the debounce window starts a new rebuild cycle
3. a failed rebuild logs an error and does not crash `user-stream`
4. a rebuild is only scheduled after successful fill persistence
5. non-fill events do not schedule rebuilds

The tests should mock the scheduler clock so the debounce behavior is deterministic.

## Operational Notes

The current one-shot `rebuild-trade-analytics` command stays available for manual recovery.

The new scheduler is the primary freshness path for normal operation. If the process is restarted or temporarily interrupted, a manual rebuild still remains the backstop.
