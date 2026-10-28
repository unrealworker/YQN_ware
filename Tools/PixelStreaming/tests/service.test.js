'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const net = require('node:net');
const { spawn } = require('node:child_process');
const { once, EventEmitter } = require('node:events');
const path = require('node:path');
const fs = require('node:fs');
const WebSocket = require('ws');
const { createService, validateConfig, buildUEArgs } = require('../server/service');

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, ms = 5000) { const start = Date.now(); while (!fn()) { if (Date.now() - start > ms) throw Error('Timed out'); await delay(20); } }
async function freePort() { const s = net.createServer(); s.listen(0, '127.0.0.1'); await once(s, 'listening'); const p = s.address().port; await new Promise(r => s.close(r)); return p; }
const token = 'test-control-token-01234567890123456789';
async function setup(t, mode = 'shared', observedExitDelayMs = 0, extra = {}) {
  const config = { executablePath: process.execPath, httpPort: await freePort(), streamerPort: await freePort(), mode, showWindow: false, width: 1920, height: 1080, fps: 60, ...extra };
  const children = [], streamerUrls = [];
  const service = createService(config, { token, reconnectGraceMs: 60, spawnProcess(exe, args, opts) {
    assert.equal(opts.shell, false); assert.equal(exe, process.execPath);
    const id = args.find(x => x.startsWith('-PixelStreamingID=')).split('=')[1];
    const streamerUrl = args.find(x => x.startsWith('-PixelStreamingURL=')).slice('-PixelStreamingURL='.length); streamerUrls.push(streamerUrl);
    const child = spawn(process.execPath, [path.join(__dirname, 'mock-ue.js'), streamerUrl, id], { stdio: 'ignore', windowsHide: true });
    children.push(child);
    if (!observedExitDelayMs) return child;
    // A delayed exit notification makes cleanup/admission queue interleaving deterministic.
    const observed = new EventEmitter(); observed.pid = child.pid; observed.exitCode = null; observed.signalCode = null; observed.kill = signal => child.kill(signal);
    child.on('exit', (code, signal) => setTimeout(() => { observed.exitCode = code; observed.signalCode = signal; observed.emit('exit', code, signal); }, observedExitDelayMs));
    child.on('error', e => observed.emit('error', e)); return observed;
  } });
  await service.start();
  t.after(async () => { await service.stop(); for (const p of children) assert.ok(p.exitCode !== null || p.signalCode !== null, 'owned child must be reaped'); });
  return { service, config, children, streamerUrls, base: `http://127.0.0.1:${config.httpPort}` };
}
async function viewer(ctx, resume, fields = {}) {
  const response = await fetch(ctx.base + '/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(resume ? { token: resume } : fields) });
  assert.equal(response.status, 200); const session = await response.json();
  const ws = new WebSocket(ctx.base.replace('http:', 'ws:') + '/ws?token=' + session.token);
  const messages = []; let close;
  ws.on('message', m => messages.push(JSON.parse(m))); ws.on('close', (code, reason) => { close = { code, reason: String(reason) }; });
  await once(ws, 'open');
  return { ws, messages, token: session.token, get close() { return close; } };
}

async function startupQueueFixture(t, failStartAt = 0) {
  const launched = []; let starts = 0;
  const config = { executablePath: process.execPath, httpPort: await freePort(), streamerPort: await freePort(), mode: 'independent', fps: 0 };
  const service = createService(config, { token, reconnectGraceMs: 60, spawnProcess(_exe, args) {
    if (++starts === failStartAt) throw Error('fixture spawn rejected');
    const child = new EventEmitter(); child.pid = null; child.exitCode = null; child.signalCode = null;
    launched.push({ child, id: args.find(a => a.startsWith('-PixelStreamingID=')).slice('-PixelStreamingID='.length), url: args.find(a => a.startsWith('-PixelStreamingURL=')).slice('-PixelStreamingURL='.length), directory: args.find(a => a.startsWith('-GHSStreamControlDir=')).slice('-GHSStreamControlDir='.length) });
    return child;
  } });
  await service.start(); t.after(() => service.stop());
  return { service, launched, base: `http://127.0.0.1:${config.httpPort}` };
}
async function acknowledgeStartup(instance) {
  const ws = new WebSocket(instance.url);
  ws.on('message', bytes => { if (JSON.parse(bytes).type === 'identify') ws.send(JSON.stringify({ type: 'endpointId', id: instance.id })); });
  await once(ws, 'open'); return ws;
}

test('startup queue starts one UE at a time and a cancelled waiting user never spawns', async t => {
  const ctx = await startupQueueFixture(t);
  const a = await viewer(ctx), b = await viewer(ctx), c = await viewer(ctx);
  await until(() => ctx.service.status().instances.length === 3);
  assert.equal(ctx.launched.length, 1, 'initialization must not overlap before streamer readiness');
  assert.equal(ctx.service.status().instances.filter(i => i.state === 'queued').length, 2);
  await until(() => c.messages.some(m => m.type === 'ghsStage'));
  assert.deepEqual(a.messages.filter(m => m.type === 'ghsStage').map(m => m.stage), ['waitingStreamer']);
  assert.deepEqual(c.messages.filter(m => m.type === 'ghsStage').map(m => m.stage), ['queued']);
  b.ws.close(); await until(() => ctx.service.status().instances.length === 2);
  assert.equal(ctx.launched.length, 1, 'closing a queued user must not start a UE');
  await acknowledgeStartup(ctx.launched[0]); await until(() => ctx.launched.length === 2);
  const cid = c.messages.find(m => m.type === 'ghsAdmission').instanceId;
  assert.equal(ctx.launched[1].id, cid);
  await until(() => c.messages.some(m => m.type === 'ghsStage' && m.stage === 'waitingStreamer'));
  assert.deepEqual(c.messages.filter(m => m.type === 'ghsStage').map(m => m.stage), ['queued', 'waitingStreamer']);
  await acknowledgeStartup(ctx.launched[1]); await until(() => ctx.service.status().instances.every(i => i.state === 'ready'));
  assert.ok(ctx.service.status().instances.every(i => i.targetFps === 0));
  for (const instance of ctx.launched) assert.equal(JSON.parse(fs.readFileSync(path.join(instance.directory, 'budget.json'), 'utf8')).fps, 0);
  assert.equal(a.close, undefined);
});

test('startup failure releases the next queued instance and service stop does not launch waiting work', async t => {
  const ctx = await startupQueueFixture(t);
  await viewer(ctx); await viewer(ctx); await viewer(ctx);
  await until(() => ctx.service.status().instances.length === 3);
  assert.equal(ctx.launched.length, 1);
  ctx.launched[0].child.exitCode = 1; ctx.launched[0].child.emit('exit', 1, null);
  await until(() => ctx.launched.length === 2);
  assert.equal(ctx.service.status().instances.filter(i => i.state === 'queued').length, 1);
  await ctx.service.stop(); assert.equal(ctx.launched.length, 2, 'stop must not drain waiting work by spawning it');
});

test('readiness keeps degraded status when releasing the startup slot synchronously fails the next spawn', async t => {
  const ctx = await startupQueueFixture(t, 2);
  await viewer(ctx); await viewer(ctx);
  await until(() => ctx.service.status().instances.length === 2);
  await acknowledgeStartup(ctx.launched[0]);
  await until(() => ctx.service.status().instances.some(i => i.state === 'failed'));
  const status = ctx.service.status();
  assert.deepEqual(status.instances.map(i => i.state), ['ready', 'failed']);
  assert.equal(status.state, 'degraded');
  assert.match(status.message, /fixture spawn rejected/);
});

test('a later ready instance cannot hide an existing failed instance or its failure explanation', async t => {
  const ctx = await startupQueueFixture(t);
  await viewer(ctx); await viewer(ctx);
  await until(() => ctx.service.status().instances.length === 2);
  ctx.launched[0].child.exitCode = 1; ctx.launched[0].child.emit('exit', 1, null);
  await until(() => ctx.launched.length === 2);
  const failedMessage = ctx.service.status().message;
  await acknowledgeStartup(ctx.launched[1]);
  await until(() => ctx.service.status().instances.some(i => i.state === 'ready'));
  assert.deepEqual(ctx.service.status().instances.map(i => i.state), ['failed', 'ready']);
  assert.equal(ctx.service.status().state, 'degraded');
  assert.equal(ctx.service.status().message, failedMessage);
});

test('configuration rejects invalid ports, dimensions and bitrate order; UE arguments preserve resolution and local media ports', () => {
  const cfg = { executablePath: process.execPath, httpPort: 8080, streamerPort: 8888 };
  assert.throws(() => validateConfig({ ...cfg, httpPort: 0 }), /端口/);
  assert.throws(() => validateConfig({ ...cfg, streamerPort: 8080 }), /不同/);
  assert.throws(() => validateConfig({ ...cfg, width: -5 }), /分辨率/);
  assert.throws(() => validateConfig({ ...cfg, startBitrateMbps: 90 }), /码率/);
  const args = buildUEArgs(validateConfig(cfg), 'shared');
  assert.ok(args.includes('-ResX=1920')); assert.ok(args.includes('-RenderOffscreen'));
  assert.ok(args.includes('-PixelStreamingWebRTCMinPort=50000'));
  assert.ok(args.includes('-PixelStreamingWebRTCMaxPort=50199'));
  assert.ok(args.includes('-PixelStreamingEncoderPreset=HIGH_QUALITY'));
  assert.ok(args.includes('-PixelStreamingEncoderMaxQP=32'));
  assert.ok(args.some(x => x.includes('r.ScreenPercentage 100') && x.includes('r.DynamicRes.OperationMode 0')));
  assert.ok(buildUEArgs(validateConfig({ ...cfg, qualityProfile: 'ultra' }), 'shared').includes('-PixelStreamingEncoderMaxQP=28'));
  for (const qualityProfile of ['balanced', 'custom']) assert.ok(buildUEArgs(validateConfig({ ...cfg, qualityProfile }), 'shared').includes('-PixelStreamingEncoderMaxQP=36'));
  assert.equal(args.some(a => a.includes('EncoderTargetBitrate')), false, 'congestion controller must retain bitrate control');
  assert.throws(() => validateConfig({ ...cfg, qualityProfile: 'unknown' }), /画质/);
  assert.throws(() => validateConfig({ ...cfg, adaptiveResourceBudget: 'true' }), /布尔/);
});

test('unlimited configuration uses an explicit zero frame cap and accepts a low congestion floor', () => {
  const cfg = { executablePath: process.execPath, httpPort: 8080, streamerPort: 8888, fps: 0, minBitrateMbps: 1, startBitrateMbps: 8, maxBitrateMbps: 20 };
  const result = validateConfig(cfg);
  assert.equal(result.fps, 0);
  assert.equal(result.minBitrateMbps, 1);
  for (const fps of [-1, 0.5, 1, 14, 121, 300]) assert.throws(() => validateConfig({ ...cfg, fps }), /帧率/);
});

test('defaults allow WebRTC congestion adaptation while explicit existing quality budgets remain intact', () => {
  const cfg = { executablePath: process.execPath, httpPort: 8080, streamerPort: 8888 };
  const defaults = validateConfig(cfg);
  assert.deepEqual([defaults.fps, defaults.minBitrateMbps, defaults.startBitrateMbps, defaults.maxBitrateMbps], [0, 1, 8, 24]);
  const existing = validateConfig({ ...cfg, fps: 60, minBitrateMbps: 12, startBitrateMbps: 35, maxBitrateMbps: 60, qualityProfile: 'custom' });
  assert.deepEqual([existing.fps, existing.minBitrateMbps, existing.startBitrateMbps, existing.maxBitrateMbps], [60, 12, 35, 60]);
});

test('new and resumed public sessions expose the exact launcher SDP bitrate budget', async t => {
  const ctx = await setup(t, 'independent', 0, { minBitrateMbps: 1.25, startBitrateMbps: 5.5, maxBitrateMbps: 15.75 });
  let session;
  for (let attempt = 0; attempt < 2; attempt++) {
    const response = await fetch(ctx.base + '/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(session ? { token: session.token } : {}) });
    assert.equal(response.status, 200); session = await response.json();
    assert.deepEqual([session.minBitrateMbps, session.startBitrateMbps, session.maxBitrateMbps], [1.25, 5.5, 15.75]);
    assert.equal(session.accessCode, undefined);
  }
});

test('unlimited launch removes render and capture caps without forcing queued frames or a fake high ceiling', () => {
  const config = validateConfig({ executablePath: process.execPath, httpPort: 8080, streamerPort: 8888, fps: 0 });
  const args = buildUEArgs(config, 'shared');
  assert.ok(args.includes('-NoVSync'));
  assert.ok(args.includes('-GHSLowLatencyPlayout'));
  assert.ok(args.includes('-PixelStreamingWebRTCFps=0'));
  const commands = args.find(a => a.startsWith('-ExecCmds=')).slice('-ExecCmds='.length).split(',');
  assert.ok(commands.includes('t.MaxFPS 0'));
  assert.ok(commands.includes('r.VSync 0'));
  assert.ok(commands.includes('PixelStreaming.DecoupleFramerate 0'));
  assert.equal(args.some(a => /DisableFrameDropper|UseFixedTimeStep|FixedFrameRate/.test(a)), false);
  assert.ok(args.includes('-PixelStreamingWebRTCMinBitrate=1000000'));
});

test('ten viewers share one UE; eleventh is rejected without disconnecting admitted users', async t => {
  const ctx = await setup(t); const active = [];
  await until(() => ctx.service.status().instances.some(x => x.state === 'ready'));
  for (let i = 0; i < 10; i++) active.push(await viewer(ctx));
  await until(() => ctx.service.status().viewerCount === 10);
  active[0].ws.send(JSON.stringify({ type: 'subscribe', streamerId: 'shared' }));
  await until(() => active[0].messages.some(x => x.type === 'offer'));
  active[0].ws.send(JSON.stringify({ type: 'answer', sdp: 'answer-from-browser' }));
  await until(() => active[0].messages.some(x => x.type === 'iceCandidate' && x.candidate.candidate === 'answer-received'));
  const rejected = await viewer(ctx); await until(() => rejected.close);
  assert.equal(rejected.close.code, 4004); assert.ok(rejected.messages.some(x => x.type === 'ghsFull' && x.reconnect === false));
  assert.equal(ctx.service.status().viewerCount, 10); assert.equal(ctx.children.length, 1);
  assert.equal(ctx.service.status().instances[0].targetFps, 60);
  assert.ok(active.every(v => !v.close));
});

test('independent admission preserves configured targets until measured pressure and never restarts survivors', async t => {
  const ctx = await setup(t, 'independent'); const a = await viewer(ctx);
  await until(() => ctx.service.status().instances.length === 1);
  const firstPid = ctx.service.status().instances[0].pid;
  assert.equal(ctx.service.status().instances[0].targetFps, 60);
  const b = await viewer(ctx); await until(() => ctx.service.status().instances.length === 2);
  assert.deepEqual(ctx.service.status().instances.map(x => x.targetFps), [60, 60]);
  const c = await viewer(ctx); await until(() => ctx.service.status().instances.length === 3);
  assert.deepEqual(ctx.service.status().instances.map(x => x.targetFps), [60, 60, 60]);
  await until(() => ctx.service.status().instances.filter(x => x.state === 'ready').length === 3);
  b.ws.close(); c.ws.close(); await until(() => ctx.service.status().instances.length === 1);
  assert.equal(ctx.service.status().instances[0].targetFps, 60);
  assert.equal(ctx.service.status().instances[0].pid, firstPid);
  assert.equal(ctx.children.length, 3, 'budget update must not restart a surviving scene');
  assert.equal(a.close, undefined);
});

test('independent viewers are routed only to owned streamers and disconnect frees their real process', async t => {
  const ctx = await setup(t, 'independent');
  assert.equal(ctx.children.length, 0);
  const a = await viewer(ctx); const b = await viewer(ctx);
  await until(() => ctx.service.status().instances.filter(x => x.state === 'ready').length === 2);
  a.ws.send(JSON.stringify({ type: 'listStreamers' })); b.ws.send(JSON.stringify({ type: 'listStreamers' }));
  await until(() => a.messages.some(x => x.type === 'streamerList' && x.ids.length) && b.messages.some(x => x.type === 'streamerList' && x.ids.length));
  const aid = a.messages.findLast(x => x.type === 'streamerList').ids[0];
  const bid = b.messages.findLast(x => x.type === 'streamerList').ids[0];
  assert.notEqual(aid, bid);
  a.ws.send(JSON.stringify({ type: 'subscribe', streamerId: bid })); await delay(40);
  assert.equal(a.messages.some(x => x.type === 'offer'), false);
  a.ws.send(JSON.stringify({ type: 'subscribe', streamerId: aid }));
  await until(() => a.messages.some(x => x.type === 'offer'));
  a.ws.close(); await until(() => ctx.service.status().instances.length === 1);
  assert.equal(ctx.service.status().viewerCount, 1);
});

test('loopback control requires bearer token; static traversal and public management routes are unavailable', async t => {
  const ctx = await setup(t);
  const base = `http://127.0.0.1:${ctx.service.controlPort}`;
  assert.equal((await fetch(base + '/status')).status, 401);
  assert.equal((await fetch(base + '/status', { headers: { Authorization: 'Bearer wrong' } })).status, 401);
  const status = await fetch(base + '/status', { headers: { Authorization: 'Bearer ' + token } });
  assert.equal(status.status, 200); assert.equal((await status.json()).maxViewers, 10);
  assert.equal((await fetch(ctx.base + '/status')).status, 404);
  assert.equal((await fetch(ctx.base + '/%2e%2e%2fserver%2fservice.js')).status, 404);
  assert.equal((await fetch(ctx.base + '/api/session', { method: 'POST', headers: { Origin: 'http://evil.example' }, body: '{}' })).status, 403);
  assert.equal((await fetch(ctx.base + '/health')).status, 200);
});

test('occupied streamer port rolls back all listeners and starts no UE', async t => {
  const occupied = net.createServer(); occupied.listen(0, '127.0.0.1'); await once(occupied, 'listening');
  t.after(() => new Promise(r => occupied.close(r)));
  const httpPort = await freePort();
  const service = createService({ executablePath: process.execPath, httpPort, streamerPort: occupied.address().port }, { token, spawnProcess() { assert.fail('must not spawn'); } });
  await assert.rejects(service.start(), /端口|EADDRINUSE/);
  const probe = net.createServer(); probe.listen(httpPort, '127.0.0.1'); await once(probe, 'listening'); await new Promise(r => probe.close(r));
});

test('unexpected UE exit is visible to viewer/status and owned children are cleaned by stop', async t => {
  const ctx = await setup(t); const a = await viewer(ctx);
  await until(() => ctx.service.status().instances[0]?.state === 'ready');
  ctx.children[0].kill();
  await until(() => ctx.service.status().instances[0]?.state === 'failed');
  await until(() => a.messages.some(x => x.type === 'ghsInstanceFailed'));
  assert.match(ctx.service.status().message, /退出|失败/);
  await ctx.service.stop(); assert.equal(ctx.service.status().state, 'stopped');
});

async function disconnect(ctx, playerId, authorization = token) {
  return fetch(`http://127.0.0.1:${ctx.service.controlPort}/disconnect`, { method: 'POST', headers: { Authorization: 'Bearer ' + authorization, 'Content-Type': 'application/json' }, body: JSON.stringify({ playerId }) });
}
test('reconnect replaces only the same session socket without increasing count', async t => {
  const ctx = await setup(t); const a = await viewer(ctx); const b = await viewer(ctx);
  const restored = await viewer(ctx, a.token); await until(() => a.close);
  assert.equal(a.close.code, 4002); assert.equal(ctx.service.status().viewerCount, 2);
  assert.equal(restored.close, undefined); assert.equal(b.close, undefined);
});
test('administrator disconnect revokes resume token, reaps only owned UE and permits explicit fresh entry', async t => {
  const ctx = await setup(t, 'independent'); const a = await viewer(ctx, null, { displayName: '张工' }); const b = await viewer(ctx);
  await until(() => ctx.service.status().instances.filter(x => x.state === 'ready').length === 2);
  const row = ctx.service.status().viewers.find(x => x.displayName === '张工');
  assert.ok(row.address); assert.ok(Date.parse(row.connectedAt)); assert.equal(row.token, undefined);
  assert.equal((await disconnect(ctx, row.playerId, 'bad')).status, 401);
  assert.equal((await fetch(ctx.base + '/disconnect', { method: 'POST', body: '{}' })).status, 405);
  assert.equal((await disconnect(ctx, row.playerId)).status, 200); await until(() => a.close);
  assert.equal(a.close.code, 4003); assert.ok(a.messages.some(x => x.type === 'ghsKicked'));
  assert.equal(ctx.service.status().instances.length, 1); assert.equal(b.close, undefined);
  const denied = await viewer(ctx, a.token); await until(() => denied.close); assert.equal(denied.close.code, 4003);
  assert.equal((await disconnect(ctx, row.playerId)).status, 404);
  await viewer(ctx); await until(() => ctx.service.status().instances.length === 2);
  assert.equal(ctx.children.filter(p => p.exitCode === null && p.signalCode === null).length, 2);
});
test('independent concurrent admissions never exceed configured capacity and closing newcomers occupy no slot', async t => {
  const ctx = await setup(t, 'independent', 0, { maxViewers: 2 });
  await viewer(ctx); await viewer(ctx);
  const attempted = await Promise.all(Array.from({ length: 8 }, () => viewer(ctx)));
  await until(() => attempted.every(v => v.close));
  assert.ok(attempted.every(v => v.close.code === 4004));
  assert.ok(ctx.children.length <= 2); assert.equal(ctx.service.status().viewerCount, 2);
  await until(() => ctx.service.status().instances.filter(i => i.state === 'ready').length === 2);
  assert.equal(ctx.children.length, 2);
});
test('queued resume behind another manual cleanup retains its owned instance', async t => {
  const ctx = await setup(t, 'independent', 400); const a = await viewer(ctx); const b = await viewer(ctx);
  await until(() => ctx.service.status().instances.filter(x => x.state === 'ready').length === 2);
  const beforeId = b.messages.find(m => m.type === 'ghsAdmission').instanceId;
  const aid = a.messages.find(m => m.type === 'ghsAdmission').playerId;
  const kicking = disconnect(ctx, aid); b.ws.terminate(); await delay(10);
  const restored = await viewer(ctx, b.token); await kicking; await delay(600);
  assert.equal(restored.ws.readyState, WebSocket.OPEN); assert.equal(ctx.service.status().viewerCount, 1);
  assert.ok(ctx.service.status().instances.some(i => i.id === beforeId && i.state === 'ready'));
});

test('POST stop confirms cleanup and both ports can be reused immediately', async t => {
  const ctx = await setup(t); await until(() => ctx.service.status().instances[0]?.state === 'ready'); await viewer(ctx);
  const response = await fetch(`http://127.0.0.1:${ctx.service.controlPort}/stop`, { method: 'POST', headers: { Authorization: 'Bearer ' + token } });
  assert.equal(response.status, 200); await until(() => ctx.service.status().state === 'stopped');
  assert.ok(ctx.children.every(p => p.exitCode !== null || p.signalCode !== null));
  for (const port of [ctx.config.httpPort, ctx.config.streamerPort]) { const server = net.createServer(); server.listen(port, '127.0.0.1'); await once(server, 'listening'); await new Promise(r => server.close(r)); }
});

test('CLI handles Chinese and space config paths, refuses occupied port, and leaves no control file', async t => {
  const folder = fs.mkdtempSync(path.join(__dirname, '中文 空格-'));
  t.after(() => { assert.ok(path.resolve(folder).startsWith(path.resolve(__dirname) + path.sep)); fs.rmSync(folder, { recursive: true, force: true }); });
  const occupied = net.createServer(); occupied.listen(0, '127.0.0.1'); await once(occupied, 'listening'); t.after(() => new Promise(r => occupied.close(r)));
  const configFile = path.join(folder, '启动 配置.json'), controlFile = path.join(folder, '控制 状态.json');
  fs.writeFileSync(configFile, '\uFEFF' + JSON.stringify({ executablePath: process.execPath, httpPort: await freePort(), streamerPort: occupied.address().port }));
  const child = spawn(process.execPath, [path.resolve(__dirname, '../server/server.js'), '--config', configFile, '--control-file', controlFile], { shell: false, windowsHide: true, env: { ...process.env, GHS_CONTROL_TOKEN: token } });
  let stderr = ''; child.stderr.on('data', x => { stderr += x; }); const [code] = await once(child, 'exit');
  assert.equal(code, 1); assert.match(stderr, /端口.*EADDRINUSE/); assert.equal(fs.existsSync(controlFile), false);
});

test('JSON null/primitive/array and malformed message shapes cannot crash player or streamer handlers', async t => {
  const ctx = await setup(t);
  for (const bad of [null, [], 'text', 42, false, {}, { type: 7 }, { type: 'subscribe' }, { type: 'answer', sdp: 5 }, { type: 'iceCandidate', candidate: null }]) {
    const v = await viewer(ctx); v.ws.send(JSON.stringify(bad)); await until(() => v.close); assert.equal(v.close.code, 1007); await delay(80);
    const ws = new WebSocket(ctx.streamerUrls[0]); let closed;
    ws.on('close', code => { closed = code; }); await once(ws, 'open'); ws.send(JSON.stringify(bad)); await until(() => closed); assert.equal(closed, 1007);
    assert.equal((await fetch(ctx.base + '/health')).status, 200);
  }
});

test('access protection defaults off, requires an explicit boolean and validates codes only when enabled', () => {
  const base = { executablePath: process.execPath };
  assert.equal(validateConfig(base).accessProtectionEnabled, false);
  assert.equal(validateConfig({ ...base, accessCode: 'previously-saved-code' }).accessProtectionEnabled, false);
  assert.equal(validateConfig({ ...base, accessProtectionEnabled: false, accessCode: 'short' }).accessCode, 'short');
  for (const value of [undefined, null, 0, 1, 'false', 'true', [], {}]) {
    assert.throws(() => validateConfig({ ...base, accessProtectionEnabled: value }), /accessProtectionEnabled.*布尔/);
  }
  for (const networkMode of ['lan', 'public']) {
    const config = { ...base, networkMode, publicUrl: networkMode === 'public' ? 'http://warehouse.example' : '', accessProtectionEnabled: true };
    for (const accessCode of ['', '12345678901', '            ']) assert.throws(() => validateConfig({ ...config, accessCode }), /12/);
    assert.equal(validateConfig({ ...config, accessCode: '123456789012' }).accessProtectionEnabled, true);
  }
  assert.throws(() => validateConfig({ ...base, networkMode: 'public', accessProtectionEnabled: false }), /公网地址/);
  assert.throws(() => validateConfig({ ...base, networkMode: 'public', publicUrl: 'https://warehouse.example', accessProtectionEnabled: false }), /HTTPS/);
});

test('access protection disabled allows automatic LAN and public sessions even with a saved code', async t => {
  for (const networkMode of ['lan', 'public']) for (const accessCode of ['', 'previously-saved-code']) {
    const ctx = await setup(t, 'independent', 0, { networkMode, publicUrl: networkMode === 'public' ? 'http://warehouse.example' : '', accessCode });
    assert.equal((await (await fetch(ctx.base + '/health')).json()).accessRequired, false);
    for (const body of [{}, { accessCode: 'irrelevant-old-client-value' }]) {
      const response = await fetch(ctx.base + '/api/session', { method: 'POST', body: JSON.stringify(body) });
      assert.equal(response.status, 200, networkMode + ' should not request a code');
      const session = await response.json(); assert.match(session.token, /^[a-f0-9]{48}$/);
      assert.equal(session.accessCode, undefined);
    }
    assert.equal(ctx.service.status().accessProtectionEnabled, false);
    assert.equal(ctx.children.length, 0, 'session allocation alone never starts UE');
  }
});

test('access protection enabled gates LAN and public sessions and preserves authenticated resumption', async t => {
  for (const networkMode of ['lan', 'public']) {
    const ctx = await setup(t, 'independent', 0, { networkMode, publicUrl: networkMode === 'public' ? 'http://warehouse.example' : '', accessProtectionEnabled: true, accessCode: 'test-only-access-code' });
    const request = body => fetch(ctx.base + '/api/session', { method: 'POST', body: JSON.stringify(body) });
    assert.equal((await (await fetch(ctx.base + '/health')).json()).accessRequired, true);
    assert.equal(ctx.service.status().accessProtectionEnabled, true);
    for (const body of [{}, { accessCode: 'wrong' }]) {
      const response = await request(body); assert.equal(response.status, 401); assert.equal((await response.json()).accessRequired, true);
    }
    const response = await request({ accessCode: ctx.config.accessCode }); assert.equal(response.status, 200);
    const session = await response.json(); assert.equal(session.accessCode, undefined);
    assert.equal((await request({ token: session.token })).status, 200);
    assert.equal((await request({ token: 'forged-token' })).status, 409);
    assert.equal(ctx.children.length, 0);
  }
});

test('access protection disabled preserves session token and public Origin Host management and IP guards', async t => {
  const ctx = await setup(t, 'independent', 0, { networkMode: 'public', publicUrl: 'https://warehouse.example', externalTlsTermination: true, accessProtectionEnabled: false });
  // Node fetch normalizes Host; exercise the actual malformed HTTP Host on wire.
  const request = (body, headers = {}) => new Promise((resolve, reject) => {
    const req = require('node:http').request(ctx.base + '/api/session', { method: 'POST', headers, timeout: 5000 }, res => {
      let text = ''; res.on('data', chunk => { text += chunk; });
      res.on('end', () => resolve({ status: res.statusCode, json: async () => JSON.parse(text) }));
    });
    req.on('error', reject); req.on('timeout', () => req.destroy(Error('session request timeout'))); req.end(JSON.stringify(body));
  });
  assert.equal((await request({}, { Origin: 'https://evil.example' })).status, 403);
  assert.equal((await request({}, { Host: 'evil.example' })).status, 403);
  assert.equal((await request({ token: 'forged-token' })).status, 409);
  const response = await request({}); assert.equal(response.status, 200); const session = await response.json();
  for (const [sessionToken, origin] of [['forged-token', undefined], [session.token, 'https://evil.example']]) {
    const status = await new Promise((resolve, reject) => {
      const ws = new WebSocket(ctx.base.replace('http:', 'ws:') + '/ws?token=' + sessionToken, { origin, handshakeTimeout: 5000 });
      ws.on('unexpected-response', (_req, res) => { res.resume(); resolve(res.statusCode); ws.terminate(); });
      ws.on('error', () => {}); ws.on('open', () => { ws.terminate(); reject(Error('guard bypassed while access protection was disabled')); });
    });
    assert.equal(status, 403);
  }
  assert.equal((await fetch(ctx.base + '/status')).status, 404);
  const { clientAddress } = require('../server/network-policy');
  assert.equal(clientAddress({ socket: { remoteAddress: '10.0.0.10' }, headers: { 'x-forwarded-for': '203.0.113.123' } }, ctx.config), '10.0.0.10');
  assert.equal(ctx.children.length, 0);
});

test('access protection enabled retains LAN rate limiting', async t => {
  const ctx = await setup(t, 'independent', 0, { accessProtectionEnabled: true, accessCode: 'test-only-access-code' });
  for (let i = 0; i < 20; i++) assert.equal((await fetch(ctx.base + '/api/session', { method: 'POST', body: JSON.stringify({ accessCode: 'wrong' }) })).status, 401);
  assert.equal((await fetch(ctx.base + '/api/session', { method: 'POST', body: JSON.stringify({ accessCode: ctx.config.accessCode }) })).status, 429);
  assert.equal(ctx.children.length, 0);
});

test('public access gate, exact origins, private ICE and manual revocation work together', async t => {
  const ctx = await setup(t, 'independent', 0, { networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'http://warehouse.example:8080', accessCode: 'test-only-access-code', stunUrl: 'stun:stun.example:3478', turnUrl: 'turn:relay.example:3478?transport=udp', turnUsername: 'test-user', turnPassword: 'test-turn-secret' });
  const request = (body, headers = {}) => fetch(ctx.base + '/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
  assert.equal((await request({})).status, 401);
  assert.equal((await request({ accessCode: 'wrong' })).status, 401);
  assert.equal((await request({ accessCode: ctx.config.accessCode }, { Origin: 'http://evil.example' })).status, 403);
  const a = await viewer(ctx, null, { accessCode: ctx.config.accessCode, displayName: 'Alice' });
  await until(() => a.messages.some(m => m.type === 'config'));
  const ice = a.messages.find(m => m.type === 'config').peerConnectionOptions.iceServers;
  assert.equal(ice[1].credential, 'test-turn-secret'); assert.equal(ice[1].urls[0], ctx.config.turnUrl);
  const publicHealth = JSON.stringify(await (await fetch(ctx.base + '/health')).json());
  const control = JSON.stringify(ctx.service.status());
  for (const text of [publicHealth, control]) for (const sensitive of [a.token, ctx.config.accessCode, ctx.config.turnPassword, ctx.config.turnUrl]) assert.equal(text.includes(sensitive), false);
  assert.equal(ctx.service.status().viewers[0].displayName, 'Alice');
  const ua = await request({ token: a.token }); assert.equal(ua.status, 200);
  assert.equal((await disconnect(ctx, ctx.service.status().viewers[0].playerId)).status, 200);
  const revoked = await request({ token: a.token }); assert.equal((await revoked.json()).evicted, true);
});

test('public access attempts are bounded and invalid sessions never spawn a UE', async t => {
  const ctx = await setup(t, 'independent', 0, { networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'http://warehouse.example', accessCode: 'test-only-access-code' });
  for (let i = 0; i < 20; i++) assert.equal((await fetch(ctx.base + '/api/session', { method: 'POST', body: JSON.stringify({ accessCode: 'wrong' }) })).status, 401);
  assert.equal((await fetch(ctx.base + '/api/session', { method: 'POST', body: JSON.stringify({ accessCode: ctx.config.accessCode }) })).status, 429);
  assert.equal(ctx.children.length, 0);
});

test('network validation fails closed for malformed public origin, TLS and ICE settings', () => {
  const c = { executablePath: process.execPath };
  for (const fields of [{ maxViewers: 11 }, { maxViewers: 0 }, { networkMode: 'public' }, { networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'https://a.example', accessCode: 'long-enough-code' }, { publicUrl: 'http://user:password@a.example' }, { publicUrl: 'http://a.example/subpath' }, { tlsCertPath: 'missing' }, { turnUrl: 'http://relay' }, { turnUrl: 'turn:relay:3478' }, { stunUrl: 'stun:host:99999' }, { trustProxy: 'yes' }, { networkMode: 'lan', trustProxy: true }]) assert.throws(() => validateConfig({ ...c, ...fields }));
  assert.equal(validateConfig({ ...c, httpPort: 443 }).httpPort, 443);
  assert.equal(validateConfig({ ...c, networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'https://warehouse.example/', accessCode: 'long-enough-code', trustProxy: true }).publicUrl, 'https://warehouse.example');
});

test('trusted proxy only accepts client address from loopback and rejects cross-origin signalling', async t => {
  const { clientAddress, sameOrigin } = require('../server/network-policy');
  const c = { trustProxy: true, networkMode: 'public', publicUrl: 'https://warehouse.example', httpPort: 8080 };
  const req = { socket: { remoteAddress: '127.0.0.1' }, headers: { host: 'warehouse.example', origin: 'https://warehouse.example', 'x-forwarded-for': '1.1.1.1, 203.0.113.2' } };
  assert.equal(clientAddress(req, c), '203.0.113.2'); assert.equal(sameOrigin(req, c), true);
  req.socket.remoteAddress = '198.51.100.2'; assert.equal(clientAddress(req, c), '198.51.100.2');
  req.headers.origin = 'https://evil.example'; assert.equal(sameOrigin(req, c), false);
});

test('cloud TLS termination requires an exclusive public HTTPS arrangement and preserves old defaults', () => {
  const base = { executablePath: process.execPath };
  const cloud = { ...base, networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'https://warehouse.example/', accessCode: 'test-only-access-code', externalTlsTermination: true };
  assert.equal(validateConfig(base).externalTlsTermination, false);
  assert.equal(validateConfig(cloud).publicUrl, 'https://warehouse.example');
  for (const fields of [
    { networkMode: 'lan' }, { publicUrl: 'http://warehouse.example' },
    { trustProxy: true }, { externalTlsTermination: 'true' },
    { tlsCertPath: path.join(__dirname, 'fixtures/test-localhost-cert.pem'), tlsKeyPath: path.join(__dirname, 'fixtures/test-localhost-key.pem') },
  ]) assert.throws(() => validateConfig({ ...cloud, ...fields }), undefined, JSON.stringify(fields));
});

test('cloud HTTPS uses HTTP backhaul with exact public Host and Origin for sessions and websocket admission', async t => {
  const http = require('node:http');
  const os = require('node:os');
  const ctx = await setup(t, 'independent', 0, { networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'https://warehouse.example', accessCode: 'test-only-access-code', externalTlsTermination: true });
  // Use the actual local network interface when available: a loopback-only bind
  // would pass localhost tests but fail remote ALB connections.
  const host = Object.values(os.networkInterfaces()).flat().find(x => x.family === 'IPv4' && !x.internal)?.address || '127.0.0.1';
  const backhaul = `http://${host}:${ctx.config.httpPort}`;
  const headers = { Host: 'warehouse.example', Origin: 'https://warehouse.example', 'Content-Type': 'application/json', 'X-Forwarded-For': '203.0.113.123', 'X-Forwarded-Proto': 'https' };
  const request = (body, changed = {}) => new Promise((resolve, reject) => {
    const req = http.request(backhaul + '/api/session', { method: 'POST', headers: { ...headers, ...changed }, timeout: 5000 }, res => {
      let text = ''; res.on('data', b => text += b); res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(text) }));
    });
    req.on('error', reject); req.on('timeout', () => req.destroy(Error('HTTP backhaul timeout'))); req.end(JSON.stringify(body));
  });
  assert.equal((await request({})).status, 401);
  const body = { accessCode: ctx.config.accessCode, displayName: 'ALB guest' };
  assert.equal((await request(body, { Host: 'evil.example' })).status, 403);
  assert.equal((await request(body, { Origin: 'https://evil.example' })).status, 403);
  assert.equal((await request(body, { Origin: 'http://warehouse.example' })).status, 403);
  const session = await request(body); assert.equal(session.status, 200);
  const wsUrl = backhaul.replace('http:', 'ws:') + '/ws?token=' + session.body.token;
  for (const changed of [{ Host: 'evil.example' }, { Origin: 'https://evil.example' }]) {
    const code = await new Promise((resolve, reject) => {
      const denied = new WebSocket(wsUrl, { headers: { ...headers, ...changed }, handshakeTimeout: 5000 });
      denied.on('unexpected-response', (_req, res) => { res.resume(); resolve(res.statusCode); denied.terminate(); });
      denied.on('error', () => {}); denied.on('open', () => { denied.terminate(); reject(Error('invalid cloud origin was admitted')); });
    });
    assert.equal(code, 403);
  }
  const ws = new WebSocket(wsUrl, { headers, handshakeTimeout: 5000 });
  const messages = []; ws.on('message', b => messages.push(JSON.parse(b))); await once(ws, 'open');
  await until(() => messages.some(m => m.type === 'ghsAdmission'));
  assert.equal(ctx.service.status().externalTlsTermination, true);
  assert.equal(ctx.service.status().tlsEnabled, false);
  assert.equal(ctx.service.status().viewerCount, 1);
  assert.notEqual(ctx.service.status().viewers[0].address, '203.0.113.123', 'untrusted forwarded address must not become viewer identity');
  assert.deepEqual(ctx.service.status().urls, ['https://warehouse.example/']);
});

