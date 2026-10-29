'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { once, EventEmitter } = require('node:events');
const WebSocket = require('ws');
const { createService } = require('../server/service');

async function listen(server) { server.listen(0, '127.0.0.1'); await once(server, 'listening'); return server.address().port; }
async function freePort() { const server = http.createServer(); const port = await listen(server); await new Promise(resolve => server.close(resolve)); return port; }
async function until(fn, timeout = 3000) {
  const start = Date.now(); while (!fn()) { if (Date.now() - start >= timeout) throw Error('Timed out waiting for integration state'); await new Promise(resolve => setTimeout(resolve, 5)); }
}
async function fixture(t, configPatch = {}, optionPatch = {}) {
  const received = [], peerSockets = new Set(), children = [];
  const backend = http.createServer((req, res) => { received.push(req.url); res.writeHead(200, { 'Content-Type': 'text/plain' }); res.end('peer route ' + req.url); });
  const wss = new WebSocket.WebSocketServer({ noServer: true, perMessageDeflate: false });
  backend.on('upgrade', (req, socket, head) => wss.handleUpgrade(req, socket, head, ws => {
    peerSockets.add(ws); ws.on('error', () => {}); ws.once('close', () => peerSockets.delete(ws)); ws.on('message', (data, binary) => ws.send(data, { binary }));
  }));
  const backendPort = await listen(backend);
  const config = { executablePath: process.execPath, httpPort: await freePort(), streamerPort: await freePort(), mode: 'independent', maxViewers: 1, fps: 0, ...configPatch };
  const service = createService(config, {
    token: 'comparison-integration-test-control-token', reconnectGraceMs: 20,
    peerComparison: { enabled: true, port: backendPort },
    spawnProcess(_exe, args) {
      // This test exercises HTTP, WebSocket admission and owned lifecycle, not
      // UE rendering. A no-PID child makes process cleanup deterministic.
      const child = new EventEmitter(); child.pid = null; child.exitCode = null; child.signalCode = null; children.push({ child, args }); return child;
    }, ...optionPatch
  });
  await service.start();
  t.after(async () => {
    await service.stop(); for (const socket of peerSockets) socket.terminate(); wss.close();
    backend.closeAllConnections?.(); if (backend.listening) await new Promise(resolve => backend.close(resolve));
  });
  return { service, base: `http://127.0.0.1:${config.httpPort}`, received, peerSockets, children };
}
function openPeer(ctx, extra = {}) { return new WebSocket(ctx.base.replace('http:', 'ws:') + '/peer-stream/', 'peer-stream', { origin: ctx.base, perMessageDeflate: false, ...extra }); }
function rejected(ws) {
  return new Promise((resolve, reject) => {
    ws.on('error', () => {}); ws.on('unexpected-response', (_req, res) => { res.resume(); ws.terminate(); resolve(res.statusCode); }); ws.on('open', () => { ws.terminate(); reject(Error('Unexpected peer acceptance')); });
  });
}
async function openOriginal(ctx) {
  const response = await fetch(ctx.base + '/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); assert.equal(response.status, 200);
  const { token } = await response.json();
  const ws = new WebSocket(ctx.base.replace('http:', 'ws:') + '/ws?token=' + token, { origin: ctx.base });
  const messages = []; let closed;
  ws.on('message', data => messages.push(JSON.parse(data))); ws.on('close', code => { closed = code; }); ws.on('error', () => {});
  await once(ws, 'open'); return { ws, messages, get closed() { return closed; } };
}

test('createService opt-in comparison serves HTTP and transparent WebSocket without starting original UE', async t => {
  const ctx = await fixture(t);
  const health = await (await fetch(ctx.base + '/health')).json(); assert.equal(health.state, 'running'); assert.equal(health.viewerCount, 0);
  assert.equal(await (await fetch(ctx.base + '/peer-stream/')).text(), 'peer route /');
  assert.equal(await (await fetch(ctx.base + '/peer-stream/player-session.js')).text(), 'peer route /player-session.js');
  const ws = openPeer(ctx); await once(ws, 'open'); const echoed = once(ws, 'message'); ws.send(Buffer.from([0, 1, 2, 255])); const [data, binary] = await echoed;
  assert.deepEqual(data, Buffer.from([0, 1, 2, 255])); assert.equal(binary, true); assert.equal(ctx.children.length, 0);
  const done = once(ws, 'close'); ws.close(); await done;
});

test('peer occupies the shared limit, original is rejected and can enter after peer releases', async t => {
  const ctx = await fixture(t); const peer = openPeer(ctx); await once(peer, 'open');
  const full = await openOriginal(ctx); await until(() => full.closed !== undefined);
  assert.equal(full.closed, 4004); assert.ok(full.messages.some(m => m.type === 'ghsFull')); assert.equal(ctx.children.length, 0);
  const done = once(peer, 'close'); peer.close(); await done; await until(() => ctx.peerSockets.size === 0);
  const original = await openOriginal(ctx); await until(() => original.messages.some(m => m.type === 'ghsAdmission'));
  assert.equal(ctx.service.status().viewerCount, 1); assert.equal(ctx.children.length, 1);
  original.ws.close(); await until(() => ctx.service.status().viewerCount === 0);
});

test('original occupies the shared limit, peer gets 503 and can enter after original releases', async t => {
  const ctx = await fixture(t); const original = await openOriginal(ctx); await until(() => original.messages.some(m => m.type === 'ghsAdmission'));
  assert.equal(await rejected(openPeer(ctx)), 503); assert.equal(ctx.peerSockets.size, 0);
  original.ws.close(); await until(() => ctx.service.status().viewerCount === 0);
  const peer = openPeer(ctx); await once(peer, 'open'); assert.equal(ctx.peerSockets.size, 1); const done = once(peer, 'close'); peer.close(); await done;
});

test('access protection disables comparison HTTP and WebSocket instead of bypassing the code gate', async t => {
  const ctx = await fixture(t, { accessProtectionEnabled: true, accessCode: 'fixture-only-access-code' });
  assert.equal((await fetch(ctx.base + '/peer-stream/')).status, 404);
  assert.equal(await rejected(openPeer(ctx)), 403); assert.equal(ctx.received.length, 0); assert.equal(ctx.peerSockets.size, 0);
  const auth = await fetch(ctx.base + '/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); assert.equal(auth.status, 401);
  assert.equal((await (await fetch(ctx.base + '/health')).json()).accessRequired, true);
});

test('service stop closes comparison sockets and invalid comparison configuration leaves main healthy', async t => {
  const ctx = await fixture(t); const peer = openPeer(ctx); await once(peer, 'open'); const closed = once(peer, 'close'); await ctx.service.stop(); await closed;
  assert.equal(ctx.service.status().state, 'stopped'); await until(() => ctx.peerSockets.size === 0);
  const invalid = await fixture(t, {}, { peerComparison: { enabled: true, port: 0 } });
  assert.equal((await fetch(invalid.base + '/peer-stream/')).status, 404); assert.equal((await (await fetch(invalid.base + '/health')).json()).state, 'running');
});

test('main origin policy also rejects cross-origin peer comparison upgrades', async t => {
  const ctx = await fixture(t); assert.equal(await rejected(openPeer(ctx, { origin: 'https://untrusted.example' })), 403); assert.equal(ctx.peerSockets.size, 0);
});
