from __future__ import annotations

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
