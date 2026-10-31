'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const net = require('node:net');
const fs = require('node:fs');
const path = require('node:path');
const { once, EventEmitter } = require('node:events');
const WebSocket = require('ws');
const { createService, validateConfig } = require('../server/service');
const { standbyHeadroom } = require('../server/resource-budget');
const token = 'warm-standby-test-token-0123456789012345';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, limit = 1600) { const start = Date.now(); while (!fn()) { if (Date.now() - start > limit) throw Error('Timed out'); await delay(10); } }
async function port() { const s = net.createServer().listen(0, '127.0.0.1'); await once(s, 'listening'); const value = s.address().port; await new Promise(r => s.close(r)); return value; }
const memory = { freeMemoryBytes: 40 * 1024 ** 3, totalMemoryBytes: 64 * 1024 ** 3, gpuFreeMiB: 12000, gpuTotalMiB: 16000, gpuReceivedAt: Date.now() };
async function fixture(t, configOverrides = {}, optionOverrides = {}) {
  const launched = [], telemetry = new Map(); let resources = memory;
  const config = { executablePath: process.execPath, mode: 'independent', warmStandbyEnabled: true, fps: 30, fixedFps: true, adaptiveResourceBudget: false, maxViewers: 3, httpPort: await port(), streamerPort: await port(), ...configOverrides };
  const service = createService(config, { token, reconnectGraceMs: 40, budgetIntervalMs: 15, warmStableMs: 40, warmBackoffMs: 150, activationTimeoutMs: 300, firstFrameStableMs: 30, resourcePressureMs: 70,
    resourceSnapshot: () => resources, readMetrics(directory) { const sample = telemetry.get(directory); return typeof sample === 'function' ? sample() : sample || null; }, ...optionOverrides,
    spawnProcess(_exe, args) {
      const child = new EventEmitter(); child.pid = null; child.exitCode = null; child.signalCode = null;
      launched.push({ child, args, id: args.find(a => a.startsWith('-PixelStreamingID=')).slice('-PixelStreamingID='.length), url: args.find(a => a.startsWith('-PixelStreamingConnectionURL=')).slice('-PixelStreamingConnectionURL='.length), dir: args.find(a => a.startsWith('-GHSStreamControlDir=')).slice('-GHSStreamControlDir='.length) }); return child;
    } });
  await service.start(); t.after(() => service.stop());
  function sample(instance, changes = {}) { const budget = JSON.parse(fs.readFileSync(path.join(instance.dir, 'budget.json'), 'utf8')); return { receivedAt: Date.now(), sequence: budget.sequence, appliedFps: budget.fps, actualFps: budget.fps || 60, gpuMs: 3, psoActivePrecacheRequests: 0, standbyMode: budget.mode || 'active', ...changes }; }
  return { service, config, launched, telemetry, sample, base: `http://127.0.0.1:${config.httpPort}`, setResources(value) { resources = value; }, autoAck(instance, changes = {}) { telemetry.set(instance.dir, () => sample(instance, changes)); } };
}
async function viewer(ctx, sessionToken) {
  const response = await fetch(ctx.base + '/api/session', { method: 'POST', body: JSON.stringify(sessionToken ? { token: sessionToken } : {}) }); const session = await response.json();
  const ws = new WebSocket(ctx.base.replace('http:', 'ws:') + '/ws?token=' + session.token), messages = []; let code;
  ws.on('message', b => messages.push(JSON.parse(b))); ws.on('close', value => { code = value; }); await once(ws, 'open');
  await until(() => messages.some(m => ['ghsAdmission', 'ghsFull', 'ghsInstanceFailed'].includes(m.type)));
  return { ws, messages, token: session.token, admission: messages.find(m => m.type === 'ghsAdmission'), get closeCode() { return code; } };
}
async function identify(instance) {
  const ws = new WebSocket(instance.url), messages = [];
  ws.on('message', b => { const m = JSON.parse(b); messages.push(m); if (m.type === 'identify') ws.send(JSON.stringify({ type: 'endpointId', id: instance.id })); });
  await once(ws, 'open'); await until(() => messages.some(m => m.type === 'config')); return { ws, messages };
}
async function readyPool(ctx) { await until(() => ctx.launched.length === 1); const instance = ctx.launched[0], signal = await identify(instance); ctx.autoAck(instance); await until(() => ctx.service.status().warmReadyCount === 1); return { instance, signal }; }
const frameReport = { type: 'ghsFirstFrame', attemptId: 1, attemptElapsedMs: 1500, navigationTotalMs: 2100, displayed: true };
async function firstFrame(ctx, client) {
  await until(() => ctx.service.status().instances.find(i => i.id === client.admission.instanceId)?.state === 'ready');
  client.ws.send(JSON.stringify({ type: 'subscribe', streamerId: client.admission.instanceId }));
  client.ws.send(JSON.stringify(frameReport));
  await until(() => ctx.service.status().viewers.find(v => v.playerId === client.admission.playerId)?.firstFrameReceived);
}

