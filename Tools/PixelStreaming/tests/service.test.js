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
  const config = { executablePath: process.execPath, httpPort: await freePort(), streamerPort: await freePort(), mode, showWindow: false, width: 1920, height: 1080, ...extra };
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
  assert.equal(ctx.children.length, 2); assert.equal(ctx.service.status().viewerCount, 2);
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

 test('public access gate, exact origins, private ICE and manual revocation work together', async t => {
  const ctx = await setup(t, 'independent', 0, { networkMode: 'public', publicUrl: 'http://warehouse.example:8080', accessCode: 'test-only-access-code', stunUrl: 'stun:stun.example:3478', turnUrl: 'turn:relay.example:3478?transport=udp', turnUsername: 'test-user', turnPassword: 'test-turn-secret' });
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
  const ctx = await setup(t, 'independent', 0, { networkMode: 'public', publicUrl: 'http://warehouse.example', accessCode: 'test-only-access-code' });
  for (let i = 0; i < 20; i++) assert.equal((await fetch(ctx.base + '/api/session', { method: 'POST', body: JSON.stringify({ accessCode: 'wrong' }) })).status, 401);
  assert.equal((await fetch(ctx.base + '/api/session', { method: 'POST', body: JSON.stringify({ accessCode: ctx.config.accessCode }) })).status, 429);
  assert.equal(ctx.children.length, 0);
});

test('network validation fails closed for malformed public origin, TLS and ICE settings', () => {
  const c = { executablePath: process.execPath };
  for (const fields of [{ maxViewers: 11 }, { maxViewers: 0 }, { networkMode: 'public' }, { networkMode: 'public', publicUrl: 'https://a.example', accessCode: 'long-enough-code' }, { publicUrl: 'http://user:password@a.example' }, { publicUrl: 'http://a.example/subpath' }, { tlsCertPath: 'missing' }, { turnUrl: 'http://relay' }, { turnUrl: 'turn:relay:3478' }, { stunUrl: 'stun:host:99999' }, { trustProxy: 'yes' }, { networkMode: 'lan', trustProxy: true }]) assert.throws(() => validateConfig({ ...c, ...fields }));
  assert.equal(validateConfig({ ...c, httpPort: 443 }).httpPort, 443);
  assert.equal(validateConfig({ ...c, networkMode: 'public', publicUrl: 'https://warehouse.example/', accessCode: 'long-enough-code', trustProxy: true }).publicUrl, 'https://warehouse.example');
});

test('trusted proxy only accepts client address from loopback and rejects cross-origin signalling', async t => {
  const { clientAddress, sameOrigin } = require('../server/network-policy');
  const c = { trustProxy: true, networkMode: 'public', publicUrl: 'https://warehouse.example', httpPort: 8080 };
  const req = { socket: { remoteAddress: '127.0.0.1' }, headers: { host: 'warehouse.example', origin: 'https://warehouse.example', 'x-forwarded-for': '1.1.1.1, 203.0.113.2' } };
  assert.equal(clientAddress(req, c), '203.0.113.2'); assert.equal(sameOrigin(req, c), true);
  req.socket.remoteAddress = '198.51.100.2'; assert.equal(clientAddress(req, c), '198.51.100.2');
  req.headers.origin = 'https://evil.example'; assert.equal(sameOrigin(req, c), false);
});

// These self-signed PEM files exist only for loopback transport tests, never the delivery.
test('native HTTPS performs a verified TLS handshake and accepts WSS with authenticated admission', async t => {
  const https = require('node:https');
  const config = { executablePath: process.execPath, httpPort: await freePort(), streamerPort: await freePort(), mode: 'independent', networkMode: 'public', accessCode: 'test-only-access-code', publicUrl: 'https://127.0.0.1', tlsCertPath: path.join(__dirname, 'fixtures/test-localhost-cert.pem'), tlsKeyPath: path.join(__dirname, 'fixtures/test-localhost-key.pem') };
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
