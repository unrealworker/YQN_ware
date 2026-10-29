import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { createNavigation } from './navigation.js';
import CountUp from './react-bits/CountUp.jsx';
import { createChart } from './charts.js';
import { parseMetric, equalSpec } from './identity.js';
import './motion.css';

const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
// Keep a bounded working set: the seven main pages plus the current detail.
// Detached entries have no running animations or resize observers.
const views = new Map(), chartHosts = new Map();
const pendingCharts = new Set();
const viewLimit = 8;
let chartFrame = 0, transitioning = false;
let numbers = new Map(), charts = new Map();
let currentView = '', visible = true, entrance = [], navControl, previousRows = new Set();
const stats = { chartCreates: 0, chartUpdates: 0, chartDisposes: 0, numberUpdates: 0, numberRoots: 0, numberBatches: 0, viewReuses: 0, errors: [] };
const canAnimate = () => visible && !document.hidden && !preference.matches;
const metricSelector = '.kpi strong.num,.stats-four strong.num,.inventory-facts strong.num,.big-stat strong.num,.ring-center strong.num,.metric-value';
const safely = fn => { try { return fn(); } catch (error) { stats.errors.push(String(error)); if (stats.errors.length > 5) stats.errors.shift(); console.error('[GHS motion]', error); } };

function renderNumber(entry, immediate = false) {
  const spec = entry.spec;
  // CountUp retains the currently displayed value when its target changes.
  // Static rendering on hide/reduced motion also stops Motion's RAF subscription.
  if (!entry.root && immediate) { entry.host.textContent = entry.text; entry.initial = spec.value; return; }
  if (!entry.root) { entry.root = createRoot(entry.host); ++stats.numberRoots; }
  entry.root.render(immediate ? entry.text :
    <CountUp to={spec.value} from={entry.initial} duration={0.24} mode="count"
      trigger="load" easing="easeOut" decimals={spec.decimals}
      separator={spec.separator} suffix={spec.suffix} />);
  if (immediate) entry.initial = spec.value;
}
function renderNumbers(updates) {
  if (!updates.length) return;
  // One React commit boundary for a data refresh, not one flush per metric.
  ++stats.numberBatches;
  flushSync(() => updates.forEach(([entry, immediate]) => renderNumber(entry, immediate)));
}
const chartResize = new ResizeObserver(entries => {
  for (const observation of entries) {
    const entry = chartHosts.get(observation.target);
    if (entry) resizeChart(entry);
  }
});
function resizeChart(entry) {
  const width = entry.host.clientWidth, height = entry.host.clientHeight;
  if (!width || !height || (entry.width === width && entry.height === height)) return;
  entry.width = width; entry.height = height; entry.chart.resize();
}
function disposeChart(entry) {
  pendingCharts.delete(entry); chartResize.unobserve(entry.host); chartHosts.delete(entry.host);
  if (entry.chart) { entry.chart.dispose(); ++stats.chartDisposes; }
}
function cancelChartFrame() { if (chartFrame) cancelAnimationFrame(chartFrame); chartFrame = 0; }
function scheduleCharts() {
  if (chartFrame || transitioning || !visible || document.hidden || !pendingCharts.size) return;
  // The server-authored SVG/HTML stays readable throughout navigation. Enhance
  // one chart per frame only after the selected page has finished entering.
  chartFrame = requestAnimationFrame(() => {
    chartFrame = 0;
    const entry = pendingCharts.values().next().value;
    if (!entry) return;
    pendingCharts.delete(entry);
    safely(() => {
      entry.chart = createChart(entry.host, entry.spec, { animate: false });
      entry.width = entry.host.clientWidth; entry.height = entry.host.clientHeight;
      chartHosts.set(entry.host, entry); chartResize.observe(entry.host);
      entry.node.classList.add('motion-chart-ready'); ++stats.chartCreates;
    });
    scheduleCharts();
  });
}
function setTransitioning(value) {
  transitioning = !!value;
  if (transitioning) cancelChartFrame(); else scheduleCharts();
}
function disposeView(view) {
  flushSync(() => view.numbers.forEach(e => e.root?.unmount()));
  view.charts.forEach(disposeChart);
}
function clearEntries() {
  cancelChartFrame(); pendingCharts.clear();
  views.forEach(disposeView); views.clear(); numbers.clear(); charts.clear();
}
function finishEntrance() { entrance.forEach(a => a.cancel()); entrance = []; }