test('warm standby is strict opt-in, never changes shared mode or starts more than one spare', async t => {
  assert.equal(validateConfig({ executablePath: process.execPath }).warmStandbyEnabled, false);
  for (const bad of ['true', 1, null]) assert.throws(() => validateConfig({ executablePath: process.execPath, warmStandbyEnabled: bad }), /布尔/);
  const disabled = await fixture(t, { warmStandbyEnabled: false }); await delay(50); assert.equal(disabled.launched.length, 0);
  const shared = await fixture(t, { mode: 'shared' }); assert.equal(shared.launched.length, 1); assert.equal(shared.launched[0].id, 'shared'); assert.equal(shared.service.status().warmStartingCount, 0);
  const ctx = await fixture(t); await delay(60); assert.equal(ctx.launched.length, 1); assert.equal(ctx.service.status().viewerCount, 0); assert.equal(ctx.service.status().warmStartingCount, 1);
  assert.ok(ctx.launched[0].args.includes('-GHSStandbyCapable'));
  assert.equal(JSON.parse(fs.readFileSync(path.join(ctx.launched[0].dir, 'budget.json'), 'utf8')).mode, 'warming');
});

test('the service defaults to five seats and safely migrates only formerly valid 6-10 seat settings', () => {
  assert.equal(validateConfig({ executablePath: process.execPath }).maxViewers, 5);
  for (const maxViewers of [1, 5, 6, 10]) assert.equal(validateConfig({ executablePath: process.execPath, maxViewers }).maxViewers, Math.min(5, maxViewers));
  for (const maxViewers of [0, -1, 5.5, 11, '5']) assert.throws(() => validateConfig({ executablePath: process.execPath, maxViewers }), /人数/);
});

test('endpoint identity alone is not warm-ready; fresh PSO-zero stable samples and idle budget acknowledgment are required', async t => {
  const ctx = await fixture(t), instance = ctx.launched[0]; await identify(instance);
  await delay(80); assert.equal(ctx.service.status().warmReadyCount, 0);
  ctx.autoAck(instance, { psoActivePrecacheRequests: 2 }); await delay(80); assert.equal(ctx.service.status().warmReadyCount, 0);
  ctx.autoAck(instance, { receivedAt: Date.now() - 6000 }); await delay(70); assert.equal(ctx.service.status().warmReadyCount, 0);
  ctx.autoAck(instance, { actualFps: 1 }); await delay(80); assert.equal(ctx.service.status().warmReadyCount, 0);
  ctx.autoAck(instance); await until(() => ctx.service.status().warmReadyCount === 1);
  const budget = JSON.parse(fs.readFileSync(path.join(instance.dir, 'budget.json'), 'utf8')); assert.equal(budget.fps, 5); assert.equal(budget.mode, 'standby');
  assert.equal(ctx.service.status().instances[0].standby, true); assert.equal(ctx.service.status().instances[0].targetFps, 5);
});

