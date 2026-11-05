'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const net = require('node:net');
const os = require('node:os');
const fs = require('node:fs');
const path = require('node:path');
const { once, EventEmitter } = require('node:events');
const WebSocket = require('ws');
const { createService } = require('../server/service');
const modulePath = path.join(__dirname, '../server/media-address.js');
const media = fs.existsSync(modulePath) ? require(modulePath) : null;
const localIp = Object.values(os.networkInterfaces()).flat().find(i => i && i.family === 'IPv4' && !i.internal)?.address || '127.0.0.1';
const mapping = { privateIp: localIp, publicIp: '8.8.4.4' };
const nativeCandidate = (ip = localIp, port = 50032) => ({ candidate: `candidate:123456 1 udp 2130706431 ${ip} ${port} typ host generation 0 ufrag test network-cost 10`, sdpMid: '0', sdpMLineIndex: 0 });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn) { const start = Date.now(); while (!fn()) { if (Date.now() - start > 2500) throw Error('Timed out'); await delay(10); } }
async function port() { const s = net.createServer().listen(0, '127.0.0.1'); await once(s, 'listening'); const p = s.address().port; await new Promise(r => s.close(r)); return p; }
async function fixture(t, mediaAddress) {
  const launched = [], config = { executablePath: process.execPath, httpPort: await port(), streamerPort: await port(), mode: 'independent', networkMode: 'public', publicUrl: 'https://warehouse.example', externalTlsTermination: true };
  const service = createService(config, { token: 'test-media-control-token-0123456789', mediaAddress, spawnProcess(_exe, args) {
    const child = new EventEmitter(); child.pid = null; child.exitCode = null; child.signalCode = null;
    launched.push({ id: args.find(a => a.startsWith('-PixelStreamingID=')).slice('-PixelStreamingID='.length), url: args.find(a => a.startsWith('-PixelStreamingConnectionURL=')).slice('-PixelStreamingConnectionURL='.length) }); return child;
  } });
  await service.start(); t.after(() => service.stop());
  return { service, launched, base: `http://127.0.0.1:${config.httpPort}` };
}
async function viewer(ctx) {
  const response = await fetch(ctx.base + '/api/session', { method: 'POST', body: '{}' }); assert.equal(response.status, 200);
  const session = await response.json(), ws = new WebSocket(ctx.base.replace('http:', 'ws:') + '/ws?token=' + session.token), messages = [];
  ws.on('message', b => messages.push(JSON.parse(b))); await once(ws, 'open'); await until(() => messages.some(m => m.type === 'ghsAdmission'));
  return { ws, messages, ...messages.find(m => m.type === 'ghsAdmission') };
}
async function streamer(instance) {
  const ws = new WebSocket(instance.url), messages = []; ws.on('message', b => messages.push(JSON.parse(b))); await once(ws, 'open');
  await until(() => messages.some(m => m.type === 'identify'));
  return { ws, messages, identify() { ws.send(JSON.stringify({ type: 'endpointId', id: instance.id })); } };
}
async function barrier(stream, time) { stream.ws.send(JSON.stringify({ type: 'ping', time })); await until(() => stream.messages.some(m => m.type === 'pong' && m.time === time)); await delay(15); }

test('explicit public media mapping validates IPv4 and rejects private or special public destinations', () => {
  assert.ok(media, 'media mapping module must be available');
  assert.deepEqual(media.validateMediaAddress(mapping), mapping);
  for (const bad of [null, [], false, {}, { ...mapping, privateIp: 'hostname' }, { ...mapping, privateIp: '::1' }, ...['0.0.0.0', '127.0.0.1', '10.1.2.3', '172.16.1.1', '192.168.1.1', '169.254.1.1', '100.64.0.1', '224.0.0.1', '255.255.255.255', 'example.com', '1.2.3.999', '::1'].map(publicIp => ({ ...mapping, publicIp }))]) assert.throws(() => media.validateMediaAddress(bad));
});

test('media candidates retain LAN data and add only port-preserving UDP host candidates in the configured range', () => {
  assert.ok(media, 'media mapping module must be available');
  const original = nativeCandidate(), before = JSON.stringify(original), mapped = media.publicMediaCandidate(original, mapping), fields = mapped.candidate.split(' ');
  assert.equal(JSON.stringify(original), before); assert.equal(fields[4], mapping.publicIp); assert.equal(fields[5], '50032'); assert.equal(fields[7], 'srflx');
  assert.deepEqual(fields.slice(8, 12), ['raddr', localIp, 'rport', '50032']); assert.ok(Number(fields[3]) < Number(original.candidate.split(' ')[3]));
  assert.equal(mapped.sdpMid, '0'); assert.equal(mapped.sdpMLineIndex, 0);
  for (const port of [50000, 50199]) assert.ok(media.publicMediaCandidate(nativeCandidate(localIp, port), mapping));
  const invalid = [nativeCandidate('10.99.99.99'), ...[49999, 50200, 1, 65536, 'notaport'].map(port => nativeCandidate(localIp, port)),
    ...['tcp', 'UDPbad'].map(protocol => ({ ...original, candidate: original.candidate.replace(' udp ', ' ' + protocol + ' ') })),
    ...['srflx', 'relay'].map(type => ({ ...original, candidate: original.candidate.replace('typ host', 'typ ' + type) })),
    ...['-1', '4294967296', 'NaN'].map(priority => ({ ...original, candidate: original.candidate.replace('2130706431', priority) })),
    { ...original, candidate: original.candidate.replace(' 1 udp ', ' bad udp ') }, { ...original, candidate: 'broken' }, null];
  for (const candidate of invalid) assert.equal(media.publicMediaCandidate(candidate, mapping), null);
  assert.equal(media.publicMediaCandidate(original, null), null);
});

