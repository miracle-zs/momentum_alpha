from __future__ import annotations


def _render_dashboard_base_styles() -> str:
    return (
        ".dashboard-tab { display: inline-flex; }\n"
        ".dashboard-tab.is-active { color: var(--fg); }\n"
        ".action-button { cursor: pointer; }\n"
    )

def _render_dashboard_cosmic_styles() -> str:
    return """
    .cosmic-identity-panel {
      display: grid;
      grid-template-columns: 0.92fr 1.08fr;
      gap: 18px;
      margin-bottom: 22px;
      padding: 22px;
      border: 1px solid rgba(245,210,138,0.12);
      border-radius: 26px;
      background:
        radial-gradient(circle at 12% 18%, rgba(245,210,138,0.14), transparent 28%),
        linear-gradient(145deg, rgba(10,12,18,0.95), rgba(7,8,12,0.96));
      box-shadow: 0 18px 42px rgba(0,0,0,0.28);
    }
    .cosmic-identity-copy {
      max-width: 360px;
    }
    .cosmic-identity-kicker {
      display: inline-flex;
      align-items: center;
      padding: 6px 12px;
      margin-bottom: 14px;
      border: 1px solid rgba(245,210,138,0.22);
      border-radius: 999px;
      color: var(--accent);
      font-size: 0.72rem;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      background: rgba(245,210,138,0.05);
    }
    .cosmic-identity-title {
      font-size: clamp(2rem, 4vw, 3.6rem);
      line-height: 0.92;
      letter-spacing: 0.18em;
      font-weight: 300;
      margin-bottom: 12px;
    }
    .cosmic-identity-subtitle {
      font-size: 0.86rem;
      line-height: 1.7;
      color: var(--fg-muted);
      max-width: 34rem;
    }
    .cosmic-identity-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }
    .cosmic-identity-card {
      position: relative;
      overflow: hidden;
      min-height: 216px;
      padding: 16px;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 20px;
      background:
        radial-gradient(circle at 18% 14%, rgba(245,210,138,0.05), transparent 20%),
        rgba(255,255,255,0.02);
    }
    .cosmic-identity-card::after {
      content: '';
      position: absolute;
      inset: auto -20% -20% auto;
      width: 120px;
      height: 120px;
      background: radial-gradient(circle, rgba(245,210,138,0.18), transparent 70%);
      pointer-events: none;
    }
    .cosmic-identity-card-label {
      font-size: 0.72rem;
      color: var(--accent);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 14px;
    }
    .cosmic-inline-label {
      margin-bottom: 10px;
    }
    .cosmic-swatches {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .cosmic-swatch {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .cosmic-dot {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      border: 1px solid rgba(255,255,255,0.12);
      box-shadow: inset 0 0 0 1px rgba(0,0,0,0.18), 0 0 20px rgba(0,0,0,0.22);
      flex-shrink: 0;
    }
    .cosmic-dot-black { background: #050507; }
    .cosmic-dot-space { background: #0E0F14; }
    .cosmic-dot-white { background: #F5F6F8; }
    .cosmic-dot-gold { background: #F5D28A; }
    .cosmic-dot-purple { background: #1A1C2A; }
    .cosmic-swatch-name {
      font-size: 0.84rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .cosmic-swatch-value {
      font-size: 0.72rem;
      color: var(--fg-muted);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-top: 2px;
    }
    .cosmic-gradient-bar {
      height: 34px;
      margin-top: 16px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(90deg, #1d4e63 0%, #29324a 24%, #f5d28a 50%, #6d516e 72%, #0e0f14 100%);
      box-shadow: inset 0 0 30px rgba(255,255,255,0.04);
    }
    .cosmic-component-row,
    .cosmic-tag-row,
    .cosmic-toggle-row,
    .cosmic-icon-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .cosmic-component-row { margin-bottom: 14px; }
    .cosmic-chip,
    .cosmic-tag,
    .cosmic-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 34px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.12);
      font-size: 0.72rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--fg);
      background: rgba(255,255,255,0.02);
    }
    .cosmic-chip-primary {
      border-color: rgba(245,210,138,0.28);
      color: var(--accent);
      background: rgba(245,210,138,0.08);
      box-shadow: 0 0 18px rgba(245,210,138,0.12);
    }
    .cosmic-chip-secondary {
      color: rgba(245,246,248,0.72);
      background: rgba(255,255,255,0.03);
    }
    .cosmic-chip-ghost {
      color: rgba(245,246,248,0.54);
      background: transparent;
    }
    .cosmic-toggle {
      position: relative;
      width: 60px;
      height: 34px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.03);
      padding: 4px;
    }
    .cosmic-toggle span {
      display: block;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      background: #20232f;
      box-shadow: 0 0 10px rgba(0,0,0,0.35);
    }
    .cosmic-toggle-on {
      border-color: rgba(245,210,138,0.34);
      background: rgba(245,210,138,0.08);
    }
    .cosmic-toggle-on span {
      margin-left: 26px;
      background: var(--accent);
      box-shadow: 0 0 14px rgba(245,210,138,0.28);
    }
    .cosmic-tag-gold {
      border-color: rgba(245,210,138,0.36);
      color: var(--accent);
    }
    .cosmic-tag-violet {
      border-color: rgba(146,123,255,0.28);
      color: #b8b0ff;
    }
    .cosmic-tag-teal {
      border-color: rgba(138,210,255,0.26);
      color: var(--accent-strong);
    }
    .cosmic-data-grid {
      display: grid;
      gap: 12px;
    }
    .cosmic-data-card {
      padding: 14px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.02);
    }
    .cosmic-data-label {
      font-size: 0.72rem;
      color: var(--fg-muted);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }
    .cosmic-ring {
      width: 88px;
      height: 88px;
      display: grid;
      place-items: center;
      margin: 6px auto 0;
      border-radius: 50%;
      border: 1px solid rgba(245,210,138,0.24);
      background: radial-gradient(circle, rgba(245,210,138,0.12), transparent 65%);
      box-shadow: inset 0 0 0 8px rgba(255,255,255,0.015);
      color: var(--fg);
      font-size: 1.15rem;
      font-weight: 600;
    }
    .cosmic-slider {
      position: relative;
      height: 4px;
      margin: 18px 0 10px;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(245,246,248,0.15), rgba(245,210,138,0.7), rgba(245,246,248,0.15));
    }
    .cosmic-slider span {
      position: absolute;
      top: 50%;
      left: 56%;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      transform: translate(-50%, -50%);
      background: var(--accent);
      box-shadow: 0 0 18px rgba(245,210,138,0.38);
    }
    .cosmic-data-value {
      text-align: right;
      font-size: 0.82rem;
      color: var(--accent);
      letter-spacing: 0.08em;
    }
    .cosmic-icon-row {
      margin-top: 12px;
    }
    .cosmic-icon {
      color: rgba(245,246,248,0.72);
      border-color: rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.015);
    }
    .cosmic-tag-block {
      margin-top: 14px;
    }
    .cosmic-identity-visuals {
      grid-column: 1 / -1;
      min-height: 0;
    }
    .cosmic-visual-tiles {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
    }
    .cosmic-visual-tile {
      position: relative;
      overflow: hidden;
      min-height: 120px;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(160deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
      display: flex;
      align-items: flex-end;
    }
    .cosmic-visual-tile::before {
      content: '';
      position: absolute;
      inset: 0;
      background: radial-gradient(circle at 50% 38%, rgba(245,210,138,0.14), transparent 24%);
      pointer-events: none;
    }
    .cosmic-visual-tile-glow {
      position: absolute;
      inset: 12px;
      border-radius: 14px;
      opacity: 0.9;
    }
    .cosmic-visual-tile-label {
      position: relative;
      z-index: 1;
      font-size: 0.7rem;
      letter-spacing: 0.16em;
      color: var(--fg);
      text-transform: uppercase;
    }
    .cosmic-visual-black-hole .cosmic-visual-tile-glow {
      background: radial-gradient(circle, rgba(0,0,0,0.96) 0 26%, rgba(245,210,138,0.42) 32%, rgba(120,80,255,0.14) 56%, transparent 70%);
      box-shadow: inset 0 0 0 1px rgba(245,210,138,0.2), 0 0 26px rgba(245,210,138,0.08);
    }
    .cosmic-visual-gravity-ring .cosmic-visual-tile-glow {
      background: radial-gradient(circle at 50% 40%, transparent 0 26%, rgba(245,210,138,0.36) 28%, transparent 31%), radial-gradient(circle at 52% 43%, rgba(245,210,138,0.07), transparent 58%);
      box-shadow: inset 0 0 0 1px rgba(245,210,138,0.12);
    }
    .cosmic-visual-light-glow .cosmic-visual-tile-glow {
      background: radial-gradient(circle at 55% 35%, rgba(245,210,138,0.9), rgba(245,210,138,0.08) 30%, transparent 60%);
    }
    .cosmic-visual-nebula-dust .cosmic-visual-tile-glow {
      background:
        radial-gradient(circle at 30% 40%, rgba(146,123,255,0.46), transparent 25%),
        radial-gradient(circle at 68% 58%, rgba(138,210,255,0.3), transparent 24%),
        radial-gradient(circle at 52% 34%, rgba(245,210,138,0.16), transparent 34%);
      filter: blur(1px);
    }
    .cosmic-visual-glass-surface .cosmic-visual-tile-glow {
      background:
        linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0.01)),
        radial-gradient(circle at 20% 20%, rgba(138,210,255,0.14), transparent 26%),
        radial-gradient(circle at 88% 82%, rgba(245,210,138,0.18), transparent 24%);
      backdrop-filter: blur(12px);
    }
    """

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
    .event-item { display: grid; grid-template-columns: 1fr 130px 80px; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 0.78rem; }
    .event-item:last-child { border-bottom: none; }
    .event-item.empty { color: var(--fg-muted); }
    .event-type { font-weight: 500; color: var(--accent); }
    .event-time, .event-source { color: var(--fg-muted); font-size: 0.72rem; }
    .refresh-indicator { position: fixed; bottom: 20px; right: 20px; padding: 10px 16px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 100px; font-size: 0.75rem; color: var(--fg-muted); display: flex; align-items: center; gap: 8px; }
    .refresh-indicator.error { border-color: rgba(255,68,102,0.35); color: var(--danger); }
    .refresh-dot { width: 8px; height: 8px; background: var(--success); border-radius: 50%; animation: blink 1s infinite; }
    .refresh-indicator.error .refresh-dot { background: var(--danger); animation: none; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .positions-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
    .position-card { background: rgba(0,0,0,0.3); padding: 14px; border-radius: 8px; border-left: 3px solid var(--success); }
    .position-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
    .position-symbol { font-weight: 700; color: var(--accent); font-family: 'JetBrains Mono', 'SF Mono', monospace; }
    .position-direction { font-size: 0.75rem; color: var(--fg-muted); }
    .position-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; font-size: 0.82rem; }
    .position-metric { text-align: center; padding: 4px 2px; }
    .position-metric.position-live { background: rgba(0,212,255,0.06); border: 1px solid rgba(0,212,255,0.12); border-radius: 8px; }
    .position-metric.position-live .metric-value { font-size: 0.96rem; font-weight: 700; }
    .position-metric.position-risk .metric-value { font-size: 0.92rem; font-weight: 700; }
    .metric-danger { color: var(--danger); }
    .metric-note { display: block; margin-top: 4px; font-size: 0.62rem; color: var(--fg-muted); }
    .position-legs { margin-top: 8px; font-size: 0.7rem; color: var(--fg-muted); }
    .positions-empty { color: var(--fg-muted); text-align: center; padding: 20px; }
    .trade-history { max-height: 200px; overflow-y: auto; }
    .trade-history-empty { color: var(--fg-muted); text-align: center; padding: 20px; }
    .trade-row { display: grid; grid-template-columns: 80px 120px 60px 80px 100px 80px 80px; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 0.75rem; }
    .trade-row:last-child { border-bottom: none; }
    .analytics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
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
    .daily-review-headline { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; border: 1px solid var(--border); border-radius: 8px; background: rgba(0,0,0,0.22); }
    .daily-review-headline.positive { border-color: rgba(0,255,136,0.26); background: rgba(0,255,136,0.06); }
    .daily-review-headline.negative { border-color: rgba(255,68,102,0.28); background: rgba(255,68,102,0.06); }
    .daily-review-eyebrow { font-size: 0.68rem; color: var(--accent); letter-spacing: 0; text-transform: uppercase; margin-bottom: 6px; }
    .daily-review-title { font-size: 1.12rem; font-weight: 800; }
    .daily-review-support { margin-top: 4px; color: var(--fg-muted); font-size: 0.78rem; }
    .daily-review-kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
    .daily-review-kpi { min-height: 82px; padding: 12px; border: 1px solid var(--border); border-radius: 8px; background: rgba(0,0,0,0.2); overflow: hidden; }
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
    .execution-flow-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
    .execution-flow-card { background: rgba(0,0,0,0.18); border: 1px solid var(--border); border-radius: 14px; padding: 14px; min-height: 116px; }
    .execution-flow-label { font-size: 0.68rem; color: var(--fg-muted); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 10px; }
    .execution-flow-primary { font-size: 1rem; font-weight: 700; word-break: break-word; }
    .execution-flow-secondary { margin-top: 8px; font-size: 0.8rem; color: var(--fg); word-break: break-word; }
    .execution-flow-detail { margin-top: 6px; font-size: 0.74rem; color: var(--fg-muted); line-height: 1.45; word-break: break-word; }
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

