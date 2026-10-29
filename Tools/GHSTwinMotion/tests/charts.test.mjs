import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { init as initECharts, use } from 'echarts/core';
import { BarChart, LineChart, PieChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';

use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, SVGRenderer]);

const source = fs.readFileSync(new URL('../src/charts.js', import.meta.url), 'utf8')
  .replace(/^import .*?;\r?\n/gm, '').replace('export function createChart', 'function createChart');

function harness({ real = false } = {}) {
  const calls = [];
  const svg = { style: { transform: 'rotate(-90deg)' } };
  const host = { style: {}, clientWidth: 180, clientHeight: 154, querySelectorAll: () => [svg] };
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
  let instance = chart;
  const scope = { init: (...args) => {
    calls.push(['init', ...args]);
    if (real) {
      instance = initECharts(null, null, { ...args[2], ssr: true });
      for (const [method, event] of [['setOption', 'option'], ['resize', 'resize']]) {
        const original = instance[method].bind(instance);
        instance[method] = (...parameters) => {
          if (method === 'resize') calls.push(['resizeAnimators', animatedElements(instance).reduce((sum, element) => sum + element.animators.length, 0)]);
          calls.push([event, ...parameters]); return original(...parameters);
        };
      }
    }
    return instance;
  }, use() {}, BarChart: {}, LineChart: {}, PieChart: {}, GridComponent: {}, TooltipComponent: {}, SVGRenderer: {} };
  // ECharts checks array types in its own realm; keep real fixture options there.
  const createChart = real
    ? new Function(...Object.keys(scope), source + '\nreturn createChart;')(...Object.values(scope))
    : vm.runInNewContext(source + '\ncreateChart;', scope);
  return { createChart, host, svg, calls, get instance() { return instance; }, option: () => calls.filter(call => call[0] === 'option').at(-1)[1] };
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
  assert.equal(first.animationDuration, 320);
  assert.equal(second.animationDurationUpdate, 240);
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
  const options = h.calls.filter(call => call[0] === 'option').length;
  control.settle();
  assert.equal(h.calls.filter(call => call[0] === 'option').length, options);
  assert.equal(h.calls.find(call => call[0] === 'action')[1].type, 'hideTip');
  control.resize();
  assert.equal(h.calls.filter(call => call[0] === 'option').length, options);
  assert.equal(h.calls.filter(call => call[0] === 'resize').length, 1);
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

function animatedElements(instance) {
  const elements = new Set();
  instance.getZr().storage.traverse(element => {
    elements.add(element);
    for (let clip = element.getClipPath?.(); clip; clip = clip.getClipPath?.()) elements.add(clip);
    const label = element.getTextContent?.();
    if (label) elements.add(label);
  });
  return [...elements];
}

function advanceAnimations(instance) {
  let advanced = 0;
  for (const element of animatedElements(instance)) for (const animator of element.animators) {
    const clip = animator.getClip();
    if (clip) { clip.onframe(0.25); advanced++; }
  }
  assert.ok(advanced > 0, 'The fixture must contain real in-flight ZRender animations.');
}

const chartShapes = instance => JSON.parse(JSON.stringify(instance.getZr().storage.getDisplayList(true)
  .filter(element => element.shape).map(element => ({ type: element.type, shape: element.shape }))));

const animationFixtures = [
  { type: 'ring', parts: [{ label: '已用', value: 4 }, { label: '可用', value: 6 }] },
  { type: 'stack', total: 10, parts: [{ label: '完成', value: 4 }, { label: '待办', value: 6 }] },
  { type: 'bars', parts: [{ label: '运行', value: 4 }, { label: '待机', value: 6 }] },
  { type: 'trend', points: [{ time: '06:00:00', x: 0, inbound: 2, outbound: 4 }, { time: '10:00:00', x: 1, inbound: 6, outbound: 3 }] }
];

for (const spec of animationFixtures) {
  test(`${spec.type} settle finishes real animation without rebuilding chart options`, () => {
    const h = harness({ real: true }), expected = harness({ real: true });
    const control = h.createChart(h.host, spec), reference = expected.createChart(expected.host, spec, { animate: false });
    try {
      assert.ok(h.option().animationDuration >= 280 && h.option().animationDuration <= 360);
      advanceAnimations(h.instance);
      control.settle();
      assert.equal(h.calls.filter(call => call[0] === 'option').length, 1);
      assert.equal(h.instance.getOption().animation, true, 'Settling must retain animation for subsequent data updates.');
      assert.ok(animatedElements(h.instance).every(element => element.animators.length === 0));
      assert.deepEqual(chartShapes(h.instance), chartShapes(expected.instance));
      const next = spec.parts ? { ...spec, parts: spec.parts.map(part => ({ ...part, value: part.value + 2 })) }
        : { ...spec, points: spec.points.map(point => ({ ...point, inbound: point.inbound + 2, outbound: point.outbound + 2 })) };
      control.update(next); reference.update(next, { animate: false });
      assert.equal(h.option().animationDurationUpdate, 240);
      // ECharts' SSR line view deliberately disables data interpolation. Its
      // updated geometry is still checked; browser frame timing is separate QA.
      if (spec.type !== 'trend') advanceAnimations(h.instance);
      control.settle();
      assert.equal(h.calls.filter(call => call[0] === 'option').length, 2);
      assert.ok(animatedElements(h.instance).every(element => element.animators.length === 0));
      assert.deepEqual(chartShapes(h.instance), chartShapes(expected.instance));
    } finally { control.dispose(); reference.dispose(); }
  });

  test(`${spec.type} resize finishes real animation without repeating data options`, () => {
    const h = harness({ real: true }), expected = harness({ real: true });
    const control = h.createChart(h.host, spec);
    expected.host.clientWidth = 320; expected.host.clientHeight = 220;
    const reference = expected.createChart(expected.host, spec, { animate: false });
    try {
      advanceAnimations(h.instance);
      h.host.clientWidth = 320; h.host.clientHeight = 220;
      control.resize();
      const options = h.calls.filter(call => call[0] === 'option');
      assert.equal(options.length, spec.type === 'bars' ? 2 : 1);
      if (spec.type === 'bars') {
        assert.equal(options[1][2].lazyUpdate, true, 'The partial layout must be consumed by the resize update.');
        assert.deepEqual(Object.keys(options[1][1]).sort(), ['grid', 'series', 'yAxis']);
        assert.equal(options[1][1].series[0].data, undefined);
        assert.equal(options[1][1].series[0].label.width, 22);
      }
      assert.equal(h.calls.filter(call => call[0] === 'resize').length, 1);
      assert.equal(h.calls.find(call => call[0] === 'resizeAnimators')[1], 0, 'Old value animations finish before resize.');
      assert.equal(h.instance.getWidth(), 320); assert.equal(h.instance.getHeight(), 220);
      assert.ok(animatedElements(h.instance).every(element => element.animators.length === 0));
      assert.deepEqual(chartShapes(h.instance), chartShapes(expected.instance));
      control.resize();
      assert.equal(h.calls.filter(call => call[0] === 'option').length, options.length, 'Unchanged widths do not patch options.');
    } finally { control.dispose(); reference.dispose(); }
  });
}
