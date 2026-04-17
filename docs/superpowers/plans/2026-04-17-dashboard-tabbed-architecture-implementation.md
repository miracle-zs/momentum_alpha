# Dashboard Tabbed Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the current dashboard into four stable tabs, `Overview`, `Execution`, `Performance`, and `System`, while preserving the existing server-rendered route, live refresh behavior, and current data sources. The first milestone is an internal architectural split, not a route split.

**Architecture:** Keep a single dashboard endpoint and snapshot builder, but refactor the renderer into a shell plus per-tab renderers. Drive active tab selection through a `tab` query parameter, persist it across in-place refreshes, and narrow each tab to one operational purpose. Keep the implementation incrementally extractable so `Overview` can later become the true landing page and the other tabs can evolve into dedicated detail pages.

**Tech Stack:** Python, unittest, existing server-rendered HTML/CSS/JS dashboard in `src/momentum_alpha/dashboard.py`, current runtime snapshot/store plumbing

---

## File Map

- Modify: `src/momentum_alpha/dashboard.py`
  - Responsibility: split the dashboard renderer into shell, tab navigation, and per-tab content sections; preserve live-refresh and local UI state.
- Modify: `tests/test_dashboard.py`
  - Responsibility: verify tab routing, content grouping, tab persistence, and refresh behavior.

## Task 1: Introduce Tab Selection as a First-Class Dashboard Input

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests for active tab parsing and default behavior**

Add focused tests in `tests/test_dashboard.py` for a small helper that normalizes the requested tab:

```python
def test_normalize_dashboard_tab_defaults_to_overview(self) -> None:
    from momentum_alpha.dashboard import normalize_dashboard_tab

    self.assertEqual(normalize_dashboard_tab(None), "overview")
    self.assertEqual(normalize_dashboard_tab(""), "overview")
    self.assertEqual(normalize_dashboard_tab("unknown"), "overview")


def test_normalize_dashboard_tab_accepts_known_tabs(self) -> None:
    from momentum_alpha.dashboard import normalize_dashboard_tab

    self.assertEqual(normalize_dashboard_tab("overview"), "overview")
    self.assertEqual(normalize_dashboard_tab("execution"), "execution")
    self.assertEqual(normalize_dashboard_tab("performance"), "performance")
    self.assertEqual(normalize_dashboard_tab("system"), "system")
```

- [ ] **Step 2: Run the targeted tests and confirm failure**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_normalize_dashboard_tab_defaults_to_overview tests.test_dashboard.DashboardTests.test_normalize_dashboard_tab_accepts_known_tabs
```

Expected: FAIL because tab normalization does not exist yet.

- [ ] **Step 3: Implement tab normalization and thread it into the dashboard entry path**

In `src/momentum_alpha/dashboard.py`:

- add a `DASHBOARD_TABS` constant:

```python
DASHBOARD_TABS = ("overview", "execution", "performance", "system")
```

- add:

```python
def normalize_dashboard_tab(value: str | None) -> str:
    tab = (value or "").strip().lower()
    return tab if tab in DASHBOARD_TABS else "overview"
```

- update the dashboard request/render entry point so the active tab is derived from the request query parameter and passed into rendering rather than inferred client-side.

- [ ] **Step 4: Re-run the targeted tests**

Run the same `python3 -m unittest ...` command from Step 2 and verify PASS.

## Task 2: Split Rendering Into Shell Plus Per-Tab Renderers

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing structural tests for tabbed rendering**

Add renderer-level tests that verify:

- the shell always renders the tab bar
- only the active tab’s content appears in the output
- content currently on the page is reassigned to the correct tab

Suggested test shape:

```python
def test_render_dashboard_overview_tab_contains_live_monitoring_sections(self) -> None:
    html = render_dashboard(snapshot=build_sample_snapshot(), active_tab="overview")
    self.assertIn("Overview", html)
    self.assertIn("Live Overview", html)
    self.assertIn("Risk &amp; Deployment", html)
    self.assertIn("Active Positions", html)
    self.assertNotIn("Recent Fills", html)
    self.assertNotIn("Stop Slippage", html)


def test_render_dashboard_execution_tab_contains_execution_sections_only(self) -> None:
    html = render_dashboard(snapshot=build_sample_snapshot(), active_tab="execution")
    self.assertIn("Execution", html)
    self.assertIn("Recent Fills", html)
    self.assertIn("Stop Slippage", html)
    self.assertNotIn("Active Positions", html)
    self.assertNotIn("System Health", html)