def _render_dashboard_responsive_styles() -> str:
    return """
    @media (max-width: 1200px) {
      .cosmic-identity-panel { grid-template-columns: 1fr; }
      .cosmic-identity-grid { grid-template-columns: 1fr; }
      .cosmic-visual-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .metrics-grid { grid-template-columns: repeat(2, 1fr); }
      .hero-grid { grid-template-columns: 1fr; }
      .home-command-grid { grid-template-columns: 1fr; }
      .charts-row { grid-template-columns: 1fr; }
      .decision-row { grid-template-columns: 1fr; }
      .bottom-row { grid-template-columns: 1fr; }
      .account-overview-grid { grid-template-columns: repeat(3, 1fr); }
      .account-snapshot-grid { grid-template-columns: repeat(2, 1fr); }
      .execution-flow-grid { grid-template-columns: repeat(2, 1fr); }
      .daily-review-kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .account-panel-header, .account-main-toolbar { flex-direction: column; align-items: flex-start; }
    }
    @media (max-width: 768px) {
      .app { padding: 12px; }
      .app-shell { padding: 18px; border-radius: 18px; }
      .cosmic-identity-panel { padding: 16px; }
      .cosmic-identity-title { font-size: 2rem; letter-spacing: 0.14em; }
      .cosmic-visual-tiles { grid-template-columns: 1fr; }
      .metrics-grid { grid-template-columns: 1fr; }
      .header { flex-direction: column; align-items: flex-start; gap: 16px; }
      .header-status { justify-content: flex-start; }
      .dashboard-tabs { padding: 8px; gap: 8px; }
      .dashboard-tab { flex: 1 1 calc(50% - 8px); min-width: 0; }
      .decision-grid { grid-template-columns: 1fr; }
      .home-command-stat-grid,
      .home-command-chip-grid { grid-template-columns: 1fr; }
      .positions-grid { grid-template-columns: 1fr; }
      .trade-row { min-width: 640px; grid-template-columns: 60px 80px 50px 60px 70px 60px 60px; font-size: 0.7rem; }
      .analytics-grid { grid-template-columns: 1fr; }
      .analytics-row { min-width: 540px; grid-template-columns: 1.2fr 0.8fr 0.8fr 0.8fr 0.7fr; font-size: 0.68rem; }
      .daily-review-kpi-grid { grid-template-columns: 1fr 1fr; }
      .daily-review-grid { min-width: 920px; grid-template-columns: minmax(112px, 1fr) minmax(82px, 0.7fr) minmax(112px, 1fr) minmax(78px, 0.72fr) minmax(78px, 0.72fr) minmax(96px, 0.82fr) minmax(60px, 0.52fr) minmax(64px, 0.52fr); }
      .daily-review-row { font-size: 0.68rem; }
      .account-overview-grid { grid-template-columns: 1fr; }
      .account-snapshot-grid { grid-template-columns: 1fr; }
      .execution-flow-grid { grid-template-columns: 1fr; }
      .desktop-only { display: none; }
      .mobile-only { display: block; }
      .analytics-table.desktop-only { display: none; }
      .analytics-card-list.mobile-only { display: flex; }
      .trade-history.desktop-only { display: none; }
      .trade-card-list.mobile-only { display: flex; }
    }
    """

