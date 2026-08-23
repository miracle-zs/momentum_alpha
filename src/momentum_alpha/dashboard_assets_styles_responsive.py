from __future__ import annotations


def _render_dashboard_responsive_styles() -> str:
    return """
    @media (max-width: 1200px) {
      .cosmic-identity-panel { grid-template-columns: 1fr; }
      .cosmic-identity-grid { grid-template-columns: 1fr; }
      .cosmic-visual-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .metrics-grid { grid-template-columns: repeat(2, 1fr); }
      .hero-grid { grid-template-columns: 1fr; }
      .charts-row { grid-template-columns: 1fr; }
      .decision-row { grid-template-columns: 1fr; }
      .bottom-row { grid-template-columns: 1fr; }
      .live-account-risk-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .live-core-lines-head { grid-template-columns: minmax(0, 1fr) auto; align-items: end; }
      .live-core-context { grid-column: 1 / -1; grid-row: 2; }
      .live-core-lines-summary { max-width: none; }
      .core-live-range-controls { justify-content: flex-end; }
      .live-support-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .system-console-grid { grid-template-columns: 1fr; }
      .execution-flow-row { grid-template-columns: minmax(150px, 0.9fr) minmax(0, 1.2fr) minmax(140px, 0.72fr); }
      .review-analysis-evidence-grid { grid-template-columns: 1fr; }
      .review-summary-ribbon { flex-direction: column; align-items: flex-start; }
      .review-summary-copy-block { flex: 0 0 auto; min-width: 0; }
      .review-summary-copy { max-width: none; text-align: left; }
      .review-summary-ribbon-items { width: 100%; }
      .system-summary-head { flex-direction: column; align-items: flex-start; }
      .system-summary-copy { max-width: none; text-align: left; }
      .system-summary-strip .decision-grid { grid-template-columns: 1fr; }
      .system-health-path { width: 100%; }
      .account-overview-grid { grid-template-columns: repeat(3, 1fr); }
      .account-snapshot-grid { grid-template-columns: repeat(2, 1fr); }
      .daily-review-kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .daily-review-history-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .daily-review-toolbar { flex-direction: column; align-items: stretch; }
      .daily-review-toolbar-note { max-width: none; text-align: left; }
      .daily-review-hero { grid-template-columns: 1fr; }
      .daily-review-counterfactual-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .daily-review-module-head, .daily-review-section-head { align-items: flex-start; flex-direction: column; }
      .daily-review-section-note { max-width: none; text-align: left; }
      .filter-review-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .filter-review-stat { border-bottom: 1px solid rgba(138,210,255,0.12); }
      .filter-review-evidence-head { align-items: flex-start; flex-direction: column; }
      .filter-review-rule-mix { justify-content: flex-start; }
      .account-panel-header, .account-main-toolbar { flex-direction: column; align-items: flex-start; }
    }
    @media (max-width: 768px) {
      .app { padding: 12px; }
      .app-shell { padding: 0; }
      .cosmic-identity-panel { padding: 16px; }
      .cosmic-identity-title { font-size: 2rem; letter-spacing: 0.14em; }
      .cosmic-visual-tiles { grid-template-columns: 1fr; }
      .metrics-grid { grid-template-columns: 1fr; }
      .header { flex-direction: column; align-items: flex-start; gap: 16px; }
      .header-status { justify-content: flex-start; width: 100%; }
      .header-runtime { justify-content: flex-start; width: 100%; flex-wrap: wrap; }
      .dashboard-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); padding: 0; gap: 4px; }
      .dashboard-tab { min-width: 0; padding-inline: 2px; font-size: 0.66rem; white-space: nowrap; }
      .decision-grid { grid-template-columns: 1fr; }
      .positions-table { min-width: 1040px; font-size: 0.68rem; }
      .positions-table th, .positions-table td { padding: 8px; }
      .trade-row { min-width: 640px; grid-template-columns: 60px 80px 50px 60px 70px 60px 60px; font-size: 0.7rem; }
      .analytics-grid { grid-template-columns: 1fr; }
      .live-account-risk-grid { grid-template-columns: 1fr; }
      .live-core-lines-head { grid-template-columns: 1fr; align-items: flex-start; }
      .live-core-context { grid-column: auto; grid-row: auto; grid-template-columns: repeat(2, minmax(0, 1fr)); width: 100%; }
      .live-core-context-item { padding: 8px 10px; border-bottom: 1px solid var(--border); }
      .live-core-lines-summary { max-width: none; }
      .core-live-range-controls { justify-content: flex-start; width: 100%; }
      .live-core-lines-grid { grid-template-columns: 1fr; }
      .live-support-grid { grid-template-columns: 1fr; }
      .live-support-card[open] { grid-column: auto; }
      .live-signal-detail .decision-grid { grid-template-columns: 1fr; }
      .live-rotation-detail { grid-template-columns: 1fr; }
      .system-console-grid { grid-template-columns: 1fr; }
      .execution-flow-row { grid-template-columns: 1fr; gap: 4px; align-items: flex-start; }
      .execution-flow-detail { text-align: left; }
      .analytics-row { min-width: 540px; grid-template-columns: 1.2fr 0.8fr 0.8fr 0.8fr 0.7fr; font-size: 0.68rem; }
      .daily-review-kpi-grid { grid-template-columns: 1fr 1fr; }
      .daily-review-history-grid { grid-template-columns: 1fr 1fr; }
      .daily-review-panel-redesign { padding: 12px; }
      .daily-review-hero-copy, .daily-review-hero-impact { min-height: 120px; padding: 17px; }
      .daily-review-hero-title { font-size: 1.35rem; }
      .daily-review-module { padding: 13px; }
      .daily-review-counterfactual-block, .daily-review-ledger { padding: 13px; }
      .daily-review-counterfactual-stats { grid-template-columns: 1fr 1fr; }
      .daily-review-rule-mix-note { flex-basis: 100%; margin-left: 0; }
      .daily-review-counterfactual-header, .daily-review-counterfactual-row { min-width: 900px; }
      .daily-review-date-form { align-items: flex-start; }
      .daily-review-grid { min-width: 920px; grid-template-columns: minmax(112px, 1fr) minmax(82px, 0.7fr) minmax(112px, 1fr) minmax(78px, 0.72fr) minmax(78px, 0.72fr) minmax(96px, 0.82fr) minmax(60px, 0.52fr) minmax(64px, 0.52fr); }
      .daily-review-row { font-size: 0.68rem; }
      .filter-review-panel { padding: 12px; }
      .filter-review-toolbar, .filter-review-verdict { align-items: flex-start; grid-template-columns: 1fr; flex-direction: column; }
      .filter-review-toolbar { display: flex; }
      .filter-review-verdict { min-height: 0; padding: 18px; }
      .filter-review-stats { grid-template-columns: 1fr 1fr; }
      .filter-review-stat { border-right: 1px solid rgba(138,210,255,0.12); }
      .filter-review-table-head, .filter-review-table-row { min-width: 860px; }
      .account-overview-grid { grid-template-columns: 1fr; }
      .account-snapshot-grid { grid-template-columns: 1fr; }
      .desktop-only { display: none; }
      .mobile-only { display: block; }
      .analytics-table.desktop-only { display: none; }
      .analytics-card-list.mobile-only { display: flex; }
      .trade-history.desktop-only { display: none; }
      .trade-card-list.mobile-only { display: flex; }
    }
    """
