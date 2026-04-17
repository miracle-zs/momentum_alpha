# Dashboard Tabbed Architecture Design

Date: 2026-04-17

## Goal

Restructure the current runtime dashboard from a single long monitoring page into a tabbed workspace with four stable views:

- `Overview`
- `Execution`
- `Performance`
- `System`

This change is explicitly staged. The first milestone keeps a single dashboard entry point and introduces tabs inside the existing page shell. After the tab structure proves stable in real use, `Overview` will become the true landing page and the other tabs can evolve into dedicated detail pages.

The design optimizes for three things:

1. Faster real-time monitoring on the default view
2. Clear separation between trading decisions, execution diagnostics, historical performance, and runtime operations
3. Minimal migration cost from the current Python-rendered dashboard implementation

## Problem Statement

The current dashboard already has stronger hierarchy than the original version, but it still mixes distinct usage modes in one scrolling surface:

- live monitoring
- execution diagnosis
- performance review
- runtime/system diagnosis

These modes are not consumed the same way.

Live monitoring needs compact, high-signal, low-scroll content that can be re-checked repeatedly during operation.

Execution and performance sections are analysis-oriented. They are valuable, but they dilute first-screen decision-making when presented alongside active trading state.

System sections serve an operations/debugging role. They are important, but they belong to a different mental model than live trade decisions.

If all of this remains in one long page, the dashboard becomes harder to scan, harder to extend, and harder to eventually split into dedicated views.

## Proposed Direction

Introduce a top-level tab bar inside the existing dashboard shell and group content into four view-specific tab panels.

This is a deliberate intermediate architecture:

- Keep one route and one server-rendered HTML document for now
- Separate content by task type immediately
- Preserve the existing auto-refresh and local interaction model
- Prepare each tab to become an independent page later with minimal rewrite

This avoids a disruptive route-level redesign while still fixing the information architecture problem now.

## Approaches Considered

### Approach A: Keep one long page and rely on collapse controls

Pros:

- Lowest implementation cost
- Minimal structural change
- No navigation model to introduce

Cons:

- Does not actually separate user tasks
- Live monitoring still competes with analysis and ops content
- Future split into dedicated pages remains expensive because content boundaries stay blurry

This is no longer sufficient as the primary architecture.

### Approach B: Immediate multi-page split

Pros:

- Cleanest information architecture
- Clear route boundaries from day one
- Best long-term shape

Cons:

- Higher implementation cost now
- Requires route design, cross-page navigation, and duplication risk too early
- More disruptive to the current dashboard code path

This is directionally correct but too aggressive as the next step.

### Approach C: Single entry point with tabs, then later split into pages

Pros:

- Fixes the information architecture now
- Preserves the existing dashboard shell and refresh model
- Gives each content area a stable boundary before route-level extraction
- Minimizes churn in the current Python-rendered implementation

Cons:

- Still one route for the short term
- Requires discipline to keep tabs from collapsing back into one giant template

This is the recommended approach.

## Recommended Information Architecture

### Overview

Purpose:

- Answer "what is happening right now?"

Content:

- top metric cards
- live overview / active signal
- risk and deployment summary
- leader rotation / current sequence
- active positions
- compact account metrics panel

Rules:

- no execution tables
- no round-trip history
- no raw system event streams
- keep this tab optimized for repeat scanning, not for reading depth

### Execution

Purpose:

- Answer "how well are orders and exits being executed?"

Content:

- execution summary
- recent fills
- stop slippage analysis

Rules:

- keep content focused on order path quality
- no long-term strategy performance metrics here

### Performance

Purpose:

- Answer "how is the strategy performing over recent history?"

Content:

- round trips
- win rate
- profit factor
- avg win / avg loss
- expectancy
- average hold time
- current streak
- trade count

Rules:

- this tab is analytical, not operational
- no runtime health or config data here

### System

Purpose:

- Answer "is the runtime healthy and what operational context explains current behavior?"

Content:

- system health
- recent events
- event sources
- strategy config / runtime operations

Rules:

- keep this as the ops/diagnostics tab
- do not mix current trading decision summaries here beyond what is strictly necessary for diagnosis

## Navigation Design

The dashboard will remain on the current route during the first phase.

Add a top tab bar below the page header and global status area.

Tabs:

- `Overview`
- `Execution`
- `Performance`
- `System`

Behavior:

- tab state is driven by URL query param such as `?tab=overview`, `?tab=execution`, `?tab=performance`, and `?tab=system`
- default tab is `overview`
- refresh keeps the active tab
- local refresh and server-rendered full reload both honor the same active tab
- direct links to specific tabs are supported immediately

