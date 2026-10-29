'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { once } = require('node:events');
const WebSocket = require('ws');
const { createPeerComparisonProxy } = require('../server/peer-comparison-proxy');

async function listen(server) { server.listen(0, '127.0.0.1'); await once(server, 'listening'); return server.address().port; }
async function close(server) { server.closeAllConnections?.(); await new Promise(resolve => server.close(resolve)); }
function request(port, path, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port, path, method: options.method || 'GET', headers: options.headers || {} }, res => {
      const data = []; res.on('data', chunk => data.push(chunk)); res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, text: Buffer.concat(data).toString() })); res.on('error', reject);
    }); req.on('error', reject); req.end();
  });
}
async function setup(t, limit = Infinity) {
  const requests = [], connections = new Set();
  const backend = http.createServer((req, res) => {
    requests.push({ path: req.url, headers: req.headers });
    const body = JSON.stringify({ path: req.url, method: req.method });
    res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body), 'Set-Cookie': 'do-not-forward=1' }); res.end(req.method === 'HEAD' ? undefined : body);
  });
  const wss = new WebSocket.WebSocketServer({ noServer: true, perMessageDeflate: false });
  backend.on('upgrade', (req, socket, head) => {
    requests.push({ path: req.url, headers: req.headers });
    wss.handleUpgrade(req, socket, head, ws => { connections.add(ws); ws.on('close', () => connections.delete(ws)); ws.on('error', () => {}); ws.on('message', (bytes, binary) => ws.send(bytes, { binary })); });
  });
  const backendPort = await listen(backend);
  const proxy = createPeerComparisonProxy({ enabled: true, port: backendPort }, { sameOrigin: req => req.headers.origin === 'https://warehouse.example' && req.headers.host === 'warehouse.example', canConnect: () => proxy.connectionCount < limit });
  const frontend = http.createServer((req, res) => { if (!proxy.handleHttp(req, res)) { res.writeHead(200); res.end('original service'); } });
  frontend.on('upgrade', (req, socket, head) => { if (!proxy.handleUpgrade(req, socket, head)) socket.destroy(); });
  const port = await listen(frontend);
  t.after(async () => { proxy.close(); for (const ws of connections) ws.terminate(); wss.close(); await close(frontend); if (backend.listening) await close(backend); });
  return { proxy, port, backend, requests, connections };
}
function socket(ctx, options = {}) { return new WebSocket(`ws://127.0.0.1:${ctx.port}${options.path || '/peer-stream/'}`, options.protocol ?? 'peer-stream', { headers: { Host: 'warehouse.example', Origin: 'https://warehouse.example', ...options.headers }, perMessageDeflate: false }); }
function rejection(ws) {
  return new Promise((resolve, reject) => {
    ws.on('unexpected-response', (_req, res) => { res.resume(); ws.terminate(); resolve(res.statusCode); });
    ws.on('open', () => { ws.terminate(); reject(Error('Unexpected accepted WebSocket')); }); ws.on('error', () => {});
  });
}

test('comparison proxy is opt-in and validates only a fixed loopback port', () => {
  for (const config of [undefined, {}, { enabled: false }]) {
    const proxy = createPeerComparisonProxy(config); assert.equal(proxy.handleHttp({ url: '/peer-stream/' }, {}), false); assert.equal(proxy.handleUpgrade({ url: '/peer-stream/' }, {}, Buffer.alloc(0)), false); proxy.close();
  }
  for (const port of [0, -1, 65536, '8088', 1.5]) assert.throws(() => createPeerComparisonProxy({ enabled: true, port }), /port/);
  assert.throws(() => createPeerComparisonProxy({ enabled: 'true' }), /enabled/);
});

