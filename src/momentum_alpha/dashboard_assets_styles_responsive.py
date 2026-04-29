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
      .live-decision-grid { grid-template-columns: 1fr; }
      .system-console-grid { grid-template-columns: 1fr; }
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
      .execution-flow-grid { grid-template-columns: repeat(2, 1fr); }
      .daily-review-kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .daily-review-history-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .daily-review-toolbar { flex-direction: column; align-items: stretch; }
      .daily-review-toolbar-note { max-width: none; text-align: left; }
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
      .positions-table { min-width: 1040px; font-size: 0.68rem; }
      .positions-table th, .positions-table td { padding: 8px; }
      .trade-row { min-width: 640px; grid-template-columns: 60px 80px 50px 60px 70px 60px 60px; font-size: 0.7rem; }
      .analytics-grid { grid-template-columns: 1fr; }
      .live-account-risk-grid { grid-template-columns: 1fr; }
      .live-core-lines-grid { grid-template-columns: 1fr; }
      .live-decision-grid,
      .system-console-grid { grid-template-columns: 1fr; }
      .analytics-row { min-width: 540px; grid-template-columns: 1.2fr 0.8fr 0.8fr 0.8fr 0.7fr; font-size: 0.68rem; }
      .daily-review-kpi-grid { grid-template-columns: 1fr 1fr; }
      .daily-review-history-grid { grid-template-columns: 1fr 1fr; }
      .daily-review-date-form { align-items: flex-start; }
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
