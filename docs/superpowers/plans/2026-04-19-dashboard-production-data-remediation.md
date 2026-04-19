# Dashboard Production Data Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the production dashboard so deployed data under `/momentum-alpha/` is complete, range-consistent, and operationally trustworthy for complete-trade and stop-slippage analysis.

**Architecture:** Keep the current server-rendered dashboard and SQLite runtime store, but split the remediation into three layers: frontend state correctness, runtime analytics correctness, and operations/backfill correctness. Account timeseries remains range-driven, complete-trade analytics move to full-history scope by default, and stop-slippage becomes dependent on robust `ALGO_UPDATE` persistence plus an explicit rebuild path for historical rows.

**Tech Stack:** Python 3.12, unittest, SQLite runtime store, server-rendered HTML/CSS/JS in `src/momentum_alpha/dashboard.py`, CLI entrypoint in `src/momentum_alpha/main.py`

---

## Worktree Note

This plan was written from the primary worktree. Execute it from a dedicated git worktree if you want isolation from unrelated local edits.

## File Map

- Modify: `src/momentum_alpha/dashboard.py`
  - Responsibility: subpath-safe API fetches, stable range/query state, correct performance-tab data scope, and summary/detail consistency.
- Modify: `src/momentum_alpha/user_stream.py`
  - Responsibility: robust `ALGO_UPDATE` parsing and extraction for stop metadata persistence.
- Modify: `src/momentum_alpha/runtime_store.py`
  - Responsibility: stop-trigger resolution, trade analytics rebuild behavior, and optional diagnostics for completeness checks.
- Modify: `src/momentum_alpha/health.py`
  - Responsibility: analytics freshness and completeness health checks.
- Modify: `src/momentum_alpha/main.py`
  - Responsibility: expose a supported CLI command for trade-analytics rebuild and wire health reporting.
- Modify: `tests/test_dashboard.py`
  - Responsibility: regression coverage for range behavior, performance-tab scope, and rendered state.
- Modify: `tests/test_user_stream.py`
  - Responsibility: regression coverage for `ALGO_UPDATE` parsing fallbacks.
- Modify: `tests/test_runtime_store.py`
  - Responsibility: regression coverage for stop-trigger resolution and rebuild payload integrity.
- Modify: `tests/test_main.py`
  - Responsibility: CLI coverage for trade-analytics rebuild.
- Modify: `tests/test_health.py`
  - Responsibility: analytics completeness warnings.
- Modify: `docs/live-ops-checklist.md`
  - Responsibility: document the required production rebuild and smoke-check sequence.

## Task 1: Fix Dashboard Subpath And Query-State Handling

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add failing coverage for preserved range state**

Add or extend tests in `tests/test_dashboard.py` to verify:

```python
self.assertIn('href="?tab=execution&range=ALL"', html)
self.assertIn('data-account-range="ALL"', html)
self.assertNotIn("fetch(`/api/dashboard/timeseries", html)
```

The rendered dashboard HTML must preserve the active query state and must not hardcode the root API path.

- [ ] **Step 2: Run the targeted dashboard tests**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
```

Expected:

- at least one new assertion fails before the implementation change

- [ ] **Step 3: Make the dashboard path and state subpath-safe**

In `src/momentum_alpha/dashboard.py`:

- replace the absolute fetch path in `loadAccountRange()` with a URL builder relative to the current page path
- preserve `range` in tab href generation
- render the active account-range button from current state instead of hardcoding `1D`
- stop refresh logic from forcing stale `localStorage` over server/query state on first reload

Target shape:

```javascript
function buildDashboardApiUrl(endpoint, range) {
  const url = new URL(window.location.href);
  url.searchParams.set("range", range);
  return `${url.pathname.replace(/\/$/, "")}${endpoint}?range=${encodeURIComponent(range)}`;
}
```

and:

```python
def render_dashboard_tab_bar(active_tab: str, account_range_key: str) -> str:
    href = f"?tab={tab}&range={account_range_key}"
```

- [ ] **Step 4: Re-run the dashboard tests**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
```

Expected:

- range-preservation and rendered-state tests pass

- [ ] **Step 5: Commit**

Run:

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "fix: preserve dashboard range state under subpath deploys"
```

## Task 2: Make Complete-Trade Analytics Full-History And Internally Consistent

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add failing coverage for performance-tab trade scope**

Extend `tests/test_dashboard.py` with assertions that a snapshot containing old and recent round trips still exposes complete-trade analytics in the performance view.

Target assertions:

```python
self.assertEqual(
    {trip["round_trip_id"] for trip in snapshot["recent_trade_round_trips"]},
    {"PLAYUSDT:old", "PLAYUSDT:recent"},
)
self.assertIn("Trade Count", html)
self.assertIn("PLAYUSDT:old", html)
```

Use the existing `load_dashboard_snapshot()` and `render_dashboard_html()` test patterns already present in the file.