test('missing media settings retain existing behavior while malformed or nonlocal mappings fail closed', t => {
  assert.ok(media, 'media mapping module must be available');
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ghs-media-settings-')); t.after(() => fs.rmSync(folder, { recursive: true, force: true }));
  const file = path.join(folder, 'media-address.json');
  assert.equal(media.loadMediaAddress('public', undefined, file), undefined);
  fs.writeFileSync(file, '\uFEFF' + JSON.stringify(mapping)); assert.deepEqual(media.loadMediaAddress('public', undefined, file), mapping);
  assert.equal(media.loadMediaAddress('lan', undefined, file), undefined);
  for (const contents of ['not json', 'false', '{}', JSON.stringify({ ...mapping, privateIp: '203.0.113.231' })]) {
    fs.writeFileSync(file, contents); assert.throws(() => media.loadMediaAddress('public', undefined, file));
  }
  assert.throws(() => createService({ executablePath: process.execPath }, { token: 'test-media-control-token-0123456789', mediaAddress: { ...mapping, privateIp: '203.0.113.231' } }), /不属于本机/);
});

test('only authenticated subscribed viewers receive their own UE mapped candidate, with original LAN candidate first', async t => {
  const ctx = await fixture(t, mapping), first = await viewer(ctx), other = await viewer(ctx);
  const stream = await streamer(ctx.launched[0]), candidate = nativeCandidate();
  stream.ws.send(JSON.stringify({ type: 'iceCandidate', playerId: first.playerId, candidate })); await barrier(stream, 1);
  assert.equal(first.messages.some(m => m.type === 'iceCandidate'), false, 'endpoint identity is required');
  stream.identify(); await until(() => ctx.launched.length === 2);
  stream.ws.send(JSON.stringify({ type: 'iceCandidate', playerId: first.playerId, candidate })); await barrier(stream, 2);
  assert.equal(first.messages.some(m => m.type === 'iceCandidate'), false, 'subscription is required');
  first.ws.send(JSON.stringify({ type: 'subscribe', streamerId: first.instanceId })); await until(() => stream.messages.some(m => m.type === 'playerConnected'));
  const second = await streamer(ctx.launched[1]); second.identify(); await until(() => ctx.service.status().instances[1].state === 'ready');
  other.ws.send(JSON.stringify({ type: 'subscribe', streamerId: other.instanceId })); await until(() => second.messages.some(m => m.type === 'playerConnected'));
  stream.ws.send(JSON.stringify({ type: 'iceCandidate', playerId: other.playerId, candidate })); await barrier(stream, 3);
  assert.equal(other.messages.some(m => m.type === 'iceCandidate'), false, 'a different instance cannot target this viewer');
  stream.ws.send(JSON.stringify({ type: 'iceCandidate', playerId: first.playerId, candidate })); await until(() => first.messages.filter(m => m.type === 'iceCandidate').length >= 2);
  const received = first.messages.filter(m => m.type === 'iceCandidate'); assert.equal(received.length, 2); assert.deepEqual(received[0].candidate, candidate);
  assert.equal(received[1].candidate.candidate.split(' ')[4], mapping.publicIp); assert.equal(received[0].playerId, undefined); assert.equal(received[1].playerId, undefined);
  first.ws.send(JSON.stringify({ type: 'iceCandidate', candidate })); await until(() => stream.messages.some(m => m.type === 'iceCandidate'));
  assert.deepEqual(stream.messages.find(m => m.type === 'iceCandidate').candidate, candidate, 'player-supplied candidates must never be mapped');
});

test('without media mapping the original candidate is forwarded exactly once', async t => {
  const ctx = await fixture(t), client = await viewer(ctx), stream = await streamer(ctx.launched[0]); stream.identify(); await until(() => ctx.service.status().instances[0].state === 'ready');
  client.ws.send(JSON.stringify({ type: 'subscribe', streamerId: client.instanceId })); await until(() => stream.messages.some(m => m.type === 'playerConnected'));
  const candidate = nativeCandidate(); stream.ws.send(JSON.stringify({ type: 'iceCandidate', playerId: client.playerId, candidate })); await barrier(stream, 5);
  assert.deepEqual(client.messages.filter(m => m.type === 'iceCandidate'), [{ type: 'iceCandidate', candidate }]);
});