```

Mirror this pattern for `performance` and `system`.

- [ ] **Step 2: Run the targeted tab-rendering tests**

Run:

```bash
python3 -m unittest tests.test_dashboard -k tab
```

Expected: FAIL because the page is still rendered as one long surface.

- [ ] **Step 3: Refactor the renderer into explicit sections**

In `src/momentum_alpha/dashboard.py`, extract:

- `render_dashboard_shell(...)`
- `render_dashboard_tab_bar(active_tab: str)`
- `render_dashboard_overview_tab(...)`
- `render_dashboard_execution_tab(...)`
- `render_dashboard_performance_tab(...)`
- `render_dashboard_system_tab(...)`

Implementation constraints:

- keep current section markup and styling primitives where possible
- move existing blocks without changing their data contracts unless necessary
- ensure the shell owns:
  - page header
  - status badge
  - refresh controls
  - tab bar
  - top-level scripts/styles
- ensure each tab renderer owns only its content blocks

- [ ] **Step 4: Reassign current content into the correct tabs**

Move sections according to the approved structure:

- `overview`:
  - top metric cards
  - live overview / active signal
  - risk and deployment
  - leader rotation
  - active positions
  - compact account metrics
- `execution`:
  - execution summary
  - recent fills
  - stop slippage analysis
- `performance`:
  - round trips and strategy performance analytics
- `system`:
  - system health
  - recent events
  - event sources
  - runtime config / operational context

- [ ] **Step 5: Re-run the targeted tab tests**

Run:

```bash
python3 -m unittest tests.test_dashboard -k tab
```

Expected: PASS

## Task 3: Preserve Tab State Across Navigation and In-Place Refresh

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests for tab links and state persistence hooks**

Add tests that assert:

- the tab bar renders links containing `?tab=overview|execution|performance|system`
- the active tab has an active state marker/class
- the client script records and restores the tab parameter during refresh

Suggested assertions:

```python
def test_dashboard_tab_bar_renders_query_param_links(self) -> None:
    html = render_dashboard(snapshot=build_sample_snapshot(), active_tab="performance")
    self.assertIn('?tab=overview', html)
    self.assertIn('?tab=execution', html)
    self.assertIn('?tab=performance', html)
    self.assertIn('?tab=system', html)
    self.assertIn('dashboard-tab is-active', html)
```

- [ ] **Step 2: Run the targeted state tests**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_dashboard_tab_bar_renders_query_param_links
```

Expected: FAIL until tab navigation markup exists.

- [ ] **Step 3: Update client-side refresh logic to preserve the active tab**

Refactor the existing JS in `src/momentum_alpha/dashboard.py` so:

- manual refresh uses the current URL, including the `tab` query param
- background refresh fetches the current URL rather than a bare pathname
- DOM replacement swaps only the tab content area plus shared live regions
- account metric/range selections, collapse state, and active tab all survive refresh
- clicking a tab updates the URL without breaking direct reload behavior

Implementation note:

- prefer using the URL as the single source of truth for active tab
- only use `localStorage` as a fallback for transient UI continuity, not as the primary navigation model

- [ ] **Step 4: Re-run the targeted tests**

Run the command from Step 2 and any adjacent refresh-related dashboard tests that already exist.

## Task 4: Tighten Tab-Specific UX So Overview Becomes a True First Screen

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests that guard content separation**

Add assertions that the default `overview` output does not include:

- trade history tables
- stop-slippage detail tables
- raw event stream panels
- system diagnostics blocks

Also add tests confirming the `system` tab does not duplicate `active positions` or other live-trading decision panels.

- [ ] **Step 2: Run the separation tests**

Run:

```bash
python3 -m unittest tests.test_dashboard -k overview
```

Expected: FAIL if overview still leaks long-form analysis or ops content.

- [ ] **Step 3: Adjust labels, section headings, and density per tab**

In `src/momentum_alpha/dashboard.py`:

- make `Overview` read like a landing workspace, not a subset of a long report
- ensure `Execution`, `Performance`, and `System` headings and empty states are specific to their use case
- keep `Overview` visually compact and scan-oriented
- keep data-heavy tables confined to `Execution` and `Performance`
- keep operational diagnostics confined to `System`

- [ ] **Step 4: Re-run the overview-focused tests**

Run the command from Step 2 and verify PASS.

## Task 5: Verify Responsive and Refresh Behavior Did Not Regress

**Files:**
- Modify: `tests/test_dashboard.py`
- Modify: `src/momentum_alpha/dashboard.py` only if required by failing tests

- [ ] **Step 1: Extend regression coverage for mobile and refresh surfaces**

Add tests covering:

- mobile card views still render on tabs that use them
- tabbed refresh does not remove the manual refresh button
- active collapse state storage still targets section identifiers correctly
- tab switches do not corrupt account metric/range state markup

- [ ] **Step 2: Run the full dashboard test module**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
```

Expected: PASS

- [ ] **Step 3: Run the full test suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS

## Task 6: Finish the Milestone Cleanly

**Files:**
- Modify: `docs/superpowers/specs/2026-04-17-dashboard-tabbed-architecture-design.md` only if implementation materially changes the agreed design

- [ ] **Step 1: Review for extraction readiness**

Before closing, confirm the code now has:

- one shell renderer
- four tab renderers with clear boundaries
- no tab containing obvious off-purpose content
- no refresh path that silently resets to `overview` when a different tab is active

- [ ] **Step 2: Document any intentional deviations**

If implementation differs from the design doc, update the spec with a short “Implementation Notes” section rather than letting code and design drift.

- [ ] **Step 3: Commit the milestone**

Run:

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py docs/superpowers/specs/2026-04-17-dashboard-tabbed-architecture-design.md docs/superpowers/plans/2026-04-17-dashboard-tabbed-architecture-implementation.md
git commit -m "Implement dashboard tabbed architecture"
```

## Risks and Checks

- Risk: tab extraction becomes only visual and leaves one giant render function in place.
  - Check: the renderer is physically split into shell plus per-tab functions.
- Risk: in-place refresh resets tab state or replaces the wrong DOM region.
  - Check: refresh fetches the current URL and tests assert query-param preservation.
- Risk: overview remains overloaded and fails to become a usable first screen.
  - Check: tests explicitly assert absence of execution/performance/system sections from the default overview output.
- Risk: mobile/table layouts regress because sections moved between renderers.
  - Check: retain and rerun existing mobile rendering tests alongside new tab coverage.

## Verification Commands

Run these before claiming completion:

```bash
python3 -m unittest tests.test_dashboard -v
python3 -m unittest discover -s tests -v
```
