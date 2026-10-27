import test from 'node:test';
import assert from 'node:assert/strict';
import { parseMetric } from '../src/identity.js';
test('counters retain separators, decimals, percent and signed quantities', () => {
  assert.deepEqual(parseMetric('337,783'), {value:337783,decimals:0,suffix:'',separator:','});
  assert.deepEqual(parseMetric('80.0%'), {value:80,decimals:1,suffix:'%',separator:''});
  assert.equal(parseMetric('-1').value,-1);
  assert.equal(parseMetric('0').value,0);
});
test('unknown telemetry and composite business fields are never animated into false numbers', () => {
  for(const value of ['—','暂无','遥测未接入','12 / 24','SKU2038','14:20','32 件','']) assert.equal(parseMetric(value),null);
});