test('warm hit leases one clean process and withholds ready/video routing until configured FPS is acknowledged', async t => {
  const ctx = await fixture(t), { instance, signal } = await readyPool(ctx); ctx.telemetry.set(instance.dir, ctx.sample(instance));
  const client = await viewer(ctx); assert.equal(client.admission.warmHit, true); assert.equal(client.admission.instanceId, instance.id);
  assert.ok(client.admission.timings.instanceStartupMs >= 0); assert.ok(client.admission.timings.standbyReadyAgeMs >= 0);
  assert.equal(ctx.service.status().instances.find(i => i.id === instance.id).state, 'activating');
  assert.equal(client.messages.some(m => m.type === 'ghsStage' && m.stage === 'streamerReady'), false);
  const budget = JSON.parse(fs.readFileSync(path.join(instance.dir, 'budget.json'), 'utf8')); assert.equal(budget.fps, 30); assert.equal(budget.mode, 'active');
  client.ws.send(JSON.stringify({ type: 'listStreamers' })); await until(() => client.messages.some(m => m.type === 'streamerList'));
  assert.deepEqual(client.messages.find(m => m.type === 'streamerList').ids, []);
  client.ws.send(JSON.stringify({ type: 'subscribe', streamerId: instance.id })); await until(() => client.messages.some(m => m.type === 'warning'));
  assert.equal(signal.messages.some(m => m.type === 'playerConnected'), false);
  ctx.autoAck(instance); await until(() => client.messages.some(m => m.type === 'ghsStage' && m.stage === 'streamerReady'));
  await firstFrame(ctx, client);
  await until(() => ctx.launched.length === 2); assert.equal(ctx.service.status().instances.find(i => i.id === instance.id).standby, false);
  assert.equal(ctx.launched.filter(i => i.id === instance.id).length, 1);
});

test('arrival during warming claims that new process without falsely claiming a warm hit or spawning a duplicate', async t => {
  const ctx = await fixture(t), instance = ctx.launched[0], client = await viewer(ctx);
  assert.equal(client.admission.instanceId, instance.id); assert.equal(client.admission.warmHit, false); assert.equal(ctx.launched.length, 1);
  assert.equal(JSON.parse(fs.readFileSync(path.join(instance.dir, 'budget.json'), 'utf8')).mode, 'active');
  await identify(instance); ctx.autoAck(instance); await until(() => ctx.service.status().instances.find(i => i.id === instance.id).state === 'ready');
});

test('spare counts against the process cap; demand is serialized and has priority over replenishment', async t => {
  const ctx = await fixture(t, { maxViewers: 2 }), instance = ctx.launched[0];
  const first = await viewer(ctx), second = await viewer(ctx), rejected = await viewer(ctx);
  assert.equal(rejected.admission, undefined); assert.ok(rejected.messages.some(m => m.type === 'ghsFull'));
  assert.equal(ctx.launched.length, 1); assert.equal(first.admission.instanceId, instance.id);
  await identify(instance); ctx.autoAck(instance); await until(() => ctx.launched.length === 2);
  assert.equal(ctx.launched[1].id, second.admission.instanceId); await identify(ctx.launched[1]); ctx.autoAck(ctx.launched[1]);
  await delay(100); assert.equal(ctx.launched.length, 2); assert.equal(ctx.service.status().warmReadyCount + ctx.service.status().warmStartingCount, 0);
});

test('leased instances are destroyed after the unchanged disconnect grace and never returned to the pool', async t => {
  const ctx = await fixture(t, { maxViewers: 1 }), { instance, signal } = await readyPool(ctx), client = await viewer(ctx); ctx.autoAck(instance);
  await until(() => ctx.service.status().instances[0].state === 'ready'); client.ws.close(); await until(() => ctx.service.status().viewerCount === 0);
  await until(() => ctx.launched.length === 2); assert.notEqual(ctx.launched[1].id, instance.id);
  assert.equal(ctx.service.status().instances.some(i => i.id === instance.id), false); await until(() => signal.ws.readyState === WebSocket.CLOSED);
});