- [ ] **Step 2: Run the targeted dashboard tests**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_load_dashboard_snapshot_uses_account_range_for_trade_round_trips -v
```

Expected:

- the new performance-scope assertions fail before implementation

- [ ] **Step 3: Decouple complete-trade analytics from account-chart range**

In `src/momentum_alpha/dashboard.py`:

- keep `account_range_key` for account snapshots and account chart data
- load complete-trade analytics from full history by default
- compute `Complete Trade Summary`, closed-trade detail, leg-count aggregate, and leg-index aggregate from the same round-trip list
- remove the hardcoded `range_key="1D"` summary call

Target shape:

```python
recent_trade_round_trips = fetch_trade_round_trips_for_range(
    path=runtime_db_file,
    now=now,
    range_key="ALL",
)

trader_metrics = build_trader_summary_metrics_from_round_trips(
    recent_trade_round_trips,
    position_details=position_details,
)
```

If a new helper is introduced, keep it local to `dashboard.py` and make the range source explicit.

- [ ] **Step 4: Re-run the dashboard tests**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
```

Expected:

- performance summary and detail tests agree on trade population

- [ ] **Step 5: Commit**

Run:

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "fix: align performance analytics with full trade history"
```

## Task 3: Persist Production `ALGO_UPDATE` Events Reliably

**Files:**
- Modify: `src/momentum_alpha/user_stream.py`
- Modify: `src/momentum_alpha/main.py`
- Modify: `tests/test_user_stream.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add failing tests for tolerant `ALGO_UPDATE` extraction**

Add coverage in `tests/test_user_stream.py` for an event that has:

- `event_type = "ALGO_UPDATE"`
- `clientAlgoId`
- `triggerPrice`
- missing or null `algoId`

Target assertions:

```python
self.assertEqual(event.client_algo_id, "ma_260419170000_MOVEUSDT_b00s")
self.assertEqual(event.trigger_price, Decimal("0.0201"))
self.assertIsNone(event.algo_id)
```

Then add extraction coverage asserting the event is still persistable:

```python
result = extract_algo_order_event(event)
self.assertIsNotNone(result)
self.assertEqual(result["client_algo_id"], "ma_260419170000_MOVEUSDT_b00s")
```

- [ ] **Step 2: Add failing CLI/runtime coverage**

Extend `tests/test_main.py` so a `run_user_stream()` pass that receives such an event still calls `insert_algo_order()` once.

Target assertion:

```python
self.assertEqual(insert_calls[0]["client_algo_id"], "ma_260419170000_MOVEUSDT_b00s")
```

- [ ] **Step 3: Run the targeted tests**

Run:

```bash
python3 -m unittest tests.test_user_stream tests.test_main -v
```

Expected:

- the new `ALGO_UPDATE` persistence assertions fail before implementation

- [ ] **Step 4: Broaden parsing and persistence rules**

In `src/momentum_alpha/user_stream.py` and `src/momentum_alpha/main.py`:

- keep parsing top-level `algoId`, `clientAlgoId`, and `triggerPrice`
- allow `extract_algo_order_event()` to return a row when there is enough stop identity to persist, even if `algo_id` is missing
- prefer `client_algo_id` as the minimum identity for strategy stop tracking
- log or count skipped `ALGO_UPDATE` events instead of silently discarding them

Target extraction rule:

```python
if event.event_type != "ALGO_UPDATE":
    return None
if event.algo_id is None and event.client_algo_id is None:
    return None
```

- [ ] **Step 5: Re-run the targeted tests**

Run:

```bash
python3 -m unittest tests.test_user_stream tests.test_main -v
```

Expected:

- tolerant `ALGO_UPDATE` parsing and persistence tests pass

- [ ] **Step 6: Commit**

Run:

```bash
git add src/momentum_alpha/user_stream.py src/momentum_alpha/main.py tests/test_user_stream.py tests/test_main.py
git commit -m "fix: persist stop algo updates without strict algo id dependency"
```

## Task 4: Restore Stop-Slippage And Leg Analytics Through Rebuild Support

**Files:**
- Modify: `src/momentum_alpha/runtime_store.py`
- Modify: `src/momentum_alpha/main.py`
- Modify: `tests/test_runtime_store.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add failing runtime-store coverage for stop-trigger resolution**

Extend `tests/test_runtime_store.py` so a stop-loss round trip with persisted algo metadata produces:

```python
self.assertEqual(stop_exit["trigger_price"], "106")
self.assertEqual(stop_exit["slippage_pct"], "0")
```

Also keep assertions that leg payload data remains present:

```python
self.assertGreater(trip["payload"]["leg_count"], 0)
self.assertIsNotNone(trip["payload"]["peak_cumulative_risk"])
```

- [ ] **Step 2: Add failing CLI coverage for rebuild command**

In `tests/test_main.py`, add a new command test:

```python
exit_code = cli_main(
    argv=["rebuild-trade-analytics", "--runtime-db-file", "/tmp/runtime.db"],
    rebuild_trade_analytics_fn=fake_rebuild_trade_analytics,
)
self.assertEqual(exit_code, 0)
```

- [ ] **Step 3: Run the targeted tests**

Run:

```bash
python3 -m unittest tests.test_runtime_store tests.test_main -v
```

Expected:

- rebuild-command and stop-trigger assertions fail before implementation

- [ ] **Step 4: Add a supported rebuild entrypoint**

In `src/momentum_alpha/main.py`:

- add a `rebuild-trade-analytics` subcommand
- resolve the runtime DB path
- call `rebuild_trade_analytics(path=...)`
- print a small success message for operators

Target shape:

```python
rebuild_trade_analytics_parser = subparsers.add_parser("rebuild-trade-analytics")
rebuild_trade_analytics_parser.add_argument("--runtime-db-file", required=True)
```

and:

```python
if args.command == "rebuild-trade-analytics":
    rebuild_trade_analytics(path=Path(os.path.abspath(args.runtime_db_file)))
    print("trade-analytics-rebuilt")
    return 0
