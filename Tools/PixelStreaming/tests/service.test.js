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
async function setup(t, mode = 'shared', observedExitDelayMs = 0) {
  const config = { executablePath: process.execPath, httpPort: await freePort(), streamerPort: await freePort(), mode, showWindow: false, width: 1920, height: 1080 };
  const children = [];
  const service = createService(config, { token, reconnectGraceMs: 60, spawnProcess(exe, args, opts) {
    assert.equal(opts.shell, false); assert.equal(exe, process.execPath);
    const id = args.find(x => x.startsWith('-PixelStreamingID=')).split('=')[1];
    const child = spawn(process.execPath, [path.join(__dirname, 'mock-ue.js'), String(config.streamerPort), id], { stdio: 'ignore', windowsHide: true });
    children.push(child);
    if (!observedExitDelayMs) return child;
    // A delayed exit notification makes cleanup/admission queue interleaving deterministic.
    const observed = new EventEmitter(); observed.pid = child.pid; observed.exitCode = null; observed.signalCode = null; observed.kill = signal => child.kill(signal);
    child.on('exit', (code, signal) => setTimeout(() => { observed.exitCode = code; observed.signalCode = signal; observed.emit('exit', code, signal); }, observedExitDelayMs));
    child.on('error', e => observed.emit('error', e)); return observed;
  } });
  await service.start();
  t.after(async () => { await service.stop(); for (const p of children) assert.ok(p.exitCode !== null || p.signalCode !== null, 'owned child must be reaped'); });
  return { service, config, children, base: `http://127.0.0.1:${config.httpPort}` };
}
async function viewer(ctx, resume) {
  const response = await fetch(ctx.base + '/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(resume ? { token: resume } : {}) });
  const session = await response.json();
  const ws = new WebSocket(ctx.base.replace('http:', 'ws:') + '/ws?token=' + session.token);
  const messages = []; let close;
  ws.on('message', m => messages.push(JSON.parse(m))); ws.on('close', (code, reason) => { close = { code, reason: String(reason) }; });
  await once(ws, 'open');
  return { ws, messages, token: session.token, get close() { return close; } };
}

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
  assert.ok(args.includes('-PixelStreamingEncoderMaxQP=26'));
  assert.ok(args.some(x => x.includes('r.ScreenPercentage 100') && x.includes('r.DynamicRes.OperationMode 0')));
  assert.ok(buildUEArgs(validateConfig({ ...cfg, qualityProfile: 'ultra' }), 'shared').includes('-PixelStreamingEncoderMaxQP=22'));
  assert.throws(() => validateConfig({ ...cfg, qualityProfile: 'unknown' }), /画质/);
  assert.throws(() => validateConfig({ ...cfg, adaptiveResourceBudget: 'true' }), /布尔/);
});

test('shared mode launches one UE, routes official offer/answer and limits fourth viewer by FIFO without eviction reconnect loop', async t => {
  const ctx = await setup(t);
  await until(() => ctx.service.status().instances.some(x => x.state === 'ready'));
  const a = await viewer(ctx); const b = await viewer(ctx); const c = await viewer(ctx);
  await until(() => c.messages.some(x => x.type === 'config'));
  a.ws.send(JSON.stringify({ type: 'subscribe', streamerId: 'shared' }));
  await until(() => a.messages.some(x => x.type === 'offer'));
  a.ws.send(JSON.stringify({ type: 'answer', sdp: 'answer-from-browser' }));
  await until(() => a.messages.some(x => x.type === 'iceCandidate' && x.candidate.candidate === 'answer-received'));
  const d = await viewer(ctx); await until(() => a.close);
  assert.equal(a.close.code, 4001); assert.ok(a.messages.some(x => x.type === 'ghsEvicted' && x.reconnect === false));
  assert.equal(ctx.service.status().viewerCount, 3); assert.equal(ctx.children.length, 1);
  assert.equal(ctx.service.status().instances[0].targetFps, 60, 'shared viewers must not divide the single renderer budget');
  const denied = await viewer(ctx, a.token); await until(() => denied.close);
  assert.equal(denied.close.code, 4001); assert.equal(ctx.service.status().viewerCount, 3);
  assert.equal(b.close, undefined); assert.equal(c.close, undefined); assert.equal(d.close, undefined);
});