test('prewarm failures back off and stopping cannot resurrect scheduled work', async t => {
  const ctx = await fixture(t), instance = ctx.launched[0]; instance.child.exitCode = 1; instance.child.emit('exit', 1, null);
  await delay(70); assert.equal(ctx.launched.length, 1); assert.equal(ctx.service.status().warmBlockedReason, 'backoff');
  assert.equal(ctx.service.status().state, 'running', 'an unused spare failure must not claim an active user failed');
  await until(() => ctx.launched.length === 2); await ctx.service.stop(); await delay(200); assert.equal(ctx.launched.length, 2); assert.equal(ctx.service.status().instances.length, 0);
});

test('a connected spare that never finishes PSO warmup expires without degrading active service', async t => {
  const ctx = await fixture(t, {}, { startupTimeoutMs: 150 }), instance = ctx.launched[0];
  ctx.autoAck(instance, { psoActivePrecacheRequests: 4 }); await identify(instance);
  await until(() => ctx.service.status().instances.length === 0);
  assert.equal(ctx.service.status().state, 'running'); assert.equal(ctx.service.status().warmBlockedReason, 'backoff');
});

test('resource guards permit the first empty pool but do not replenish from unknown telemetry or low memory', async t => {
  const ctx = await fixture(t), instance = ctx.launched[0], client = await viewer(ctx); await identify(instance); ctx.autoAck(instance, { gpuMs: null });
  await firstFrame(ctx, client);
  await until(() => ctx.service.status().instances[0].state === 'ready'); await delay(80); assert.equal(ctx.launched.length, 1); assert.equal(ctx.service.status().warmBlockedReason, 'unknown-metrics');
  ctx.autoAck(instance); ctx.setResources({ ...memory, freeMemoryBytes: 1024 ** 3 }); await delay(70); assert.equal(ctx.launched.length, 1);
  ctx.setResources(memory); await until(() => ctx.launched.length === 2); assert.ok(client.admission);
});

test('stale standby telemetry is never counted as a warm hit and failed activation cannot expose a 5-FPS stream', async t => {
  const ctx = await fixture(t, { maxViewers: 1 }, { activationTimeoutMs: 100 }), { instance } = await readyPool(ctx);
  ctx.telemetry.set(instance.dir, ctx.sample(instance, { receivedAt: Date.now() - 6000 }));
  const client = await viewer(ctx); assert.equal(client.admission.warmHit, false);
  await until(() => client.messages.some(m => m.type === 'ghsInstanceFailed')); assert.equal(client.messages.some(m => m.type === 'ghsStage' && m.stage === 'streamerReady'), false);
  assert.equal(ctx.service.status().instances[0].state, 'failed');
});

test('a failed active-budget write discards the spare and admits a clean demand instance without leaving an orphan', async t => {
  const ctx = await fixture(t, { maxViewers: 1 }), { instance } = await readyPool(ctx);
  fs.mkdirSync(path.join(instance.dir, 'budget.json.tmp'));
  const client = await viewer(ctx);
  assert.ok(client.admission, 'an unusable spare must fall back to normal admission');
  assert.equal(client.admission.warmHit, false); assert.notEqual(client.admission.instanceId, instance.id);
  await until(() => ctx.launched.length === 2);
  assert.equal(ctx.launched[1].id, client.admission.instanceId);
  assert.equal(ctx.service.status().instances.some(i => i.id === instance.id), false);
});