```

- [ ] **Step 5: Re-run the targeted tests**

Run:

```bash
python3 -m unittest tests.test_runtime_store tests.test_main -v
```

Expected:

- rebuild-command and analytics-persistence tests pass

- [ ] **Step 6: Commit**

Run:

```bash
git add src/momentum_alpha/runtime_store.py src/momentum_alpha/main.py tests/test_runtime_store.py tests/test_main.py
git commit -m "feat: add supported trade analytics rebuild command"
```

## Task 5: Surface Analytics Completeness In Health Checks

**Files:**
- Modify: `src/momentum_alpha/health.py`
- Modify: `tests/test_health.py`
- Modify: `docs/live-ops-checklist.md`

- [ ] **Step 1: Add failing health-check coverage**

Extend `tests/test_health.py` with a case where:

- runtime DB is fresh
- `algo_orders` is empty
- recent stop exits exist with null trigger coverage

Target assertions:

```python
self.assertEqual(report.overall_status, "WARN")
self.assertIn("analytics", {item.name for item in report.items})
```

- [ ] **Step 2: Run the targeted tests**

Run:

```bash
python3 -m unittest tests.test_health -v
```

Expected:

- the new analytics-completeness check fails before implementation

- [ ] **Step 3: Add an analytics-quality health check**

In `src/momentum_alpha/health.py`, add a new report item that evaluates:

- whether recent `algo_orders` exist
- whether recent stop exits have null `trigger_price` coverage
- whether recent trade round trips have zero or missing leg payloads

Target shape:

```python
HealthCheckItem(
    name="analytics",
    status="WARN",
    message="algo_orders_empty recent_stop_trigger_coverage=0/6 round_trips_with_legs=0/20",
)
```

Use `WARN`, not `FAIL`, unless the dashboard would become completely unusable.

- [ ] **Step 4: Update the live ops checklist**

Add a short production section to `docs/live-ops-checklist.md` covering:

- running `python3 -m momentum_alpha.main rebuild-trade-analytics --runtime-db-file ...`
- checking the dashboard after backfill
- verifying stop-slippage and performance-leg tables specifically

- [ ] **Step 5: Re-run the targeted tests**

Run:

```bash
python3 -m unittest tests.test_health -v
```

Expected:

- analytics health warnings are emitted correctly

- [ ] **Step 6: Commit**

Run:

```bash
git add src/momentum_alpha/health.py tests/test_health.py docs/live-ops-checklist.md
git commit -m "feat: warn when dashboard analytics completeness degrades"
```

## Task 6: Regression And Production Smoke Validation

**Files:**
- No code changes required unless a regression is found

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
python3 -m unittest tests.test_dashboard tests.test_user_stream tests.test_runtime_store tests.test_main tests.test_health -v
```

Expected:

- all targeted tests pass

- [ ] **Step 2: Run the full test suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected:

- no regressions in unrelated areas

- [ ] **Step 3: Run the production backfill**

On the server, run:

```bash
cd /root/momentum_alpha
./.venv/bin/python -m momentum_alpha.main rebuild-trade-analytics --runtime-db-file /root/momentum_alpha/var/runtime.db
```

Expected:

- the command exits `0`
- no traceback is printed

- [ ] **Step 4: Perform live smoke checks**

Verify these pages after deployment:

```text
http://43.153.134.252/momentum-alpha/
http://43.153.134.252/momentum-alpha/?tab=execution
http://43.153.134.252/momentum-alpha/?tab=performance
```

Expected:

- range switching does not generate `404`
- `Latest Stop Order` is no longer permanently `n/a`
- recent stop exits can show non-null `STOP` and `SLIP %`
- `Performance` no longer defaults to an empty closed-trade history when historical rows exist
- historical rows show leg counts and peak risk after backfill

- [ ] **Step 5: Final commit if smoke checks require follow-up fixes**

Run only if Step 4 required an additional patch:

```bash
git add -A
git commit -m "fix: complete production dashboard remediation"
```

## Handoff Notes

- Do not mark the work complete until a rebuild has been run against the production runtime DB.
- If a raw production `ALGO_UPDATE` payload differs from the expected shape, fix the parser first, then rerun the rebuild and smoke checks.
- If historical rows still lack leg metrics after rebuild, inspect whether the original fills or stop identifiers were missing at ingest time. That is a data-availability problem, not necessarily a rebuild bug.
