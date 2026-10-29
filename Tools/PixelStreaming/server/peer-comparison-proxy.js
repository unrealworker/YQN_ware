'use strict';
const http = require('node:http');
const crypto = require('node:crypto');

const PREFIX = '/peer-stream';
const FILES = new Set(['/', '/player.html', '/peer-stream.js', '/player-session.js', '/health']);
const DEADLINE_MS = 10000;
const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;
const WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';

// This proxy carries only the comparison page and signalling. UE video remains
// on WebRTC; no media packets or operator API calls pass through this endpoint.
function createPeerComparisonProxy(config = {}, options = {}) {
  if (!config || typeof config !== 'object' || Array.isArray(config)) throw Error('Invalid peer comparison config');
  if (config.enabled !== undefined && typeof config.enabled !== 'boolean') throw Error('Invalid peer comparison enabled');
  const enabled = config.enabled === true, port = config.port ?? 8088;
  if (enabled && (!Number.isInteger(port) || port < 1 || port > 65535)) throw Error('Invalid peer comparison port');
  const requests = new Set(), sockets = new Set(), clients = new Set(); let closed = false;
  function route(req) {
    const value = typeof req.url === 'string' ? req.url : '';
    const path = value.split('?')[0];
    if (path !== PREFIX && !path.startsWith(PREFIX + '/')) return null;
    // Match raw paths, without URL normalization: encoded slashes and dot
    // segments cannot turn a rejected route into a trusted local endpoint.
    if (value.length > 2048 || value.includes('?') || value.includes('#')) return false;
    return value.slice(PREFIX.length);
  }
  function headers(req, websocket = false) {
    const result = {};
    for (const key of ['host', 'origin', 'accept', 'user-agent']) if (typeof req.headers[key] === 'string') result[key] = req.headers[key];
    if (websocket) {
      result.connection = 'Upgrade'; result.upgrade = 'websocket';
      for (const key of ['sec-websocket-key', 'sec-websocket-version', 'sec-websocket-protocol', 'sec-websocket-extensions']) if (typeof req.headers[key] === 'string') result[key] = req.headers[key];
    }
    return result;
  }
  function failHttp(res, code) {
    if (res.destroyed) return;
    if (res.headersSent) return res.destroy();
    const text = code === 502 ? '对比服务暂不可用，请稍后重试。' : code === 503 ? '对比服务已停止。' : '请求不可用。';
    res.writeHead(code, { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' }); res.end(text);
  }
  function rejectUpgrade(socket, code) {
    if (socket.destroyed) return;
    socket.on('error', () => {});
    socket.end(`HTTP/1.1 ${code} ${http.STATUS_CODES[code]}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`);
    socket.setTimeout(1000, () => socket.destroy());
  }
  function trackRequest(req) {
    requests.add(req); req.once('close', () => requests.delete(req)); return req;
  }
  function handleHttp(req, res) {
    if (!enabled) return false;
    const target = route(req); if (target === null) return false;
    if (closed) { failHttp(res, 503); return true; }
    if (!['GET', 'HEAD'].includes(req.method)) { req.resume(); failHttp(res, 405); return true; }
    if (target === false || (target !== '' && !FILES.has(target))) { failHttp(res, 404); return true; }
    if (req.headers['transfer-encoding'] || (req.headers['content-length'] && req.headers['content-length'] !== '0')) {
      res.setHeader('Connection', 'close'); req.resume(); failHttp(res, 400); return true;
    }
    if (target === '') { res.writeHead(308, { Location: PREFIX + '/', 'Cache-Control': 'no-store' }); res.end(); return true; }
    let upstream;
    try { upstream = trackRequest(http.request({ hostname: '127.0.0.1', port, path: target, method: req.method, headers: headers(req), agent: false, maxHeaderSize: 16384 })); }
    catch { failHttp(res, 502); return true; }
    const deadline = setTimeout(() => upstream.destroy(Error('comparison timeout')), DEADLINE_MS); deadline.unref();
    upstream.once('close', () => clearTimeout(deadline));
    res.once('close', () => { if (!res.writableFinished) upstream.destroy(); });
    req.once('aborted', () => upstream.destroy());
    upstream.on('error', () => failHttp(res, 502));
    upstream.on('response', response => {
      const length = Number(response.headers['content-length']);
      if (Number.isFinite(length) && length > MAX_RESPONSE_BYTES) { response.destroy(); failHttp(res, 502); return; }
      const safeHeaders = { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer' };
      for (const key of ['content-type', 'content-length']) if (response.headers[key] !== undefined) safeHeaders[key] = response.headers[key];
      res.writeHead(response.statusCode || 502, safeHeaders);
      let bytes = 0;
      response.on('data', data => { bytes += data.length; if (bytes > MAX_RESPONSE_BYTES) { response.destroy(); res.destroy(); } });
      response.on('error', () => res.destroy()); response.on('aborted', () => res.destroy());
      response.pipe(res);
    });
    upstream.end(); return true;
  }
  function handleUpgrade(req, socket, head) {
    if (!enabled) return false;
    const target = route(req); if (target === null) return false;
    if (closed) { rejectUpgrade(socket, 503); return true; }
    if (target !== '/') { rejectUpgrade(socket, 404); return true; }
    let allowed = false;
    try { allowed = typeof options.sameOrigin === 'function' && options.sameOrigin(req) === true; } catch {}
    if (!allowed) { rejectUpgrade(socket, 403); return true; }
    const key = req.headers['sec-websocket-key'];
    if (req.method !== 'GET' || req.headers['sec-websocket-protocol'] !== 'peer-stream' || req.headers['sec-websocket-version'] !== '13' || typeof key !== 'string' || !/^[+/0-9A-Za-z]{22}==$/.test(key) || String(req.headers.upgrade).toLowerCase() !== 'websocket' || (head?.length || 0) > 65536) {
      rejectUpgrade(socket, 400); return true;
    }
    let hasCapacity = true;
    try { if (options.canConnect !== undefined) hasCapacity = typeof options.canConnect === 'function' && options.canConnect(req) === true; } catch { hasCapacity = false; }
    if (!hasCapacity) { rejectUpgrade(socket, 503); return true; }
    // Reserve synchronously before any upstream I/O. The original service can
    // include pending handshakes in its shared admission limit without races.
    clients.add(socket); socket.once('close', () => clients.delete(socket));
    let upstream;
    try { upstream = trackRequest(http.request({ hostname: '127.0.0.1', port, path: '/', method: 'GET', headers: headers(req, true), agent: false, maxHeaderSize: 16384 })); }
    catch { rejectUpgrade(socket, 502); return true; }
    sockets.add(socket); socket.once('close', () => { sockets.delete(socket); upstream.destroy(); }); socket.on('error', () => upstream.destroy());
    // Read while the local handshake is pending so a client's FIN is noticed
    // immediately. Keep any pipelined frame bytes bounded until the 101 reply.
    let pendingBytes = head?.length || 0;
    const pendingData = head?.length ? [head] : [];
    const collectPending = data => { pendingBytes += data.length; if (pendingBytes > 65536) { socket.destroy(); upstream.destroy(); } else pendingData.push(data); };
    const endPending = () => { socket.destroy(); upstream.destroy(); };
    socket.on('data', collectPending); socket.once('end', endPending);
    const deadline = setTimeout(() => upstream.destroy(Error('comparison timeout')), DEADLINE_MS); deadline.unref();
    upstream.once('close', () => clearTimeout(deadline));
    upstream.on('error', () => rejectUpgrade(socket, 502));
    upstream.on('response', response => { response.destroy(); rejectUpgrade(socket, 502); });
    upstream.on('upgrade', (response, remote, remoteHead) => {
      clearTimeout(deadline);
      const accept = crypto.createHash('sha1').update(key + WS_GUID).digest('base64');
      if (closed || socket.destroyed || response.statusCode !== 101 || response.headers['sec-websocket-accept'] !== accept || response.headers['sec-websocket-protocol'] !== 'peer-stream') { remote.destroy(); rejectUpgrade(socket, 502); return; }
      socket.pause(); socket.removeListener('data', collectPending); socket.removeListener('end', endPending);
      // Handshake fields are selected, never serialized from an arbitrary
      // upstream response. The local WebSocket server chooses any extension.
      const lines = ['HTTP/1.1 101 Switching Protocols', 'Upgrade: websocket', 'Connection: Upgrade', 'Sec-WebSocket-Accept: ' + accept, 'Sec-WebSocket-Protocol: peer-stream'];
      const extension = response.headers['sec-websocket-extensions']; if (typeof extension === 'string' && !/[\r\n]/.test(extension)) lines.push('Sec-WebSocket-Extensions: ' + extension);
      socket.write(lines.join('\r\n') + '\r\n\r\n');
      sockets.add(remote); remote.once('close', () => { sockets.delete(remote); socket.destroy(); }); remote.on('error', () => socket.destroy());
      socket.once('close', () => remote.destroy());
      socket.setTimeout(0); remote.setTimeout(0);
      if (remoteHead.length) socket.write(remoteHead); for (const data of pendingData) remote.write(data);
      // Native pipe applies backpressure in both directions. No user-space
      // message queue accumulates while a client or local server is slow.
      remote.pipe(socket); socket.pipe(remote);
    });
    upstream.end(); return true;
  }
  function close() { closed = true; for (const req of requests) req.destroy(); for (const socket of sockets) socket.destroy(); for (const socket of clients) socket.destroy(); requests.clear(); sockets.clear(); clients.clear(); }
  return { handleHttp, handleUpgrade, close, get connectionCount() { return clients.size; } };
}

module.exports = { createPeerComparisonProxy };