test('five total processes include the idle spare; its first owner receives the fifth slot without starting a sixth UE', async t => {
  const ctx = await fixture(t, { maxViewers: 5 });
  for (let i = 0; i < 4; i++) {
    const instance = ctx.launched[i]; await identify(instance); ctx.autoAck(instance);
    await until(() => ctx.service.status().warmReadyCount === 1);
    const client = await viewer(ctx); assert.equal(client.admission.warmHit, true);
    await firstFrame(ctx, client);
    await until(() => ctx.launched.length === i + 2);
  }
  const last = ctx.launched[4]; await identify(last); ctx.autoAck(last); await until(() => ctx.service.status().warmReadyCount === 1);
  assert.equal(ctx.service.status().viewerCount, 4); assert.equal(ctx.service.status().instances.length, 5);
  const fifth = await viewer(ctx); assert.equal(fifth.admission.instanceId, last.id); assert.equal(fifth.admission.warmHit, true);
  const sixth = await viewer(ctx); assert.equal(sixth.admission, undefined); assert.ok(sixth.messages.some(m => m.type === 'ghsFull'));
  await delay(80); assert.equal(ctx.launched.length, 5); assert.equal(ctx.service.status().warmStartingCount, 0);
});

test('resource admission is conservative without reducing existing user render budgets', () => {
  assert.equal(typeof standbyHeadroom, 'function');
  assert.equal(standbyHeadroom([], memory, 1000).allowed, true);
  const good = { receivedAt: 1000, appliedFps: 30, actualFps: 30, gpuMs: 3 };
  const capacity = { ...memory, gpuReceivedAt: 1000 };
  assert.equal(standbyHeadroom([good], capacity, 1000).allowed, true);
  for (const sample of [null, { ...good, gpuMs: null }, { ...good, receivedAt: -5000 }, { ...good, actualFps: 10 }, { ...good, gpuMs: 40 }]) assert.equal(standbyHeadroom([sample], memory, 1000).allowed, false);
  assert.equal(standbyHeadroom([], { ...memory, freeMemoryBytes: 1024 ** 3 }, 1000).allowed, false);
  for (const resources of [{ ...capacity, gpuFreeMiB: 2048 }, { ...capacity, gpuReceivedAt: -25000 }, { ...capacity, gpuFreeMiB: undefined }]) assert.equal(standbyHeadroom([good], resources, 1000).allowed, false);
  assert.equal(standbyHeadroom([], { ...capacity, gpuFreeMiB: 1024 }, 1000).allowed, false);
  assert.equal(standbyHeadroom([], { ...capacity, gpuFreeMiB: undefined }, 1000).allowed, true);
});

test('known low VRAM blocks an empty pool and retires an unused idle spare after sustained pressure', async t => {
  const low = { ...memory, gpuFreeMiB: 1024 }, blocked = await fixture(t, {}, { resourceSnapshot: () => low });
  await delay(60); assert.equal(blocked.launched.length, 0); assert.equal(blocked.service.status().warmBlockedReason, 'resources');
  const ctx = await fixture(t); await readyPool(ctx); ctx.setResources(low);
  await until(() => ctx.service.status().instances.length === 0);
  await delay(180); assert.equal(ctx.launched.length, 1); assert.equal(ctx.service.status().warmBlockedReason, 'resources');
});

test('replenishment waits for an authenticated subscribed first frame and a short quiet interval', async t => {
  const ctx = await fixture(t), { instance } = await readyPool(ctx), client = await viewer(ctx); ctx.autoAck(instance);
  await until(() => ctx.service.status().instances[0].state === 'ready');
  await delay(80); assert.equal(ctx.launched.length, 1); assert.equal(ctx.service.status().warmBlockedReason, 'first-frame');
  client.ws.send(JSON.stringify(frameReport)); await delay(50);
  assert.equal(ctx.service.status().viewers[0].firstFrameReceived, false, 'an unsubscribed client cannot trigger background startup');
  await firstFrame(ctx, client); assert.equal(ctx.launched.length, 1);
  await until(() => ctx.launched.length === 2);
  client.ws.send(JSON.stringify(frameReport)); await delay(40);
  assert.equal(ctx.service.status().logs.filter(l => l.includes('phase=firstFrame')).length, 1);
});

