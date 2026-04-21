from __future__ import annotations

from .dashboard_assets_styles import render_dashboard_styles

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
