from __future__ import annotations


def _render_dashboard_component_styles() -> str:
    return """
    .section-frame { margin-bottom: 20px; }
    .section-topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
    .section-toggle { border: 1px solid var(--border); background: rgba(255,255,255,0.03); color: var(--fg-muted); border-radius: 999px; padding: 6px 11px; font-size: 0.68rem; letter-spacing: 0.12em; text-transform: uppercase; cursor: pointer; }
    .section-frame.is-collapsed .section-body { display: none; }
    .chart-container { background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); padding: 12px; margin-top: 8px; }
    .chart-svg, .bar-svg, .timeline-svg, .pie-svg { width: 100%; height: auto; display: block; }
    .chart-svg .grid-line { stroke: rgba(100,130,170,0.1); stroke-width: 1; }
    .chart-svg .axis-label { font-size: 9px; fill: var(--fg-muted); }
    .chart-svg .x-axis-line { stroke: rgba(180,200,230,0.28); stroke-width: 1; }
    .chart-svg .x-axis-label { font-size: 9px; fill: var(--fg-muted); }
    .chart-svg .chart-dot { filter: drop-shadow(0 0 4px currentColor); }
    .chart-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 160px; color: var(--fg-muted); font-size: 0.85rem; gap: 8px; }
    .chart-empty-icon { font-size: 2rem; opacity: 0.3; }
    .pie-container { display: flex; align-items: center; gap: 20px; }
    .pie-svg { width: 140px; height: 140px; flex-shrink: 0; }
    .pie-slice { transition: transform 0.2s; transform-origin: center; }
    .pie-slice:hover { transform: scale(1.05); }
    .pie-legend { display: flex; flex-direction: column; gap: 6px; font-size: 0.75rem; }
    .legend-item { display: flex; align-items: center; gap: 8px; }
    .legend-color { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
    .legend-label { color: var(--fg-muted); flex: 1; }
    .legend-value { font-weight: 600; }
    .bar-svg .bar-rect { transition: opacity 0.2s; }
    .bar-svg .bar-rect:hover { opacity: 0.8; }
    .bar-svg .bar-value { font-size: 9px; fill: var(--fg); font-weight: 600; }
    .bar-svg .bar-label { font-size: 8px; fill: var(--fg-muted); }
    .timeline-svg .timeline-line { stroke: var(--border); stroke-width: 2; stroke-dasharray: 4 4; }
    .timeline-svg .timeline-dot { filter: drop-shadow(0 0 6px currentColor); transition: r 0.2s; }
    .timeline-svg .timeline-dot.current { animation: pulse-dot 1.5s infinite; }
    @keyframes pulse-dot { 0%, 100% { r: 12; } 50% { r: 16; } }
    .timeline-svg .timeline-label { font-size: 10px; fill: var(--fg); font-weight: 600; }
    .timeline-svg .timeline-time { font-size: 8px; fill: var(--fg-muted); }
    .health-grid { display: flex; flex-direction: column; gap: 10px; }
    .health-item { display: grid; grid-template-columns: 8px 1fr 80px 1fr; gap: 12px; align-items: center; padding: 12px 14px; background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); border-left: 3px solid transparent; }
    .health-item.status-ok { border-left-color: var(--success); }
    .health-item.status-fail { border-left-color: var(--danger); }
    .health-status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--fg-muted); }
    .status-ok .health-status-dot { background: var(--success); box-shadow: 0 0 8px var(--success); }
    .status-fail .health-status-dot { background: var(--danger); box-shadow: 0 0 8px var(--danger); }
    .health-name { font-size: 0.8rem; font-weight: 500; }
    .health-status { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; }
    .status-ok .health-status { color: var(--success); }
    .status-fail .health-status { color: var(--danger); }
    .health-msg { font-size: 0.75rem; color: var(--fg-muted); }
    .decision-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
    .decision-item { background: rgba(0,0,0,0.25); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 14px; }
    .decision-item.warning { border-color: rgba(255,184,0,0.35); box-shadow: 0 0 0 1px rgba(255,184,0,0.08); }
    .decision-item.danger { border-color: rgba(255,68,102,0.38); box-shadow: 0 0 0 1px rgba(255,68,102,0.1); }
    .decision-label { font-size: 0.68rem; color: var(--fg-muted); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 6px; }
    .decision-value { font-size: 1rem; font-weight: 600; word-break: break-word; }
    .signal-breakdown { display: flex; flex-direction: column; gap: 8px; }
    .signal-breakdown-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; background: rgba(0,0,0,0.18); border: 1px solid var(--border); border-radius: var(--radius-sm); }
    .signal-breakdown-label { font-size: 0.8rem; color: var(--fg); word-break: break-word; }
    .signal-breakdown-count { min-width: 28px; padding: 2px 8px; border-radius: 999px; background: rgba(0,212,255,0.12); color: var(--accent); font-size: 0.78rem; font-weight: 700; text-align: center; }
    .signal-breakdown-empty { padding: 10px 12px; background: rgba(0,0,0,0.18); border: 1px dashed var(--border); border-radius: var(--radius-sm); font-size: 0.78rem; color: var(--fg-muted); }
    .signal-breakdown-empty.compact { padding: 8px 10px; display: inline-flex; align-items: center; min-height: auto; }
    .rotation-summary { margin-top: 10px; padding: 10px 12px; background: rgba(0,0,0,0.18); border: 1px solid var(--border); border-radius: var(--radius-sm); }
    .rotation-summary-label { font-size: 0.68rem; color: var(--fg-muted); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 6px; }
    .rotation-summary-value { font-size: 0.82rem; color: var(--fg); word-break: break-word; }
    .source-tags { display: flex; flex-wrap: wrap; gap: 8px; }
    .source-tag { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: rgba(0,212,255,0.08); border: 1px solid rgba(0,212,255,0.2); border-radius: 100px; font-size: 0.75rem; }
    .source-tag span { color: var(--fg-muted); }
    .source-tag b { color: var(--accent); }
    .event-list { max-height: 320px; overflow-y: auto; }
    .event-item { display: grid; grid-template-columns: 1fr 130px minmax(0, 1.2fr); gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 0.78rem; }
    .event-item:last-child { border-bottom: none; }
    .event-item.empty { color: var(--fg-muted); }
    .event-type { font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.04em; }
    .event-time { color: var(--fg-muted); font-size: 0.72rem; }
    .event-detail { color: var(--fg); font-size: 0.72rem; word-break: break-word; }
    .refresh-indicator { position: fixed; bottom: 20px; right: 20px; padding: 10px 16px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 100px; font-size: 0.75rem; color: var(--fg-muted); display: flex; align-items: center; gap: 8px; }
    .refresh-indicator.error { border-color: rgba(255,68,102,0.35); color: var(--danger); }
    .refresh-dot { width: 8px; height: 8px; background: var(--success); border-radius: 50%; animation: blink 1s infinite; }
    .refresh-indicator.error .refresh-dot { background: var(--danger); animation: none; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .positions-table-shell { width: 100%; overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius-sm); background: rgba(0,0,0,0.24); }
    .positions-table { width: 100%; min-width: 1120px; border-collapse: collapse; font-size: 0.72rem; }
    .positions-table th { padding: 9px 10px; color: var(--fg-muted); font-weight: 600; text-align: left; border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.025); white-space: nowrap; }
    .positions-table td { padding: 9px 10px; border-bottom: 1px solid rgba(100,130,170,0.12); color: var(--fg); white-space: nowrap; vertical-align: middle; }
    .positions-table tbody tr:last-child td { border-bottom: 0; }
    .positions-table tbody tr:hover { background: rgba(0,212,255,0.045); }
    .position-index-cell { color: var(--fg-muted); text-align: center; width: 34px; }
    .position-symbol-cell { color: var(--accent); font-family: 'JetBrains Mono', 'SF Mono', monospace; font-weight: 700; letter-spacing: 0.02em; }
    .position-side { display: inline-flex; align-items: center; justify-content: center; min-width: 46px; padding: 2px 7px; border-radius: 6px; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.04em; }
    .position-side-long { color: var(--success); background: rgba(0,255,136,0.08); border: 1px solid rgba(0,255,136,0.18); }
    .position-side-short { color: var(--danger); background: rgba(255,68,102,0.08); border: 1px solid rgba(255,68,102,0.2); }
    .position-primary { display: block; font-weight: 700; }
    .position-subtle { display: block; margin-top: 3px; color: var(--fg-muted); font-size: 0.64rem; }
    .position-legs-summary { color: var(--fg-muted); border-bottom: 1px dotted rgba(180,200,230,0.35); cursor: help; }
    .value-positive { color: var(--success); font-weight: 700; }
    .value-negative { color: var(--danger); font-weight: 700; }
    .value-neutral { color: var(--fg-muted); }
    .metric-danger { color: var(--danger); }
    .metric-note { display: block; margin-top: 4px; font-size: 0.62rem; color: var(--fg-muted); }
    .positions-empty { color: var(--fg-muted); text-align: center; padding: 20px; }
    .trade-history { max-height: 200px; overflow-y: auto; }
    .trade-history-empty { color: var(--fg-muted); text-align: center; padding: 20px; }
    .trade-row { display: grid; grid-template-columns: 80px 120px 60px 80px 100px 80px 80px; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 0.75rem; }
    .trade-row:last-child { border-bottom: none; }
    .analytics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .review-analysis-shell { display: flex; flex-direction: column; gap: 16px; }
    .review-summary-strip {
      padding: 14px 16px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: linear-gradient(180deg, rgba(245,210,138,0.05), rgba(0,0,0,0.16));
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
    .review-summary-copy { color: var(--fg-muted); font-size: 0.78rem; line-height: 1.45; max-width: 420px; }
    .review-summary-ribbon-items {
      display: flex;
      align-items: stretch;
      gap: 10px;
      flex-wrap: nowrap;
      overflow-x: auto;
      padding-bottom: 2px;
      scrollbar-width: thin;
      scrollbar-color: rgba(245,210,138,0.32) rgba(255,255,255,0.04);
    }
    .review-summary-ribbon-items::-webkit-scrollbar {
      height: 8px;
    }
    .review-summary-ribbon-items::-webkit-scrollbar-track {
      background: rgba(255,255,255,0.04);
      border-radius: 999px;
    }
    .review-summary-ribbon-items::-webkit-scrollbar-thumb {
      border: 2px solid rgba(255,255,255,0.04);
      border-radius: 999px;
      background: linear-gradient(180deg, rgba(245,210,138,0.5), rgba(245,210,138,0.24));
    }
    .review-summary-ribbon-item {
      min-width: 124px;
      padding: 10px 12px;
      border: 1px solid rgba(245,210,138,0.14);
      border-radius: 14px;
      background: rgba(0,0,0,0.18);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
      flex: 0 0 auto;
    }
    .review-summary-ribbon-label {
      font-size: 0.64rem;
      color: var(--fg-muted);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 6px;
      white-space: nowrap;
    }
    .review-summary-ribbon-value {
      font-size: 0.98rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      white-space: nowrap;
    }
    .review-analysis-main-row { display: block; }
    .review-analysis-main { min-height: 100%; }
    .review-analysis-main .table-scroll {
      max-height: 620px;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      scrollbar-width: thin;
      scrollbar-color: rgba(245,210,138,0.42) rgba(255,255,255,0.04);
    }
    .review-analysis-main .table-scroll::-webkit-scrollbar {
      width: 10px;
      height: 10px;
    }
    .review-analysis-main .table-scroll::-webkit-scrollbar-track {
      background: rgba(255,255,255,0.04);
      border-radius: 999px;
    }
    .review-analysis-main .table-scroll::-webkit-scrollbar-thumb {
      border: 2px solid rgba(255,255,255,0.04);
      border-radius: 999px;
      background: linear-gradient(180deg, rgba(245,210,138,0.58), rgba(245,210,138,0.28));
    }
    .review-analysis-main .table-scroll::-webkit-scrollbar-thumb:hover {
      background: linear-gradient(180deg, rgba(245,210,138,0.82), rgba(245,210,138,0.48));
    }
    .review-analysis-main .round-trip-row-header {
      position: sticky;
      top: 0;
      z-index: 2;
      background:
        linear-gradient(180deg, rgba(12,15,22,0.98), rgba(8,10,16,0.92)),
        radial-gradient(circle at 50% 0%, rgba(245,210,138,0.14), transparent 55%);
      backdrop-filter: blur(10px);
      box-shadow:
        0 10px 22px rgba(0,0,0,0.34),
        inset 0 -1px 0 rgba(245,210,138,0.16);
      border-bottom: 1px solid rgba(245,210,138,0.22);
    }
    .review-analysis-main .round-trip-row-header span {
      padding-top: 4px;
      padding-bottom: 4px;
    }
    .review-analysis-evidence-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; align-items: start; }
    .review-analysis-card { display: flex; flex-direction: column; gap: 10px; }
    .review-section-label { font-size: 0.68rem; color: var(--accent); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px; }
    .live-control-frame { display: flex; flex-direction: column; gap: 14px; margin-bottom: 0; }
    .live-risk-band,
    .live-core-lines-band {
      width: 100%;
      padding: 8px 14px 5px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: rgba(5,8,13,0.56);
    }
    .live-core-lines-band {
      padding: 12px;
      border-color: rgba(245,210,138,0.2);
      background: linear-gradient(180deg, rgba(245,210,138,0.055), rgba(0,0,0,0.2));
    }
    .live-risk-band > .dashboard-section,
    .live-core-lines-band > .dashboard-section {
      margin: 0;
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
    }
    .live-account-risk-panel > .section-header {
      margin-bottom: 4px;
    }
    .live-core-lines-head {
      display: grid;
      grid-template-columns: minmax(150px, 0.65fr) minmax(500px, 2fr) auto;
      align-items: flex-end;
      gap: 16px;
      margin-bottom: 10px;
    }
    .live-core-lines-title-block {
      min-width: 0;
    }
    .live-core-lines-title-block .section-header {
      margin-bottom: 5px;
    }
    .live-core-context {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      min-width: 0;
      border-left: 1px solid var(--border);
    }
    .live-core-context-item {
      min-width: 0;
      padding: 0 11px 2px;
      border-right: 1px solid var(--border);
    }
    .live-core-context-label {
      margin-bottom: 4px;
      color: var(--fg-muted);
      font-size: 0.58rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .live-core-context-value {
      overflow: hidden;
      color: var(--fg);
      font-size: 0.76rem;
      font-weight: 700;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .live-core-context-value--accent { color: var(--accent); }
    .live-core-context-value--success { color: var(--success); }
    .live-core-context-value--warning { color: var(--warning); }
    .live-core-context-value--danger { color: var(--danger); }
    .live-core-context-value--neutral { color: var(--fg); }
    .live-core-context-value--accent,
    .live-core-context-value--success,
    .live-core-context-value--warning,
    .live-core-context-value--danger {
      text-shadow: 0 0 14px currentColor;
    }
    .live-core-lines-summary {
      color: var(--fg-muted);
      font-size: 0.66rem;
      letter-spacing: 0;
      max-width: 240px;
      line-height: 1.4;
    }
    .live-core-lines-summary[data-core-live-summary-state='ready'] {
      color: var(--success);
    }
    .live-core-lines-summary[data-core-live-summary-state='partial'] {
      color: var(--warning);
    }
    .live-core-lines-summary[data-core-live-summary-state='empty'] {
      color: var(--fg-muted);
    }
    .live-core-lines-summary[data-core-live-summary-state='unavailable'] {
      color: var(--danger);
    }
    .core-live-range-controls {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 5px;
      flex-wrap: wrap;
      flex: 0 0 auto;
    }
    .core-live-range-chip {
      min-width: 38px;
      min-height: 29px;
      padding: 5px 8px;
      justify-content: center;
    }
    .live-core-lines-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    .live-core-line-card {
      min-height: 244px;
      padding: 12px;
      border: 1px solid rgba(184,160,120,0.14);
      background: rgba(0,0,0,0.24);
    }
    .live-core-chart {
      width: 100%;
      height: 188px;
      min-height: 188px;
    }
    .live-core-chart .chart-empty {
      min-height: 188px;
    }
    .live-core-chart[data-core-live-chart-state='loading'] .chart-empty {
      color: var(--fg-muted);
      opacity: 0.88;
    }
    .live-core-chart[data-core-live-chart-state='empty'] .chart-empty {
      color: var(--fg-muted);
    }
    .live-core-chart[data-core-live-chart-state='unavailable'] .chart-empty {
      color: var(--danger);
    }
    .live-core-line-card--open-risk {
      border-color: rgba(255,93,115,0.24);
      box-shadow: 0 0 0 1px rgba(255,93,115,0.06), inset 0 0 0 1px rgba(255,255,255,0.02);
    }
    .live-core-line-card--open-risk .section-header {
      color: var(--danger);
    }
    .live-account-risk-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
      grid-auto-rows: 68px;
      gap: 1px;
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--border);
    }
    .live-account-risk-grid .decision-item {
      min-height: 0;
      padding: 6px 13px;
      border: 0;
      border-radius: 0;
      background: rgba(5,8,13,0.96);
    }
    .live-account-risk-grid .decision-item.warning {
      box-shadow: inset 3px 0 0 var(--warning);
    }
    .live-account-risk-grid .decision-item.danger {
      box-shadow: inset 3px 0 0 var(--danger);
    }
    .live-account-risk-grid .decision-label {
      margin-bottom: 4px;
      font-size: 0.6rem;
    }
    .live-account-risk-grid .decision-value {
      font-size: 1.02rem;
    }
    .live-account-risk-grid .decision-support {
      margin-top: 3px;
      color: var(--fg-muted);
      font-size: 0.62rem;
    }
    .live-support-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .live-support-card {
      min-width: 0;
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: rgba(5,8,13,0.72);
      transition: border-color 0.2s, background 0.2s;
    }
    .live-support-card:hover {
      border-color: rgba(245,210,138,0.28);
      background: rgba(245,210,138,0.045);
    }
    .live-support-card[open] {
      grid-column: 1 / -1;
      border-color: rgba(245,210,138,0.28);
      background: rgba(5,8,13,0.9);
    }
    .live-support-summary {
      min-height: 76px;
      padding: 12px 15px;
      cursor: pointer;
    }
    .live-support-summary::marker {
      color: var(--accent);
    }
    .live-support-title {
      display: block;
      color: var(--accent);
      font-size: 0.66rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .live-support-status {
      display: block;
      min-width: 0;
      margin-top: 9px;
      overflow: hidden;
      color: var(--fg-muted);
      font-size: 0.7rem;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .live-support-body {
      padding: 14px;
      border-top: 1px solid var(--border);
    }
    .live-support-detail {
      min-width: 0;
    }
    .live-signal-detail .decision-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .live-rotation-detail {
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(240px, 0.8fr);
      gap: 14px;
      align-items: stretch;
    }
    .live-rotation-detail .chart-container,
    .live-rotation-detail .rotation-summary {
      margin-top: 0;
    }
    .live-support-body > .dashboard-section {
      margin: 0;
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
    }
    .live-support-body > .execution-flow-panel > .section-header {
      display: none;
    }
    .live-support-body .positions-table-shell {
      border-radius: 8px;
    }
    .live-ops-grid { display: grid; grid-template-columns: 1fr 0.95fr; gap: 16px; align-items: start; }
    .system-analysis-shell { display: flex; flex-direction: column; gap: 16px; }
    .system-summary-strip { padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: linear-gradient(180deg, rgba(138,210,255,0.06), rgba(0,0,0,0.16)); }
    .system-summary-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; margin-bottom: 12px; }
    .system-summary-kicker { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
    .system-summary-copy { color: var(--fg-muted); font-size: 0.78rem; max-width: 520px; text-align: right; }
    .system-summary-strip .decision-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .system-health-path { margin: 2px 0 10px; padding: 8px 12px; border: 1px solid rgba(245,210,138,0.18); border-radius: var(--radius-sm); background: rgba(245,210,138,0.06); color: var(--accent); font-size: 0.72rem; font-family: 'JetBrains Mono', 'SF Mono', monospace; word-break: break-all; }
    .system-health-panel { display: flex; flex-direction: column; gap: 10px; }
    .system-console-grid { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr); gap: 16px; align-items: stretch; }
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
    .analytics-row { display: grid; grid-template-columns: 1.4fr 0.8fr 0.8fr 0.8fr 0.7fr; gap: 8px; padding: 9px 0; border-bottom: 1px solid var(--border); font-size: 0.78rem; align-items: center; }
    .analytics-row.analytics-row-header { color: var(--fg-muted); font-size: 0.68rem; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700; }
    .round-trip-view.desktop-only { display: block; }
    .round-trip-details, .round-trip-card { border-bottom: 1px solid var(--border); }
    .round-trip-details:last-child, .round-trip-card:last-child { border-bottom: none; }
    .round-trip-details > summary, .round-trip-card > summary { display: grid; list-style: none; cursor: pointer; }
    .round-trip-details > summary::-webkit-details-marker, .round-trip-card > summary::-webkit-details-marker { display: none; }
    .round-trip-summary, .round-trip-row-header { grid-template-columns: 1.4fr 0.85fr 0.85fr 0.45fr 0.7fr 0.65fr 0.7fr 0.65fr; }
    .round-trip-summary { padding: 10px 0; }
    .round-trip-detail-body { padding: 0 0 12px 12px; }
    .round-trip-leg-table { overflow-x: auto; padding-top: 8px; }
    .round-trip-leg-row { display: grid; grid-template-columns: 0.45fr 0.7fr 0.9fr 0.6fr 0.8fr 0.85fr 0.7fr 0.7fr 0.8fr 0.7fr 0.9fr; gap: 8px; min-width: 1080px; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 0.7rem; align-items: center; }
    .round-trip-leg-row:last-child { border-bottom: none; }
    .round-trip-leg-row-header { color: var(--fg-muted); font-size: 0.64rem; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700; }
    .round-trip-leg-empty { color: var(--fg-muted); font-size: 0.74rem; padding: 8px 0 0 0; }
    .analytics-row:last-child { border-bottom: none; }
    .analytics-main { color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .daily-review-panel { display: flex; flex-direction: column; gap: 14px; padding: 16px; }
    .daily-review-panel-redesign { gap: 18px; padding: 20px; background: radial-gradient(circle at 82% 8%, rgba(0,212,255,0.07), transparent 28%), linear-gradient(145deg, rgba(245,210,138,0.035), rgba(0,0,0,0.18)); }
    .daily-review-panel-redesign .daily-review-toolbar { border-color: rgba(245,210,138,0.16); background: rgba(0,0,0,0.24); }
    .daily-review-module { display: flex; flex-direction: column; gap: 14px; padding: 18px; border: 1px solid var(--border); border-radius: 16px; }
    .daily-review-original-block { background: rgba(0,0,0,0.13); }
    .daily-review-filtered-base-block { border-color: rgba(138,210,255,0.24); background: linear-gradient(155deg, rgba(0,212,255,0.045), rgba(0,0,0,0.16) 46%); }
    .daily-review-module-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; padding-bottom: 2px; }
    .daily-review-module-head h3 { margin: 0; color: var(--fg); font-family: Georgia, 'Times New Roman', serif; font-size: 1.32rem; font-weight: 500; letter-spacing: -0.02em; }
    .daily-review-original-block .daily-review-history-summary { border-color: rgba(245,210,138,0.13); background: rgba(245,210,138,0.035); }
    .daily-review-original-block .daily-review-ledger { border-radius: 12px; }
    .daily-review-filtered-base-block .daily-review-counterfactual-block { border-color: rgba(138,210,255,0.18); background: rgba(0,0,0,0.14); }
    .daily-review-toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding: 14px 16px; border: 1px solid var(--border); border-radius: 8px; background: rgba(0,0,0,0.18); }
    .daily-review-toolbar-left { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
    .daily-review-toolbar-note { max-width: 340px; color: var(--fg-muted); font-size: 0.76rem; line-height: 1.45; text-align: right; }
    .daily-review-hero { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(240px, 0.7fr); gap: 16px; align-items: stretch; }
    .daily-review-hero-copy { display: flex; flex-direction: column; justify-content: center; min-height: 142px; padding: 22px 24px; border: 1px solid rgba(245,210,138,0.16); border-radius: 16px; background: linear-gradient(135deg, rgba(245,210,138,0.07), rgba(0,0,0,0.2)); }
    .daily-review-hero-title { max-width: 720px; color: var(--fg); font-family: Georgia, 'Times New Roman', serif; font-size: clamp(1.35rem, 2.2vw, 2.15rem); line-height: 1.2; letter-spacing: -0.03em; }
    .daily-review-hero-title em { color: var(--accent); font-style: normal; }
    .daily-review-hero-impact { display: flex; flex-direction: column; justify-content: center; min-height: 142px; padding: 20px 22px; border: 1px solid var(--border); border-radius: 16px; background: rgba(0,0,0,0.25); }
    .daily-review-hero-impact span { color: var(--fg-muted); font-size: 0.64rem; letter-spacing: 0.16em; }
    .daily-review-hero-impact strong { margin-top: 10px; color: var(--fg); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: clamp(1.25rem, 2vw, 1.8rem); line-height: 1.1; }
    .daily-review-hero-impact small { margin-top: 12px; color: var(--fg-muted); font-size: 0.7rem; }
    .daily-review-hero-impact.positive { border-color: rgba(0,255,136,0.3); background: linear-gradient(145deg, rgba(0,255,136,0.09), rgba(0,0,0,0.24)); }
    .daily-review-hero-impact.positive strong { color: var(--success); }
    .daily-review-hero-impact.negative { border-color: rgba(255,68,102,0.3); background: linear-gradient(145deg, rgba(255,68,102,0.09), rgba(0,0,0,0.24)); }
    .daily-review-hero-impact.negative strong { color: var(--danger); }
    .daily-review-hero-impact.neutral strong { color: var(--accent-strong); }
    .daily-review-date-form { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .daily-review-date-label { color: var(--fg-muted); font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase; }
    .daily-review-date-select { min-width: 160px; padding: 8px 12px; border-radius: 999px; border: 1px solid rgba(245,210,138,0.24); background: rgba(0,0,0,0.22); color: var(--fg); font-size: 0.74rem; font-weight: 700; outline: none; }
    .daily-review-date-select:focus { border-color: rgba(245,210,138,0.46); box-shadow: 0 0 0 3px rgba(245,210,138,0.08); }
    .daily-review-nav { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .daily-review-nav-link, .daily-review-nav-current { display: inline-flex; align-items: center; justify-content: center; min-height: 32px; padding: 6px 12px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; }
    .daily-review-nav-link { color: var(--accent); border: 1px solid rgba(245,210,138,0.28); background: rgba(245,210,138,0.06); text-decoration: none; transition: border-color 0.2s, background 0.2s, color 0.2s; }
    .daily-review-nav-link:hover { color: var(--fg); border-color: rgba(245,210,138,0.48); background: rgba(245,210,138,0.12); }
    .daily-review-nav-link-disabled { color: var(--fg-muted); border-color: var(--border); background: rgba(255,255,255,0.03); }
    .daily-review-nav-current { color: var(--fg); border: 1px solid var(--border-accent); background: rgba(0,212,255,0.07); }
    .daily-review-nav-link-latest { color: var(--success); border-color: rgba(0,255,136,0.22); background: rgba(0,255,136,0.06); }
    .daily-review-history-summary { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid rgba(138,210,255,0.18); border-radius: 8px; background: rgba(138,210,255,0.04); }
    .daily-review-history-summary-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
    .daily-review-history-title { font-size: 0.92rem; font-weight: 800; color: var(--accent-strong); }
    .daily-review-history-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }
    .daily-review-history-kpi { min-height: 76px; background: rgba(0,0,0,0.16); border-color: rgba(138,210,255,0.14); }
    .daily-review-headline { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; border: 1px solid var(--border); border-radius: 8px; background: rgba(0,0,0,0.22); }
    .daily-review-headline.positive { border-color: rgba(0,255,136,0.26); background: rgba(0,255,136,0.06); }
    .daily-review-headline.negative { border-color: rgba(255,68,102,0.28); background: rgba(255,68,102,0.06); }
    .daily-review-eyebrow { font-size: 0.68rem; color: var(--accent); letter-spacing: 0; text-transform: uppercase; margin-bottom: 6px; }
    .daily-review-title { font-size: 1.12rem; font-weight: 800; }
    .daily-review-support { margin-top: 4px; color: var(--fg-muted); font-size: 0.78rem; }
    .daily-review-kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
    .daily-review-kpi { min-height: 82px; padding: 12px; border: 1px solid var(--border); border-radius: 8px; background: rgba(0,0,0,0.2); overflow: hidden; }
    .daily-review-counterfactual-block { display: flex; flex-direction: column; gap: 14px; padding: 18px; border: 1px solid rgba(138,210,255,0.22); border-radius: 16px; background: linear-gradient(155deg, rgba(0,212,255,0.07), rgba(0,0,0,0.2) 42%); }
    .daily-review-section-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; }
    .daily-review-section-head h3 { margin: 0; color: var(--fg); font-family: Georgia, 'Times New Roman', serif; font-size: 1.28rem; font-weight: 500; letter-spacing: -0.02em; }
    .daily-review-section-note { max-width: 420px; color: var(--fg-muted); font-size: 0.72rem; line-height: 1.5; text-align: right; }
    .daily-review-counterfactual-stats { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; }
    .daily-review-counterfactual-stat { display: flex; flex-direction: column; gap: 8px; min-height: 68px; padding: 11px 12px; border: 1px solid rgba(138,210,255,0.14); border-radius: 11px; background: rgba(0,0,0,0.2); }
    .daily-review-counterfactual-stat span { color: var(--fg-muted); font-size: 0.61rem; letter-spacing: 0.11em; }
    .daily-review-counterfactual-stat strong { color: var(--fg); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 1rem; }
    .daily-review-counterfactual-stat.positive strong { color: var(--success); }
    .daily-review-counterfactual-stat.negative strong { color: var(--danger); }
    .daily-review-counterfactual-stat.tail strong { color: var(--accent); }
    .daily-review-filter-explainer { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; color: var(--fg-muted); font-size: 0.72rem; line-height: 1.45; }
    .daily-review-filter-chip { display: inline-flex; align-items: center; min-height: 24px; padding: 4px 8px; border: 1px solid rgba(138,210,255,0.25); border-radius: 999px; background: rgba(138,210,255,0.08); color: var(--accent-strong); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.65rem; white-space: nowrap; }
    .daily-review-counterfactual-table { overflow-x: auto; border: 1px solid rgba(138,210,255,0.14); border-radius: 12px; background: rgba(0,0,0,0.18); }
    .daily-review-counterfactual-header, .daily-review-counterfactual-row { display: grid; grid-template-columns: minmax(120px, 0.85fr) minmax(120px, 0.85fr) minmax(250px, 1.7fr) minmax(145px, 1fr) minmax(90px, 0.62fr) minmax(72px, 0.48fr); gap: 12px; min-width: 920px; align-items: center; }
    .daily-review-counterfactual-header { padding: 12px 14px 9px; border-bottom: 1px solid rgba(138,210,255,0.14); color: var(--fg-muted); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.1em; }
    .daily-review-counterfactual-row { padding: 13px 14px; border-bottom: 1px solid rgba(138,210,255,0.1); font-size: 0.75rem; }
    .daily-review-counterfactual-row:last-child { border-bottom: none; }
    .daily-review-counterfactual-row:hover { background: rgba(138,210,255,0.045); }
    .daily-review-counterfactual-time, .daily-review-counterfactual-symbol, .daily-review-counterfactual-pnl { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
    .daily-review-counterfactual-time span, .daily-review-counterfactual-symbol strong { color: var(--fg); }
    .daily-review-counterfactual-symbol strong { color: var(--accent); }
    .daily-review-counterfactual-time small, .daily-review-counterfactual-symbol small, .daily-review-counterfactual-pnl small, .daily-review-counterfactual-addons small { color: var(--fg-muted); font-size: 0.62rem; }
    .daily-review-veto-evidence { min-width: 0; }
    .daily-review-rule-chips { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
    .daily-review-rule-chip { min-height: 22px; padding: 3px 7px; font-size: 0.59rem; }
    .daily-review-rule-a { border-color: rgba(245,210,138,0.36); background: rgba(245,210,138,0.08); color: var(--accent); }
    .daily-review-rule-b, .daily-review-rule-c { border-color: rgba(138,210,255,0.3); background: rgba(138,210,255,0.08); color: var(--accent-strong); }
    .daily-review-rule-d, .daily-review-rule-e { border-color: rgba(255,184,0,0.3); background: rgba(255,184,0,0.08); color: var(--warning); }
    .daily-review-rule-breakout { border-color: rgba(0,255,136,0.28); background: rgba(0,255,136,0.07); color: var(--success); }
    .daily-review-rule-empty, .daily-review-rule-mix-empty { color: var(--fg-muted); font-size: 0.72rem; }
    .daily-review-feature-pills { display: flex; flex-direction: column; gap: 3px; margin-top: 7px; color: var(--fg-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.64rem; white-space: normal; line-height: 1.35; }
    .daily-review-feature-line-secondary { color: var(--accent-strong); }
    .daily-review-rule-mix { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 9px 10px; border: 1px solid rgba(138,210,255,0.12); border-radius: 10px; background: rgba(0,0,0,0.13); }
    .daily-review-rule-mix-title { margin-right: 3px; color: var(--fg-muted); font-size: 0.6rem; font-weight: 800; letter-spacing: 0.12em; }
    .daily-review-rule-mix-item { display: inline-flex; align-items: center; gap: 6px; min-height: 23px; padding: 3px 7px; border: 1px solid rgba(138,210,255,0.18); border-radius: 999px; background: rgba(138,210,255,0.05); }
    .daily-review-rule-mix-item b { color: var(--fg-muted); font-size: 0.6rem; font-weight: 700; }
    .daily-review-rule-mix-item strong { color: var(--fg); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.7rem; }
    .daily-review-outcome { display: inline-flex; align-items: center; min-height: 24px; padding: 4px 8px; border: 1px solid var(--border); border-radius: 999px; font-size: 0.62rem; font-weight: 800; letter-spacing: 0.04em; }
    .daily-review-outcome-win { color: var(--success); border-color: rgba(0,255,136,0.24); background: rgba(0,255,136,0.08); }
    .daily-review-outcome-loss { color: var(--danger); border-color: rgba(255,68,102,0.25); background: rgba(255,68,102,0.08); }
    .daily-review-outcome-pending { color: var(--warning); border-color: rgba(255,184,0,0.25); background: rgba(255,184,0,0.08); }
    .daily-review-outcome-neutral { color: var(--accent-strong); border-color: rgba(138,210,255,0.24); background: rgba(138,210,255,0.08); }
    .daily-review-tail-badge { display: inline-flex; margin: 5px 0 0 4px; color: var(--accent); font-size: 0.61rem; white-space: nowrap; }
    .daily-review-counterfactual-pnl strong { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.92rem; }
    .daily-review-counterfactual-addons { color: var(--fg); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .daily-review-empty { display: flex; flex-direction: column; gap: 5px; padding: 28px 16px; color: var(--fg-muted); font-size: 0.76rem; }
    .daily-review-empty strong { color: var(--fg); font-size: 0.84rem; }
    .daily-review-ledger { display: flex; flex-direction: column; gap: 12px; padding: 18px; border: 1px solid var(--border); border-radius: 16px; background: rgba(0,0,0,0.16); }
    .daily-review-table { max-height: 520px; overflow: auto; border: 1px solid var(--border); border-radius: 8px; padding: 0 12px; }
    .daily-review-grid { display: grid; grid-template-columns: minmax(126px, 1fr) minmax(88px, 0.7fr) minmax(126px, 1fr) minmax(88px, 0.75fr) minmax(88px, 0.75fr) minmax(108px, 0.85fr) minmax(68px, 0.52fr) minmax(70px, 0.52fr); min-width: 1040px; }
    .daily-review-row { gap: 10px; padding: 10px 0; font-size: 0.74rem; }
    .daily-review-row-header { position: sticky; top: 0; z-index: 1; background: rgba(7,9,14,0.98); padding-top: 12px; }
    .daily-review-impact-positive { color: var(--success); font-weight: 700; }
    .daily-review-impact-negative { color: var(--danger); font-weight: 700; }
    .daily-review-status { display: inline-flex; align-items: center; justify-content: center; min-width: 44px; padding: 3px 8px; border-radius: 999px; font-size: 0.66rem; font-weight: 800; letter-spacing: 0; }
    .daily-review-status-ok { color: var(--success); background: rgba(0,255,136,0.08); border: 1px solid rgba(0,255,136,0.18); }
    .daily-review-status-warn { color: var(--warning); background: rgba(255,184,0,0.08); border: 1px solid rgba(255,184,0,0.24); }
    .trade-time { color: var(--fg-muted); }
    .trade-symbol { color: var(--accent); font-weight: 500; }
    .side-buy { color: var(--success); }
    .side-sell { color: var(--danger); }
    .status-filled { color: var(--success); }
    .status-pending { color: var(--warning); }
    .trade-card-list, .analytics-card-list { display: flex; flex-direction: column; gap: 10px; }
    .analytics-card { padding: 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 14px; }
    .analytics-card-main { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; font-size: 0.86rem; }
    .analytics-card-meta { display: flex; flex-wrap: wrap; gap: 10px; color: var(--fg-muted); font-size: 0.74rem; }
    .section-header { font-size: 0.7rem; color: var(--accent); padding: 4px 0; margin-bottom: 8px; border-bottom: 1px solid var(--border); text-transform: uppercase; letter-spacing: 0.1em; }
    .config-panel { background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px; font-size: 0.8rem; }
    .config-row { display: flex; justify-content: space-between; padding: 4px 0; }
    .config-label { color: var(--fg-muted); }
    .config-value-true { color: var(--warning); }
    .config-value-false { color: var(--fg-muted); }
    .dashboard-section { margin-bottom: 20px; padding: 16px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius); }
    .charts-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
    .chart-card { background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); padding: 12px; }
    .account-metrics-panel { padding: 20px; }
    .account-snapshot-panel { padding: 18px; margin-bottom: 20px; }
    .account-snapshot-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
    .account-snapshot-card { background: rgba(0,0,0,0.18); border: 1px solid var(--border); border-radius: 14px; padding: 14px; min-height: 112px; }
    .account-snapshot-label { font-size: 0.68rem; color: var(--fg-muted); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px; }
    .account-snapshot-value { font-size: 1.18rem; font-weight: 700; }
    .account-snapshot-sub { margin-top: 8px; font-size: 0.74rem; color: var(--fg-muted); line-height: 1.45; }
    .execution-flow-panel { padding: 18px; margin-bottom: 20px; }
    .execution-flow-grid { display: flex; flex-direction: column; gap: 12px; }
    .execution-flow-group { display: flex; flex-direction: column; gap: 8px; }
    .execution-flow-group + .execution-flow-group { padding-top: 10px; border-top: 1px solid rgba(184,160,120,0.12); }
    .execution-flow-group-label { font-size: 0.62rem; color: var(--accent); letter-spacing: 0.12em; text-transform: uppercase; margin: 0 0 2px; }
    .execution-flow-row {
      display: grid;
      grid-template-columns: minmax(170px, 0.9fr) minmax(0, 1.25fr) minmax(160px, 0.8fr);
      gap: 12px;
      align-items: center;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: rgba(0,0,0,0.16);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
      transition: border-color 0.2s, background 0.2s;
    }
    .execution-flow-row-primary {
      border-color: rgba(245,210,138,0.2);
      background: linear-gradient(180deg, rgba(245,210,138,0.06), rgba(0,0,0,0.16));
    }
    .execution-flow-row-support {
      border-color: rgba(184,160,120,0.1);
      background: rgba(0,0,0,0.14);
    }
    .execution-flow-row:hover {
      border-color: rgba(245,210,138,0.18);
      background: rgba(0,212,255,0.045);
    }
    .execution-flow-label {
      font-size: 0.62rem;
      color: var(--fg-muted);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-bottom: 0;
      line-height: 1.3;
    }
    .execution-flow-body {
      display: flex;
      flex-direction: column;
      gap: 3px;
      min-width: 0;
    }
    .execution-flow-row-primary .execution-flow-primary { font-size: 0.98rem; }
    .execution-flow-primary { font-size: 0.92rem; font-weight: 700; word-break: break-word; line-height: 1.25; }
    .execution-flow-secondary { margin-top: 0; font-size: 0.72rem; color: var(--fg-muted); word-break: break-word; line-height: 1.35; }
    .execution-flow-detail { margin-top: 0; font-size: 0.72rem; color: var(--fg-muted); line-height: 1.35; word-break: break-word; text-align: right; }
    .system-diagnostics-panel, .system-warning-panel { margin-bottom: 20px; }
    .system-warning-list { display: flex; flex-direction: column; gap: 10px; }
    .system-warning-item { padding: 12px 14px; background: rgba(255,184,0,0.08); border: 1px solid rgba(255,184,0,0.22); border-radius: 12px; color: var(--warning); font-size: 0.78rem; line-height: 1.5; word-break: break-word; }
    .account-panel-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
    .account-panel-title { font-size: 0.95rem; font-weight: 700; letter-spacing: 0.06em; }
    .account-panel-subtitle { font-size: 0.76rem; color: var(--fg-muted); margin-top: 6px; max-width: 680px; }
    .account-panel-note { font-size: 0.76rem; color: var(--warning); max-width: 420px; line-height: 1.45; padding: 10px 12px; background: rgba(255,184,0,0.08); border: 1px solid rgba(255,184,0,0.22); border-radius: var(--radius-sm); }
    .account-range-switches, .account-metric-switches { display: flex; flex-wrap: wrap; gap: 8px; }
    .account-chip { border: 1px solid var(--border); background: rgba(0,0,0,0.24); color: var(--fg-muted); border-radius: 999px; padding: 8px 12px; font-size: 0.72rem; cursor: pointer; transition: all 0.2s; }
    .account-chip.active { color: var(--accent); border-color: var(--border-accent); background: rgba(0,212,255,0.08); }
    .account-overview-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 16px; }
    .account-overview-card { background: rgba(0,0,0,0.2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 14px; min-height: 98px; }
    .account-overview-card-highlight { background: rgba(0,212,255,0.05); border-color: var(--border-accent); }
    .account-overview-label { font-size: 0.68rem; color: var(--fg-muted); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px; }
    .account-overview-value { font-size: 1.2rem; font-weight: 700; }
    .account-overview-sub { font-size: 0.72rem; color: var(--fg-muted); margin-top: 8px; }
    .account-main-panel { background: rgba(0,0,0,0.22); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 16px; }
    .account-main-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 14px; }
    .account-main-meta { display: flex; gap: 16px; font-size: 0.72rem; color: var(--fg-muted); }
    .account-main-chart { min-height: 280px; }
    .account-chart-svg { width: 100%; height: auto; display: block; }
    .account-grid-line { stroke: rgba(100,130,170,0.12); stroke-width: 1; }
    .account-axis-label { fill: var(--fg-muted); font-size: 10px; }
    .account-series-line { fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
    .account-series-area { opacity: 0.18; }
    .account-last-dot { filter: drop-shadow(0 0 6px currentColor); }
    .decision-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .decision-half { background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); padding: 12px; }
    .bottom-row { display: grid; grid-template-columns: 200px 1fr 1fr; gap: 16px; }
    .decision-grid-stack { grid-template-columns: 1fr 1fr; }
    .decision-support { margin-top: 6px; color: var(--fg-muted); font-size: 0.76rem; }
    .bottom-col { }
    """
