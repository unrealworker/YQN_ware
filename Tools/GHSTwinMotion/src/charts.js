import { init, use } from 'echarts/core';
import { BarChart, LineChart, PieChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';

use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, SVGRenderer]);

const BLUE = '#356bfa';
const TEXT = '#34445d';
const MUTED = '#6a7d97';
const PALETTE = [BLUE, '#88aaf3', '#c1cfe5', '#e9a858'];
const numberFormat = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 6 });
const escapeHTML = value => String(value == null ? '' : value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
const finiteNumber = value => value !== null && value !== '' && value !== undefined && Number.isFinite(Number(value)) ? Number(value) : null;
const formatValue = (value, unit = '') => (finiteNumber(value) === null ? '—' : numberFormat.format(Number(value))) + (unit ? ' ' + unit : '');
const colorAt = (color, index) => typeof color === 'string' && /^[#a-z0-9(),.%\s-]+$/i.test(color) ? color : PALETTE[index % PALETTE.length];

function partsFor(spec) {
  const occurrences = new Map();
  return (Array.isArray(spec.parts) ? spec.parts : []).map((part, index) => {
    const label = String(part.label == null ? '' : part.label);
    const key = String(part.id == null ? label || index : part.id);
    const occurrence = occurrences.get(key) || 0;
    occurrences.set(key, occurrence + 1);
    return { id: key + ':' + occurrence, label, value: finiteNumber(part.value), unit: part.unit || spec.unit || '', color: colorAt(part.color, index) };
  });
}

function tooltipRow(label, value, color, unit) {
  return '<div style="display:flex;align-items:center;gap:7px;white-space:nowrap;line-height:22px"><span style="width:7px;height:7px;flex:none;border-radius:50%;background:' + escapeHTML(color) + '"></span><span>' + escapeHTML(label) + '</span><strong style="margin-left:10px;font-weight:600">' + escapeHTML(formatValue(value, unit)) + '</strong></div>';
}

function tooltipFor(spec) {
  return {
    trigger: spec.type === 'trend' ? 'axis' : 'item',
    renderMode: 'html',
    confine: true,
    appendToBody: false,
    enterable: false,
    showDelay: 30,
    hideDelay: 60,
    transitionDuration: 0.1,
    backgroundColor: 'rgba(255,255,255,0.98)',
    borderColor: '#dce4ef',
    borderWidth: 1,
    padding: [6, 9],
    extraCssText: 'box-shadow:0 4px 16px rgba(28,54,91,0.10);border-radius:7px;pointer-events:none;',
    textStyle: { color: TEXT, fontSize: 12, fontFamily: 'Arial, "Microsoft YaHei", sans-serif' },
    axisPointer: { type: 'line', lineStyle: { color: '#9db7ea', width: 1, type: 'dashed' } },
    formatter(parameters) {
      const rows = Array.isArray(parameters) ? parameters : [parameters];
      if (spec.type === 'trend') {
        const point = rows[0] && rows[0].data;
        return '<div style="color:' + MUTED + ';margin-bottom:3px">' + escapeHTML(point && point.time || '') + '</div>' + rows.map(row => tooltipRow(row.seriesName, row.data && row.data.value[1], row.color, spec.unit || '')).join('');
      }
      return rows.map(row => {
        const datum = row.data || {};
        return tooltipRow(datum.name || row.seriesName || '', datum.rawValue, datum.itemStyle && datum.itemStyle.color || row.color, datum.unit || '');
      }).join('');
    }
  };
}

function datumFor(part, nonNegative = false) {
  return { id: part.id, name: part.label, value: part.value === null || nonNegative && part.value < 0 ? '-' : part.value, rawValue: part.value, unit: part.unit, itemStyle: { color: part.color } };
}

function optionFor(spec, width, animate, isUpdate) {
  const parts = partsFor(spec);
  const duration = spec.type === 'ring' ? 600 : spec.type === 'trend' ? 650 : 450;
  const base = {
    animation: animate,
    animationDuration: animate ? isUpdate ? 350 : duration : 0,
    animationDurationUpdate: animate ? 350 : 0,
    animationEasing: 'cubicOut',
    animationEasingUpdate: 'cubicInOut',
    color: PALETTE,
    textStyle: { color: TEXT, fontFamily: 'Arial, "Microsoft YaHei", sans-serif' },
    tooltip: tooltipFor(spec),
    grid: [], xAxis: [], yAxis: [], series: []
  };
  if (spec.type === 'ring') {
    base.series = [{
      id: 'ring:capacity', type: 'pie', radius: ['82%', '94%'], center: ['50%', '50%'], startAngle: 90,
      clockwise: true, animationType: 'expansion', animationTypeUpdate: 'transition',
      label: { show: false }, labelLine: { show: false },
      emphasis: { scale: false }, select: { disabled: true },
      showEmptyCircle: true, emptyCircleStyle: { color: '#e8eef8' },
      stillShowZeroSum: false, data: parts.map(part => datumFor(part, true))
    }];
  } else if (spec.type === 'stack') {
    const sum = parts.reduce((total, part) => total + Math.max(0, part.value || 0), 0);
    const suppliedTotal = finiteNumber(spec.total);
    base.grid = [{ id: 'stack:grid', top: 0, bottom: 0, left: 0, right: 0, containLabel: false }];
    base.xAxis = [{ id: 'stack:x', type: 'value', min: 0, max: suppliedTotal > 0 ? Math.max(suppliedTotal, sum) : Math.max(1, sum), show: false }];
    base.yAxis = [{ id: 'stack:y', type: 'category', data: [''], show: false }];
    base.series = parts.map(part => ({
      id: 'stack:' + part.id, name: part.label, type: 'bar', stack: 'total',
      barWidth: '100%', barCategoryGap: 0, clip: true,
      emphasis: { disabled: true },
      data: [{ ...datumFor(part, true), itemStyle: { color: part.color, borderColor: '#fff', borderWidth: 0.7 } }]
    }));
  } else if (spec.type === 'bars') {
    const chartWidth = Math.max(180, width);
    const left = Math.max(48, Math.min(96, Math.round(chartWidth * 0.29)));
    const longestValue = Math.max(1, ...parts.map(part => formatValue(part.value, part.unit).length));
    const right = Math.max(30, Math.min(Math.round(chartWidth * 0.33), Math.ceil(longestValue * 6.5 + 10)));
    base.grid = [{ id: 'bars:grid', top: 4, bottom: 4, left, right, containLabel: false }];
    base.xAxis = [{ id: 'bars:x', type: 'value', show: false, min: value => Math.min(0, value.min) }];
    base.yAxis = [{
      id: 'bars:y', type: 'category', inverse: true, data: parts.map(part => part.label),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: MUTED, fontSize: 12, width: left - 8, overflow: 'truncate', margin: 8, interval: 0 }
    }];
    base.series = [{
      id: 'bars:states', type: 'bar', barMaxWidth: 9, showBackground: true,
      backgroundStyle: { color: '#edf2f9', borderRadius: 2 },
      itemStyle: { borderRadius: [0, 2, 2, 0] },
      emphasis: { itemStyle: { opacity: 0.86 } },
      label: { show: true, position: 'right', distance: 6, color: TEXT, fontSize: 12, width: right - 8, overflow: 'truncate', valueAnimation: animate, formatter: row => formatValue(row.value, row.data.unit) },
      data: parts.map(part => datumFor(part))
    }];
  } else if (spec.type === 'trend') {
    const pointOccurrences = new Map();
    const points = (Array.isArray(spec.points) ? spec.points : []).map((point, index) => {
      const x = finiteNumber(point.x) === null ? index : Number(point.x);
      const time = String(point.time || '');
      const key = String(point.id == null ? time || x : point.id);
      const occurrence = pointOccurrences.get(key) || 0;
      pointOccurrences.set(key, occurrence + 1);
      return { ...point, x, time, chartId: key + ':' + occurrence };
    });
    const minX = points.length ? Math.min(...points.map(point => point.x)) : 0;
    const maxX = points.length ? Math.max(...points.map(point => point.x)) : 1;
    const first = points.find(point => point.x === minX);
    const last = points.find(point => point.x === maxX);
    const seconds = time => /^\d{1,2}:\d{2}(:\d{2})?$/.test(time) ? time.split(':').reduce((sum, item, index) => sum + Number(item) * [3600, 60, 1][index], 0) : null;
    const start = first ? seconds(first.time) : null;
    let end = last ? seconds(last.time) : null;
    if (end !== null && start !== null && end < start) end += 86400;
    base.grid = [{ id: 'trend:grid', left: 36, right: 12, top: 12, bottom: 24, containLabel: false }];
    base.xAxis = [{
      id: 'trend:x', type: 'value', min: minX, max: maxX > minX ? maxX : minX + 1, splitNumber: 4,
      axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { color: MUTED, fontSize: 11, hideOverlap: true, margin: 9, formatter(value) {
        if (start !== null && end !== null && maxX > minX) {
          const minutes = Math.round((start + (value - minX) / (maxX - minX) * (end - start)) / 60);
          return String(Math.floor(minutes / 60) % 24).padStart(2, '0') + ':' + String(minutes % 60).padStart(2, '0');
        }
        return numberFormat.format(value);
      } }
    }];
    base.yAxis = [{ id: 'trend:y', type: 'value', min: 0, splitNumber: 3,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: MUTED, fontSize: 11, margin: 8 },
      splitLine: { lineStyle: { color: '#e8eef7', type: 'dashed' } }
    }];
    base.series = [{ key: 'inbound', label: '入库', color: '#879bb8' }, { key: 'outbound', label: '出库', color: BLUE }].map(series => ({
      id: 'trend:' + series.key, name: series.label, type: 'line',
      showSymbol: false, symbol: 'circle', symbolSize: 5,
      smooth: 0.2, smoothMonotone: 'x', connectNulls: false,
      lineStyle: { color: series.color, width: 2.2 }, itemStyle: { color: series.color },
      emphasis: { focus: 'series', lineStyle: { width: 2.8 } },
      data: points.map(point => ({ id: point.chartId, time: point.time, value: [point.x, finiteNumber(point[series.key])] }))
    }));
  } else {
    throw new Error('Unsupported GHS chart type: ' + spec.type);
  }
  return base;
}

