import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { createNavigation } from './navigation.js';
import CountUp from './react-bits/CountUp.jsx';
import { createChart } from './charts.js';
import { parseMetric, equalSpec } from './identity.js';
import './motion.css';

const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
const numbers = new Map(), charts = new Map();
let currentView = '', visible = true, entrance = [], navControl, lastPage, previousRows = new Set();
const stats = { chartCreates: 0, chartUpdates: 0, chartDisposes: 0, numberUpdates: 0, errors: [] };
const canAnimate = () => visible && !document.hidden && !preference.matches;
const metricSelector = '.kpi strong.num,.stats-four strong.num,.inventory-facts strong.num,.big-stat strong.num,.ring-center strong.num,.metric-value';
const safely = fn => { try { return fn(); } catch (error) { stats.errors.push(String(error)); if (stats.errors.length > 5) stats.errors.shift(); console.error('[GHS motion]', error); } };

function renderNumber(entry, immediate = false) {
  const spec = entry.spec;
  // CountUp retains the currently displayed value when its target changes.
  // Static rendering on hide/reduced motion also stops Motion's RAF subscription.
  flushSync(() => entry.root.render(immediate ? entry.text :
    <CountUp to={spec.value} from={entry.initial} duration={0.68} mode="count"
      trigger="load" easing="easeOut" decimals={spec.decimals}
      separator={spec.separator} suffix={spec.suffix} />));
  if (immediate) entry.initial = spec.value;
}
const chartResize = new ResizeObserver(entries => {
  for (const observation of entries) {
    const entry = [...charts.values()].find(e => e.host === observation.target);
    if (entry) resizeChart(entry);
  }
});
function resizeChart(entry) {
  const width = entry.host.clientWidth, height = entry.host.clientHeight;
  if (!width || !height || (entry.width === width && entry.height === height)) return;
  entry.width = width; entry.height = height; entry.chart.resize();
}
function disposeChart(entry) { chartResize.unobserve(entry.host); entry.chart.dispose(); ++stats.chartDisposes; }
function clearEntries() {
  numbers.forEach(e => e.root.unmount()); numbers.clear();
  charts.forEach(disposeChart); charts.clear();
}
function finishEntrance() { entrance.forEach(a => a.cancel()); entrance = []; }

function beforePaint(page, view) {
  lastPage = page;
  finishEntrance();
  if (currentView !== view) { clearEntries(); currentView = view; previousRows.clear(); }
  // Preserve the actual React roots and chart instances across a same-view DOM paint.
  // They are reattached synchronously before the browser presents the next frame.
  for (const entry of [...numbers.values(), ...charts.values()]) { entry.seen = false; entry.host.remove(); }
}
function mountNumbers(page) {
  page.querySelectorAll(metricSelector).forEach((node, index) => safely(() => {
    const text = node.textContent.trim(), spec = parseMetric(text);
    if (!spec) return;
    const key = node.dataset.motionKey || `${index}:${node.closest('.section')?.querySelector('h2')?.textContent || ''}`;
    let entry = numbers.get(key);
    if (!entry) {
      const host = document.createElement('span'); host.className = 'motion-number';
      entry = { host, root: createRoot(host), spec: null, initial: canAnimate() ? 0 : spec.value };
      numbers.set(key, entry);
    }
    const changed = !equalSpec(entry.spec, spec);
    entry.seen = true; entry.spec = spec; entry.text = text;
    node.dataset.motionValue = text;
    node.setAttribute('aria-label', text);
    entry.host.setAttribute('aria-hidden', 'true');
    node.replaceChildren(entry.host);
    if (changed) { renderNumber(entry, !canAnimate()); ++stats.numberUpdates; }
  }));
  for (const [key, entry] of numbers) if (!entry.seen) { entry.root.unmount(); numbers.delete(key); }
}
function mountCharts(page) {
  page.querySelectorAll('[data-motion-chart]').forEach((node, index) => safely(() => {
    const spec = JSON.parse(node.dataset.motionChart), key = `${index}:${spec.type}`;
    let entry = charts.get(key);
    if (!entry) {
      const host = document.createElement('div'); host.className = 'motion-chart'; host.setAttribute('aria-hidden', 'true');
      node.append(host);
      entry = { host, spec, chart: createChart(host, spec, { animate: canAnimate() }) };
      entry.width = host.clientWidth; entry.height = host.clientHeight;
      chartResize.observe(host);
      charts.set(key, entry); ++stats.chartCreates;
    } else {
      node.append(entry.host);
      resizeChart(entry);
      if (!equalSpec(entry.spec, spec)) { entry.chart.update(spec, { animate: canAnimate() }); ++stats.chartUpdates; }
      entry.spec = spec;
    }
    entry.seen = true;
    node.classList.add('motion-chart-ready');
  }));
  for (const [key, entry] of charts) if (!entry.seen) { disposeChart(entry); charts.delete(key); }
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
  lastPage = page;
  mountCharts(page); mountNumbers(page);
  enterItems(page, enter);
}

function navigation(nav) {
  if (!navControl) navControl = createNavigation(nav, { canAnimate, document, ResizeObserver });
  navControl.update();
}
function settle() {
  finishEntrance(); navControl?.settle();
  numbers.forEach(entry => renderNumber(entry, true));
  charts.forEach(entry => entry.chart.settle());
}
function setVisibility(value) { visible = !!value; if (!visible) settle(); }
preference.addEventListener('change', () => { if (preference.matches) settle(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) settle(); });
window.addEventListener('pagehide', () => { finishEntrance(); clearEntries(); navControl?.dispose(); });

window.TwinMotion = {
  beforePaint: (...args) => safely(() => beforePaint(...args)),
  afterPaint: (...args) => safely(() => afterPaint(...args)),
  navigation: nav => safely(() => navigation(nav)), setVisibility, settle,
  diagnostics: () => ({ engine: 'React Bits + ECharts', version: 1, view: currentView, visible, reduced: preference.matches,
    numbers: numbers.size, charts: charts.size, ...stats }),
  // Reports expose canonical target values, including during a numeric transition.
  text: page => { const clone = page.cloneNode(true); clone.querySelectorAll('[data-motion-value]').forEach(n => { n.textContent = n.dataset.motionValue; }); clone.querySelectorAll('.motion-chart').forEach(n => n.remove()); return clone.textContent; }
};