function beforePaint(page, view) {
  finishEntrance();
  if (currentView !== view) {
    renderNumbers([...numbers.values()].filter(e => e.root).map(e => [e, true]));
    charts.forEach(e => { e.chart?.settle(); pendingCharts.delete(e); chartResize.unobserve(e.host); chartHosts.delete(e.host); });
    for (const entry of [...numbers.values(), ...charts.values()]) entry.host.remove();
    let cached = views.get(view);
    if (cached) { ++stats.viewReuses; views.delete(view); }
    else cached = { numbers: new Map(), charts: new Map() };
    views.set(view, cached); currentView = view;
    numbers = cached.numbers; charts = cached.charts; previousRows.clear();
    if (views.size > viewLimit) {
      const oldest = views.keys().next().value;
      disposeView(views.get(oldest)); views.delete(oldest);
    }
  }
  // Preserve the actual React roots and chart instances across a same-view DOM paint.
  // They are reattached synchronously before the browser presents the next frame.
  for (const entry of [...numbers.values(), ...charts.values()]) { entry.seen = false; entry.host.remove(); }
}
function mountNumbers(page) {
  const updates = [];
  page.querySelectorAll(metricSelector).forEach((node, index) => safely(() => {
    const text = node.textContent.trim(), spec = parseMetric(text);
    if (!spec) return;
    const key = node.dataset.motionKey || `${index}:${node.closest('.section')?.querySelector('h2')?.textContent || ''}`;
    let entry = numbers.get(key);
    if (!entry) {
      const host = document.createElement('span'); host.className = 'motion-number';
      // Known data is readable on the first frame. React Bits is needed only
      // when that value actually changes, not for counting every visit from 0.
      host.textContent = text;
      entry = { host, root: null, spec, initial: spec.value };
      numbers.set(key, entry);
    }
    const changed = !equalSpec(entry.spec, spec);
    entry.seen = true; entry.spec = spec; entry.text = text;
    node.dataset.motionValue = text;
    node.setAttribute('aria-label', text);
    entry.host.setAttribute('aria-hidden', 'true');
    node.replaceChildren(entry.host);
    if (changed) { updates.push([entry, !canAnimate()]); ++stats.numberUpdates; }
  }));
  renderNumbers(updates);
  for (const [key, entry] of numbers) if (!entry.seen) { entry.root?.unmount(); numbers.delete(key); }
}
function mountCharts(page) {
  page.querySelectorAll('[data-motion-chart]').forEach((node, index) => safely(() => {
    const spec = JSON.parse(node.dataset.motionChart), key = `${index}:${spec.type}`;
    let entry = charts.get(key);
    if (!entry) {
      const host = document.createElement('div'); host.className = 'motion-chart'; host.setAttribute('aria-hidden', 'true');
      node.append(host);
      entry = { host, spec, chart: null };
      charts.set(key, entry);
    } else {
      node.append(entry.host);
      if (entry.chart) {
        resizeChart(entry);
        if (!equalSpec(entry.spec, spec)) { entry.chart.update(spec, { animate: canAnimate() }); ++stats.chartUpdates; }
      }
      entry.spec = spec;
    }
    entry.seen = true; entry.node = node;
    if (entry.chart) {
      chartHosts.set(entry.host, entry); chartResize.observe(entry.host);
      node.classList.add('motion-chart-ready');
    } else pendingCharts.add(entry);
  }));
  for (const [key, entry] of charts) if (!entry.seen) { disposeChart(entry); charts.delete(key); }
  scheduleCharts();
}
function enterItems(page, enter) {
  const rowKey = n => `${n.classList[0]}:${n.dataset.id || n.dataset.ledgerSample || n.querySelector('[data-id]')?.dataset.id || n.querySelector('h3')?.textContent || n.querySelector('.row-title')?.textContent || ''}`;
  const rowNodes = [...page.querySelectorAll('.list-row,.ledger-sample,.replay-device,.replay-event,.replay-order')];
  const newRows = rowNodes.filter(n => !previousRows.has(rowKey(n)));
  previousRows = new Set(rowNodes.map(rowKey));
  // A view already has one parent transition. A second staggered entrance
  // makes the destination feel late and dims it twice while charts mount.
  if (!canAnimate() || enter) return;
  const candidates = newRows;
  // Do not animate an element and its ancestor simultaneously.
  const items = candidates.filter(n => !candidates.some(p => p !== n && p.contains(n)));
  items.slice(0, 24).forEach((node, i) => {
    const animation = node.animate([{ opacity: 0, transform: 'translateY(4px)' }, { opacity: 1, transform: 'translateY(0)' }],
      { duration: 160, delay: Math.min(i * 20, 60), easing: 'cubic-bezier(.16,1,.3,1)', fill: 'backwards' });
    entrance.push(animation);
  });
}
function afterPaint(page, view, enter) {
  mountCharts(page); mountNumbers(page);
  enterItems(page, enter);
}