def render_dashboard_styles() -> str:
    return (
        _render_dashboard_base_styles()
        + _render_dashboard_component_styles()
        + _render_dashboard_responsive_styles()
    )

def render_dashboard_head() -> str:
    return f"""<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Momentum Alpha | 交易监控面板</title>
    <style>
    :root {{
      --bg-deep: #050507;
      --bg: #0b0d12;
      --bg-panel: linear-gradient(145deg, rgba(14,18,27,0.94), rgba(8,10,15,0.98));
      --bg-card: rgba(16,20,29,0.84);
      --fg: #f5f6f8;
      --fg-muted: #9aa3b2;
      --accent: #f5d28a;
      --accent-strong: #8ad2ff;
      --accent-glow: rgba(245,210,138,0.25);
      --success: #00ff88;
      --success-bg: rgba(0,255,136,0.1);
      --warning: #ffb800;
      --danger: #ff4466;
      --danger-bg: rgba(255,68,102,0.1);
      --border: rgba(184,160,120,0.12);
      --border-accent: rgba(245,210,138,0.32);
      --shadow: 0 16px 48px rgba(0,0,0,0.45);
      --radius: 18px;
      --radius-sm: 10px;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: 'SF Pro Display', 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', sans-serif;
      background:
        radial-gradient(circle at top right, rgba(245,210,138,0.12), transparent 28%),
        radial-gradient(circle at top left, rgba(138,210,255,0.08), transparent 24%),
        radial-gradient(circle at bottom left, rgba(120,80,255,0.08), transparent 26%),
        var(--bg-deep);
      color: var(--fg);
      min-height: 100vh;
      line-height: 1.5;
    }}
    .app {{
      max-width: 1600px;
      margin: 0 auto;
      padding: 24px;
    }}
    .app-shell {{
      position: relative;
      border: 1px solid rgba(245,210,138,0.1);
      border-radius: 30px;
      padding: 28px;
      background:
        radial-gradient(circle at 18% 12%, rgba(245,210,138,0.06), transparent 22%),
        radial-gradient(circle at 82% 4%, rgba(138,210,255,0.06), transparent 18%),
        linear-gradient(180deg, rgba(10,12,18,0.94), rgba(5,6,10,0.98));
      box-shadow: 0 28px 90px rgba(0,0,0,0.42);
      overflow: hidden;
    }}
    .app-shell::before {{
      content: '';
      position: absolute;
      inset: 0;
      background:
        linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px),
        linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px);
      background-size: 36px 36px;
      mask-image: linear-gradient(180deg, rgba(0,0,0,0.45), transparent 70%);
      pointer-events: none;
    }}
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 22px;
      padding: 18px 0 20px;
      border-bottom: 1px solid var(--border);
    }}
    .header-left {{
      display: flex;
      align-items: center;
      gap: 16px;
    }}
    .header-status {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .logo {{
      width: 48px;
      height: 48px;
      background: linear-gradient(135deg, rgba(245,210,138,0.96), rgba(138,210,255,0.68));
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      font-weight: 700;
      box-shadow: 0 4px 20px var(--accent-glow);
    }}
    .title-group h1 {{
      font-size: 1.5rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      background: linear-gradient(90deg, var(--fg), var(--accent));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .title-group p {{
      font-size: 0.8rem;
      color: var(--fg-muted);
      margin-top: 2px;
    }}
    .status-badge {{
      padding: 10px 20px;
      border-radius: 100px;
      font-size: 0.85rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      border: 1px solid;
    }}
    .status-badge.ok {{
      background: var(--success-bg);
      color: var(--success);
      border-color: rgba(0,255,136,0.3);
    }}
    .status-badge.fail {{
      background: var(--danger-bg);
      color: var(--danger);
      border-color: rgba(255,68,102,0.3);
      animation: pulse-danger 2s infinite;
    }}
    .mode-badge {{
      padding: 10px 16px;
      border-radius: 100px;
      font-size: 0.78rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      border: 1px solid;
    }}
    .mode-badge.danger {{
      background: rgba(255,68,102,0.14);
      color: var(--danger);
      border-color: rgba(255,68,102,0.45);
      box-shadow: 0 0 0 1px rgba(255,68,102,0.12);
    }}
    .mode-badge.warning {{
      background: rgba(255,184,0,0.11);
      color: var(--warning);
      border-color: rgba(255,184,0,0.36);
    }}
    @keyframes pulse-danger {{
      0%, 100% {{ box-shadow: 0 0 0 0 rgba(255,68,102,0.4); }}
      50% {{ box-shadow: 0 0 0 10px rgba(255,68,102,0); }}
    }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }}
    .metric {{
      background: var(--bg-panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      position: relative;
      overflow: hidden;
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    .metric:hover {{
      transform: translateY(-2px);
      box-shadow: var(--shadow);
    }}
    .metric.warning {{
      border-color: rgba(255,184,0,0.35);
      box-shadow: 0 0 0 1px rgba(255,184,0,0.08);
    }}
    .metric.danger {{
      border-color: rgba(255,68,102,0.38);
      box-shadow: 0 0 0 1px rgba(255,68,102,0.1);
    }}
    .metric::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), transparent);
    }}
    .metric-label {{
      font-size: 0.72rem;
      color: var(--fg-muted);
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-bottom: 8px;
    }}
    .metric-value {{
      font-size: 1.6rem;
      font-weight: 700;
      color: var(--fg);
    }}
    .metric-value.positive {{ color: var(--success); }}
    .metric-value.negative {{ color: var(--danger); }}
    .metric-sub {{
      font-size: 0.75rem;
      color: var(--fg-muted);
      margin-top: 6px;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: 1.2fr 0.9fr 0.9fr;
      gap: 16px;
      margin-bottom: 20px;
    }}
    .hero-card {{
      position: relative;
      padding: 18px;
      border-radius: 22px;
      border: 1px solid rgba(100,130,170,0.18);
      background: linear-gradient(160deg, rgba(15,23,38,0.92), rgba(8,12,19,0.96));
      overflow: hidden;
    }}
    .hero-card::before {{
      content: '';
      position: absolute;
      inset: 0 auto auto 0;
      width: 120px;
      height: 120px;
      background: radial-gradient(circle, rgba(0,212,255,0.16), transparent 68%);
      pointer-events: none;
    }}
    .hero-card-wide {{
      min-height: 240px;
    }}
    .hero-card-compact {{
      min-height: 240px;
    }}
    .hero-eyebrow {{
      position: relative;
      font-size: 0.68rem;
      letter-spacing: 0.16em;
      color: var(--accent);
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .hero-title {{
      position: relative;
      font-size: 1.25rem;
      font-weight: 700;
      margin-bottom: 12px;
    }}
    .hero-copy {{
      position: relative;
      max-width: 32rem;
      font-size: 0.84rem;
      color: var(--fg-muted);
      margin-bottom: 16px;
    }}
    .home-command-panel {{ padding: 20px; }}
    .active-positions-panel {{
      padding: 18px;
      border-color: rgba(0,212,255,0.22);
      background: linear-gradient(145deg, rgba(11,18,31,0.96), rgba(6,10,17,0.98));
    }}
    .home-command-grid {{
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 16px;
    }}
    .home-command-column {{
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .home-command-card {{
      background: rgba(0,0,0,0.2);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
    }}
    .home-command-card-muted {{
      background: linear-gradient(145deg, rgba(11,19,32,0.92), rgba(10,14,24,0.88));
    }}
    .home-command-card-header {{
      font-size: 0.72rem;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-bottom: 14px;
    }}
    .home-command-stat-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }}
    .home-command-stat {{
      padding: 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.02);
      border: 1px solid var(--border);
    }}
    .home-command-label {{
      font-size: 0.68rem;
      color: var(--fg-muted);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-bottom: 8px;
    }}
    .home-command-value {{
      font-size: 1.02rem;
      font-weight: 700;
      word-break: break-word;
    }}
    .home-command-chip-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }}
    .home-command-chip {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(0,212,255,0.05);
      border: 1px solid rgba(0,212,255,0.12);
      color: var(--fg-muted);
      font-size: 0.76rem;
    }}
    .home-command-chip strong {{
      color: var(--fg);
      font-size: 0.92rem;
      font-weight: 700;
    }}
    .next-actions-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
    }}
    .next-action-card {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 16px;
      border-radius: 16px;
      text-decoration: none;
      color: var(--fg);
      background: linear-gradient(145deg, rgba(9,17,29,0.95), rgba(7,13,23,0.9));
      border: 1px solid rgba(100,130,170,0.18);
      transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
    }}
    .next-action-card:hover {{
      transform: translateY(-2px);
      border-color: var(--border-accent);
      box-shadow: 0 10px 24px rgba(0,0,0,0.22);
    }}
    .next-action-label {{
      font-size: 1rem;
      font-weight: 700;
      color: var(--fg);
    }}
    .next-action-copy {{
      font-size: 0.8rem;
      line-height: 1.5;
      color: var(--fg-muted);
    }}
    .toolbar {{
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 20px;
    }}
    .dashboard-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 20px;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 18px;
      background: rgba(255,255,255,0.02);
      backdrop-filter: blur(18px);
    }}
    .dashboard-tab {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 120px;
      padding: 10px 16px;
      border-radius: 999px;
      border: 1px solid transparent;
      color: var(--fg-muted);
      text-decoration: none;
      font-size: 0.76rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      transition: transform 0.2s, background 0.2s, border-color 0.2s, color 0.2s;
    }}
    .dashboard-tab:hover {{
      transform: translateY(-1px);
      color: var(--fg);
      background: rgba(255,255,255,0.04);
    }}
    .dashboard-tab.is-active {{
      color: var(--fg);
      border-color: var(--border-accent);
      background: rgba(245,210,138,0.1);
      box-shadow: 0 0 0 1px rgba(245,210,138,0.08);
    }}
    .dashboard-tab-shell {{
      min-height: 480px;
    }}
    .dashboard-tab-panel {{
      display: block;
    }}
    .toolbar-spacer {{
      flex: 1;
    }}
    .status-line {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
      color: var(--fg-muted);
      font-size: 0.76rem;
    }}
    .action-button {{
      border: 1px solid var(--border-accent);
      background: rgba(245,210,138,0.08);
      color: var(--fg);
      border-radius: 999px;
      padding: 9px 14px;
      font-size: 0.72rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      cursor: pointer;
      transition: transform 0.2s, background 0.2s, border-color 0.2s;
    }}
    .action-button:hover {{
      transform: translateY(-1px);
      background: rgba(245,210,138,0.16);
    }}
    .action-button.is-refreshing {{
      border-color: rgba(255,184,0,0.35);
      background: rgba(255,184,0,0.1);
    }}

    <!-- render_dashboard_styles -->
    {render_dashboard_styles()}
    </style>
</head>"""