test('HTTP allowlist maps relative player assets, redirects slash and preserves original routes', async t => {
  const ctx = await setup(t);
  assert.equal((await request(ctx.port, '/')).text, 'original service');
  const redirect = await request(ctx.port, '/peer-stream'); assert.equal(redirect.status, 308); assert.equal(redirect.headers.location, '/peer-stream/');
  for (const name of ['', 'player.html', 'peer-stream.js', 'player-session.js', 'health']) {
    const res = await request(ctx.port, '/peer-stream/' + name); assert.equal(res.status, 200); assert.equal(JSON.parse(res.text).path, '/' + name);
  }
  const head = await request(ctx.port, '/peer-stream/peer-stream.js', { method: 'HEAD' }); assert.equal(head.status, 200); assert.equal(head.text, '');
});

test('proxy strips credentials and forwarded headers but retains browser Host and Origin', async t => {
  const ctx = await setup(t);
  const res = await request(ctx.port, '/peer-stream/health', { headers: { Host: 'warehouse.example', Origin: 'https://warehouse.example', Authorization: 'Bearer private', Cookie: 'session=private', Forwarded: 'for=admin', 'X-Forwarded-For': '127.0.0.1', 'X-Forwarded-Host': 'evil.example' } });
  assert.equal(res.headers['set-cookie'], undefined);
  const headers = ctx.requests.at(-1).headers; assert.equal(headers.host, 'warehouse.example'); assert.equal(headers.origin, 'https://warehouse.example');
  for (const key of ['authorization', 'cookie', 'forwarded', 'x-forwarded-for', 'x-forwarded-host']) assert.equal(headers[key], undefined);
});

test('control, engine, traversal, absolute targets, queries and unsupported methods never reach backend', async t => {
  const ctx = await setup(t);
  for (const path of ['/peer-stream/control/status', '/peer-stream/control/stop', '/peer-stream/0', '/peer-stream/exec', '/peer-stream/../health', '/peer-stream/%2e%2e/health', '/peer-stream//health', '/peer-stream/http://example.com/', '/peer-stream/health?token=private']) assert.equal((await request(ctx.port, path)).status, 404, path);
  for (const method of ['POST', 'PUT', 'DELETE']) assert.equal((await request(ctx.port, '/peer-stream/health', { method })).status, 405);
  assert.equal(ctx.requests.length, 0);
});

test('WebSocket accepts only exact player endpoint, protocol and allowed browser origin', async t => {
  const ctx = await setup(t);
  for (const options of [{ path: '/peer-stream/0' }, { path: '/peer-stream/control/status' }, { path: '/peer-stream/?token=secret' }, { protocol: 'exec-ue' }, { protocol: [] }, { headers: { Origin: 'https://evil.example' } }, { headers: { Host: 'evil.example' } }]) assert.ok([400, 403, 404].includes(await rejection(socket(ctx, options))));
  assert.equal(ctx.requests.length, 0);
});

test('binary and text WebSocket frames are transparent and client close releases upstream', async t => {
  const ctx = await setup(t); const ws = socket(ctx, { headers: { 'X-Forwarded-For': '127.0.0.1', Authorization: 'Bearer private' } });
  await once(ws, 'open'); assert.equal(ws.protocol, 'peer-stream');
  let incoming = once(ws, 'message'); ws.send('hello'); let [data, binary] = await incoming; assert.equal(data.toString(), 'hello'); assert.equal(binary, false);
  const payload = Buffer.alloc(256 * 1024, 179); incoming = once(ws, 'message'); ws.send(payload); [data, binary] = await incoming; assert.deepEqual(data, payload); assert.equal(binary, true);
  const headers = ctx.requests.at(-1).headers; assert.equal(ctx.requests.at(-1).path, '/'); assert.equal(headers.origin, 'https://warehouse.example'); assert.equal(headers.host, 'warehouse.example'); assert.equal(headers.authorization, undefined); assert.equal(headers['x-forwarded-for'], undefined);
  const backendWs = [...ctx.connections][0]; const backendClose = once(backendWs, 'close'), clientClose = once(ws, 'close'); ws.close(1000, 'user left'); await Promise.all([backendClose, clientClose]); assert.equal(ctx.connections.size, 0);
});

