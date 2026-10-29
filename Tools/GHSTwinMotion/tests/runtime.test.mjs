import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { transformSync } from 'esbuild';
import { parseMetric, equalSpec } from '../src/identity.js';

// Exercise the production lifecycle with counted rendering resources. Real CEF
// frame timing is covered separately by verify_ui_motion_performance.py.
const source = fs.readFileSync(new URL('../src/runtime.jsx', import.meta.url), 'utf8').replace(/^import .*;\r?\n/gm, '');
const code = transformSync(source, { loader: 'jsx', jsx: 'transform' }).code;
function harness({ startup = false } = {}) {
  const calls = { roots: 0, flushes: 0, unmounts: 0, charts: [], renders: [] };
  let preparedNodes = [];
  const frames = new Map(); let nextFrame = 0;
  function frame() { const batch = [...frames.values()]; frames.clear(); batch.forEach(fn => fn()); }
  function drain() { while (frames.size) frame(); }
  const events = new Map(), observed = new Set();
  const preference = { matches: false, addEventListener: (name, fn) => events.set('preference', fn) };
  const node = (text = '') => ({ textContent: text, dataset: {}, style: {}, clientWidth: 180, clientHeight: 124,
    children: [], classList: { add() {} }, setAttribute() {}, closest: () => null, querySelectorAll: () => preparedNodes,
    append(child) { child.remove(); this.children.push(child); child.parent = this; },
    replaceChildren(child) { this.children = []; this.append(child); },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter(n => n !== this); this.parent = null; }
  });
  const document = { hidden: false, body: node(), createElement: () => node(), addEventListener: (name, fn) => events.set(name, fn) };
  const window = { matchMedia: () => preference, addEventListener: (name, fn) => events.set(name, fn) };
  const startupCallbacks = [];
  if (startup) window.TwinStartup = { presented: false, whenReady: fn => startupCallbacks.push(fn) };
  const context = { window, document, console, parseMetric, equalSpec,
    getComputedStyle: () => ({ padding: '26px 24px' }),
    requestAnimationFrame(fn) { frames.set(++nextFrame, fn); return nextFrame; }, cancelAnimationFrame(id) { frames.delete(id); },
    React: { createElement: (type, props) => ({ type, props }) }, CountUp: 'CountUp',
    flushSync(fn) { ++calls.flushes; fn(); },
    createRoot(host) { ++calls.roots; return { render(value) { calls.renders.push(value); host.textContent = typeof value === 'string' ? value : String(value.props.to); }, unmount() { ++calls.unmounts; } }; },
    ResizeObserver: class { observe(n) { observed.add(n); } unobserve(n) { observed.delete(n); } disconnect() { observed.clear(); } },
    createNavigation: () => ({ update() {}, settle() {}, dispose() {} }),
    createChart(host, spec, options) { const chart = { spec, options, updates: 0, settles: 0, disposed: false, resizes: 0,
      update(next) { this.spec = next; ++this.updates; }, settle() { ++this.settles; },
      dispose() { this.disposed = true; }, resize() { ++this.resizes; } }; calls.charts.push(chart); return chart; }
  };
  vm.runInNewContext(code, context);
  function paint(view, values = ['42'], withChart = true, flushFrames = true) {
    const metrics = values.map(v => node(v)), chart = node();
    chart.dataset.motionChart = JSON.stringify({ type: 'ring', parts: [{ label: '占用', value: Number(values[0]) }] });
    const page = { querySelectorAll: selector => selector === '[data-motion-chart]' ? withChart ? [chart] : [] : selector.startsWith('.list-row') ? [] : metrics };
    window.TwinMotion.beforePaint(page, view); window.TwinMotion.afterPaint(page, view, true);
    if (flushFrames) drain();
    return { metrics, chart };
  }
  return { motion: window.TwinMotion, calls, paint, observed, events, preference, frame, drain, document,
    prepare(view) {
      const chart = node(); chart.dataset.motionChart = JSON.stringify({ type: 'ring', parts: [{ label: '占用', value: 42 }] });
      preparedNodes = [chart];
      const page = node(); page.parentElement = document.body;
      window.TwinMotion.prepareView(page, view, 'actual chart markup');
    } };
}

test('first paint displays canonical metrics without React roots or a replay from zero', () => {
  const h = harness(), page = h.paint('overview', ['337,783', '80.0%', '156']);
  assert.equal(h.calls.roots, 0);
  assert.deepEqual(page.metrics.map(n => n.children[0].textContent), ['337,783', '80.0%', '156']);
  assert.equal(h.motion.diagnostics().numbers, 3);
});