test('cloud TLS termination never trusts forwarded client addresses, even from loopback', () => {
  const { clientAddress, sameOrigin } = require('../server/network-policy');
  const config = validateConfig({ executablePath: process.execPath, networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'https://warehouse.example', accessCode: 'test-only-access-code', externalTlsTermination: true });
  const req = { socket: { remoteAddress: '10.0.0.10' }, headers: { host: 'warehouse.example', origin: 'https://warehouse.example', 'x-forwarded-for': '203.0.113.123', 'x-forwarded-host': 'warehouse.example' } };
  assert.equal(clientAddress(req, config), '10.0.0.10');
  req.socket.remoteAddress = '127.0.0.1'; assert.equal(clientAddress(req, config), '127.0.0.1');
  req.headers.host = 'evil.example'; assert.equal(sameOrigin(req, config), false);
});

async function cloudCodeRequest(ctx, accessCode, headers = {}) {
  const response = await fetch(ctx.base + '/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify({ accessCode }) });
  return { status: response.status, retryAfter: response.headers.get('retry-after'), body: await response.json() };
}

test('cloud authentication does not lock all ALB visitors after twenty wrong access codes', async t => {
  const ctx = await setup(t, 'independent', 0, { networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'https://warehouse.example', accessCode: 'test-only-access-code', externalTlsTermination: true });
  const started = performance.now();
  for (let i = 0; i < 20; i++) assert.equal((await cloudCodeRequest(ctx, 'wrong', { 'X-Forwarded-For': '203.0.113.20' })).status, 401);
  const legitimate = await cloudCodeRequest(ctx, ctx.config.accessCode, { 'X-Forwarded-For': '198.51.100.30' });
  assert.equal(legitimate.status, 200, 'a correct code from the same ALB peer must not inherit a five-minute lock');
  assert.ok(performance.now() - started >= 2000, 'wrong codes must consume the global five-per-second budget after the initial burst');
  assert.equal(ctx.children.length, 0);
});

test('cloud authentication throttles correct codes too and bounds excess pending requests', async t => {
  const ctx = await setup(t, 'independent', 0, { networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'https://warehouse.example', accessCode: 'test-only-access-code', externalTlsTermination: true });
  const started = performance.now();
  const results = await Promise.all(Array.from({ length: 31 }, () => cloudCodeRequest(ctx, ctx.config.accessCode)));
  const rejected = results.filter(x => x.status === 429);
  assert.ok(rejected.length >= 1, 'ten immediate attempts plus twenty queued attempts is the hard burst bound');
  assert.ok(rejected.every(x => x.retryAfter === '1'));
  assert.ok(results.filter(x => x.status === 200).length >= 29, 'the bounded FIFO must still drain legitimate queued logins');
  assert.ok(performance.now() - started >= 3700, 'correct codes cannot bypass the sustained rate limit');
  assert.ok(performance.now() - started < 5000, 'queued requests expire within four seconds, with scheduling tolerance');
  assert.equal(ctx.children.length, 0);
});

test('cloud authentication stop settles pending requests', async t => {
  const ctx = await setup(t, 'independent', 0, { networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'https://warehouse.example', accessCode: 'test-only-access-code', externalTlsTermination: true });
  await Promise.all(Array.from({ length: 10 }, () => cloudCodeRequest(ctx, ctx.config.accessCode)));
  let settled = false;
  const waiting = cloudCodeRequest(ctx, ctx.config.accessCode).then(value => { settled = true; return value; });
  await delay(40);
  assert.equal(settled, false, 'an exhausted burst must queue even a correct access code');
  await ctx.service.stop();
  assert.equal((await waiting).status, 503);
});

test('cloud authentication releases queue capacity when clients disconnect', async t => {
  const ctx = await setup(t, 'independent', 0, { networkMode: 'public', accessProtectionEnabled: true, publicUrl: 'https://warehouse.example', accessCode: 'test-only-access-code', externalTlsTermination: true });
  await Promise.all(Array.from({ length: 10 }, () => cloudCodeRequest(ctx, ctx.config.accessCode)));
  const controllers = Array.from({ length: 20 }, () => new AbortController());
  let completed = 0;
  const waiting = controllers.map(controller => fetch(ctx.base + '/api/session', { method: 'POST', signal: controller.signal, body: JSON.stringify({ accessCode: ctx.config.accessCode }) }).then(response => { completed++; return response.text(); }).catch(() => {}));
  await delay(40);
  assert.equal(completed, 0, 'queued clients must not be validated before a permit exists');
  controllers.forEach(controller => controller.abort()); await Promise.all(waiting); await delay(40);
  assert.equal((await cloudCodeRequest(ctx, ctx.config.accessCode)).status, 200, 'abandoned requests must not keep the queue full');
});

// These self-signed PEM files exist only for loopback transport tests, never the delivery.
test('native HTTPS performs a verified TLS handshake and accepts WSS with authenticated admission', async t => {
  const https = require('node:https');
  const config = { executablePath: process.execPath, httpPort: await freePort(), streamerPort: await freePort(), mode: 'independent', networkMode: 'public', accessProtectionEnabled: true, accessCode: 'test-only-access-code', publicUrl: 'https://127.0.0.1', tlsCertPath: path.join(__dirname, 'fixtures/test-localhost-cert.pem'), tlsKeyPath: path.join(__dirname, 'fixtures/test-localhost-key.pem') };
  config.publicUrl = 'https://127.0.0.1:' + config.httpPort;
  const service = createService(config, { token, spawnProcess() { const child = new EventEmitter(); child.pid = null; child.exitCode = 0; return child; } });
  await service.start(); t.after(() => service.stop());
  const ca = fs.readFileSync(config.tlsCertPath);
  const session = await new Promise((resolve, reject) => {
    const req = https.request(config.publicUrl + '/api/session', { ca, method: 'POST', headers: { Origin: config.publicUrl, 'Content-Type': 'application/json' } }, res => { let text = ''; res.on('data', b => text += b); res.on('end', () => { assert.equal(res.statusCode, 200); resolve(JSON.parse(text)); }); });
    req.on('error', reject); req.end(JSON.stringify({ accessCode: config.accessCode }));
  });
  const ws = new WebSocket(config.publicUrl.replace('https:', 'wss:') + '/ws?token=' + session.token, { ca, origin: config.publicUrl });
  const messages = []; ws.on('message', b => messages.push(JSON.parse(b))); await once(ws, 'open');
  await until(() => messages.some(m => m.type === 'ghsAdmission')); assert.equal(service.status().viewerCount, 1); assert.equal(service.status().tlsEnabled, true);
  assert.equal((await disconnect({ service }, service.status().viewers[0].playerId)).status, 200);
  await until(() => ws.readyState === WebSocket.CLOSED);
});
test('streamer channel rejects browser origins and never releases ICE secrets before owned identity', async t => {
  let ownedUrl;
  const config = { executablePath: process.execPath, httpPort: await freePort(), streamerPort: await freePort(), mode: 'shared', turnUrl: 'turn:relay.example:3478', turnUsername: 'test-relay-user', turnPassword: 'test-private-relay-secret' };
  const service = createService(config, { token, spawnProcess(_exe, args) { ownedUrl = args.find(a => a.startsWith('-PixelStreamingURL=')).slice('-PixelStreamingURL='.length); const child = new EventEmitter(); child.pid = null; child.exitCode = 0; return child; } });
  await service.start(); t.after(() => service.stop());
  async function rejected(url, origin) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url, origin ? { origin } : undefined); ws.on('error', () => {});
      ws.on('unexpected-response', (_req, res) => { res.resume(); ws.terminate(); resolve(res.statusCode); });
      ws.on('open', () => { ws.terminate(); reject(Error('Untrusted streamer upgraded')); });
    });
  }
  assert.equal(await rejected(`ws://127.0.0.1:${config.streamerPort}`, 'https://evil.example'), 403);
  assert.equal(await rejected(ownedUrl, 'https://evil.example'), 403);
  assert.equal(await rejected(`ws://127.0.0.1:${config.streamerPort}`, 'http://127.0.0.1'), 403);
  const unknown = new WebSocket(ownedUrl, { origin: 'http://127.0.0.1' }); const unknownMessages = [];
  unknown.on('message', bytes => unknownMessages.push(JSON.parse(bytes))); await once(unknown, 'open');
  await until(() => unknownMessages.some(m => m.type === 'identify')); await delay(30);
  assert.equal(unknownMessages.some(m => m.type === 'config'), false);
  unknown.send(JSON.stringify({ type: 'endpointId', id: 'another-instance' })); const [closeCode] = await once(unknown, 'close'); assert.equal(closeCode, 1008);
  assert.equal(JSON.stringify(unknownMessages).includes(config.turnPassword), false);
  const owned = new WebSocket(ownedUrl, { origin: 'http://127.0.0.1' }); const messages = [];
  owned.on('message', bytes => { const m = JSON.parse(bytes); messages.push(m); if (m.type === 'identify') owned.send(JSON.stringify({ type: 'endpointId', id: 'shared' })); });
  await once(owned, 'open'); await until(() => messages.some(m => m.type === 'config'));
  assert.equal(messages.find(m => m.type === 'config').peerConnectionOptions.iceServers[0].credential, config.turnPassword);
  assert.equal(service.status().instances[0].state, 'ready');
  const status = JSON.stringify(service.status()); assert.equal(status.includes(config.turnPassword), false); assert.equal(status.includes(new URL(ownedUrl).searchParams.get('streamerToken')), false);
});