The query-param choice is intentional. It allows a later transition to dedicated pages without changing the conceptual navigation model.

## Rendering Strategy

The current dashboard is server-rendered in `src/momentum_alpha/dashboard.py`. The next implementation should not treat tabs as a purely visual hide/show layer inside one giant template string.

Instead, the rendering flow should be split into a shell and per-tab content renderers.

Recommended structure:

- `render_dashboard_shell(...)`
- `render_dashboard_tab_bar(active_tab)`
- `render_dashboard_overview_tab(snapshot, ...)`
- `render_dashboard_execution_tab(snapshot, ...)`
- `render_dashboard_performance_tab(snapshot, ...)`
- `render_dashboard_system_tab(snapshot, ...)`

The shell remains responsible for:

- global page structure
- header
- status badge
- refresh controls
- tab navigation
- client-side refresh wiring

Each tab renderer remains responsible only for that tab's content.

This is the key design choice that makes later extraction into dedicated pages cheap.

## Data Boundaries

No new database tables or API families are required for the first phase.

The current snapshot payload already contains enough data to populate all four tabs:

- runtime summary
- recent account snapshots
- trade fills
- trade round trips
- stop exit summaries
- signal decisions
- event/source summaries
- health/config/runtime metadata

The implementation should reuse the current snapshot builder and only reorganize which sections consume which existing data.

If lightweight tab-specific JSON endpoints are useful later, they should be added only after the tab boundaries are stable in production use.

## Client-Side Behavior

The current dashboard already supports:

- in-place refresh
- preserved account metric/range selections
- collapsible sections

The tab design should extend this behavior consistently:

- preserve active tab across refreshes
- do not reset account metric/range state when switching tabs
- keep section collapse state scoped to the tab content where it belongs
- only initialize interactive controls for the currently active tab content

The client script should treat tab selection as first-class page state, not as a styling afterthought.

## Phase Plan

### Phase 1: Tabbed single-page workspace

Scope:

- add tab bar
- reorganize content into the four tabs
- move existing sections without changing their underlying metrics logic
- preserve refresh behavior and local state
- keep the existing single route

Success criteria:

- default `Overview` can be used alone as a live monitoring view
- no execution/performance/system detail pollutes the overview tab
- direct links like `?tab=performance` work

### Phase 2: Stabilize tab boundaries

Scope:

- observe real usage
- refine what belongs in each tab
- remove any cross-tab content leakage
- tighten naming and layout inside each tab

Success criteria:

- the four tabs each answer one distinct question
- the team can describe each tab's purpose in one sentence

### Phase 3: Promote Overview to true landing page

Scope:

- make `Overview` the default dashboard landing page
- move other tabs toward dedicated pages or routes

Likely route evolution:

- `/dashboard` or `/monitor`
- `/dashboard/execution`
- `/dashboard/performance`
- `/dashboard/system`

Success criteria:

- the current tab renderers can be reused with only shell/routing changes
- route extraction does not require rethinking content boundaries

## Minimal Implementation Scope

To keep risk low, the first implementation should avoid:

- introducing a frontend framework
- redesigning snapshot APIs
- changing runtime storage
- changing metrics definitions
- reworking account chart logic unless required for tab placement

The change should focus on:

- view architecture
- content grouping
- navigation state
- renderer decomposition

## Testing Strategy

The existing `tests/test_dashboard.py` pattern should remain the primary safety net.

Add coverage for:

- default tab rendering
- query-param-driven active tab rendering
- overview includes only monitoring sections
- execution tab includes execution-only sections
- performance tab includes performance-only sections
- system tab includes system-only sections
- active tab persists across refresh logic

Tests should verify both:

- presence of expected tab content
- absence of content that belongs to other tabs

This is important because the goal is architectural separation, not just visual grouping.

## Risks and Mitigations

### Risk: Tabs become a cosmetic layer over the old long page

Mitigation:

- split render functions by tab immediately
- treat each tab as a bounded unit

### Risk: Overview keeps accumulating secondary detail

Mitigation:

- enforce the "what is happening right now?" rule
- keep analysis/history out of this tab by default

### Risk: Query-param/tab refresh state becomes brittle

Mitigation:

- centralize active-tab parsing and rendering
- test active-tab persistence explicitly

### Risk: Future route extraction still feels expensive

Mitigation:

- design the current tab renderers as future page bodies
- keep shell and content separated now

## Decision

Adopt the staged architecture:

1. Tabbed dashboard now
2. Stabilize boundaries through usage
3. Promote `Overview` into the true landing page later
4. Extract other tabs into dedicated pages when justified

This delivers the architectural benefit immediately while keeping implementation risk and migration cost low.
