from __future__ import annotations

from .dashboard_assets_styles import render_dashboard_styles

ECHARTS_CDNJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/echarts/5.6.0/echarts.min.js"
ECHARTS_CDNJS_INTEGRITY = "sha512-XSmbX3mhrD2ix5fXPTRQb2FwK22sRMVQTpBP2ac8hX7Dh/605hA2QDegVWiAvZPiXIxOV0CbkmUjGionDpbCmw=="
ECHARTS_JSDELIVR_URL = "https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"

def render_dashboard_head() -> str:
    return f"""<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Momentum Alpha | 交易监控面板</title>
  <script>
    window.__loadFallbackECharts = function () {{
      if (window.echarts) {{
        window.dispatchEvent(new Event('echarts-ready'));
        return;
      }}
      if (window.__echartsFallbackRequested) return;
      window.__echartsFallbackRequested = true;
      const fallback = document.createElement('script');
      fallback.src = "{ECHARTS_JSDELIVR_URL}";
      fallback.defer = true;
      fallback.onload = function () {{
        window.dispatchEvent(new Event('echarts-ready'));
      }};
      fallback.onerror = function () {{
        window.dispatchEvent(new Event('echarts-unavailable'));
      }};
      document.head.appendChild(fallback);
    }};
  </script>
  <script src="{ECHARTS_CDNJS_URL}" integrity="{ECHARTS_CDNJS_INTEGRITY}" crossorigin="anonymous" defer onload="window.dispatchEvent(new Event('echarts-ready'))" onerror="window.__loadFallbackECharts()"></script>
    <style>
    :root {{
      --bg-deep: #08090c;
      --bg: #08090c;
      --bg-panel: #0e1117;
      --bg-card: #12161f;
      --well: #0a0d13;
      --fg: #e8ecf3;
      --fg-muted: #99a3b6;
      --fg-faint: #5f6b80;
      --accent: #f0b429;
      --accent-soft: rgba(240,180,41,0.1);
      --accent-strong: #58a6ff;
      --accent-glow: rgba(240,180,41,0.16);
      --success: #0ecb81;
      --success-bg: rgba(14,203,129,0.09);
      --warning: #f0b429;
      --warning-bg: rgba(240,180,41,0.09);
      --danger: #f6465d;
      --danger-bg: rgba(246,70,93,0.09);
      --line: rgba(151,163,186,0.11);
      --line-strong: rgba(151,163,186,0.22);
      --border: rgba(151,163,186,0.11);
      --border-accent: rgba(240,180,41,0.42);
      --shadow: 0 10px 28px rgba(0,0,0,0.32);
      --radius: 12px;
      --radius-sm: 8px;
      --font-ui: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
      --font-mono: ui-monospace, 'SF Mono', 'JetBrains Mono', 'Cascadia Code', 'Roboto Mono', Menlo, Consolas, monospace;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html {{ scrollbar-color: rgba(151,163,186,0.28) transparent; }}
    body {{
      font-family: var(--font-ui);
      background: var(--bg);
      color: var(--fg);
      min-height: 100vh;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
    }}
    ::selection {{ background: rgba(240,180,41,0.25); }}
    .app {{
      max-width: 1600px;
      margin: 0 auto;
      padding: 0 28px 40px;
    }}
    .app-shell {{
      position: relative;
    }}
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 0 14px;
      border-bottom: 1px solid var(--line);
    }}
    .header-left {{
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }}
    .header-status {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .logo {{
      width: 34px;
      height: 34px;
      flex-shrink: 0;
      background: linear-gradient(160deg, #f8ca5e, #eda711);
      color: #131007;
      border-radius: 9px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 17px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }}
    .title-group h1 {{
      font-size: 1.02rem;
      font-weight: 650;
      letter-spacing: 0.01em;
      color: var(--fg);
      line-height: 1.25;
    }}
    .title-group p {{
      font-size: 0.72rem;
      color: var(--fg-faint);
      margin-top: 1px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .status-badge {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 5px 11px;
      border-radius: 7px;
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      border: 1px solid;
    }}
    .status-badge::before {{
      content: '';
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: currentColor;
    }}
    .status-badge.ok {{
      background: var(--success-bg);
      color: var(--success);
      border-color: rgba(14,203,129,0.28);
    }}
    .status-badge.fail {{
      background: var(--danger-bg);
      color: var(--danger);
      border-color: rgba(246,70,93,0.3);
      animation: pulse-danger 2s infinite;
    }}
    .mode-badge {{
      padding: 5px 11px;
      border-radius: 7px;
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      border: 1px solid;
    }}
    .mode-badge.danger {{
      background: var(--danger-bg);
      color: var(--danger);
      border-color: rgba(246,70,93,0.35);
    }}
    .mode-badge.warning {{
      background: var(--warning-bg);
      color: var(--warning);
      border-color: rgba(240,180,41,0.32);
    }}
    @keyframes pulse-danger {{
      0%, 100% {{ box-shadow: 0 0 0 0 rgba(246,70,93,0.32); }}
      50% {{ box-shadow: 0 0 0 8px rgba(246,70,93,0); }}
    }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 20px;
    }}
    .metric {{
      background: var(--bg-panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px;
      position: relative;
    }}
    .metric.warning {{ border-color: rgba(240,180,41,0.35); }}
    .metric.danger {{ border-color: rgba(246,70,93,0.38); }}
    .metric-label {{
      font-size: 0.66rem;
      color: var(--fg-faint);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 6px;
    }}
    .metric-value {{
      font-size: 1.35rem;
      font-weight: 650;
      color: var(--fg);
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.02em;
    }}
    .metric-value.positive {{ color: var(--success); }}
    .metric-value.negative {{ color: var(--danger); }}
    .metric-sub {{
      font-size: 0.72rem;
      color: var(--fg-muted);
      margin-top: 5px;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.75fr);
      gap: 12px;
    }}
    .hero-card {{
      position: relative;
      padding: 16px;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: var(--bg-card);
      min-width: 0;
    }}
    .hero-card-wide {{
      min-height: 220px;
    }}
    .hero-card-compact {{
      min-height: 220px;
    }}
    .hero-eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      font-size: 0.64rem;
      letter-spacing: 0.14em;
      color: var(--accent);
      text-transform: uppercase;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .hero-eyebrow::before {{
      content: '';
      width: 14px;
      height: 2px;
      border-radius: 1px;
      background: var(--accent);
    }}
    .hero-title {{
      font-size: 1.05rem;
      font-weight: 700;
      letter-spacing: 0.01em;
      margin-bottom: 8px;
    }}
    .hero-copy {{
      max-width: 34rem;
      font-size: 0.78rem;
      color: var(--fg-muted);
      margin-bottom: 14px;
    }}
    .active-positions-panel {{
      padding: 16px;
    }}
    .toolbar {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      padding: 10px 0;
    }}
    .dashboard-tabs {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 2px;
      margin-bottom: 18px;
      border-bottom: 1px solid var(--line);
    }}
    .dashboard-tab {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      position: relative;
      min-width: 96px;
      padding: 9px 16px 11px;
      border: none;
      color: var(--fg-muted);
      text-decoration: none;
      font-size: 0.8rem;
      font-weight: 550;
      letter-spacing: 0.02em;
      transition: color 0.15s;
    }}
    .dashboard-tab::after {{
      content: '';
      position: absolute;
      left: 12px;
      right: 12px;
      bottom: -1px;
      height: 2px;
      border-radius: 1px;
      background: transparent;
      transition: background 0.15s;
    }}
    .dashboard-tab:hover {{
      color: var(--fg);
    }}
    .dashboard-tab.is-active {{
      color: var(--fg);
      font-weight: 650;
    }}
    .dashboard-tab.is-active::after {{
      background: var(--accent);
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
      gap: 8px;
      padding: 5px 10px;
      border-radius: 7px;
      background: transparent;
      border: 1px solid var(--line);
      color: var(--fg-faint);
      font-size: 0.72rem;
    }}
    .status-line strong {{
      color: var(--fg-muted);
      font-weight: 600;
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
    }}
    .action-button {{
      border: 1px solid var(--line-strong);
      background: transparent;
      color: var(--fg-muted);
      border-radius: 7px;
      padding: 6px 12px;
      font-size: 0.68rem;
      font-weight: 650;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      cursor: pointer;
      transition: color 0.15s, border-color 0.15s, background 0.15s;
    }}
    .action-button:hover {{
      color: var(--fg);
      border-color: var(--border-accent);
      background: var(--accent-soft);
    }}
    .action-button.is-refreshing {{
      border-color: rgba(240,180,41,0.4);
      color: var(--warning);
      background: var(--warning-bg);
    }}

    <!-- render_dashboard_styles -->
    {render_dashboard_styles()}
    </style>
</head>"""