function navigation(nav) {
  if (!navControl) navControl = createNavigation(nav, { canAnimate, document, ResizeObserver });
  navControl.update();
}
function settle() {
  finishEntrance(); navControl?.settle();
  renderNumbers([...numbers.values()].filter(e => e.root).map(e => [e, true]));
  charts.forEach(entry => entry.chart?.settle());
}
function setVisibility(value) { visible = !!value; if (!visible) { cancelChartFrame(); settle(); } else scheduleCharts(); }
preference.addEventListener('change', () => { if (preference.matches) settle(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) { cancelChartFrame(); settle(); } else scheduleCharts(); });
window.addEventListener('pagehide', () => { finishEntrance(); clearEntries(); navControl?.dispose(); });

// Prepare the real, stable ledger chart behind the startup curtain. Reuse that
// exact instance on first navigation; a dummy warmup does not prime all labels.
function prepareView(page, view, html) {
  if (views.has(view) || !window.TwinStartup || window.TwinStartup.presented) return;
  const stage = document.createElement('div'), cached = { numbers: new Map(), charts: new Map() };
  stage.setAttribute('aria-hidden', 'true');
  stage.style.cssText = 'position:absolute;left:0;top:0;visibility:hidden;pointer-events:none;box-sizing:border-box';
  stage.style.width = `${page.clientWidth}px`; stage.style.padding = getComputedStyle(page).padding;
  stage.innerHTML = html; page.parentElement.append(stage);
  try {
    stage.querySelectorAll('[data-motion-chart]').forEach((node, index) => {
      const spec = JSON.parse(node.dataset.motionChart), host = document.createElement('div');
      host.className = 'motion-chart'; host.setAttribute('aria-hidden', 'true'); node.append(host);
      const entry = { host, spec, chart: createChart(host, spec, { animate: false }), width: host.clientWidth, height: host.clientHeight };
      cached.charts.set(`${index}:${spec.type}`, entry); ++stats.chartCreates;
      host.remove();
    });
    views.set(view, cached);
  } catch (error) { disposeView(cached); throw error; }
  finally { stage.remove(); }
}

window.TwinMotion = {
  beforePaint: (...args) => safely(() => beforePaint(...args)),
  afterPaint: (...args) => safely(() => afterPaint(...args)),
  prepareView: (...args) => safely(() => prepareView(...args)),
  navigation: nav => safely(() => navigation(nav)), setVisibility, setTransitioning, settle,
  diagnostics: () => ({ engine: 'React Bits + ECharts', version: 2, view: currentView, visible, reduced: preference.matches,
    numbers: numbers.size, charts: charts.size, pendingCharts: pendingCharts.size, cachedViews: views.size, viewLimit, ...stats }),
  // Reports expose canonical target values, including during a numeric transition.
  text: page => { const clone = page.cloneNode(true); clone.querySelectorAll('[data-motion-value]').forEach(n => { n.textContent = n.dataset.motionValue; }); clone.querySelectorAll('.motion-chart').forEach(n => n.remove()); return clone.textContent; }
};
