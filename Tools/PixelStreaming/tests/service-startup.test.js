'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const net = require('node:net');
const { once, EventEmitter } = require('node:events');
const WebSocket = require('ws');
const { createService } = require('../server/service');

const token = 'startup-test-control-token-0123456789';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, limit = 2500) { const start = Date.now(); while (!fn()) { if (Date.now() - start > limit) throw Error('Timed out'); await delay(10); } }
async function port() { const server = net.createServer().listen(0, '127.0.0.1'); await once(server, 'listening'); const value = server.address().port; await new Promise(resolve => server.close(resolve)); return value; }
async function fixture(t, options = {}) {
  const launched = [], config = { executablePath: process.execPath, httpPort: await port(), streamerPort: await port(), mode: 'independent', turnUrl: 'turn:test.example:3478', turnUsername: 'private-user', turnPassword: 'private-relay-password' };
  const service = createService(config, { token, reconnectGraceMs: 30, identificationTimeoutMs: 60, startupTimeoutMs: 1200, ...options, spawnProcess(_exe, args) {
    const child = new EventEmitter(); child.pid = null; child.exitCode = null; child.signalCode = null;
    launched.push({ child, id: args.find(a => a.startsWith('-PixelStreamingID=')).slice('-PixelStreamingID='.length), url: args.find(a => a.startsWith('-PixelStreamingConnectionURL=')).slice('-PixelStreamingConnectionURL='.length) }); return child;
  } });
  await service.start(); t.after(() => service.stop());
  return { service, config, launched, base: `http://127.0.0.1:${config.httpPort}` };
}
async function viewer(ctx) {
  const response = await fetch(ctx.base + '/api/session', { method: 'POST', body: '{}' });
  const session = await response.json(), ws = new WebSocket(ctx.base.replace('http:', 'ws:') + '/ws?token=' + session.token), messages = [];
  ws.on('message', bytes => messages.push(JSON.parse(bytes))); await once(ws, 'open');
  await until(() => messages.some(m => m.type === 'ghsAdmission'));
  return { ws, messages, id: messages.find(m => m.type === 'ghsAdmission').instanceId, playerId: messages.find(m => m.type === 'ghsAdmission').playerId };
}
async function streamer(instance, options = {}) {
  const ws = new WebSocket(instance.url, options), messages = []; let closeCode;
  ws.on('message', bytes => messages.push(JSON.parse(bytes))); ws.on('close', code => { closeCode = code; });
  await once(ws, 'open'); await until(() => messages.some(m => m.type === 'identify'));
  return { ws, messages, identify() { ws.send(JSON.stringify({ type: 'endpointId', id: instance.id })); }, get closeCode() { return closeCode; } };
}
async function denied(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url); ws.on('error', () => {});
    ws.on('unexpected-response', (_req, res) => { res.resume(); ws.terminate(); resolve(res.statusCode); });
    ws.on('open', () => { ws.terminate(); reject(Error('Unexpected streamer upgrade')); });
  });
}

test('owned initialization waits beyond normal identity deadline without exposing ICE or releasing startup queue', async t => {
  const ctx = await fixture(t), first = await viewer(ctx); await viewer(ctx);
  const stream = await streamer(ctx.launched[0]);
  await delay(150);
  assert.equal(stream.ws.readyState, WebSocket.OPEN, 'slow initialization must keep its first socket');
  assert.equal(ctx.launched.length, 1, 'identity is not ready merely because a socket connected');
  assert.equal(stream.messages.some(m => m.type === 'config'), false);
  const starting = ctx.service.status().instances.find(i => i.id === first.id);
  assert.equal(starting.startupStage, 'waitingIdentity'); assert.ok(starting.identityWaitMs >= 100);
  assert.ok(first.messages.some(m => m.type === 'ghsStage' && m.stage === 'initializingStreamer'));
  stream.identify(); await until(() => ctx.service.status().instances[0].state === 'ready');
  assert.equal(ctx.launched.length, 2); assert.equal(stream.messages.filter(m => m.type === 'identify').length, 1);
  await until(() => stream.messages.some(m => m.type === 'config'));
  const ready = ctx.service.status().instances[0]; assert.equal(ready.startupStage, 'ready'); assert.ok(ready.startupElapsedMs >= 150);
  const logs = ctx.service.status().logs.join('\n'); assert.match(logs, /phase=waitingIdentity/); assert.match(logs, /phase=ready/);
  for (const secret of [ctx.config.turnPassword, new URL(ctx.launched[0].url).searchParams.get('streamerToken')]) assert.equal(JSON.stringify(ctx.service.status()).includes(secret), false);
});

test('initialization deadline is anchored to process launch and reconnects cannot extend it', async t => {
  const ctx = await fixture(t, { startupTimeoutMs: 420 }); await viewer(ctx); await viewer(ctx);
  const started = Date.now(); await delay(130);
  const first = await streamer(ctx.launched[0]); await delay(80); first.ws.close(); await until(() => first.closeCode !== undefined);
  const second = await streamer(ctx.launched[0]);
  await until(() => ctx.service.status().instances[0].state === 'failed', 800);
  assert.ok(Date.now() - started < 650, 'reconnect must not restart the total initialization budget');
  await until(() => second.ws.readyState === WebSocket.CLOSED);
  assert.equal(ctx.launched.length, 2, 'expired initialization releases only the next queued process');
  assert.equal(ctx.service.status().instances[0].startupStage, 'failed');
  assert.match(ctx.service.status().message, /身份确认/);
});

