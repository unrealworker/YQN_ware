'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { readMetrics, BudgetPolicy } = require('../server/resource-budget');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const sample = (id, time, appliedFps, actualFps, gpuMs = 10) => ({ id, receivedAt: time, appliedFps, actualFps, gpuMs });
test('unlimited frame budget stays zero across admission pressure telemetry and departure', () => {
  const p = new BudgetPolicy({ mode: 'independent', fps: 0, adaptiveResourceBudget: true });
  assert.equal(p.update([null], 0), 0);
  assert.equal(p.update(Array(10).fill(null), 1000), 0);
  const loaded = time => Array.from({ length: 10 }, (_, i) => sample(String(i), time, 0, 18, 50));
  assert.equal(p.update(loaded(7000), 7000), 0);
  assert.equal(p.update(loaded(9000), 9000), 0);
  assert.equal(p.update([sample('one', 10000, 0, 95)], 10000), 0);
  assert.equal(p.update([], 12000), 0);
});
test('zero-frame cap telemetry remains visible while negative and fractional limits are rejected', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ghs-unlimited-metrics-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'metrics.json');
  fs.writeFileSync(file, JSON.stringify({ version: 1, sequence: 8, appliedFps: 0, actualFps: 87.5, gpuMs: 9, screenPercentage: 100 }));
  assert.equal(readMetrics(dir)?.appliedFps, 0);
  assert.equal(readMetrics(dir)?.actualFps, 87.5);
  for (const appliedFps of [-1, 0.5, 4, 121]) {
    fs.writeFileSync(file, JSON.stringify({ version: 1, sequence: 8, appliedFps, actualFps: 87.5 }));
    assert.equal(readMetrics(dir), null);
  }
});
test('admission preserves configured targets and waits for warmup plus fresh acknowledgements', () => {
  const p = new BudgetPolicy({ mode: 'independent', fps: 60 });
  assert.equal(p.update([null, null], 0), 60);
  assert.equal(p.update([sample('a', 2000, 60, 30), sample('b', 2000, 60, 30)], 2000), 60);
  assert.equal(p.update([sample('a', 6000, 60, 60), sample('b', 6000, 30, 30)], 6000), 60);
  assert.equal(p.update([sample('a', 7000, 60, 60), sample('b', 7000, 60, 60)], 7000), 60);
  assert.equal(p.update([sample('a', 8000, 60, 30), null], 8000), 60);
  assert.equal(p.update([sample('a', 8000, 60, 30)], 8000), 60);
  assert.equal(p.update(Array(10).fill(null), 9000), 60);
});
test('two observed low-fps intervals apply a fair cap, duplicate telemetry is not counted, and recovery waits twelve seconds', () => {
  const p = new BudgetPolicy({ mode: 'independent', fps: 60 });
  p.update([null, null], 0);
  const low = [sample('a', 6000, 60, 35), sample('b', 6000, 60, 40)];
  assert.equal(p.update(low, 6000), 60);
  assert.equal(p.update(low, 7000), 60);
  assert.equal(p.update([sample('a', 8000, 60, 35), sample('b', 8000, 60, 40)], 8000), 52);
  assert.equal(p.update([sample('a', 10000, 52, 52), sample('b', 10000, 52, 52)], 10000), 44);
  assert.equal(p.update([sample('a', 12000, 44, 44), sample('b', 12000, 44, 44)], 12000), 36);
  assert.equal(p.update([sample('a', 14000, 36, 36), sample('b', 14000, 36, 36)], 14000), 33);
  assert.equal(p.update([sample('a', 18000, 33, 33), sample('b', 18000, 33, 33)], 18000), 33);
  assert.equal(p.update([sample('a', 21000, 33, 33), sample('b', 21000, 33, 33)], 21000), 33);
  assert.equal(p.update([sample('a', 23000, 33, 33), sample('b', 23000, 33, 33)], 23000), 35);
});
test('GPU wait measurements cannot reduce a healthy delivered frame rate', () => {
  const p = new BudgetPolicy({ mode: 'independent', fps: 60 });
  assert.equal(p.update([null, null, null], 0), 60);
  const m = time => [sample('a', time, 60, 60, 27), sample('b', time, 60, 60, 27), sample('c', time, 60, 60, 15)];
  assert.equal(p.update(m(6000), 6000), 60);
  assert.equal(p.update(m(8000), 8000), 60);
  assert.equal(p.update([sample('a', 10000, 60, 60, 250), sample('b', 10000, 60, 60, 250), sample('c', 10000, 60, 60, null)], 10000), 60);
  assert.equal(p.update([sample('a', 12000, 60, 60, null), sample('b', 12000, 60, 60, NaN), sample('c', 12000, 60, 60, 500)], 12000), 60);
});
test('missing GPU timings still permit pressure detection and shared or disabled mode keeps full target', () => {
  const p = new BudgetPolicy({ mode: 'independent', fps: 60 });
  p.update([null, null], 0);
  assert.equal(p.update([sample('a', 6000, 60, 40, null), sample('b', 6000, 60, 40, null)], 6000), 60);
  assert.equal(p.update([sample('a', 8000, 60, 40, null), sample('b', 8000, 60, 40, null)], 8000), 52);
  assert.equal(new BudgetPolicy({ mode: 'shared', fps: 60 }).update([null, null, null], 0), 60);
  assert.equal(new BudgetPolicy({ mode: 'independent', fps: 60, adaptiveResourceBudget: false }).update([null, null, null], 0), 60);
});
test('an expired pressure hold does not promote a newly struggling instance', () => {
  const p = new BudgetPolicy({ mode: 'independent', fps: 60 });
  p.update([null, null], 0);
  p.update([sample('a', 6000, 60, 35), sample('b', 6000, 60, 35)], 6000);
  p.update([sample('a', 8000, 60, 35), sample('b', 8000, 60, 35)], 8000);
  p.update([sample('a', 10000, 52, 52), sample('b', 10000, 52, 52)], 10000);
  assert.equal(p.update([sample('a', 21000, 44, 8), sample('b', 21000, 44, 8)], 21000), 44);
});
test('probing requires consecutive healthy samples, a four-second interval and fresh acknowledgements', () => {
  const p = new BudgetPolicy({ mode: 'independent', fps: 60 });
  p.update([null, null], 0);
  const m = (time, applied, actual = applied) => [sample('a', time, applied, actual), sample('b', time, applied, actual)];
  p.update(m(6000, 60, 40), 6000); p.update(m(8000, 60, 40), 8000);
  assert.equal(p.update(m(21000, 52), 21000), 52);
  assert.equal(p.update(m(21000, 52), 22000), 52);
  assert.equal(p.update(m(23000, 52, 47), 23000), 52);
  assert.equal(p.update(m(25000, 52), 25000), 52);
  assert.equal(p.update(m(27000, 52), 27000), 54);
  assert.equal(p.update(m(29000, 54), 29000), 54);
  assert.equal(p.update(m(30000, 54), 30000), 54);
  assert.equal(p.update(m(31000, 54), 31000), 56);
  assert.equal(p.update(m(24000, 56), 32000), 56);
  assert.equal(p.update(m(33000, 54), 33000), 56);
});
test('metrics reader only accepts fresh bounded local telemetry and tolerates atomic replace and malformed data', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ghs-metrics-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'metrics.json');
  assert.equal(readMetrics(dir), null);
  fs.writeFileSync(file, '{'); assert.equal(readMetrics(dir), null);
  fs.writeFileSync(file, JSON.stringify({ version: 1, sequence: 3, appliedFps: 30, actualFps: 29.5, gpuMs: 10, screenPercentage: 100 }));
  assert.equal(readMetrics(dir).actualFps, 29.5);
  fs.utimesSync(file, new Date(0), new Date(0)); assert.equal(readMetrics(dir), null);
  fs.writeFileSync(file, JSON.stringify({ version: 1, sequence: 3, appliedFps: 30, actualFps: 10000 }));
  assert.equal(readMetrics(dir), null);
});