test('returning to a view reuses its chart and numbers; detached charts are not observed', () => {
  const h = harness(), first = h.paint('overview');
  const numberHost = first.metrics[0].children[0], chartHost = first.chart.children[0];
  h.paint('devices', ['82']);
  assert.equal(h.observed.size, 1);
  assert.equal(h.observed.has(chartHost), false);
  const returned = h.paint('overview');
  assert.equal(returned.metrics[0].children[0], numberHost);
  assert.equal(returned.chart.children[0], chartHost);
  assert.equal(h.calls.charts.length, 2);
  assert.ok(h.calls.charts.every(c => !c.disposed));
  assert.equal(h.motion.diagnostics().viewReuses, 1);
  assert.equal(h.calls.roots, 0);
});

test('changed metrics use a single batch, animate from previous values and ignore identical refreshes', () => {
  const h = harness(); h.paint('overview', ['40', '50', '60']);
  const before = h.calls.flushes;
  h.paint('overview', ['41', '51', '61']);
  assert.equal(h.calls.flushes - before, 1);
  assert.equal(h.calls.roots, 3);
  assert.deepEqual(h.calls.renders.map(v => v.props.from), [40, 50, 60]);
  assert.ok(h.calls.renders.every(v => v.props.duration === 0.24));
  const renders = h.calls.renders.length;
  h.paint('overview', ['41', '51', '61']);
  assert.equal(h.calls.renders.length, renders);
  assert.equal(h.calls.charts[0].updates, 1);
  h.motion.setVisibility(false);
  assert.deepEqual(h.calls.renders.slice(-3), ['41', '51', '61']);
  h.motion.setVisibility(true); h.paint('overview', ['42', '52', '62']);
  assert.deepEqual(h.calls.renders.slice(-3).map(v => v.props.from), [41, 51, 61]);
  assert.equal(h.calls.roots, 3);
});

test('detail churn evicts old resources at a fixed bound; pagehide disposes the remainder', () => {
  const h = harness();
  for (let i = 0; i < 12; ++i) { h.paint('device:' + i, ['40']); h.paint('device:' + i, ['41']); }
  assert.equal(h.motion.diagnostics().cachedViews, 8);
  assert.equal(h.calls.charts.filter(c => c.disposed).length, 4);
  assert.equal(h.calls.unmounts, 4);
  assert.equal(h.observed.size, 1);
  h.events.get('pagehide')();
  assert.ok(h.calls.charts.every(c => c.disposed));
  assert.equal(h.calls.unmounts, 12);
  assert.equal(h.observed.size, 0);
});

test('reduced motion keeps real updates literal without creating animation roots', () => {
  const h = harness(); h.preference.matches = true;
  h.paint('overview', ['40']); h.paint('overview', ['41']);
  assert.equal(h.calls.roots, 0);
  assert.equal(h.motion.diagnostics().numberUpdates, 1);
  assert.equal(h.motion.diagnostics().errors.length, 0);
});

test('cold charts wait until navigation finishes and obsolete destinations never initialize', () => {
  const h = harness();
  h.motion.setTransitioning(true);
  h.paint('overview'); h.paint('devices');
  assert.equal(h.calls.charts.length, 0);
  assert.equal(h.motion.diagnostics().pendingCharts, 1);
  h.motion.setTransitioning(false); h.frame();
  assert.equal(h.calls.charts.length, 1);
  assert.equal(h.calls.charts[0].options.animate, false);
  assert.equal(h.motion.diagnostics().pendingCharts, 0);
  h.paint('overview', ['42'], true, false);
  h.motion.setVisibility(false); h.drain();
  assert.equal(h.calls.charts.length, 1);
  h.motion.setVisibility(true); h.drain();
  assert.equal(h.calls.charts.length, 2);
});

test('startup preparation reuses the real chart on first visit and removes its temporary markup', () => {
  const h = harness({ startup: true });
  assert.equal(h.calls.charts.length, 0);
  h.prepare('devices');
  assert.equal(h.calls.charts.length, 1);
  assert.equal(h.calls.charts[0].disposed, false);
  assert.equal(h.document.body.children.length, 0);
  assert.equal(h.observed.size, 0);
  h.prepare('devices'); h.paint('overview'); h.paint('devices');
  assert.equal(h.calls.charts.length, 2);
  assert.equal(h.motion.diagnostics().viewReuses, 1);
  h.events.get('pagehide')();
  assert.ok(h.calls.charts.every(c => c.disposed));
});
