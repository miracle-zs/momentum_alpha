from __future__ import annotations


def _render_dashboard_cosmic_styles() -> str:
    return """
    .cosmic-identity-panel {
      display: grid;
      grid-template-columns: 0.92fr 1.08fr;
      gap: 14px;
      margin-bottom: 18px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--bg-panel);
    }
    .cosmic-identity-copy {
      max-width: 360px;
    }
    .cosmic-identity-kicker {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      margin-bottom: 12px;
      border: 1px solid var(--border-accent);
      border-radius: 7px;
      color: var(--accent);
      font-size: 0.66rem;
      font-weight: 700;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      background: var(--accent-soft);
    }
    .cosmic-identity-title {
      font-size: clamp(1.8rem, 4vw, 3rem);
      line-height: 1;
      letter-spacing: 0.12em;
      font-weight: 300;
      margin-bottom: 12px;
    }
    .cosmic-identity-subtitle {
      font-size: 0.82rem;
      line-height: 1.7;
      color: var(--fg-muted);
      max-width: 34rem;
    }
    .cosmic-identity-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .cosmic-identity-card {
      position: relative;
      overflow: hidden;
      min-height: 216px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--bg-card);
    }
    .cosmic-identity-card-label {
      font-size: 0.64rem;
      color: var(--accent);
      font-weight: 700;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      margin-bottom: 12px;
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
      width: 36px;
      height: 36px;
      border-radius: 10px;
      border: 1px solid var(--line-strong);
      flex-shrink: 0;
    }
    .cosmic-dot-black { background: #08090c; }
    .cosmic-dot-space { background: #12161f; }
    .cosmic-dot-white { background: #e8ecf3; }
    .cosmic-dot-gold { background: #f0b429; }
    .cosmic-dot-purple { background: #1a1c2a; }
    .cosmic-swatch-name {
      font-size: 0.82rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .cosmic-swatch-value {
      font-size: 0.7rem;
      color: var(--fg-faint);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-top: 2px;
      font-family: var(--font-mono);
    }
    .cosmic-gradient-bar {
      height: 30px;
      margin-top: 14px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: linear-gradient(90deg, #58a6ff 0%, #12161f 30%, #f0b429 55%, #f6465d 80%, #08090c 100%);
    }
    .cosmic-component-row,
    .cosmic-tag-row,
    .cosmic-toggle-row,
    .cosmic-icon-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .cosmic-component-row { margin-bottom: 12px; }
    .cosmic-chip,
    .cosmic-tag,
    .cosmic-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 30px;
      padding: 0 12px;
      border-radius: 7px;
      border: 1px solid var(--line-strong);
      font-size: 0.68rem;
      font-weight: 650;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--fg);
      background: transparent;
    }
    .cosmic-chip-primary {
      border-color: var(--border-accent);
      color: var(--accent);
      background: var(--accent-soft);
    }
    .cosmic-chip-secondary {
      color: var(--fg-muted);
      background: var(--well);
    }
    .cosmic-chip-ghost {
      color: var(--fg-faint);
      background: transparent;
      border-color: var(--line);
    }
    .cosmic-toggle {
      position: relative;
      width: 52px;
      height: 30px;
      border-radius: 999px;
      border: 1px solid var(--line-strong);
      background: var(--well);
      padding: 4px;
    }
    .cosmic-toggle span {
      display: block;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--fg-faint);
    }
    .cosmic-toggle-on {
      border-color: var(--border-accent);
      background: var(--accent-soft);
    }
    .cosmic-toggle-on span {
      margin-left: 22px;
      background: var(--accent);
    }
    .cosmic-tag-gold {
      border-color: var(--border-accent);
      color: var(--accent);
    }
    .cosmic-tag-violet {
      border-color: rgba(167,139,250,0.32);
      color: #a78bfa;
    }
    .cosmic-tag-teal {
      border-color: rgba(88,166,255,0.3);
      color: var(--accent-strong);
    }
    .cosmic-data-grid {
      display: grid;
      gap: 12px;
    }
    .cosmic-data-card {
      padding: 12px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--line);
      background: var(--well);
    }
    .cosmic-data-label {
      font-size: 0.64rem;
      color: var(--fg-faint);
      font-weight: 650;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }
    .cosmic-ring {
      width: 84px;
      height: 84px;
      display: grid;
      place-items: center;
      margin: 6px auto 0;
      border-radius: 50%;
      border: 2px solid var(--border-accent);
      background: var(--accent-soft);
      color: var(--fg);
      font-size: 1.1rem;
      font-weight: 650;
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
    }
    .cosmic-slider {
      position: relative;
      height: 4px;
      margin: 18px 0 10px;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(151,163,186,0.2), rgba(240,180,41,0.7), rgba(151,163,186,0.2));
    }
    .cosmic-slider span {
      position: absolute;
      top: 50%;
      left: 56%;
      width: 13px;
      height: 13px;
      border-radius: 50%;
      transform: translate(-50%, -50%);
      background: var(--accent);
    }
    .cosmic-data-value {
      text-align: right;
      font-size: 0.78rem;
      color: var(--accent);
      letter-spacing: 0.06em;
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
    }
    .cosmic-icon-row {
      margin-top: 12px;
    }
    .cosmic-icon {
      color: var(--fg-muted);
      border-color: var(--line);
      background: var(--well);
    }
    .cosmic-tag-block {
      margin-top: 12px;
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
      padding: 12px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--line);
      background: var(--well);
      display: flex;
      align-items: flex-end;
    }
    .cosmic-visual-tile-glow {
      position: absolute;
      inset: 12px;
      border-radius: 8px;
      opacity: 0.9;
    }
    .cosmic-visual-tile-label {
      position: relative;
      z-index: 1;
      font-size: 0.64rem;
      font-weight: 650;
      letter-spacing: 0.14em;
      color: var(--fg);
      text-transform: uppercase;
    }
    .cosmic-visual-black-hole .cosmic-visual-tile-glow {
      background: radial-gradient(circle, rgba(8,9,12,0.96) 0 26%, rgba(240,180,41,0.4) 32%, rgba(88,166,255,0.14) 56%, transparent 70%);
    }
    .cosmic-visual-gravity-ring .cosmic-visual-tile-glow {
      background: radial-gradient(circle at 50% 40%, transparent 0 26%, rgba(240,180,41,0.36) 28%, transparent 31%), radial-gradient(circle at 52% 43%, rgba(240,180,41,0.07), transparent 58%);
    }
    .cosmic-visual-light-glow .cosmic-visual-tile-glow {
      background: radial-gradient(circle at 55% 35%, rgba(240,180,41,0.85), rgba(240,180,41,0.08) 30%, transparent 60%);
    }
    .cosmic-visual-nebula-dust .cosmic-visual-tile-glow {
      background:
        radial-gradient(circle at 30% 40%, rgba(167,139,250,0.42), transparent 25%),
        radial-gradient(circle at 68% 58%, rgba(88,166,255,0.3), transparent 24%),
        radial-gradient(circle at 52% 34%, rgba(240,180,41,0.16), transparent 34%);
      filter: blur(1px);
    }
    .cosmic-visual-glass-surface .cosmic-visual-tile-glow {
      background:
        linear-gradient(135deg, rgba(232,236,243,0.08), rgba(232,236,243,0.01)),
        radial-gradient(circle at 20% 20%, rgba(88,166,255,0.14), transparent 26%),
        radial-gradient(circle at 88% 82%, rgba(240,180,41,0.18), transparent 24%);
    }
    """