test('normal ready-instance reconnect keeps the short identity deadline and never launches another UE', async t => {
  const ctx = await fixture(t); await viewer(ctx);
  const first = await streamer(ctx.launched[0]); first.identify(); await until(() => ctx.service.status().instances[0].state === 'ready');
  first.ws.close(); await until(() => ctx.service.status().instances[0].state === 'reconnecting');
  const second = await streamer(ctx.launched[0]); await until(() => second.closeCode !== undefined, 500);
  assert.equal(second.closeCode, 1008); assert.equal(ctx.launched.length, 1);
  const third = await streamer(ctx.launched[0]); third.identify(); await until(() => ctx.service.status().instances[0].state === 'ready');
  assert.equal(ctx.launched.length, 1);
});

test('pending identity is unique and unknown tokens or endpoint IDs never gain initialization authority', async t => {
  const ctx = await fixture(t); await viewer(ctx);
  const first = await streamer(ctx.launched[0]);
  assert.equal(await denied(ctx.launched[0].url), 403, 'second pending socket must not displace the owned initialization');
  const unknown = new URL(ctx.launched[0].url); unknown.searchParams.set('streamerToken', 'wrong-token'); assert.equal(await denied(unknown.href), 403);
  first.ws.send(JSON.stringify({ type: 'endpointId', id: 'another-instance' })); await until(() => first.closeCode !== undefined);
  assert.equal(first.closeCode, 1008); assert.equal(first.messages.some(m => m.type === 'config'), false);
  const valid = await streamer(ctx.launched[0]); valid.identify(); await until(() => ctx.service.status().instances[0].state === 'ready');
});

test('process exit immediately closes its pending identity and releases initialization capacity', async t => {
  const ctx = await fixture(t); const first = await viewer(ctx); await viewer(ctx);
  const stream = await streamer(ctx.launched[0]);
  ctx.launched[0].child.exitCode = 1; ctx.launched[0].child.emit('exit', 1, null);
  await until(() => stream.ws.readyState === WebSocket.CLOSED, 500);
  assert.equal(ctx.launched.length, 2); assert.equal(ctx.service.status().instances[0].state, 'failed');
  assert.ok(first.messages.some(m => m.type === 'ghsInstanceFailed'));
});

test('stopping during pending identity closes sockets and never drains queued launches', async t => {
  const ctx = await fixture(t); await viewer(ctx); await viewer(ctx);
  const stream = await streamer(ctx.launched[0]); await ctx.service.stop();
  await until(() => stream.ws.readyState === WebSocket.CLOSED);
  assert.equal(ctx.launched.length, 1); assert.equal(ctx.service.status().instances.length, 0);
});

test('administrator removal during initialization closes pending identity without restarting the removed instance', async t => {
  const ctx = await fixture(t), first = await viewer(ctx); await viewer(ctx); const stream = await streamer(ctx.launched[0]);
  const response = await fetch(`http://127.0.0.1:${ctx.service.controlPort}/disconnect`, { method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, body: JSON.stringify({ playerId: first.playerId }) });
  assert.equal(response.status, 200); await until(() => stream.ws.readyState === WebSocket.CLOSED, 500);
  assert.equal(ctx.launched.length, 2); assert.equal(ctx.service.status().instances.some(i => i.id === first.id), false);
});

test('a delayed native pong shares only the owned initialization budget and normal heartbeat resumes after identity', async t => {
  const ctx = await fixture(t, { heartbeatIntervalMs: 40 }); await viewer(ctx);
  const stream = await streamer(ctx.launched[0], { autoPong: false });
  await delay(150); assert.equal(stream.ws.readyState, WebSocket.OPEN, 'initializing UE must not lose its first socket to the shorter heartbeat');
  stream.identify(); await until(() => ctx.service.status().instances[0].state === 'ready');
  await until(() => stream.ws.readyState === WebSocket.CLOSED, 300);
  assert.equal(ctx.service.status().instances[0].state, 'reconnecting', 'ready instances regain ordinary missing-pong detection');
});

test('lack of any signalling socket fails at the unchanged process startup budget', async t => {
  const ctx = await fixture(t, { startupTimeoutMs: 130 }); await viewer(ctx); await viewer(ctx);
  await until(() => ctx.service.status().instances[0].state === 'failed', 400);
  assert.equal(ctx.launched.length, 2); assert.match(ctx.service.status().message, /信令连接/);
  assert.equal(await denied(ctx.launched[0].url), 403, 'expired tokens cannot revive a failed process');
});

test('duplicate endpoint acknowledgments cannot rerun readiness or launch additional queued instances', async t => {
  const ctx = await fixture(t); await viewer(ctx); await viewer(ctx); await viewer(ctx);
  const stream = await streamer(ctx.launched[0]); stream.identify(); await until(() => ctx.launched.length === 2);
  const elapsed = ctx.service.status().instances[0].startupElapsedMs;
  stream.identify(); stream.identify(); await delay(40);
  assert.equal(ctx.launched.length, 2); assert.equal(ctx.service.status().instances[0].startupElapsedMs, elapsed);
  assert.equal(ctx.service.status().logs.filter(line => line.includes('id=' + ctx.launched[0].id + ' phase=ready')).length, 1);
});

test('production identity timeout is crossed on the original socket without an extra UE launch', async t => {
  // This reproduces the measured regression with the real 10-second identity
  // value. Only the total process deadline is shortened for a bounded test.
  const ctx = await fixture(t, { identificationTimeoutMs: 10000, startupTimeoutMs: 15000 }); await viewer(ctx);
  const stream = await streamer(ctx.launched[0]); await delay(10300);
  assert.equal(stream.ws.readyState, WebSocket.OPEN);
  stream.identify(); await until(() => ctx.service.status().instances[0].state === 'ready');
  assert.equal(ctx.launched.length, 1); assert.equal(stream.closeCode, undefined);
});