test('proxy shutdown closes an active WebSocket and refuses further comparison requests only', async t => {
  const ctx = await setup(t); const ws = socket(ctx); await once(ws, 'open'); const closed = once(ws, 'close'); ctx.proxy.close(); await closed;
  assert.equal((await request(ctx.port, '/peer-stream/')).status, 503); assert.equal((await request(ctx.port, '/')).text, 'original service');
});

test('upstream closes propagate with their WebSocket reason and do not affect the original route', async t => {
  const ctx = await setup(t); const ws = socket(ctx); await once(ws, 'open'); const done = once(ws, 'close');
  [...ctx.connections][0].close(1001, 'comparison stopped'); const [code, reason] = await done;
  assert.equal(code, 1001); assert.equal(reason.toString(), 'comparison stopped'); assert.equal((await request(ctx.port, '/')).text, 'original service');
});

test('unavailable comparison backend returns sanitized 502 and keeps original route healthy', async t => {
  const ctx = await setup(t); await close(ctx.backend);
  const res = await request(ctx.port, '/peer-stream/'); assert.equal(res.status, 502); assert.doesNotMatch(res.text, /ECONNREFUSED|127\.0\.0\.1|stack|token/i);
  assert.equal((await request(ctx.port, '/')).text, 'original service'); assert.equal(await rejection(socket(ctx)), 502);
});

test('WebSocket without a supplied origin policy fails closed', async t => {
  const proxy = createPeerComparisonProxy({ enabled: true });
  const server = http.createServer(); server.on('upgrade', (req, socket, head) => proxy.handleUpgrade(req, socket, head)); const port = await listen(server);
  t.after(async () => { proxy.close(); await close(server); }); assert.equal(await rejection(socket({ port })), 403);
});

test('shared capacity reserves connections synchronously and releases them exactly once', async t => {
  const ctx = await setup(t, 2); assert.equal(ctx.proxy.connectionCount, 0);
  const a = socket(ctx), b = socket(ctx); await Promise.all([once(a, 'open'), once(b, 'open')]);
  assert.equal(ctx.proxy.connectionCount, 2); assert.equal(await rejection(socket(ctx)), 503); assert.equal(ctx.proxy.connectionCount, 2);
  let ended = once(a, 'close'); a.close(); await ended;
  // The client close handshake is complete once its underlying TCP connection
  // closes; allow that same event turn to release the proxy's reservation.
  await new Promise(resolve => setImmediate(resolve)); assert.equal(ctx.proxy.connectionCount, 1);
  const c = socket(ctx); await once(c, 'open'); assert.equal(ctx.proxy.connectionCount, 2);
  const completed = [once(b, 'close'), once(c, 'close')]; ctx.proxy.close(); ctx.proxy.close(); await Promise.all(completed); assert.equal(ctx.proxy.connectionCount, 0);
});

test('a pending upstream handshake occupies capacity and aborted handshake releases it', async t => {
  const backendSockets = new Set(); const backend = http.createServer();
  backend.on('connection', socket => { backendSockets.add(socket); socket.on('close', () => backendSockets.delete(socket)); });
  backend.on('upgrade', () => {}); // Deliberately never send 101.
  const backendPort = await listen(backend);
  const proxy = createPeerComparisonProxy({ enabled: true, port: backendPort }, { sameOrigin: () => true, canConnect: () => proxy.connectionCount < 1 });
  const frontend = http.createServer(); frontend.on('upgrade', (req, socket, head) => proxy.handleUpgrade(req, socket, head)); const port = await listen(frontend);
  t.after(async () => { proxy.close(); for (const socket of backendSockets) socket.destroy(); await close(frontend); await close(backend); });
  const reached = once(backend, 'upgrade'), pending = socket({ port }); pending.on('error', () => {}); await reached;
  assert.equal(proxy.connectionCount, 1); assert.equal(await rejection(socket({ port })), 503);
  const done = once(pending, 'close').catch(() => {}); pending.terminate(); await done;
  for (let i = 0; proxy.connectionCount && i < 20; i++) await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal(proxy.connectionCount, 0);
});