test('idle spare is retired only after sustained resource pressure and is not immediately recreated', async t => {
  const ctx = await fixture(t), { instance } = await readyPool(ctx), client = await viewer(ctx); ctx.autoAck(instance); await firstFrame(ctx, client);
  await until(() => ctx.launched.length === 2); const spare = ctx.launched[1]; await identify(spare); ctx.autoAck(spare); await until(() => ctx.service.status().warmReadyCount === 1);
  ctx.setResources({ ...memory, gpuFreeMiB: 1024 }); await delay(25); assert.equal(ctx.service.status().instances.length, 2);
  ctx.setResources(memory); await delay(60); assert.equal(ctx.service.status().instances.length, 2);
  ctx.setResources({ ...memory, gpuFreeMiB: 1024 }); await until(() => ctx.service.status().instances.length === 1);
  await delay(100); assert.equal(ctx.launched.length, 2); assert.equal(ctx.service.status().instances[0].id, instance.id);
});

test('unsubscribe starts a fresh media gate while duplicate subscribe preserves the current first frame', async t => {
  const ctx = await fixture(t), { instance, signal } = await readyPool(ctx), client = await viewer(ctx); ctx.autoAck(instance);
  ctx.setResources({ ...memory, gpuFreeMiB: 1024 }); await firstFrame(ctx, client); await delay(60);
  client.ws.send(JSON.stringify({ type: 'subscribe', streamerId: instance.id })); await delay(30);
  assert.equal(ctx.service.status().viewers[0].firstFrameReceived, true);
  assert.equal(signal.messages.filter(m => m.type === 'playerConnected').length, 1);
  client.ws.send(JSON.stringify({ type: 'unsubscribe' })); await until(() => signal.messages.some(m => m.type === 'playerDisconnected'));
  assert.equal(ctx.service.status().viewers[0].firstFrameReceived, false);
  client.ws.send(JSON.stringify({ type: 'subscribe', streamerId: instance.id }));
  await until(() => signal.messages.filter(m => m.type === 'playerConnected').length === 2);
  ctx.setResources(memory); await delay(80);
  assert.equal(ctx.launched.length, 1); assert.equal(ctx.service.status().warmBlockedReason, 'first-frame');
  client.ws.send(JSON.stringify({ ...frameReport, attemptId: 2 }));
  await until(() => ctx.launched.length === 2);
  assert.equal(ctx.service.status().logs.filter(l => l.includes('phase=firstFrame')).length, 2);
});

test('UE signalling reconnect on the same viewer socket cannot reuse the previous media first frame', async t => {
  const ctx = await fixture(t), { instance, signal } = await readyPool(ctx), client = await viewer(ctx); ctx.autoAck(instance);
  ctx.setResources({ ...memory, gpuFreeMiB: 1024 }); await firstFrame(ctx, client); await delay(60);
  signal.ws.close(); await until(() => ctx.service.status().instances[0].state === 'reconnecting');
  assert.equal(ctx.service.status().viewers[0].firstFrameReceived, false);
  const replacement = await identify(instance);
  client.ws.send(JSON.stringify({ type: 'subscribe', streamerId: instance.id }));
  await until(() => replacement.messages.some(m => m.type === 'playerConnected'));
  ctx.setResources(memory); await delay(80);
  assert.equal(ctx.launched.length, 1); assert.equal(ctx.service.status().warmBlockedReason, 'first-frame');
  assert.equal(client.ws.readyState, WebSocket.OPEN);
  client.ws.send(JSON.stringify({ ...frameReport, attemptId: 2 })); await until(() => ctx.launched.length === 2);
  assert.equal(ctx.service.status().logs.filter(l => l.includes('phase=firstFrame')).length, 2);
});