test('independent admission and departure apply equal live frame budgets without restarting surviving UE instances', async t => {
  const ctx = await setup(t, 'independent'); const a = await viewer(ctx);
  await until(() => ctx.service.status().instances.length === 1);
  const firstPid = ctx.service.status().instances[0].pid;
  assert.equal(ctx.service.status().instances[0].targetFps, 60);
  const b = await viewer(ctx); await until(() => ctx.service.status().instances.length === 2);
  assert.deepEqual(ctx.service.status().instances.map(x => x.targetFps), [30, 30]);
  const c = await viewer(ctx); await until(() => ctx.service.status().instances.length === 3);
  assert.deepEqual(ctx.service.status().instances.map(x => x.targetFps), [20, 20, 20]);
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
  assert.equal(status.status, 200); assert.equal((await status.json()).maxViewers, 3);
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

test('reconnect keeps FIFO rank and replaces only the same session socket without increasing count', async t => {
  const ctx = await setup(t); const a = await viewer(ctx); const b = await viewer(ctx); const c = await viewer(ctx);
  const restored = await viewer(ctx, a.token); await until(() => a.close);
  assert.equal(a.close.code, 4002); assert.equal(ctx.service.status().viewerCount, 3);
  const fourth = await viewer(ctx); await until(() => restored.close);
  assert.equal(restored.close.code, 4001); assert.equal(b.close, undefined); assert.equal(c.close, undefined); assert.equal(fourth.close, undefined);
});

test('independent replacement queues early WS messages while old UE exits and never owns over 3 live children', async t => {
  const ctx = await setup(t, 'independent'); const a = await viewer(ctx); await viewer(ctx); await viewer(ctx);
  await until(() => ctx.service.status().instances.filter(x => x.state === 'ready').length === 3);
  const session = await (await fetch(ctx.base + '/api/session', { method: 'POST', body: '{}' })).json();
  const ws = new WebSocket(ctx.base.replace('http:', 'ws:') + '/ws?token=' + session.token); const messages = [];
  ws.on('message', x => messages.push(JSON.parse(x))); ws.on('open', () => ws.send(JSON.stringify({ type: 'ping', time: 123456 })));
  await until(() => messages.some(m => m.type === 'pong' && m.time === 123456));
  assert.equal(a.close.code, 4001); assert.equal(ctx.children.length, 4);
  assert.equal(ctx.children.filter(p => p.exitCode === null && p.signalCode === null).length, 3);
  assert.equal(ctx.service.status().viewerCount, 3);
});

test('a fourth viewer closing during independent replacement cannot leave an invisible occupied slot', async t => {
  const ctx = await setup(t, 'independent'); await viewer(ctx); await viewer(ctx); await viewer(ctx);
  await until(() => ctx.service.status().instances.filter(x => x.state === 'ready').length === 3);
  const session = await (await fetch(ctx.base + '/api/session', { method: 'POST', body: '{}' })).json();
  const ws = new WebSocket(ctx.base.replace('http:', 'ws:') + '/ws?token=' + session.token);
  ws.on('open', () => ws.close()); await once(ws, 'close'); await delay(250);
  const instanceCount = ctx.service.status().instances.length;
  const connectedCount = ctx.service.status().viewerCount;
  assert.ok(instanceCount <= 2, 'closed newcomer must not keep an independent UE alive');
  assert.equal(connectedCount, instanceCount);
});

test('queued grace-period cleanup cannot release a session restored behind another process cleanup', async t => {
  const ctx = await setup(t, 'independent', 400); await viewer(ctx); const b = await viewer(ctx); await viewer(ctx);
  await until(() => ctx.service.status().instances.filter(x => x.state === 'ready').length === 3);
  const beforeId = b.messages.find(m => m.type === 'ghsAdmission').instanceId;
  b.ws.terminate(); await delay(10); await viewer(ctx); const restored = await viewer(ctx, b.token); await delay(1000);
  assert.equal(restored.ws.readyState, WebSocket.OPEN); assert.equal(ctx.service.status().viewerCount, 3);
  assert.ok(ctx.service.status().instances.some(i => i.id === beforeId && i.state === 'ready'));
  assert.equal(ctx.children.filter(p => p.exitCode === null && p.signalCode === null).length, 3);
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
    const ws = new WebSocket(`ws://127.0.0.1:${ctx.config.streamerPort}`); let closed;
    ws.on('close', code => { closed = code; }); await once(ws, 'open'); ws.send(JSON.stringify(bad)); await until(() => closed); assert.equal(closed, 1007);
    assert.equal((await fetch(ctx.base + '/health')).status, 200);
  }
});
