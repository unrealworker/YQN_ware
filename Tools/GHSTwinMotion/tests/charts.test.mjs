import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../src/charts.js', import.meta.url), 'utf8')
  .replace(/^import .*?;\r?\n/gm, '').replace('export function createChart', 'function createChart');

function harness() {
  const calls = [];
  const svg = { style: { transform: 'rotate(-90deg)' } };
  const host = { style: {}, clientWidth: 180, querySelectorAll: () => [svg] };
  const stop = (scope, final) => calls.push(['stop', scope, final]);
  const chart = {
    on: (event, callback) => calls.push(['on', event, callback]),
    off: (...args) => calls.push(['off', ...args]),
    setOption: (...args) => calls.push(['option', ...args]),
    resize: (...args) => calls.push(['resize', ...args]),
    dispose: () => calls.push(['dispose']),
    dispatchAction: (...args) => calls.push(['action', ...args]),
    getZr: () => ({ storage: { traverse: visit => visit({ stopAnimation: stop, getClipPath: () => ({ stopAnimation: stop }), getTextContent: () => ({ stopAnimation: stop }) }) }, refreshImmediately: () => calls.push(['refresh']) })
  };
  const scope = { init: (...args) => { calls.push(['init', ...args]); return chart; }, use() {}, BarChart: {}, LineChart: {}, PieChart: {}, GridComponent: {}, TooltipComponent: {}, SVGRenderer: {} };
  vm.runInNewContext(source + '\nthis.createChart = createChart;', scope);
  return { createChart: scope.createChart, host, svg, calls, option: () => calls.filter(call => call[0] === 'option').at(-1)[1] };
}

test('data changes reuse the SVG instance and retain item identities when reordered', () => {
  const h = harness();
  const control = h.createChart(h.host, { type: 'ring', parts: [{ label: '可用', value: 4 }, { label: '占用', value: 6 }] });
  const first = h.option();
  control.update({ type: 'ring', parts: [{ label: '占用', value: 8 }, { label: '可用', value: 2 }] });
  const second = h.option();
  assert.equal(h.calls.filter(call => call[0] === 'init').length, 1);
  assert.equal(h.calls.find(call => call[0] === 'init')[3].renderer, 'svg');
  assert.equal(first.series[0].data[1].id, second.series[0].data[0].id);
  assert.equal(first.animationDuration, 600);
  assert.equal(second.animationDurationUpdate, 350);
  assert.equal(h.svg.style.transform, 'none');
});

test('missing values remain unknown, and tooltip labels cannot introduce HTML', () => {
  const h = harness();
  h.createChart(h.host, { type: 'bars', parts: [{ label: '<img onerror=alert(1)>', value: null }] });
  const option = h.option();
  const datum = option.series[0].data[0];
  assert.equal(datum.value, '-');
  assert.equal(option.series[0].label.formatter({ data: datum, value: datum.value }), '—');
  const tooltip = option.tooltip.formatter({ data: datum });
  assert.ok(!tooltip.includes('<img'));
  assert.ok(tooltip.includes('&lt;img'));
  assert.ok(tooltip.includes('—'));
  assert.equal(option.tooltip.confine, true);
  assert.ok(option.grid[0].left + option.grid[0].right < 120);
});

test('trend respects supplied unequal time spacing and stable IDs on insertion', () => {
  const h = harness();
  const old = { time: '10:00:00', x: 0.7, inbound: 2, outbound: null };
  const control = h.createChart(h.host, { type: 'trend', points: [{ time: '06:00:00', x: 0, inbound: 0, outbound: 0 }, old] });
  const id = h.option().series[0].data[1].id;
  control.update({ type: 'trend', points: [{ time: '06:00:00', x: 0, inbound: 0, outbound: 0 }, { time: '08:00:00', x: 0.3, inbound: 1, outbound: 1 }, old] });
  const option = h.option();
  assert.equal(option.series[0].data[2].id, id);
  assert.equal(option.series[0].data[2].value[0], 0.7);
  assert.equal(option.series[1].data[2].value[1], null);
  assert.equal(option.xAxis[0].axisLabel.formatter(0.35), '08:00');
});

test('reduced/hidden updates and settle resolve in-flight shapes without reinitializing', () => {
  const h = harness();
  const control = h.createChart(h.host, { type: 'stack', total: 10, parts: [{ label: '完成', value: 4 }] });
  control.update({ type: 'stack', total: 10, parts: [{ label: '完成', value: 8 }] }, { animate: false });
  assert.equal(h.option().animation, false);
  assert.equal(h.option().animationDuration, 0);
  assert.equal(h.option().series[0].data[0].rawValue, 8);
  assert.ok(h.calls.some(call => call[0] === 'stop' && call[2] === true));
  control.settle();
  assert.equal(h.calls.find(call => call[0] === 'action')[1].type, 'hideTip');
  control.resize();
  assert.equal(h.calls.filter(call => call[0] === 'init').length, 1);
  control.dispose();
  control.dispose();
  const length = h.calls.length;
  control.resize();
  control.update({ type: 'ring', parts: [] });
  control.settle();
  assert.equal(h.calls.length, length);
  assert.equal(h.calls.filter(call => call[0] === 'dispose').length, 1);
});
