from __future__ import annotations


def render_dashboard_core_live_script() -> str:
    return """
    let coreLiveCharts = new Map();
    let coreLiveResizeObserver = null;
    let coreLiveResizeBound = false;
    let coreLiveResizeScheduled = false;

    function getCoreLiveLinesDataFromDocument(sourceDocument = document) {
      const jsonNode = sourceDocument.getElementById('core-live-lines-json');
      if (!jsonNode) return [];
      try {
        const parsed = JSON.parse(jsonNode.textContent || '[]');
        return Array.isArray(parsed) ? parsed : [];
      } catch (error) {
        console.error(error);
        return [];
      }
    }
    function getCoreLiveBandNode() {
      return document.querySelector('.live-core-lines-band');
    }
    function getCoreLiveSummaryNode() {
      return document.querySelector('[data-core-live-summary]');
    }
    function getCoreLiveChartNodes() {
      const band = getCoreLiveBandNode();
      return band ? Array.from(band.querySelectorAll('[data-core-live-chart]')) : [];
    }
    function getCoreLiveRangeControls() {
      const band = getCoreLiveBandNode();
      return band ? Array.from(band.querySelectorAll('[data-core-live-range]')) : [];
    }
    function setCoreLiveRangeControls(range) {
      getCoreLiveRangeControls().forEach((button) => {
        const isActive = button.dataset.coreLiveRange === range;
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      });
    }
    function buildCoreLiveRangeUrl(range) {
      const url = new URL(window.location.href);
      const activeRoom = document.querySelector('[data-dashboard-active-room]')?.dataset.dashboardActiveRoom;
      if (activeRoom) url.searchParams.set('room', activeRoom);
      url.searchParams.set('range', range);
      return `${url.pathname}${url.search}${url.hash}`;
    }
    async function loadCoreLiveRange(range) {
      if (!range) return;
      localStorage.setItem(ACCOUNT_RANGE_STORAGE_KEY, range);
      setCoreLiveRangeControls(range);
      const nextUrl = buildCoreLiveRangeUrl(range);
      const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      if (nextUrl !== currentUrl) {
        window.history.pushState({}, '', nextUrl);
      }
      await refreshDashboard(true);
    }
    function bindCoreLiveRangeControls() {
      getCoreLiveRangeControls().forEach((button) => {
        button.onclick = async () => {
          await loadCoreLiveRange(button.dataset.coreLiveRange);
        };
      });
      setCoreLiveRangeControls(getSelectedAccountRange());
    }
    function setCoreLiveSummary(text, state) {
      const summaryNode = getCoreLiveSummaryNode();
      if (!summaryNode) return;
      summaryNode.textContent = text;
      summaryNode.dataset.coreLiveSummaryState = state;
    }
    function setCoreLiveChartState(chartNode, state) {
      chartNode.dataset.coreLiveChartState = state;
      chartNode.setAttribute('aria-busy', state === 'ready' ? 'false' : 'true');
    }
    function disposeCoreLiveChart(chartNode) {
      const chart = coreLiveCharts.get(chartNode);
      if (!chart) return;
      try {
        chart.dispose();
      } catch (error) {
        console.error(error);
      }
      coreLiveCharts.delete(chartNode);
    }
    function renderCoreLivePlaceholder(chartNode, message, state = 'empty') {
      disposeCoreLiveChart(chartNode);
      setCoreLiveChartState(chartNode, state);
      chartNode.innerHTML = '<div class="chart-empty"><span class="chart-empty-icon">◎</span><span>' + message + '</span></div>';
    }
    function getCoreLiveDomain(points) {
      const timestamps = points
        .map((point) => new Date(point.timestamp).getTime())
        .filter((value) => Number.isFinite(value));
      if (!timestamps.length) return null;
      let min = Math.min(...timestamps);
      let max = Math.max(...timestamps);
      if (min === max) {
        min -= 30000;
        max += 30000;
      }
      return [min, max];
    }
    function getCoreLiveSeries(points, metric) {
      return points
        .filter((point) => typeof point[metric] === 'number' && Number.isFinite(point[metric]))
        .map((point) => [new Date(point.timestamp).getTime(), point[metric]])
        .filter((pair) => Number.isFinite(pair[0]));
    }
    function formatCoreLiveTime(value) {
      const date = new Date(value);
      const parts = new Intl.DateTimeFormat('zh-CN', {
        hour12: false,
        timeZone: 'Asia/Shanghai',
        hour: '2-digit',
        minute: '2-digit'
      }).formatToParts(date);
      const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
      return `${lookup.hour}:${lookup.minute}`;
    }
    function formatCoreLiveValue(value, integerAxis = false) {
      const numericValue = Number(value);
      if (!Number.isFinite(numericValue)) return 'n/a';
      if (integerAxis) return Math.round(numericValue).toLocaleString();
      const magnitude = Math.abs(numericValue);
      if (magnitude >= 100) return numericValue.toLocaleString(undefined, { maximumFractionDigits: 0 });
      if (magnitude >= 10) return numericValue.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
      if (magnitude >= 1) return numericValue.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
      if (magnitude >= 0.1) return numericValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      return numericValue.toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
    }
    function buildCoreLiveChartOption(config) {
      const label = config.label;
      const color = config.color;
      const integerAxis = config.integerAxis;
      const seriesData = config.seriesData;
      const domain = config.domain;
      const compact = Boolean(config.compact);
      return {
        backgroundColor: 'transparent',
        animation: false,
        color: [color],
        grid: {
          top: compact ? 14 : 18,
          right: compact ? 10 : 16,
          bottom: compact ? 22 : 28,
          left: integerAxis ? (compact ? 40 : 46) : (compact ? 44 : 54)
        },
        tooltip: {
          trigger: 'axis',
          confine: true,
          backgroundColor: 'rgba(8,10,15,0.94)',
          borderColor: 'rgba(245,210,138,0.24)',
          textStyle: { color: '#f5f6f8', fontSize: 12 },
          axisPointer: { type: 'line', lineStyle: { color: 'rgba(245,210,138,0.34)' } },
          formatter: (params) => {
            const point = Array.isArray(params) ? params[0] : params;
            if (!point || !point.value) return '';
            return formatCoreLiveTime(point.value[0]) + '<br/>' + label + ': ' + formatCoreLiveValue(point.value[1], integerAxis);
          }
        },
        xAxis: {
          type: 'time',
          min: domain[0],
          max: domain[1],
          boundaryGap: false,
          axisLine: { lineStyle: { color: 'rgba(180,200,230,0.28)' } },
          axisTick: { show: false },
          axisLabel: {
            color: '#9aa3b2',
            fontSize: compact ? 9 : 10,
            hideOverlap: true,
            formatter: (value) => formatCoreLiveTime(value)
          },
          splitNumber: compact ? 3 : 4,
          splitLine: { show: true, lineStyle: { color: 'rgba(100,130,170,0.1)' } }
        },
        yAxis: {
          type: 'value',
          scale: !integerAxis,
          minInterval: integerAxis ? 1 : 0,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: '#9aa3b2',
            fontSize: compact ? 9 : 10,
            formatter: (value) => formatCoreLiveValue(value, integerAxis)
          },
          splitNumber: compact ? 2 : 4,
          splitLine: { show: true, lineStyle: { color: 'rgba(100,130,170,0.1)' } }
        },
        series: [{
          name: label,
          type: 'line',
          data: seriesData,
          showSymbol: seriesData.length <= 8 && !compact,
          symbolSize: compact ? 4 : 5,
          smooth: false,
          connectNulls: false,
          lineStyle: { width: compact ? 2 : 2.5, color: color },
          itemStyle: { color: color },
          areaStyle: { color: color, opacity: compact ? 0.1 : 0.14 },
          emphasis: { focus: 'series' }
        }]
      };
    }
    function bindCoreLiveResize() {
      if (coreLiveResizeBound) return;
      const chartNodes = getCoreLiveChartNodes();
      if (!chartNodes.length) return;
      const scheduleRefresh = () => {
        if (coreLiveResizeScheduled) return;
        coreLiveResizeScheduled = true;
        window.requestAnimationFrame(() => {
          coreLiveResizeScheduled = false;
          if (document.querySelector('.live-core-lines-band')) {
            updateCoreLiveChartsFromDocument(document);
          }
        });
      };
      if (window.ResizeObserver) {
        coreLiveResizeObserver = new ResizeObserver(scheduleRefresh);
        chartNodes.forEach((chartNode) => coreLiveResizeObserver.observe(chartNode));
      } else {
        window.addEventListener('resize', scheduleRefresh);
      }
      coreLiveResizeBound = true;
    }
    function renderCoreLiveChart(chartNode, config, domain) {
      if (!window.echarts) {
        renderCoreLivePlaceholder(chartNode, 'chart library unavailable', 'unavailable');
        return false;
      }
      const seriesData = config.seriesData;
      if (!seriesData.length) {
        renderCoreLivePlaceholder(chartNode, 'waiting for data', 'empty');
        return false;
      }
      const compact = chartNode.clientWidth > 0 && chartNode.clientWidth < 420;
      let chart = coreLiveCharts.get(chartNode);
      if (!chart) {
        chartNode.innerHTML = '';
        chart = window.echarts.init(chartNode, null, { renderer: 'canvas' });
        coreLiveCharts.set(chartNode, chart);
      }
      try {
        chart.resize();
      } catch (error) {
        console.error(error);
      }
      chart.setOption(buildCoreLiveChartOption({
        label: config.label,
        color: config.color,
        integerAxis: config.integerAxis,
        seriesData: seriesData,
        domain: domain,
        compact: compact
      }), { notMerge: true, lazyUpdate: true });
      setCoreLiveChartState(chartNode, 'ready');
      return true;
    }
    function updateCoreLiveChartsFromDocument(sourceDocument = document, options = {}) {
      const chartNodes = getCoreLiveChartNodes();
      if (!chartNodes.length) return false;
      bindCoreLiveResize();
      if (!window.echarts) {
        if (options.forceUnavailable) {
          setCoreLiveSummary('Chart library unavailable', 'unavailable');
          chartNodes.forEach((chartNode) => renderCoreLivePlaceholder(chartNode, 'chart library unavailable', 'unavailable'));
        } else {
          setCoreLiveSummary('Loading charts', 'loading');
        }
        return false;
      }
      const points = getCoreLiveLinesDataFromDocument(sourceDocument);
      const domain = getCoreLiveDomain(points);
      if (!domain) {
        setCoreLiveSummary('Waiting for data', 'empty');
        chartNodes.forEach((chartNode) => renderCoreLivePlaceholder(chartNode, 'waiting for data', 'empty'));
        return true;
      }
      let readyCount = 0;
      let emptyCount = 0;
      chartNodes.forEach((chartNode) => {
        const metric = chartNode.dataset.coreMetric;
        const label = chartNode.dataset.coreLabel || metric;
        const color = chartNode.dataset.coreColor || '#4cc9f0';
        const integerAxis = chartNode.dataset.coreIntegerAxis === 'true';
        const seriesData = getCoreLiveSeries(points, metric);
        if (!seriesData.length) {
          emptyCount += 1;
          renderCoreLivePlaceholder(chartNode, 'waiting for data', 'empty');
          return;
        }
        if (renderCoreLiveChart(chartNode, {
          label: label,
          color: color,
          integerAxis: integerAxis,
          seriesData: seriesData
        }, domain)) {
          readyCount += 1;
        }
      });
      if (readyCount === 0) {
        setCoreLiveSummary('Waiting for data', 'empty');
        return true;
      }
      const suffix = emptyCount ? ' · ' + emptyCount + ' empty' : '';
      setCoreLiveSummary(readyCount + ' chart' + (readyCount === 1 ? '' : 's') + ' ready' + suffix, emptyCount ? 'partial' : 'ready');
      return true;
    }
    function syncCoreLiveChartsFromDocument(sourceDocument = document) {
      const currentBand = getCoreLiveBandNode();
      const nextBand = sourceDocument.querySelector('.live-core-lines-band');
      if (!currentBand || !nextBand) return false;
      const currentJson = currentBand.querySelector('#core-live-lines-json');
      const nextJson = nextBand.querySelector('#core-live-lines-json');
      if (currentJson && nextJson) {
        currentJson.textContent = nextJson.textContent || '[]';
      }
      const summaryNode = getCoreLiveSummaryNode();
      if (summaryNode) {
        summaryNode.textContent = 'Loading charts';
        summaryNode.dataset.coreLiveSummaryState = 'loading';
      }
      const nextActiveRange = nextBand.querySelector('[data-core-live-range].active')?.dataset.coreLiveRange || getSelectedAccountRange();
      setCoreLiveRangeControls(nextActiveRange);
      currentBand.querySelectorAll('[data-core-live-chart]').forEach((chartNode) => {
        setCoreLiveChartState(chartNode, 'loading');
      });
      return updateCoreLiveChartsFromDocument(document);
    }
    function initializeCoreLiveCharts() {
      const chartNodes = getCoreLiveChartNodes();
      if (!chartNodes.length) return;
      bindCoreLiveResize();
      if (!window.echarts) {
        setCoreLiveSummary('Loading charts', 'loading');
        chartNodes.forEach((chartNode) => setCoreLiveChartState(chartNode, 'loading'));
        return;
      }
      updateCoreLiveChartsFromDocument(document);
    }
    function markCoreLiveChartsUnavailable() {
      updateCoreLiveChartsFromDocument(document, { forceUnavailable: true });
    }
    """
