'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const quality = require('../player/stream-quality');

test('uncapped official SDK config accepts zero before and after streamer initial settings', () => {
  const fps = { id: 'WebRTCFPS', _min: 1, number: 1 };
  const config = { getNumericSettings: () => [fps], setNumericSetting(id, value) { assert.equal(id, fps.id); fps.number = Math.max(fps._min, value); } };
  quality.configureUncapped(config, 0);
  assert.equal(fps._min, 0); assert.equal(fps.number, 0);
  config.setNumericSetting('WebRTCFPS', 0); assert.equal(fps.number, 0);
  quality.configureUncapped(config, 48); assert.equal(fps.number, 0, 'finite mode is left to SDK');
});

test('low latency hints are feature checked and a rejected hint does not break playback', () => {
  const video = { track: { kind: 'video' }, jitterBufferTarget: 300, playoutDelayHint: .3 };
  const audio = { track: { kind: 'audio' }, jitterBufferTarget: 250 };
  const unsupported = { track: { kind: 'video' } };
  const rejects = { track: { kind: 'video' }, get jitterBufferTarget() { return null; }, set jitterBufferTarget(_) { throw Error('unsupported'); } };
  const result = quality.configureReceivers({ getReceivers: () => [video, audio, unsupported, rejects] });
  assert.equal(video.jitterBufferTarget, 0); assert.equal(video.playoutDelayHint, 0);
  assert.equal(audio.jitterBufferTarget, 250, 'audio policy stays independent');
  assert.equal(Object.hasOwn(unsupported, 'jitterBufferTarget'), false);
  assert.equal(result, true);
  assert.equal(quality.configureReceivers(null), false);
});

const sample = (overrides = {}) => ({ id: 'v1', ssrc: 5, timestamp: 1000, framesDecoded: 50, bytesReceived: 1000000, packetsReceived: 1000, packetsLost: 5, jitterBufferDelay: 20, jitterBufferEmittedCount: 50, totalDecodeTime: .05, freezeCount: 2, ...overrides });
test('interval metrics distinguish receive buffering from decode work, and missing values from zero', () => {
  const meter = quality.createMeter();
  assert.equal(meter.update(sample()).fps, null);
  const m = meter.update(sample({ timestamp: 2000, framesDecoded: 110, bytesReceived: 2000000, packetsReceived: 1999, packetsLost: 6, jitterBufferDelay: 23, jitterBufferEmittedCount: 110, totalDecodeTime: .08, freezeCount: 3 }));
  assert.equal(m.fps, 60); assert.equal(m.bitrateMbps, 8); assert.equal(m.bufferMs, 50);
  assert.ok(Math.abs(m.decodeMs - .5) < .0001); assert.equal(m.lossPercent, .1); assert.equal(m.freezes, 1);
  assert.equal(meter.update(sample({ timestamp: 2000 })).fps, null, 'duplicate/backwards counters do not manufacture values');
  assert.equal(meter.update(sample({ id: 'v2', ssrc: 6, timestamp: 3000, framesDecoded: 2 })).bufferMs, null, 'new receiver starts a new interval');
  meter.reset(); assert.equal(meter.update(sample()).fps, null);
});

test('network path uses selected candidate IDs and never confuses TURN or TCP with direct UDP', () => {
  const pair = { localCandidateId: 'local', remoteCandidateId: 'remote' };
  assert.equal(quality.describePath(pair, [{ id: 'local', candidateType: 'host' }], [{ id: 'remote', protocol: 'udp', candidateType: 'host', address: '10.100.185.161' }]), '内网地址 · UDP');
  assert.equal(quality.describePath(pair, [{ id: 'local', candidateType: 'relay', relayProtocol: 'tcp' }], [{ id: 'remote', protocol: 'udp', candidateType: 'host' }]), 'TURN 中继 · TCP');
  assert.equal(quality.describePath(pair, [], [{ id: 'remote', protocol: 'udp', candidateType: 'srflx', address: '47.96.135.179' }]), '公网映射 · UDP');
  assert.equal(quality.describePath(null, [], []), '协商中');
});
