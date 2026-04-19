# SQLite Runtime Store Design

**Date:** 2026-04-15

**Goal:** Move audit, health, notification, and dashboard query data to SQLite so `runtime.db` is the live recovery and query source.

## Decision

Adopt SQLite as the primary store for:

- audit events
- dashboard queries
- health snapshots

Keep `runtime.db` as the authoritative runtime state store for:

- previous leader restore
- local position restore
- processed user-stream ids
- tracked order statuses

## Why This Split

`runtime.db` is small, direct, and tightly coupled to live recovery. Replacing it with file state would add migration risk without much operational benefit.

Audit and dashboard data are different:

- append-heavy
- query-oriented
- used for replay, statistics, and UI rendering

That makes them a better fit for SQLite than JSONL files.

## Migration Strategy

### Phase 1

Short transition window:

- keep audit events in SQLite
- switch dashboard reads to SQLite first

This lowers risk because:

- dashboard can be verified against known-good JSONL behavior
- runtime still has the existing file trail if the DB layer has issues

### Phase 2

After SQLite writes are proven stable:

- stop treating file-based audit output as the primary source
- keep the runtime database as the only source of truth for structured live data

The user already approved this end state, but the implementation should still use a brief dual-write stage to de-risk rollout.

## Proposed Database

Default path:

- `/root/momentum_alpha/var/runtime.db`

Local default for development:

- `./var/runtime.db`

## Schema

### `audit_events`

Primary append-only event table.

Columns:

- `id INTEGER PRIMARY KEY`
- `timestamp TEXT NOT NULL`
- `event_type TEXT NOT NULL`
- `payload_json TEXT NOT NULL`
- `source TEXT`

Indexes:

- `idx_audit_events_timestamp`
- `idx_audit_events_event_type_timestamp`

### `health_snapshots`

Periodic health verdicts used for dashboard and alert history.

Columns:

- `id INTEGER PRIMARY KEY`
- `timestamp TEXT NOT NULL`
- `overall_status TEXT NOT NULL`
- `details_json TEXT NOT NULL`

Indexes:

- `idx_health_snapshots_timestamp`

### `dashboard_cache`

Optional denormalized latest-summary table. Not required for v1. Prefer computing current summary from `audit_events` and runtime state tables first.

## Write Path

### Poll worker

When `poll` records:

- `poll_worker_start`
- `poll_tick`
- `tick_result`
- `broker_submit`
- `stop_replacements`

write each event to SQLite through a small repository layer.

### User-stream worker

When `user-stream` records:

- `user_stream_worker_start`
- `user_stream_event`

write each event to SQLite through the same repository abstraction.

### Health checks

When health checks run, optionally persist one row into `health_snapshots`.

## Dashboard Read Path

The dashboard should stop reading file-based audit output directly.

Instead it should:

1. query recent audit events from SQLite
2. aggregate event counts from SQLite
3. compute latest timestamps from SQLite
4. still read runtime state from SQLite
5. still use the existing health builder until health snapshots become useful enough to query directly

## Error Handling

- SQLite connection failures must not break live trading; the runtime should log and continue
- event inserts should be best-effort in the early migration stage
- corrupted DB files should be surfaced clearly in the dashboard and logs

## Operational Notes

- SQLite is appropriate because this system runs on one server
- WAL mode should be enabled for safer concurrent read/write behavior
- schema creation should happen automatically on startup or through a small bootstrap helper

## Testing Scope

Add tests for:

- schema bootstrap
- audit event inserts
- querying recent events and counts
- dashboard snapshot builder using SQLite instead of JSONL
- failure tolerance when the DB write path raises
