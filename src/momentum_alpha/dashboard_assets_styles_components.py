from __future__ import annotations


def _render_dashboard_component_styles() -> str:
    return """
    .section-frame { margin-bottom: 18px; }
    .section-topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
    .section-topbar .section-header { font-size: 0.86rem; color: var(--fg); letter-spacing: 0.04em; border: none; padding: 0; margin-bottom: 0; }
    .section-toggle { border: 1px solid var(--line); background: transparent; color: var(--fg-faint); border-radius: 7px; padding: 5px 10px; font-size: 0.64rem; font-weight: 650; letter-spacing: 0.1em; text-transform: uppercase; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
    .section-toggle:hover { color: var(--fg-muted); border-color: var(--line-strong); }
    .section-frame.is-collapsed .section-body { display: none; }
    .section-header { display: flex; align-items: center; gap: 8px; font-size: 0.66rem; font-weight: 700; color: var(--fg-muted); padding: 0; margin-bottom: 10px; border-bottom: none; text-transform: uppercase; letter-spacing: 0.13em; }
    .section-header::before { content: ''; width: 3px; height: 11px; border-radius: 1.5px; background: var(--accent); flex-shrink: 0; }
    .section-subtitle { color: var(--fg-faint); }
    .chart-container { background: var(--well); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 12px; margin-top: 8px; }
    .chart-svg, .bar-svg, .timeline-svg, .pie-svg { width: 100%; height: auto; display: block; }
    .chart-svg .grid-line { stroke: rgba(151,163,186,0.09); stroke-width: 1; }
    .chart-svg .axis-label { font-size: 9px; fill: var(--fg-faint); }
    .chart-svg .x-axis-line { stroke: rgba(151,163,186,0.22); stroke-width: 1; }
    .chart-svg .x-axis-label { font-size: 9px; fill: var(--fg-faint); }
    .chart-svg .chart-dot { }
    .chart-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 160px; color: var(--fg-faint); font-size: 0.8rem; gap: 8px; }
    .chart-empty-icon { font-size: 1.6rem; opacity: 0.35; }
    .pie-container { display: flex; align-items: center; gap: 20px; }
    .pie-svg { width: 140px; height: 140px; flex-shrink: 0; }
    .pie-slice { transition: transform 0.2s; transform-origin: center; }
    .pie-slice:hover { transform: scale(1.04); }
    .pie-legend { display: flex; flex-direction: column; gap: 6px; font-size: 0.75rem; }
    .legend-item { display: flex; align-items: center; gap: 8px; }
    .legend-color { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
    .legend-label { color: var(--fg-muted); flex: 1; }
    .legend-value { font-weight: 600; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .bar-svg .bar-rect { transition: opacity 0.2s; }
    .bar-svg .bar-rect:hover { opacity: 0.8; }
    .bar-svg .bar-value { font-size: 9px; fill: var(--fg); font-weight: 600; }
    .bar-svg .bar-label { font-size: 8px; fill: var(--fg-faint); }
    .timeline-svg .timeline-line { stroke: var(--line-strong); stroke-width: 1.5; stroke-dasharray: 4 4; }
    .timeline-svg .timeline-dot { transition: r 0.2s; }
    .timeline-svg .timeline-dot.current { animation: pulse-dot 1.5s infinite; }
    @keyframes pulse-dot { 0%, 100% { r: 12; } 50% { r: 15; } }
    .timeline-svg .timeline-label { font-size: 10px; fill: var(--fg); font-weight: 600; }
    .timeline-svg .timeline-time { font-size: 8px; fill: var(--fg-faint); }
    .health-grid { display: flex; flex-direction: column; gap: 8px; }
    .health-item { display: grid; grid-template-columns: 8px 1fr 80px 1fr; gap: 12px; align-items: center; padding: 10px 12px; background: var(--well); border: 1px solid var(--line); border-radius: var(--radius-sm); border-left: 3px solid var(--line-strong); }
    .health-item.status-ok { border-left-color: var(--success); }
    .health-item.status-fail { border-left-color: var(--danger); }
    .health-status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--fg-faint); }
    .status-ok .health-status-dot { background: var(--success); }
    .status-fail .health-status-dot { background: var(--danger); }
    .health-name { font-size: 0.78rem; font-weight: 600; font-family: var(--font-mono); }
    .health-status { font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }
    .status-ok .health-status { color: var(--success); }
    .status-fail .health-status { color: var(--danger); }
    .health-msg { font-size: 0.72rem; color: var(--fg-faint); font-family: var(--font-mono); word-break: break-word; }
    .decision-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .decision-item { background: var(--well); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 12px 14px; min-width: 0; }
    .decision-item.warning { border-color: rgba(240,180,41,0.4); background: var(--warning-bg); }
    .decision-item.danger { border-color: rgba(246,70,93,0.42); background: var(--danger-bg); }
    .decision-label { font-size: 0.62rem; color: var(--fg-faint); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 5px; font-weight: 650; }
    .decision-value { font-size: 1.02rem; font-weight: 650; word-break: break-word; font-family: var(--font-mono); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
    .signal-breakdown { display: flex; flex-direction: column; gap: 6px; }
    .signal-breakdown-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 7px 10px; background: var(--bg-panel); border: 1px solid var(--line); border-radius: 7px; }
    .signal-breakdown-label { font-size: 0.74rem; color: var(--fg-muted); word-break: break-word; font-family: var(--font-mono); }
    .signal-breakdown-count { min-width: 26px; padding: 1px 8px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-size: 0.74rem; font-weight: 700; text-align: center; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .signal-breakdown-empty { padding: 8px 10px; background: transparent; border: 1px dashed var(--line-strong); border-radius: 7px; font-size: 0.74rem; color: var(--fg-faint); }
    .signal-breakdown-empty.compact { padding: 6px 10px; display: inline-flex; align-items: center; min-height: auto; }
    .rotation-summary { margin-top: 10px; padding: 10px 12px; background: var(--well); border: 1px solid var(--line); border-radius: var(--radius-sm); }
    .rotation-summary-label { font-size: 0.62rem; color: var(--fg-faint); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 5px; font-weight: 650; }
    .rotation-summary-value { font-size: 0.8rem; color: var(--fg); word-break: break-word; font-family: var(--font-mono); }
    .source-tags { display: flex; flex-wrap: wrap; gap: 8px; }
    .source-tag { display: flex; align-items: center; gap: 8px; padding: 6px 11px; background: var(--well); border: 1px solid var(--line); border-radius: 7px; font-size: 0.74rem; }
    .source-tag span { color: var(--fg-faint); }
    .source-tag b { color: var(--accent); }
    .event-list { max-height: 320px; overflow-y: auto; }
    .event-item { display: grid; grid-template-columns: 1fr 130px minmax(0, 1.2fr); gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--line); font-size: 0.76rem; }
    .event-item:last-child { border-bottom: none; }
    .event-item.empty { color: var(--fg-faint); }
    .event-type { font-weight: 650; color: var(--accent); text-transform: uppercase; letter-spacing: 0.04em; font-size: 0.7rem; font-family: var(--font-mono); }
    .event-time { color: var(--fg-faint); font-size: 0.7rem; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .event-detail { color: var(--fg-muted); font-size: 0.72rem; word-break: break-word; font-family: var(--font-mono); }
    .refresh-indicator { position: fixed; bottom: 18px; right: 18px; padding: 8px 13px; background: var(--bg-card); border: 1px solid var(--line-strong); border-radius: 8px; font-size: 0.72rem; color: var(--fg-muted); display: flex; align-items: center; gap: 8px; box-shadow: var(--shadow); }
    .refresh-indicator.error { border-color: rgba(246,70,93,0.4); color: var(--danger); }
    .refresh-dot { width: 7px; height: 7px; background: var(--success); border-radius: 50%; animation: blink 1.2s infinite; }
    .refresh-indicator.error .refresh-dot { background: var(--danger); animation: none; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .positions-table-shell { width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--well); }
    .positions-table { width: 100%; min-width: 1120px; border-collapse: collapse; font-size: 0.72rem; font-variant-numeric: tabular-nums; }
    .positions-table th { padding: 9px 10px; color: var(--fg-faint); font-weight: 650; text-align: left; border-bottom: 1px solid var(--line-strong); background: var(--bg-panel); white-space: nowrap; font-size: 0.64rem; text-transform: uppercase; letter-spacing: 0.07em; }
    .positions-table td { padding: 9px 10px; border-bottom: 1px solid var(--line); color: var(--fg); white-space: nowrap; vertical-align: middle; font-family: var(--font-mono); }
    .positions-table tbody tr:last-child td { border-bottom: 0; }
    .positions-table tbody tr:hover { background: rgba(151,163,186,0.05); }
    .position-index-cell { color: var(--fg-faint); text-align: center; width: 34px; }
    .position-symbol-cell { color: var(--fg); font-family: var(--font-mono); font-weight: 700; letter-spacing: 0.02em; }
    .position-side { display: inline-flex; align-items: center; justify-content: center; min-width: 46px; padding: 2px 7px; border-radius: 5px; font-size: 0.64rem; font-weight: 700; letter-spacing: 0.05em; font-family: var(--font-ui); }
    .position-side-long { color: var(--success); background: var(--success-bg); border: 1px solid rgba(14,203,129,0.22); }
    .position-side-short { color: var(--danger); background: var(--danger-bg); border: 1px solid rgba(246,70,93,0.24); }
    .position-primary { display: block; font-weight: 650; }
    .position-subtle { display: block; margin-top: 3px; color: var(--fg-faint); font-size: 0.64rem; }
    .position-legs-summary { color: var(--fg-muted); border-bottom: 1px dotted rgba(151,163,186,0.4); cursor: help; }
    .value-positive { color: var(--success); font-weight: 650; }
    .value-negative { color: var(--danger); font-weight: 650; }
    .value-neutral { color: var(--fg-muted); }
    .metric-danger { color: var(--danger); }
    .metric-note { display: block; margin-top: 4px; font-size: 0.62rem; color: var(--fg-faint); }
    .positions-empty { color: var(--fg-faint); text-align: center; padding: 20px; font-size: 0.8rem; }
    .trade-history { max-height: 200px; overflow-y: auto; }
    .trade-history-empty { color: var(--fg-faint); text-align: center; padding: 20px; }
    .trade-row { display: grid; grid-template-columns: 80px 120px 60px 80px 100px 80px 80px; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--line); font-size: 0.73rem; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .trade-row:last-child { border-bottom: none; }
    .analytics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .review-analysis-shell { display: flex; flex-direction: column; gap: 12px; }
    .review-summary-strip {
      padding: 14px 16px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--bg-card);
    }
    .review-summary-ribbon {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 72px;
    }
    .review-summary-copy-block {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 240px;
      flex: 0 0 280px;
    }
    .review-summary-kicker { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
    .review-summary-copy { color: var(--fg-faint); font-size: 0.76rem; line-height: 1.45; max-width: 420px; }
    .review-summary-ribbon-items {
      display: flex;
      align-items: stretch;
      gap: 8px;
      flex-wrap: nowrap;
      overflow-x: auto;
      padding-bottom: 2px;
      scrollbar-width: thin;
      scrollbar-color: rgba(151,163,186,0.3) rgba(151,163,186,0.06);
    }
    .review-summary-ribbon-items::-webkit-scrollbar {
      height: 7px;
    }
    .review-summary-ribbon-items::-webkit-scrollbar-track {
      background: rgba(151,163,186,0.06);
      border-radius: 999px;
    }
    .review-summary-ribbon-items::-webkit-scrollbar-thumb {
      border-radius: 999px;
      background: rgba(151,163,186,0.3);
    }
    .review-summary-ribbon-item {
      min-width: 118px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--well);
      flex: 0 0 auto;
    }
    .review-summary-ribbon-label {
      font-size: 0.6rem;
      color: var(--fg-faint);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      font-weight: 650;
      margin-bottom: 6px;
      white-space: nowrap;
    }
    .review-summary-ribbon-value {
      font-size: 0.96rem;
      font-weight: 650;
      letter-spacing: -0.01em;
      white-space: nowrap;
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
    }
    .review-analysis-main-row { display: block; }
    .review-analysis-main { min-height: 100%; }
    .review-analysis-main .table-scroll {
      max-height: 620px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--well);
      scrollbar-width: thin;
      scrollbar-color: rgba(151,163,186,0.3) rgba(151,163,186,0.06);
    }
    .review-analysis-main .table-scroll::-webkit-scrollbar {
      width: 9px;
      height: 9px;
    }
    .review-analysis-main .table-scroll::-webkit-scrollbar-track {
      background: rgba(151,163,186,0.06);
      border-radius: 999px;
    }
    .review-analysis-main .table-scroll::-webkit-scrollbar-thumb {
      border-radius: 999px;
      background: rgba(151,163,186,0.3);
    }
    .review-analysis-main .table-scroll::-webkit-scrollbar-thumb:hover {
      background: rgba(151,163,186,0.45);
    }
    .review-analysis-main .round-trip-details,
    .review-analysis-main .round-trip-row-header { padding-left: 12px; padding-right: 12px; }
    .review-analysis-main .round-trip-row-header {
      position: sticky;
      top: 0;
      z-index: 2;
      background: var(--bg-panel);
      border-bottom: 1px solid var(--line-strong);
    }
    .review-analysis-main .round-trip-row-header span {
      padding-top: 8px;
      padding-bottom: 8px;
    }
    .review-analysis-evidence-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: start; }
    .review-analysis-card { display: flex; flex-direction: column; gap: 10px; }
    .review-section-label { display: flex; align-items: center; gap: 8px; font-size: 0.64rem; font-weight: 700; color: var(--fg-muted); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 8px; }
    .review-section-label::before { content: ''; width: 3px; height: 10px; border-radius: 1.5px; background: var(--accent); flex-shrink: 0; }
    .live-control-frame { display: flex; flex-direction: column; gap: 12px; }
    .live-control-frame .dashboard-section { margin-bottom: 0; }
    .live-risk-band,
    .live-core-lines-band,
    .live-signal-band {
      width: 100%;
      padding: 0;
      border: none;
      border-radius: 0;
      background: transparent;
    }
    .live-core-lines-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 12px;
      margin-bottom: 12px;
    }
    .live-core-lines-summary {
      color: var(--fg-faint);
      font-size: 0.73rem;
      letter-spacing: 0;
      max-width: 520px;
      line-height: 1.4;
    }
    .live-core-lines-summary[data-core-live-summary-state='ready'] {
      color: var(--success);
    }
    .live-core-lines-summary[data-core-live-summary-state='partial'] {
      color: var(--warning);
    }
    .live-core-lines-summary[data-core-live-summary-state='empty'] {
      color: var(--fg-faint);
    }
    .live-core-lines-summary[data-core-live-summary-state='unavailable'] {
      color: var(--danger);
    }
    .core-live-range-controls {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 6px;
      flex-wrap: wrap;
      flex: 0 0 auto;
    }
    .core-live-range-chip {
      min-width: 42px;
      justify-content: center;
    }
    .live-core-lines-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .live-core-line-card {
      min-height: 248px;
    }
    .live-core-chart {
      width: 100%;
      height: 190px;
      min-height: 190px;
    }
    .live-core-chart .chart-empty {
      min-height: 190px;
    }
    .live-core-chart[data-core-live-chart-state='loading'] .chart-empty {
      color: var(--fg-faint);
      opacity: 0.88;
    }
    .live-core-chart[data-core-live-chart-state='empty'] .chart-empty {
      color: var(--fg-faint);
    }
    .live-core-chart[data-core-live-chart-state='unavailable'] .chart-empty {
      color: var(--danger);
    }
    .live-core-line-card--open-risk {
      border-color: rgba(246,70,93,0.28);
    }
    .live-core-line-card--open-risk .section-header {
      color: var(--danger);
    }
    .live-core-line-card--open-risk .section-header::before {
      background: var(--danger);
    }
    .live-account-risk-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    .live-decision-grid { display: flex; flex-direction: column; gap: 16px; align-items: stretch; }
    .live-decision-grid .execution-flow-panel { margin-bottom: 0; }
    .live-card-shell { margin-bottom: 0; }
    .live-ops-grid { display: grid; grid-template-columns: 1fr 0.95fr; gap: 12px; align-items: start; }
    .system-analysis-shell { display: flex; flex-direction: column; gap: 12px; }
    .system-summary-strip { padding: 14px 16px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--bg-card); }
    .system-summary-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; margin-bottom: 12px; }
    .system-summary-kicker { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
    .system-summary-copy { color: var(--fg-faint); font-size: 0.76rem; max-width: 520px; text-align: right; }
    .system-summary-strip .decision-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .system-health-path { margin: 2px 0 10px; padding: 7px 11px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--well); color: var(--fg-muted); font-size: 0.7rem; font-family: var(--font-mono); word-break: break-all; }
    .system-health-panel { display: flex; flex-direction: column; gap: 10px; }
    .system-console-grid { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr); gap: 12px; align-items: stretch; }
    .system-console-card { display: flex; flex-direction: column; gap: 10px; }
    .system-console-events { display: flex; flex-direction: column; gap: 10px; min-height: 100%; }
    .table-scroll { overflow-x: auto; }
    .desktop-only { display: block; }
    .mobile-only { display: none; }
    .analytics-table.desktop-only { display: block; }
    .analytics-card-list.mobile-only { display: none; }
    .trade-history.desktop-only { display: block; }
    .trade-card-list.mobile-only { display: none; }
    .analytics-table { max-height: 220px; overflow-y: auto; }
    .analytics-row { display: grid; grid-template-columns: 1.4fr 0.8fr 0.8fr 0.8fr 0.7fr; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--line); font-size: 0.74rem; align-items: center; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .analytics-row.analytics-row-header { color: var(--fg-faint); font-size: 0.62rem; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700; font-family: var(--font-ui); }
    .round-trip-view.desktop-only { display: block; }
    .round-trip-details, .round-trip-card { border-bottom: 1px solid var(--line); }
    .round-trip-details:last-child, .round-trip-card:last-child { border-bottom: none; }
    .round-trip-details > summary, .round-trip-card > summary { display: grid; list-style: none; cursor: pointer; }
    .round-trip-details > summary:hover { background: rgba(151,163,186,0.05); }
    .round-trip-details[open] > summary { background: rgba(151,163,186,0.04); }
    .round-trip-details > summary::-webkit-details-marker, .round-trip-card > summary::-webkit-details-marker { display: none; }
    .round-trip-summary, .round-trip-row-header { grid-template-columns: 1.4fr 0.85fr 0.85fr 0.45fr 0.7fr 0.65fr 0.7fr 0.65fr; }
    .round-trip-summary { padding: 9px 0; font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: 0.74rem; }
    .round-trip-row-header { color: var(--fg-faint); font-size: 0.62rem; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700; }
    .round-trip-detail-body { padding: 0 0 12px 12px; }
    .round-trip-leg-table { overflow-x: auto; padding-top: 8px; }
    .round-trip-leg-row { display: grid; grid-template-columns: 0.45fr 0.7fr 0.9fr 0.6fr 0.8fr 0.85fr 0.7fr 0.7fr 0.8fr 0.7fr 0.9fr; gap: 8px; min-width: 1080px; padding: 6px 0; border-bottom: 1px solid var(--line); font-size: 0.7rem; align-items: center; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .round-trip-leg-row:last-child { border-bottom: none; }
    .round-trip-leg-row-header { color: var(--fg-faint); font-size: 0.62rem; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700; font-family: var(--font-ui); }
    .round-trip-leg-empty { color: var(--fg-faint); font-size: 0.74rem; padding: 8px 0 0 0; }
    .analytics-row:last-child { border-bottom: none; }
    .analytics-main { color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .daily-review-panel { display: flex; flex-direction: column; gap: 12px; padding: 0; }
    .daily-review-toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding: 12px 14px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--bg-card); }
    .daily-review-toolbar-left { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
    .daily-review-toolbar-note { max-width: 340px; color: var(--fg-faint); font-size: 0.74rem; line-height: 1.45; text-align: right; }
    .daily-review-date-form { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .daily-review-date-label { color: var(--fg-faint); font-size: 0.68rem; font-weight: 650; letter-spacing: 0.08em; text-transform: uppercase; }
    .daily-review-date-select { min-width: 150px; padding: 6px 11px; border-radius: 7px; border: 1px solid var(--line-strong); background: var(--well); color: var(--fg); font-size: 0.74rem; font-weight: 650; font-family: var(--font-mono); outline: none; }
    .daily-review-date-select:focus { border-color: var(--border-accent); box-shadow: 0 0 0 3px var(--accent-soft); }
    .daily-review-nav { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
    .daily-review-nav-link, .daily-review-nav-current { display: inline-flex; align-items: center; justify-content: center; min-height: 28px; padding: 4px 11px; border-radius: 7px; font-size: 0.7rem; font-weight: 650; letter-spacing: 0.03em; }
    .daily-review-nav-link { color: var(--fg-muted); border: 1px solid var(--line); background: transparent; text-decoration: none; transition: border-color 0.15s, background 0.15s, color 0.15s; }
    .daily-review-nav-link:hover { color: var(--fg); border-color: var(--border-accent); background: var(--accent-soft); }
    .daily-review-nav-link-disabled { color: var(--fg-faint); border-color: var(--line); background: transparent; }
    .daily-review-nav-current { color: var(--accent); border: 1px solid var(--border-accent); background: var(--accent-soft); }
    .daily-review-nav-link-latest { color: var(--success); border-color: rgba(14,203,129,0.26); background: var(--success-bg); }
    .daily-review-history-summary { display: flex; flex-direction: column; gap: 10px; padding: 12px 14px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--bg-card); }
    .daily-review-history-summary-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
    .daily-review-history-title { font-size: 0.86rem; font-weight: 700; color: var(--fg); }
    .daily-review-history-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }
    .daily-review-history-kpi { min-height: 76px; background: var(--well); border-color: var(--line); }
    .daily-review-headline { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 14px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--bg-card); }
    .daily-review-headline.positive { border-color: rgba(14,203,129,0.3); background: var(--success-bg); }
    .daily-review-headline.negative { border-color: rgba(246,70,93,0.3); background: var(--danger-bg); }
    .daily-review-eyebrow { font-size: 0.64rem; font-weight: 700; color: var(--accent); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 5px; }
    .daily-review-title { font-size: 1.05rem; font-weight: 700; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .daily-review-support { margin-top: 4px; color: var(--fg-muted); font-size: 0.76rem; }
    .daily-review-kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
    .daily-review-kpi { min-height: 82px; padding: 12px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--well); overflow: hidden; }
    .daily-review-table { max-height: 520px; overflow: auto; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--well); padding: 0 12px; }
    .daily-review-grid { display: grid; grid-template-columns: minmax(126px, 1fr) minmax(88px, 0.7fr) minmax(126px, 1fr) minmax(88px, 0.75fr) minmax(88px, 0.75fr) minmax(108px, 0.85fr) minmax(68px, 0.52fr) minmax(70px, 0.52fr); min-width: 1040px; }
    .daily-review-row { gap: 10px; padding: 9px 0; font-size: 0.72rem; font-family: var(--font-mono); font-variant-numeric: tabular-nums; border-bottom: 1px solid var(--line); }
    .daily-review-row:last-child { border-bottom: none; }
    .daily-review-row-header { position: sticky; top: 0; z-index: 1; background: var(--bg-panel); padding-top: 10px; color: var(--fg-faint); font-size: 0.62rem; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700; font-family: var(--font-ui); }
    .daily-review-impact-positive { color: var(--success); font-weight: 650; }
    .daily-review-impact-negative { color: var(--danger); font-weight: 650; }
    .daily-review-status { display: inline-flex; align-items: center; justify-content: center; min-width: 44px; padding: 2px 8px; border-radius: 999px; font-size: 0.64rem; font-weight: 700; letter-spacing: 0; font-family: var(--font-ui); }
    .daily-review-status-ok { color: var(--success); background: var(--success-bg); border: 1px solid rgba(14,203,129,0.22); }
    .daily-review-status-warn { color: var(--warning); background: var(--warning-bg); border: 1px solid rgba(240,180,41,0.28); }
    .trade-time { color: var(--fg-faint); }
    .trade-symbol { color: var(--fg); font-weight: 600; }
    .side-buy { color: var(--success); }
    .side-sell { color: var(--danger); }
    .status-filled { color: var(--success); }
    .status-pending { color: var(--warning); }
    .trade-card-list, .analytics-card-list { display: flex; flex-direction: column; gap: 10px; }
    .analytics-card { padding: 12px; background: var(--well); border: 1px solid var(--line); border-radius: var(--radius-sm); }
    .analytics-card-main { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; font-size: 0.84rem; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .analytics-card-meta { display: flex; flex-wrap: wrap; gap: 10px; color: var(--fg-faint); font-size: 0.72rem; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .config-panel { background: var(--well); border: 1px solid var(--line); padding: 12px 14px; border-radius: var(--radius-sm); font-size: 0.78rem; }
    .config-row { display: flex; justify-content: space-between; gap: 12px; padding: 5px 0; border-bottom: 1px solid var(--line); }
    .config-row:last-child { border-bottom: none; }
    .config-row span:last-child { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-weight: 600; }
    .config-label { color: var(--fg-faint); font-family: var(--font-ui); font-weight: 400; }
    .config-value-true { color: var(--warning); }
    .config-value-false { color: var(--fg-muted); }
    .dashboard-section { margin-bottom: 18px; padding: 16px; background: var(--bg-panel); border: 1px solid var(--line); border-radius: var(--radius); }
    .charts-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .chart-card { background: var(--bg-card); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 14px; min-width: 0; }
    .account-metrics-panel { padding: 16px; }
    .account-snapshot-panel { padding: 16px; margin-bottom: 18px; }
    .account-snapshot-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .account-snapshot-card { background: var(--well); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 12px 14px; min-height: 104px; }
    .account-snapshot-label { font-size: 0.62rem; color: var(--fg-faint); font-weight: 650; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 6px; }
    .account-snapshot-value { font-size: 1.1rem; font-weight: 650; font-family: var(--font-mono); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
    .account-snapshot-sub { margin-top: 6px; font-size: 0.72rem; color: var(--fg-faint); line-height: 1.45; }
    .execution-flow-panel { padding: 16px; margin-bottom: 18px; }
    .execution-flow-grid { display: flex; flex-direction: column; gap: 12px; }
    .execution-flow-group { display: flex; flex-direction: column; gap: 8px; }
    .execution-flow-group + .execution-flow-group { padding-top: 10px; border-top: 1px solid var(--line); }
    .execution-flow-group-label { font-size: 0.62rem; color: var(--accent); letter-spacing: 0.12em; text-transform: uppercase; margin: 0 0 2px; }
    .execution-flow-row {
      display: grid;
      grid-template-columns: minmax(170px, 0.9fr) minmax(0, 1.25fr) minmax(160px, 0.8fr);
      gap: 12px;
      align-items: center;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--well);
      transition: border-color 0.15s, background 0.15s;
    }
    .execution-flow-row-primary {
      border-color: var(--line-strong);
      background: var(--bg-card);
    }
    .execution-flow-row-support {
      border-color: var(--line);
      background: var(--well);
    }
    .execution-flow-row:hover {
      border-color: var(--line-strong);
      background: rgba(151,163,186,0.05);
    }
    .execution-flow-label {
      font-size: 0.62rem;
      color: var(--fg-faint);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      font-weight: 650;
      margin-bottom: 0;
      line-height: 1.3;
    }
    .execution-flow-body {
      display: flex;
      flex-direction: column;
      gap: 3px;
      min-width: 0;
    }
    .execution-flow-row-primary .execution-flow-primary { font-size: 0.94rem; }
    .execution-flow-primary { font-size: 0.88rem; font-weight: 650; word-break: break-word; line-height: 1.25; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .execution-flow-secondary { margin-top: 0; font-size: 0.7rem; color: var(--fg-faint); word-break: break-word; line-height: 1.35; font-family: var(--font-mono); }
    .execution-flow-detail { margin-top: 0; font-size: 0.72rem; color: var(--fg-muted); line-height: 1.35; word-break: break-word; text-align: right; }
    .system-diagnostics-panel, .system-warning-panel { margin-bottom: 0; padding: 0; background: transparent; border: none; border-radius: 0; }
    .system-summary-strip .system-diagnostics-panel > .section-header { display: none; }
    .system-warning-panel { margin-top: 12px; }
    .system-warning-list { display: flex; flex-direction: column; gap: 8px; }
    .system-warning-item { padding: 10px 13px; background: var(--warning-bg); border: 1px solid rgba(240,180,41,0.26); border-radius: var(--radius-sm); color: var(--warning); font-size: 0.76rem; line-height: 1.5; word-break: break-word; }
    .account-panel-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 14px; }
    .account-panel-title { font-size: 0.9rem; font-weight: 700; letter-spacing: 0.04em; }
    .account-panel-subtitle { font-size: 0.74rem; color: var(--fg-faint); margin-top: 5px; max-width: 680px; }
    .account-panel-note { font-size: 0.74rem; color: var(--warning); max-width: 420px; line-height: 1.45; padding: 9px 12px; background: var(--warning-bg); border: 1px solid rgba(240,180,41,0.26); border-radius: var(--radius-sm); }
    .account-range-switches, .account-metric-switches { display: flex; flex-wrap: wrap; gap: 6px; }
    .account-chip { border: 1px solid var(--line); background: transparent; color: var(--fg-muted); border-radius: 7px; padding: 5px 11px; font-size: 0.7rem; font-weight: 600; font-family: var(--font-mono); cursor: pointer; transition: color 0.15s, border-color 0.15s, background 0.15s; }
    .account-chip:hover { color: var(--fg); border-color: var(--line-strong); }
    .account-chip.active { color: var(--accent); border-color: var(--border-accent); background: var(--accent-soft); }
    .account-overview-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 14px; }
    .account-overview-card { background: var(--well); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 12px 14px; min-height: 96px; }
    .account-overview-card-highlight { background: var(--bg-card); border-color: var(--line-strong); }
    .account-overview-label { font-size: 0.62rem; color: var(--fg-faint); font-weight: 650; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 6px; }
    .account-overview-value { font-size: 1.12rem; font-weight: 650; font-family: var(--font-mono); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
    .account-overview-sub { font-size: 0.7rem; color: var(--fg-faint); margin-top: 6px; }
    .account-main-panel { background: var(--bg-card); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 14px; }
    .account-main-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 12px; }
    .account-main-meta { display: flex; gap: 14px; font-size: 0.7rem; color: var(--fg-faint); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .account-main-chart { min-height: 280px; }
    .account-chart-svg { width: 100%; height: auto; display: block; }
    .account-grid-line { stroke: rgba(151,163,186,0.09); stroke-width: 1; }
    .account-axis-label { fill: var(--fg-faint); font-size: 10px; }
    .account-series-line { fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .account-series-area { opacity: 0.16; }
    .account-last-dot { }
    .decision-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .decision-half { background: var(--well); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 12px; }
    .bottom-row { display: grid; grid-template-columns: 200px 1fr 1fr; gap: 12px; }
    .decision-grid-stack { grid-template-columns: 1fr 1fr; }
    .decision-support { margin-top: 5px; color: var(--fg-faint); font-size: 0.72rem; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .bottom-col { }
    """
