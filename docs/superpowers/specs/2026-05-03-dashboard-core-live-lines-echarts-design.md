# Dashboard Core Live Lines ECharts Design

**Date**: 2026-05-03
**Status**: Approved

## Overview

Refactor the realtime monitoring room's `CORE LIVE LINES` module from hand-written server-rendered SVG charts to Apache ECharts rendered in the browser.

The user selected a CDN integration. The dashboard currently has no JavaScript build pipeline, so this design keeps the server-rendered HTML model and loads a fixed ECharts browser bundle from CDN.

## Goals

1. Keep the current `CORE LIVE LINES` section, 2x2 layout, and card order.
2. Replace the four hand-written SVG line charts with ECharts line charts.
3. Reuse the existing `core_live_timeline` payload so all four charts continue to share one time domain.
4. Keep dashboard auto-refresh working by reinitializing charts after the live-room DOM is replaced.
5. Show the existing empty-state treatment when ECharts is unavailable or a metric has no usable points.

## Non-Goals

- Add a frontend bundler.
- Replace account overview, pie, bar, or timeline SVG helpers.
- Vendor ECharts into the repository.
- Redesign the live room layout.

## Architecture

`dashboard_render_panels_account.py` will render ECharts mount points and a JSON payload instead of inline SVG for `CORE LIVE LINES`.

`dashboard_assets_head.py` will load a fixed-version ECharts CDN script.

`dashboard_assets_scripts.py` will parse the payload, initialize one ECharts line chart per card, dispose old chart instances before refresh replacement, and resize charts with the window.

## Data Flow

The existing `build_dashboard_timeseries_payload(...)` output remains the source of truth:

- `core_live_timeline[].timestamp`
- `core_live_timeline[].equity`
- `core_live_timeline[].margin_usage_pct`
- `core_live_timeline[].position_count`
- `core_live_timeline[].open_risk`

Each chart filters usable numeric values for its own metric, but all charts compute their x-axis min/max from the shared timeline timestamps.

## Error Handling

- Missing or malformed JSON produces empty chart data.
- Missing `window.echarts` produces a chart-library-unavailable empty state.
- A metric with no numeric points keeps the waiting-for-data empty state.
- A single timestamp expands the time domain by 30 seconds on each side so the chart has a stable x-axis.

## Testing

Regression tests should verify:

1. `CORE LIVE LINES` renders four ECharts mount points and the JSON payload.
2. The live core panel no longer emits `chart-svg` hand-written SVG for those four cards.
3. The dashboard document includes the fixed ECharts CDN script.
4. The dashboard script initializes, disposes, and reinitializes live core charts after refresh.
5. The `Position Count` chart keeps an integer-axis marker for browser-side formatting.
