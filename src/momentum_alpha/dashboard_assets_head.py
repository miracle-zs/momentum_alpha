from __future__ import annotations

from functools import lru_cache

from .dashboard_assets_styles import render_dashboard_styles

ECHARTS_CDNJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/echarts/5.6.0/echarts.min.js"
ECHARTS_CDNJS_INTEGRITY = "sha512-XSmbX3mhrD2ix5fXPTRQb2FwK22sRMVQTpBP2ac8hX7Dh/605hA2QDegVWiAvZPiXIxOV0CbkmUjGionDpbCmw=="
ECHARTS_JSDELIVR_URL = "https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"
DASHBOARD_CSS_ASSET_PATH = "assets/dashboard.css?v=1"
DASHBOARD_CSS_ASSET_ROUTE = "/assets/dashboard.css"
DASHBOARD_JS_ASSET_PATH = "assets/dashboard.js?v=2"
DASHBOARD_JS_ASSET_ROUTE = "/assets/dashboard.js"


@lru_cache(maxsize=2)
def render_dashboard_head(*, external_stylesheet: bool = False) -> str:
    head = f"""<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Momentum Alpha | 交易监控面板</title>
  <link rel="preconnect" href="https://cdnjs.cloudflare.com" crossorigin>
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
      padding: 8px 20px 16px;
    }}
    .app-shell {{
      position: relative;
      padding: 0;
      background: transparent;
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
      gap: 18px;
      margin-bottom: 0;
      padding: 10px 0 12px;
      border-bottom: 1px solid var(--border);
    }}
    .header-left {{
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 0 0 auto;
    }}
    .header-status {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
      min-width: 0;
      flex: 1 1 auto;
    }}
    .header-runtime {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      min-width: 0;
      margin-right: 4px;
    }}
    .logo {{
      width: 40px;
      height: 40px;
      background: linear-gradient(135deg, rgba(245,210,138,0.96), rgba(138,210,255,0.68));
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      font-weight: 700;
      box-shadow: 0 4px 20px var(--accent-glow);
    }}
    .title-group h1 {{
      font-size: 1.15rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      background: linear-gradient(90deg, var(--fg), var(--accent));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .title-group p {{
      font-size: 0.7rem;
      color: var(--fg-muted);
      margin-top: 1px;
    }}
    .status-badge {{
      padding: 7px 12px;
      border-radius: 100px;
      font-size: 0.7rem;
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
      padding: 7px 11px;
      border-radius: 100px;
      font-size: 0.68rem;
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
      grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.75fr);
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
    .active-positions-panel {{
      padding: 18px;
      border-color: rgba(0,212,255,0.22);
      background: linear-gradient(145deg, rgba(11,18,31,0.96), rgba(6,10,17,0.98));
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
      gap: 26px;
      margin-bottom: 14px;
      padding: 0 2px;
      border-bottom: 1px solid var(--border);
    }}
    .dashboard-tab {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 0;
      padding: 11px 2px 10px;
      border-bottom: 2px solid transparent;
      color: var(--fg-muted);
      text-decoration: none;
      font-size: 0.72rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      transition: transform 0.2s, background 0.2s, border-color 0.2s, color 0.2s;
    }}
    .dashboard-tab:hover {{
      color: var(--fg);
      border-bottom-color: rgba(245,210,138,0.28);
    }}
    .dashboard-tab.is-active {{
      color: var(--accent);
      border-bottom-color: var(--accent);
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
      padding: 6px 9px;
      border-radius: 999px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
      color: var(--fg-muted);
      font-size: 0.68rem;
    }}
    .action-button {{
      border: 1px solid var(--border-accent);
      background: rgba(245,210,138,0.08);
      color: var(--fg);
      border-radius: 999px;
      padding: 7px 10px;
      font-size: 0.68rem;
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
    .header-refresh-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      min-height: 30px;
    }}

    <!-- render_dashboard_styles -->
    {render_dashboard_styles()}
    </style>
</head>"""
    if not external_stylesheet:
        return head

    style_start = head.index("    <style>")
    style_end = head.index("    </style>", style_start) + len("    </style>")
    return (
        head[:style_start]
        + f'  <link rel="stylesheet" href="{DASHBOARD_CSS_ASSET_PATH}">\n'
        + head[style_end:]
    )


def render_dashboard_stylesheet() -> str:
    """Return the dashboard CSS without the surrounding HTML style tag."""

    head = render_dashboard_head()
    style_start = head.index("<style>") + len("<style>")
    style_end = head.index("</style>", style_start)
    return head[style_start:style_end].replace("    <!-- render_dashboard_styles -->\n", "").strip() + "\n"