def render_dashboard_scripts() -> str:
    return """  <script>
    const ACCOUNT_METRIC_STORAGE_KEY = 'dashboard.account.metric';
    const ACCOUNT_RANGE_STORAGE_KEY = 'dashboard.account.range';
    const COLLAPSED_SECTIONS_STORAGE_KEY = 'dashboard.collapsed-sections';
    const DASHBOARD_SECTION_SELECTORS = [
      '[data-dashboard-section="status"]',
      '[data-dashboard-section="toolbar"]',
      '[data-dashboard-section="room-nav"]',
      '[data-dashboard-active-room]',
    ];

    function getAccountMetricsData() {{
      const jsonNode = document.getElementById('account-metrics-json');
      if (!jsonNode) return [];
      try {{
        return JSON.parse(jsonNode.textContent || '[]');
      }} catch (error) {{
        console.error(error);
        return [];
      }}
    }}
    function getCollapsedSections() {{
      try {{
        return JSON.parse(localStorage.getItem(COLLAPSED_SECTIONS_STORAGE_KEY) || '[]');
      }} catch (error) {{
        return [];
      }}
    }}
    function writeCollapsedSections(nextCollapsedSections) {{
      localStorage.setItem(COLLAPSED_SECTIONS_STORAGE_KEY, JSON.stringify(nextCollapsedSections));
    }}
    function applyCollapsedSections() {{
      const collapsedSections = new Set(getCollapsedSections());
      document.querySelectorAll('[data-collapsible-section]').forEach((section) => {{
        const sectionKey = section.dataset.collapsibleSection;
        const isCollapsed = collapsedSections.has(sectionKey);
        section.classList.toggle('is-collapsed', isCollapsed);
        const toggle = section.querySelector('[data-section-toggle]');
        if (toggle) toggle.textContent = isCollapsed ? 'Expand' : 'Collapse';
      }});
    }}
    function formatAccountValue(value, signed = false, suffix = '') {{
      if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
      const numericValue = Number(value);
      if (signed && numericValue === 0) return `0.00${{suffix}}`;
      const formatted = numericValue.toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
      const withSign = signed ? `${{numericValue > 0 ? '+' : ''}}${{formatted}}` : formatted;
      return `${{withSign}}${{suffix}}`;
    }}
    function formatAccountWindowTimestamp(timestamp) {{
      if (!timestamp) return 'n/a';
      const date = new Date(timestamp);
      const parts = new Intl.DateTimeFormat('zh-CN', {{
        hour12: false,
        timeZone: 'Asia/Shanghai',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      }}).formatToParts(date);
      const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
      return `${{lookup.month}}-${{lookup.day}} ${{lookup.hour}}:${{lookup.minute}}`;
    }}
    function filterAccountPoints(points, range) {{
      if (!points.length || range === 'ALL') return points;
      const hours = {{ '1H': 1, '1D': 24, '1W': 24 * 7, '1M': 24 * 30, '1Y': 24 * 365 }}[range] || 24;
      const latest = new Date(points[points.length - 1].timestamp).getTime();
      const cutoff = latest - hours * 60 * 60 * 1000;
      const filtered = points.filter((point) => new Date(point.timestamp).getTime() >= cutoff);
      return filtered.length ? filtered : points;
    }}
    function buildAccountChartSvg(points, metric) {{
      if (!points.length) {{
        return `<div class="chart-empty"><span class="chart-empty-icon">◎</span><span>waiting for account history</span></div>`;
      }}
      const width = 920;
      const height = 280;
      const padX = 56;
      const padY = 20;
      const values = points.map((point) => point[metric]);
      const numericValues = values.filter((value) => value !== null && value !== undefined && !Number.isNaN(value));
      if (!numericValues.length || numericValues.length !== values.length) {{
        return `<div class="chart-empty"><span class="chart-empty-icon">◎</span><span>waiting for visible metric data</span></div>`;
      }}
      const minValue = Math.min(...numericValues);
      const maxValue = Math.max(...numericValues);
      const spread = Math.max(maxValue - minValue, 1e-9);
      const chartWidth = width - padX * 2;
      const chartHeight = height - padY * 2;
      const axisSuffix = metric.endsWith('_pct') ? '%' : '';
      const coords = numericValues.map((value, index) => {{
        const x = padX + (chartWidth * index / Math.max(values.length - 1, 1));
        const y = padY + chartHeight - (((value - minValue) / spread) * chartHeight);
        return [x, y];
      }});
      const polyline = coords.map(([x, y]) => `${{x.toFixed(2)}},${{y.toFixed(2)}}`).join(' ');
      const area = `${{coords[0][0].toFixed(2)}},${{(height - padY).toFixed(2)}} ` + polyline + ` ${{coords[coords.length - 1][0].toFixed(2)}},${{(height - padY).toFixed(2)}}`;
      const palette = {{ equity: '#4cc9f0', adjusted_equity: '#ffbc42', wallet_balance: '#36d98a', unrealized_pnl: '#a855f7', margin_usage_pct: '#ff8c42' }};
      const stroke = palette[metric] || '#4cc9f0';
      let grid = '';
      let labels = '';
      for (let i = 0; i < 5; i++) {{
        const y = padY + (chartHeight * i / 4);
        const val = maxValue - (spread * i / 4);
        grid += `<line x1="${{padX}}" y1="${{y.toFixed(2)}}" x2="${{width - padX}}" y2="${{y.toFixed(2)}}" class="account-grid-line" />`;
        labels += `<text x="${{padX - 8}}" y="${{(y + 4).toFixed(2)}}" class="account-axis-label" text-anchor="end">${{formatAccountValue(val, false, axisSuffix)}}</text>`;
      }}
      const last = coords[coords.length - 1];
      return `
        <svg viewBox="0 0 ${{width}} ${{height}}" class="account-chart-svg" role="img" aria-label="${{metric}} account chart">
          <defs>
            <linearGradient id="account-gradient-${{metric}}" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stop-color="${{stroke}}" stop-opacity="0.38"></stop>
              <stop offset="100%" stop-color="${{stroke}}" stop-opacity="0.02"></stop>
            </linearGradient>
          </defs>
          ${{grid}}
          ${{labels}}
          <polygon points="${{area}}" fill="url(#account-gradient-${{metric}})" class="account-series-area"></polygon>
          <polyline points="${{polyline}}" stroke="${{stroke}}" class="account-series-line"></polyline>
          <circle cx="${{last[0].toFixed(2)}}" cy="${{last[1].toFixed(2)}}" r="4" fill="${{stroke}}" class="account-last-dot"></circle>
        </svg>`;
    }}
    function updateAccountOverview(points, metric, range) {{
      if (!points.length) return;
      const first = points[0];
      const last = points[points.length - 1];
      const numericValues = points
        .map((point) => ({{
          equity: point.equity,
          wallet_balance: point.wallet_balance,
          adjusted_equity: point.adjusted_equity,
          unrealized_pnl: point.unrealized_pnl,
          margin_usage_pct: point.margin_usage_pct,
        }}));
      const equityPoints = numericValues
        .map((point) => point.equity)
        .filter((value) => value !== null && value !== undefined && !Number.isNaN(value));
      const peakEquity = equityPoints.length ? Math.max(...equityPoints) : null;
      const marginUsagePoints = points
        .map((point) => point.margin_usage_pct)
        .filter((value) => value !== null && value !== undefined && !Number.isNaN(value));
      const currentEquity = last.equity;
      const drawdownAbs = (currentEquity === null || currentEquity === undefined || peakEquity === null)
        ? null
        : currentEquity - peakEquity;
      const drawdownPct = (drawdownAbs === null || !peakEquity) ? null : (drawdownAbs / peakEquity) * 100;
      const currentMarginUsage = last.margin_usage_pct;
      const peakMarginUsage = marginUsagePoints.length ? Math.max(...marginUsagePoints) : null;
      const averageMarginUsage = marginUsagePoints.length
        ? marginUsagePoints.reduce((sum, value) => sum + value, 0) / marginUsagePoints.length
        : null;
      const computeDelta = (start, end) => {{
        if (start === null || start === undefined || end === null || end === undefined) return null;
        return end - start;
      }};
      const deltas = {{
        wallet_balance: computeDelta(first.wallet_balance, last.wallet_balance),
        equity: computeDelta(first.equity, last.equity),
        adjusted_equity: computeDelta(first.adjusted_equity, last.adjusted_equity),
        unrealized_pnl: computeDelta(first.unrealized_pnl, last.unrealized_pnl),
        margin_usage_pct: computeDelta(first.margin_usage_pct, last.margin_usage_pct),
      }};
      const values = {{
        wallet_balance: formatAccountValue(last.wallet_balance),
        equity: formatAccountValue(last.equity),
        adjusted_equity: formatAccountValue(last.adjusted_equity),
        unrealized_pnl: formatAccountValue(last.unrealized_pnl, true),
        current_margin_usage_pct: formatAccountValue(currentMarginUsage, false, '%'),
        peak_margin_usage_pct: formatAccountValue(peakMarginUsage, false, '%'),
        average_margin_usage_pct: formatAccountValue(averageMarginUsage, false, '%'),
        exposure: `${{last.position_count ?? 0}} / ${{last.open_order_count ?? 0}}`,
        peak_equity: formatAccountValue(peakEquity),
        drawdown: formatAccountValue(drawdownAbs, true),
      }};
      Object.entries(values).forEach(([key, value]) => {{
        const node = document.querySelector(`[data-account-value="${{key}}"]`);
        if (node) node.textContent = value;
      }});
      ['wallet_balance', 'equity', 'adjusted_equity', 'unrealized_pnl', 'margin_usage_pct'].forEach((key) => {{
        const node = document.querySelector(`[data-account-delta="${{key}}"]`);
        if (node) node.textContent = `Range Δ ${{formatAccountValue(deltas[key], true, key.endsWith('_pct') ? '%' : '')}}`;
      }});
      const ddNode = document.querySelector('[data-account-drawdown-pct]');
      if (ddNode) ddNode.textContent = formatAccountValue(drawdownPct, true, '%');
      const pointCountNode = document.querySelector('[data-account-point-count]');
      if (pointCountNode) pointCountNode.textContent = `${{points.length}} points`;
      const labelNode = document.querySelector('[data-account-window-label]');
      const metricLabels = {{
        equity: 'EQUITY',
        adjusted_equity: 'ADJUSTED EQUITY',
        wallet_balance: 'WALLET',
        unrealized_pnl: 'UNREALIZED PNL',
        margin_usage_pct: 'MARGIN USAGE %',
      }};
      if (labelNode) labelNode.textContent = `${{range}} · ${{metricLabels[metric] || metric.replace('_', ' ').toUpperCase()}} · ${{formatAccountWindowTimestamp(first.timestamp)}} → ${{formatAccountWindowTimestamp(last.timestamp)}}`;
    }}
    let accountMetricsData = [];
    let activeMetric = 'equity';
    let activeRange = '1D';
    function renderAccountChart() {{
      const chartNode = document.getElementById('account-metrics-chart');
      const chartWrapper = document.querySelector('.account-main-chart') || chartNode?.parentElement;
      if (chartNode) {{
        chartNode.innerHTML = buildAccountChartSvg(accountMetricsData, activeMetric);
      }} else if (chartWrapper) {{
        // If the chart node doesn't exist (e.g., was replaced by empty state), recreate it
        const wrapper = document.createElement('div');
        wrapper.id = 'account-metrics-chart';
        wrapper.className = 'account-main-chart';
        wrapper.innerHTML = buildAccountChartSvg(accountMetricsData, activeMetric);
        const emptyNode = chartWrapper.querySelector('.chart-empty');
        if (emptyNode) {{
          emptyNode.replaceWith(wrapper);
        }} else {{
          chartWrapper.innerHTML = '';
          chartWrapper.appendChild(wrapper);
        }}
      }}
      updateAccountOverview(accountMetricsData, activeMetric, activeRange);
    }}
    function buildDashboardApiUrl(endpoint, range) {{
      const basePath = window.location.pathname.replace(/\\/$/, "");
      return `${{basePath}}${{endpoint}}?range=${{encodeURIComponent(range)}}`;
    }}
    function getSelectedAccountRange() {{
      const urlRange = new URL(window.location.href).searchParams.get('range');
      if (urlRange) return urlRange;
      const activeButton = document.querySelector('[data-account-range].active');
      if (activeButton?.dataset.accountRange) return activeButton.dataset.accountRange;
      return localStorage.getItem('dashboard.account.range') || '1D';
    }}
    async function loadAccountRange(range) {{
      try {{
        const response = await fetch(buildDashboardApiUrl('/api/dashboard/timeseries', range), {{ cache: 'no-store' }});
        if (!response.ok) throw new Error(`account range fetch failed: ${{response.status}}`);
        const payload = await response.json();
        accountMetricsData = Array.isArray(payload.account) ? payload.account : [];
        renderAccountChart();
      }} catch (error) {{
        console.error(error);
        renderAccountChart();
      }}
    }}
    function initializeAccountMetrics() {{
      accountMetricsData = getAccountMetricsData();
      if (!Array.isArray(accountMetricsData)) return;
      activeMetric = localStorage.getItem('dashboard.account.metric') || 'equity';
      activeRange = getSelectedAccountRange();
      document.querySelectorAll('[data-account-metric]').forEach((button) => {{
        button.addEventListener('click', () => {{
          activeMetric = button.dataset.accountMetric;
          localStorage.setItem('dashboard.account.metric', activeMetric);
          document.querySelectorAll('[data-account-metric]').forEach((node) => node.classList.toggle('active', node === button));
          renderAccountChart();
        }});
      }});
      document.querySelectorAll('[data-account-range]').forEach((button) => {{
        button.addEventListener('click', async () => {{
          activeRange = button.dataset.accountRange;
          localStorage.setItem('dashboard.account.range', activeRange);
          document.querySelectorAll('[data-account-range]').forEach((node) => node.classList.toggle('active', node === button));
          await loadAccountRange(activeRange);
        }});
      }});
      document.querySelectorAll('[data-account-metric]').forEach((node) => node.classList.toggle('active', node.dataset.accountMetric === activeMetric));
      document.querySelectorAll('[data-account-range]').forEach((node) => node.classList.toggle('active', node.dataset.accountRange === activeRange));
      if (activeRange === '1D') {{
        renderAccountChart();
      }} else {{
        loadAccountRange(activeRange);
      }}
    }}
    function bindDashboardControls() {{
      const refreshButton = document.getElementById('manual-refresh-button');
      if (refreshButton) {{
        refreshButton.onclick = () => refreshDashboard(true);
      }}
      document.querySelectorAll('[data-section-toggle]').forEach((toggle) => {{
        toggle.onclick = () => {{
          const sectionKey = toggle.dataset.sectionToggle;
          const collapsedSections = new Set(getCollapsedSections());
          if (collapsedSections.has(sectionKey)) {{
            collapsedSections.delete(sectionKey);
          }} else {{
            collapsedSections.add(sectionKey);
          }}
          writeCollapsedSections(Array.from(collapsedSections));
          applyCollapsedSections();
        }};
      }});
      applyCollapsedSections();
    }}
    function replaceSectionFromDocument(nextDocument, selector) {{
      const current = document.querySelector(selector);
      const replacement = nextDocument.querySelector(selector);
      if (current && replacement) {{
        current.replaceWith(replacement);
      }}
    }}
    function setRefreshIndicatorState(state, label) {{
      const indicator = document.getElementById('refresh-indicator');
      const indicatorText = document.getElementById('refresh-indicator-text');
      if (!indicator || !indicatorText) return;
      indicator.classList.toggle('error', state === 'error');
      indicatorText.textContent = label;
    }}
    async function refreshDashboard(force = false) {{
      const refreshButton = document.getElementById('manual-refresh-button');
      const activeRoom = document.querySelector('[data-dashboard-active-room]')?.dataset.dashboardActiveRoom;
      if (!force && activeRoom === 'review') return;
      try {{
        if (refreshButton) refreshButton.classList.add('is-refreshing');
        const currentUrl = `${{window.location.pathname}}${{window.location.search}}`;
        const res = await fetch(currentUrl, {{ cache: 'no-store' }});
        if (!res.ok) {{
          setRefreshIndicatorState('error', 'Unable to refresh');
          return;
        }}
        const html = await res.text();
        const nextDocument = new DOMParser().parseFromString(html, 'text/html');
        DASHBOARD_SECTION_SELECTORS.forEach((selector) => replaceSectionFromDocument(nextDocument, selector));
        const nextTitle = nextDocument.querySelector('title');
        if (nextTitle) document.title = nextTitle.textContent || document.title;
        // Preserve user-selected range on refresh
        activeMetric = localStorage.getItem('dashboard.account.metric') || 'equity';
        activeRange = getSelectedAccountRange();
        if (activeRange === '1D') {{
          // Reload from DOM for default range
          accountMetricsData = getAccountMetricsData();
          renderAccountChart();
        }} else {{
          // Reload via API for custom range
          await loadAccountRange(activeRange);
        }}
        // Update button states
        document.querySelectorAll('[data-account-metric]').forEach((node) => node.classList.toggle('active', node.dataset.accountMetric === activeMetric));
        document.querySelectorAll('[data-account-range]').forEach((node) => node.classList.toggle('active', node.dataset.accountRange === activeRange));
        bindDashboardControls();
        setRefreshIndicatorState('ok', 'Auto refresh: 5s');
      }} catch (e) {{
        console.error(e);
        setRefreshIndicatorState('error', 'Unable to refresh');
      }}
      finally {{
        if (refreshButton) refreshButton.classList.remove('is-refreshing');
      }}
    }}
    initializeAccountMetrics();
    bindDashboardControls();
    setInterval(() => refreshDashboard(false), 5000);
  </script>
</body>
</html>""".replace("{{", "{").replace("}}", "}")