/** One SVG chart per host. Data updates merge into the existing ECharts instance. */
export function createChart(host, spec, { animate = true } = {}) {
  if (!host || typeof host.querySelectorAll !== 'function') throw new TypeError('A chart host element is required.');
  host.style.width = '100%';
  host.style.height = '100%';
  let currentSpec = spec;
  let disposed = false;
  let rendered = false;
  // SVGRenderer temporarily hides the host to measure it. Chromium 90 then
  // reports percentage styles as "100%", which its parser mistakes for 100px.
  // Supply unscaled layout pixels explicitly (UE applies its own root scale).
  const dimensions = () => ({ width: host.clientWidth || 180, height: host.clientHeight || (currentSpec.type === 'stack' ? 11 : currentSpec.type === 'ring' ? host.clientWidth || 124 : 154) });
  const chart = init(host, null, { renderer: 'svg', ...dimensions() });
  // The legacy ring rotates every descendant SVG. ECharts owns its start angle.
  function normalizeSVG() {
    host.querySelectorAll('svg').forEach(svg => {
      if (svg.style.transform !== 'none') svg.style.transform = 'none';
      if (svg.style.height !== '100%') svg.style.height = '100%';
      if (svg.style.width !== '100%') svg.style.width = '100%';
      if (svg.style.display !== 'block') svg.style.display = 'block';
    });
  }
  function finishAnimations() {
    const renderer = chart.getZr();
    renderer.storage.traverse(element => {
      element.stopAnimation(null, true);
      const clip = element.getClipPath && element.getClipPath();
      if (clip) clip.stopAnimation(null, true);
      const label = element.getTextContent && element.getTextContent();
      if (label) label.stopAnimation(null, true);
    });
    renderer.refreshImmediately();
    normalizeSVG();
  }
  function apply(nextSpec, enabled) {
    if (disposed) return;
    currentSpec = nextSpec;
    const width = host.clientWidth || host.parentElement && host.parentElement.clientWidth || 180;
    chart.setOption(optionFor(currentSpec, width, enabled, rendered), {
      notMerge: false, replaceMerge: ['series', 'xAxis', 'yAxis', 'grid'], lazyUpdate: false, silent: true
    });
    rendered = true;
    normalizeSVG();
    if (!enabled) finishAnimations();
  }
  chart.on('rendered', normalizeSVG);
  try {
    apply(spec, animate);
  } catch (error) {
    chart.off('rendered', normalizeSVG);
    chart.dispose();
    throw error;
  }
  return {
    update(nextSpec, { animate: enabled = true } = {}) { apply(nextSpec, enabled); },
    resize() {
      if (disposed) return;
      chart.resize({ ...dimensions(), animation: { duration: 0 }, silent: true });
      apply(currentSpec, false);
    },
    settle() {
      if (disposed) return;
      apply(currentSpec, false);
      chart.dispatchAction({ type: 'hideTip' });
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      chart.off('rendered', normalizeSVG);
      chart.dispose();
    }
  };
}
