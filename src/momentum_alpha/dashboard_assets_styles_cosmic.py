from __future__ import annotations


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
