'use strict';
const http = require('node:http');
const https = require('node:https');
const { NETWORK_DEFAULTS, validateNetwork, iceServers, clientAddress, sameOrigin: requestSameOrigin, secretEqual } = require('./network-policy');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { performance } = require('node:perf_hooks');
const { spawn } = require('node:child_process');
const { WebSocketServer, WebSocket } = require('ws');
const { BudgetPolicy, readMetrics, writeBudget } = require('./resource-budget');

const EVICTED = '管理员已断开此连接，已停止自动重连。需要再次访问时请主动重新进入。';
const DEFAULTS = { ...NETWORK_DEFAULTS, httpPort: 8080, streamerPort: 8888, showWindow: false, width: 1920, height: 1080, mode: 'shared', fps: 60, minBitrateMbps: 12, startBitrateMbps: 35, maxBitrateMbps: 60, qualityProfile: 'clear', adaptiveResourceBudget: true };
function validateConfig(raw) {
  const config = { ...DEFAULTS, ...raw };
  for (const key of ['httpPort', 'streamerPort']) if (!Number.isInteger(config[key]) || config[key] < 1 || config[key] > 65535) throw Error('端口必须是1至65535的整数：' + key);
  if (config.httpPort === config.streamerPort) throw Error('网页端口和信令端口必须不同');
  if (!['shared', 'independent'].includes(config.mode)) throw Error('模式必须为 shared 或 independent');
  if (typeof config.showWindow !== 'boolean') throw Error('showWindow 必须是布尔值');
  if (typeof config.adaptiveResourceBudget !== 'boolean') throw Error('adaptiveResourceBudget 必须是布尔值');
  if (!['balanced', 'clear', 'ultra', 'custom'].includes(config.qualityProfile)) throw Error('无效画质档位');
  if (![config.width, config.height].every(n => Number.isInteger(n) && n >= 320 && n <= 7680)) throw Error('分辨率必须为320至7680的整数');
  if (!Number.isInteger(config.fps) || config.fps < 15 || config.fps > 120) throw Error('帧率必须为15至120');
  if (![config.minBitrateMbps, config.startBitrateMbps, config.maxBitrateMbps].every(n => Number.isFinite(n) && n >= 1 && n <= 200) || config.minBitrateMbps > config.startBitrateMbps || config.startBitrateMbps > config.maxBitrateMbps) throw Error('码率必须满足 1 ≤ 最小 ≤ 初始 ≤ 最大 ≤ 200 Mbps');
  if (typeof config.executablePath !== 'string' || !path.isAbsolute(config.executablePath) || !fs.statSync(config.executablePath, { throwIfNoEntry: false })?.isFile()) throw Error('UE可执行文件不存在，请选择完整EXE路径');
  return validateNetwork(config);
}
function buildUEArgs(c, id, controlDir, streamerToken) {
  const quality = c.qualityProfile || 'clear';
  const args = ['-PixelStreamingURL=ws://127.0.0.1:' + c.streamerPort + (streamerToken ? '/?streamerToken=' + encodeURIComponent(streamerToken) : ''), '-PixelStreamingID=' + id,
    '-ResX=' + c.width, '-ResY=' + c.height, '-ForceRes', '-AudioMixer', '-Unattended', '-NoSplash', '-StdOut', '-FullStdOutLogOutput',
    c.showWindow ? '-Windowed' : '-RenderOffscreen', '-PixelStreamingWebRTCFps=' + c.fps,
    '-PixelStreamingWebRTCMinBitrate=' + c.minBitrateMbps * 1000000, '-PixelStreamingWebRTCStartBitrate=' + c.startBitrateMbps * 1000000,
    '-PixelStreamingWebRTCMaxBitrate=' + c.maxBitrateMbps * 1000000, '-PixelStreamingEncoderMaxBitrate=' + c.maxBitrateMbps * 1000000,
    '-PixelStreamingWebRTCMinPort=50000', '-PixelStreamingWebRTCMaxPort=50199', '-PixelStreamingWebRTCDegradationPreference=MAINTAIN_RESOLUTION',
    '-PixelStreamingEncoderPreset=' + (quality === 'balanced' ? 'DEFAULT' : 'HIGH_QUALITY'),
    '-PixelStreamingEncoderRateControl=CBR', '-PixelStreamingEncoderMinQP=0',
    '-PixelStreamingEncoderMaxQP=' + (quality === 'ultra' ? 22 : quality === 'balanced' ? 36 : 26),
    '-ExecCmds=t.MaxFPS ' + c.fps + ',r.ScreenPercentage 100,r.DynamicRes.OperationMode 0,r.MotionBlurQuality 0,r.DepthOfFieldQuality 0,r.Tonemapper.Sharpen 0.3'];
  if (controlDir) args.push('-GHSStreamControlDir=' + controlDir);
  return args;
}
const send = (ws, message) => { if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message)); };
function parseMessage(bytes, side) {
  const m = JSON.parse(bytes);
  if (!m || typeof m !== 'object' || Array.isArray(m) || typeof m.type !== 'string') throw Error('Expected message object');
  const allowed = side === 'player' ? ['listStreamers', 'subscribe', 'unsubscribe', 'offer', 'answer', 'iceCandidate', 'ping', 'pong'] : ['endpointId', 'offer', 'answer', 'iceCandidate', 'disconnectPlayer', 'ping', 'pong'];
  if (!allowed.includes(m.type)) throw Error('Unsupported message type');
  if (m.type === 'subscribe' && (typeof m.streamerId !== 'string' || m.streamerId.length > 100)) throw Error('Invalid streamer ID');
  if (m.type === 'endpointId' && (typeof m.id !== 'string' || m.id.length > 100)) throw Error('Invalid endpoint ID');
  if (['offer', 'answer'].includes(m.type) && (typeof m.sdp !== 'string' || m.sdp.length > 256000)) throw Error('Invalid SDP');
  if (m.type === 'iceCandidate') {
    const c = m.candidate;
    if (!c || typeof c !== 'object' || Array.isArray(c) || typeof c.candidate !== 'string' || c.candidate.length > 16000 || (c.sdpMid != null && typeof c.sdpMid !== 'string') || (c.sdpMLineIndex != null && (!Number.isInteger(c.sdpMLineIndex) || c.sdpMLineIndex < 0 || c.sdpMLineIndex > 65535))) throw Error('Invalid ICE candidate');
  }
  if (side === 'streamer' && ['offer', 'answer', 'iceCandidate', 'disconnectPlayer'].includes(m.type) && (typeof m.playerId !== 'string' || !/^\d{1,16}$/.test(m.playerId))) throw Error('Invalid player ID');
  if (['ping', 'pong'].includes(m.type) && m.time !== undefined && !Number.isFinite(m.time)) throw Error('Invalid ping timestamp');
  return m;
}
function json(res, code, value) { const body = JSON.stringify(value); res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'Content-Length': Buffer.byteLength(body), 'X-Content-Type-Options': 'nosniff' }); res.end(body); }
async function readJSON(req) { let body = ''; for await (const chunk of req) { body += chunk; if (body.length > 4096) throw Error('请求过大'); } return body ? JSON.parse(body) : {}; }
function listen(server, port, host) { return new Promise((resolve, reject) => { const onError = e => { server.removeListener('listening', onListen); reject(Error(`端口 ${port} 启动失败 (${e.code})：${e.message}`)); }; const onListen = () => { server.removeListener('error', onError); resolve(); }; server.once('error', onError); server.once('listening', onListen); server.listen({ port, host, exclusive: true }); }); }
function closeServer(server) { return new Promise(resolve => { if (!server.listening) return resolve(); server.close(resolve); server.closeAllConnections?.(); }); }

function createService(rawConfig, options = {}) {
  const config = validateConfig(rawConfig);
  const token = options.token || process.env.GHS_CONTROL_TOKEN;
  if (!token || token.length < 24) throw Error('缺少有效的 GHS_CONTROL_TOKEN（至少24字符）');
  const playerRoot = path.resolve(options.playerRoot || path.join(__dirname, '../player'));
  const sessions = new Map(), viewers = new Map(), instances = new Map(), authAttempts = new Map();
  const ice = iceServers(config), scheme = config.tlsCertPath ? 'https' : 'http';
  const logs = []; let state = 'starting', message = '正在启动服务', order = 0, nextPlayer = 1, stopPromise, admission = Promise.resolve(), heartbeat, budgetTimer;
  const budgetPolicy = new BudgetPolicy(config);
  const reconnectGraceMs = options.reconnectGraceMs ?? 8000;
  const spawnProcess = options.spawnProcess || spawn;
  const cloudAuthQueue = [];
  let cloudAuthTokens = 10, cloudAuthUpdated = performance.now(), cloudAuthTimer;
  function drainCloudAuth() {
    clearTimeout(cloudAuthTimer); cloudAuthTimer = undefined;
    const now = performance.now();
    cloudAuthTokens = Math.min(10, cloudAuthTokens + (now - cloudAuthUpdated) / 200);
    cloudAuthUpdated = now;
    while (cloudAuthQueue.length) {
      const next = cloudAuthQueue[0];
      if (now >= next.expires) { cloudAuthQueue.shift().finish(429); continue; }
      if (cloudAuthTokens < 1) break;
      cloudAuthTokens--; cloudAuthQueue.shift().finish(200);
    }
    if (cloudAuthQueue.length) {
      const wait = Math.min((1 - cloudAuthTokens) * 200, cloudAuthQueue[0].expires - now);
      cloudAuthTimer = setTimeout(drainCloudAuth, Math.max(1, Math.ceil(wait)));
      cloudAuthTimer.unref();
    }
  }
  function reserveCloudAuth(res) {
    if (res.destroyed) return Promise.resolve(0);
    if (state === 'stopping' || state === 'stopped') return Promise.resolve(503);
    drainCloudAuth();
    if (cloudAuthQueue.length >= 20) return Promise.resolve(429);
    return new Promise(resolve => {
      const cancel = () => { const i = cloudAuthQueue.indexOf(entry); if (i >= 0) { cloudAuthQueue.splice(i, 1); entry.finish(0); drainCloudAuth(); } };
      const entry = { expires: performance.now() + 4000, finish(code) { res.removeListener('close', cancel); resolve(code); } };
      res.once('close', cancel); cloudAuthQueue.push(entry); drainCloudAuth();
    });
  }
  function log(text) { let safe = String(text); for (const secret of [config.accessCode, config.turnPassword, config.turnUsername, config.turnUrl, config.stunUrl, ...[...instances.values()].map(i => i.streamerToken)]) if (secret) { safe = safe.split(JSON.stringify(secret).slice(1, -1)).join('[已隐藏]'); safe = safe.split(secret).join('[已隐藏]'); } const line = new Date().toISOString() + ' ' + safe.slice(0, 1500); logs.push(line); if (logs.length > 100) logs.shift(); options.onLog?.(line); }
  function urls() { if (config.networkMode === 'public') return [config.publicUrl + '/']; const ips = Object.values(os.networkInterfaces()).flat().filter(x => x && x.family === 'IPv4' && !x.internal).map(x => x.address); return [...new Set(ips)].map(ip => `${scheme}://${ip}:${config.httpPort}/`); }
  function status() { return { state, message, mode: config.mode, networkMode: config.networkMode, publicUrl: config.publicUrl, tlsEnabled: !!config.tlsCertPath, trustProxy: config.trustProxy, externalTlsTermination: config.externalTlsTermination, qualityProfile: config.qualityProfile, adaptiveResourceBudget: config.adaptiveResourceBudget, viewerCount: viewers.size, maxViewers: config.maxViewers,
    viewers: [...viewers.values()].map(v => ({ playerId: v.playerId, displayName: v.displayName, address: v.address, userAgent: v.userAgent, connectedAt: v.connectedAt, state: !v.ws ? 'reconnecting' : v.subscribed ? 'connected' : instances.get(v.instanceId)?.state === 'failed' ? 'failed' : 'starting', instanceId: v.instanceId })),
    instances: [...instances.values()].map(i => ({ id: i.id, pid: i.child?.pid || null, state: i.state, targetFps: i.targetFps, actualFps: i.metrics?.actualFps ?? null, gpuMs: i.metrics?.gpuMs ?? null, budgetAcknowledged: !!i.metrics && i.metrics.sequence === i.sequence, screenPercentage: i.metrics?.screenPercentage ?? null })), urls: urls(), localUrl: `${scheme}://127.0.0.1:${config.httpPort}/`, logs: [...logs] }; }
  function rebalance() {
    if (state === 'stopping' || state === 'stopped') return;
    const active = [...instances.values()].filter(i => !['stopping', 'failed'].includes(i.state));
    for (const i of active) i.metrics = readMetrics(i.controlDir);
    const budgetFps = budgetPolicy.update(active.map(i => i.readyAt && Date.now() - i.readyAt >= 5000 && i.metrics?.sequence === i.sequence ? { ...i.metrics, id: i.id } : null));
    for (const i of active) if (i.targetFps !== budgetFps || !i.sequence) {
      try { writeBudget(i.controlDir, config, budgetFps, i.sequence + 1); i.sequence++; i.targetFps = budgetFps; }
      catch (e) { log('写入实例资源预算失败：' + e.message); }
    }
  }
  const sameOrigin = req => requestSameOrigin(req, config);
  function publicSession(s) { return { token: s.token, evicted: !!s.evicted, message: s.evicted ? EVICTED : '', mode: config.mode, maxViewers: config.maxViewers, width: config.width, height: config.height, fps: config.fps, minBitrateMbps: config.minBitrateMbps, maxBitrateMbps: config.maxBitrateMbps }; }
  function pruneSessions() { const now = Date.now(); for (const [id, s] of sessions) if (!viewers.has(id) && now - s.created > 12 * 60 * 60 * 1000) sessions.delete(id); for (const [ip, attempt] of authAttempts) if (now > attempt.until) authAttempts.delete(ip); }
  const handlePublic = async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      if (req.method === 'GET' && url.pathname === '/health') return json(res, 200, { state, mode: config.mode, viewerCount: viewers.size, maxViewers: config.maxViewers, accessRequired: config.networkMode === 'public' });
      if (req.method === 'POST' && url.pathname === '/api/session') {
        if (!sameOrigin(req)) return json(res, 403, { error: '仅允许已配置地址的同源连接' });
        const body = await readJSON(req); if (!body || typeof body !== 'object' || Array.isArray(body)) return json(res, 400, { error: '无效会话请求' });
        pruneSessions();
        if (typeof body.token === 'string' && sessions.has(body.token)) return json(res, 200, publicSession(sessions.get(body.token)));
        if (body.token) return json(res, 409, { error: '会话已过期，请重新进入', expired: true });
        if (config.networkMode === 'public') {
          if (!body.accessCode) return json(res, 401, { error: '请输入访问码', accessRequired: true });
          let ip, attempt;
          if (config.externalTlsTermination) {
            // ALB peers share socket IPs. Bound every code comparison, including
            // correct codes, without trusting XFF or locking the whole ALB out.
            const permit = await reserveCloudAuth(res);
            if (res.destroyed || !permit) return;
            if (permit !== 200) { res.setHeader('Retry-After', '1'); return json(res, permit, { error: '访问验证繁忙，请稍后重试' }); }
          } else {
            ip = clientAddress(req, config); attempt = authAttempts.get(ip);
            if (attempt?.count >= 20) return json(res, 429, { error: '访问码尝试过多，请5分钟后重试' });
          }
          if (!secretEqual(body.accessCode, config.accessCode)) {
            if (!config.externalTlsTermination) {
              if (!attempt && authAttempts.size >= 10000) return json(res, 429, { error: '请求过多，请稍后重试' });
              authAttempts.set(ip, { count: (attempt?.count || 0) + 1, until: attempt?.until || Date.now() + 300000 });
            }
            return json(res, 401, { error: '请输入有效的访问码', accessRequired: true });
          }
          if (!config.externalTlsTermination) authAttempts.delete(ip);
        }
        if (sessions.size >= 10000) return json(res, 503, { error: '会话数量达到上限，请稍后重试' });
        const displayName = typeof body.displayName === 'string' ? body.displayName.replace(/[\x00-\x1f\x7f]/g, '').trim().slice(0, 40) : '';
        const session = { token: crypto.randomBytes(24).toString('hex'), created: Date.now(), evicted: false, displayName };
        sessions.set(session.token, session); return json(res, 200, publicSession(session));
      }
      if (req.method !== 'GET' && req.method !== 'HEAD') return json(res, 405, { error: '不支持的请求' });
      // Only this static root is visible. Decode first; reject slash/backslash traversal and symlinks.
      let name; try { name = decodeURIComponent(url.pathname); } catch { return json(res, 404, {}); }
      if (name === '/') name = '/index.html';
      if (name.includes('\0') || name.includes('\\') || name.split('/').includes('..')) return json(res, 404, {});
      const filename = path.resolve(playerRoot, '.' + name);
      if (!filename.startsWith(playerRoot + path.sep)) return json(res, 404, {});
      const stat = await fs.promises.stat(filename).catch(() => null);
      if (!stat?.isFile()) return json(res, 404, {});
      const real = await fs.promises.realpath(filename);
      if (!real.toLowerCase().startsWith(playerRoot.toLowerCase() + path.sep)) return json(res, 404, {});
      const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.md': 'text/plain; charset=utf-8', '.json': 'application/json; charset=utf-8', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.svg': 'image/svg+xml' };
      res.writeHead(200, { 'Content-Type': types[path.extname(filename).toLowerCase()] || 'application/octet-stream', 'Content-Length': stat.size, 'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer' });
      if (req.method === 'HEAD') return res.end();
      fs.createReadStream(filename).on('error', () => res.destroy()).pipe(res);
    } catch (e) { if (!res.headersSent) json(res, 400, { error: '无效请求' }); else res.destroy(); }
  };
  const publicServer = config.tlsCertPath ? https.createServer({ cert: fs.readFileSync(config.tlsCertPath), key: fs.readFileSync(config.tlsKeyPath), minVersion: 'TLSv1.2' }, handlePublic) : http.createServer(handlePublic);
  publicServer.requestTimeout = 15000; publicServer.headersTimeout = 10000;
  const streamerServer = http.createServer((_req, res) => json(res, 404, {}));
  const controlServer = http.createServer(async (req, res) => {
    const supplied = Buffer.from(req.headers.authorization || ''); const expected = Buffer.from('Bearer ' + token);
    if (supplied.length !== expected.length || !crypto.timingSafeEqual(supplied, expected)) return json(res, 401, { error: '未授权' });
    if (req.method === 'GET' && req.url === '/status') return json(res, 200, status());
    if (req.method === 'POST' && req.url === '/disconnect') {
      try {
        const body = await readJSON(req);
        if (!body || typeof body.playerId !== 'string' || !/^\d{1,16}$/.test(body.playerId)) return json(res, 400, { error: '无效访问者编号' });
        let found = false;
        admission = admission.then(async () => {
          const viewer = [...viewers.values()].find(v => v.playerId === body.playerId);
          if (!viewer) return;
          found = true; sessions.get(viewer.token).evicted = true;
          send(viewer.ws, { type: 'ghsKicked', message: EVICTED, reconnect: false }); viewer.ws?.close(4003, 'Disconnected by administrator');
          await release(viewer, '管理员断开');
        });
        await admission;
        return json(res, found ? 200 : 404, found ? { disconnected: true, playerId: body.playerId } : { error: '访问者已离线' });
      } catch { admission = admission.catch(() => {}); return json(res, 400, { error: '断开连接失败' }); }
    }
    if (req.method === 'POST' && req.url === '/stop') { json(res, 200, { state: 'stopping' }); setImmediate(() => stop().then(() => options.onStopped?.())); return; }
    json(res, 404, {});
  });
  const playersWS = new WebSocketServer({ noServer: true, maxPayload: 1024 * 1024, perMessageDeflate: false });
  const streamersWS = new WebSocketServer({ noServer: true, maxPayload: 1024 * 1024, perMessageDeflate: false });
  publicServer.on('upgrade', (req, socket, head) => {
    let url; try { url = new URL(req.url, 'http://localhost'); } catch { return socket.destroy(); }
    if (state === 'stopping' || state === 'stopped' || url.pathname !== '/ws' || !sameOrigin(req) || !sessions.has(url.searchParams.get('token'))) { socket.write('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); return socket.destroy(); }
    playersWS.handleUpgrade(req, socket, head, ws => {
      ws.alive = true; ws.on('pong', () => { ws.alive = true; }); ws.on('error', () => {});
      ws.pendingMessages = []; ws.bufferMessage = bytes => { if (ws.pendingMessages.length < 16) ws.pendingMessages.push(bytes); else ws.close(1008, 'Too many early messages'); }; ws.on('message', ws.bufferMessage);
      admission = admission.then(() => admit(ws, sessions.get(url.searchParams.get('token')), req)).catch(e => { log('接入失败：' + e.message); send(ws, { type: 'ghsInstanceFailed', message: e.message }); ws.close(1011, 'Admission failed'); });
    });
  });
  streamerServer.on('upgrade', (req, socket, head) => {
    // Native UE 5.4 libwebsockets supplies a loopback Origin; browsers must not
    // bootstrap onto this local control channel, even from a malicious website.
    const origins = [undefined, '127.0.0.1', 'http://127.0.0.1', 'http://127.0.0.1:' + config.streamerPort];
    let url; try { url = new URL(req.url, 'http://localhost'); } catch { return socket.destroy(); }
    const suppliedToken = url.searchParams.get('streamerToken');
    const expectedInstance = [...instances.values()].find(i => suppliedToken && secretEqual(suppliedToken, i.streamerToken));
    if (!origins.includes(req.headers.origin) || !expectedInstance || ['stopping', 'failed'].includes(expectedInstance.state) || ['stopping', 'stopped'].includes(state)) {
      socket.write('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); return socket.destroy();
    }
    streamersWS.handleUpgrade(req, socket, head, ws => {
    ws.alive = true; ws.on('pong', () => { ws.alive = true; }); ws.on('error', () => {}); let instance;
    const identityTimeout = setTimeout(() => { if (!instance) ws.close(1008, 'Identification required'); }, 10000); identityTimeout.unref();
    send(ws, { type: 'identify' });
    ws.on('message', bytes => {
      let m; try { m = parseMessage(bytes, 'streamer'); } catch { return ws.close(1007, 'Invalid signalling message'); }
      if (m.type === 'endpointId') {
        const candidate = instances.get(m.id);
        if (!candidate || candidate !== expectedInstance || candidate.state === 'stopping' || candidate.state === 'failed' || (candidate.ws && candidate.ws !== ws)) return ws.close(1008, 'Unknown or duplicate streamer');
        instance = candidate; instance.ws = ws; instance.state = 'ready'; instance.readyAt = Date.now(); clearTimeout(instance.startTimer); clearTimeout(identityTimeout);
        send(ws, { type: 'config', peerConnectionOptions: { iceServers: ice } });
        state = 'running'; message = '像素流服务运行中'; log('UE信令已连接：' + instance.id);
        for (const viewer of viewers.values()) if (viewer.instanceId === instance.id) { notifyStage(viewer, 'streamerReady', '场景已启动，正在建立视频连接'); sendStreamerList(viewer); }
        return;
      }
      if (m.type === 'ping') return send(ws, { type: 'pong', time: m.time });
      if (!instance) return;
      const viewer = [...viewers.values()].find(v => v.playerId === String(m.playerId) && v.instanceId === instance.id && v.subscribed);
      if (!viewer) return;
      if (m.type === 'disconnectPlayer') { send(viewer.ws, { type: 'ghsInstanceFailed', message: '场景已断开当前视频连接' }); viewer.ws?.close(1011, 'Streamer disconnected player'); return; }
      if (['offer', 'answer', 'iceCandidate'].includes(m.type)) { const outgoing = { ...m }; delete outgoing.playerId; send(viewer.ws, outgoing); }
    });
    ws.on('close', () => {
      clearTimeout(identityTimeout);
      if (!instance || instance.ws !== ws) return;
      instance.ws = null;
      if (!['stopping', 'failed'].includes(instance.state) && state !== 'stopping') { instance.state = 'reconnecting'; log('UE信令连接断开：' + instance.id); for (const viewer of viewers.values()) if (viewer.instanceId === instance.id) { viewer.subscribed = false; notifyStage(viewer, 'waitingStreamer', '场景信令连接断开，等待恢复'); } }
    });
    });
  });
  function notifyStage(viewer, stage, text) { send(viewer.ws, { type: 'ghsStage', stage, message: text, mode: config.mode }); }
  function sendStreamerList(viewer) { const i = instances.get(viewer.instanceId); send(viewer.ws, { type: 'streamerList', ids: i?.state === 'ready' ? [i.id] : [] }); }
  function broadcastCount() { for (const v of viewers.values()) send(v.ws, { type: 'playerCount', count: viewers.size }); }
  function unsubscribe(v) { if (v.subscribed) send(instances.get(v.instanceId)?.ws, { type: 'playerDisconnected', playerId: v.playerId }); v.subscribed = false; }
  async function release(viewer, reason) {
    if (viewers.get(viewer.token) !== viewer) return;
    clearTimeout(viewer.disconnectTimer); unsubscribe(viewer); viewers.delete(viewer.token);
    if (config.mode === 'independent') await stopInstance(instances.get(viewer.instanceId));
    log('访问者离开：' + viewer.playerId + '，' + reason); broadcastCount();
  }
  async function admit(ws, session, req) {
    if (session.evicted) { send(ws, { type: 'ghsKicked', message: EVICTED, reconnect: false }); return ws.close(4003, 'Disconnected by administrator'); }
    if (ws.readyState !== WebSocket.OPEN || ['stopping', 'stopped'].includes(state)) return ws.close(1001, 'Service stopping');
    let viewer = viewers.get(session.token);
    if (!viewer) {
      if (viewers.size >= config.maxViewers) {
        send(ws, { type: 'ghsFull', message: `当前 ${config.maxViewers} 个访问名额已满，请稍后重新进入。`, reconnect: false });
        return ws.close(4004, 'Service at capacity');
      }
      // Reclaiming a process is asynchronous; a tab may have closed while we waited.
      if (ws.readyState !== WebSocket.OPEN || ['stopping', 'stopped'].includes(state)) return ws.close(1001, 'Connection ended during admission');
      viewer = { displayName: session.displayName, address: clientAddress(req, config), userAgent: String(req.headers['user-agent'] || '').replace(/[\x00-\x1f\x7f]/g, '').slice(0, 240), connectedAt: new Date().toISOString(), token: session.token, playerId: String(nextPlayer++), order: ++order, instanceId: config.mode === 'shared' ? 'shared' : 'viewer-' + crypto.randomBytes(6).toString('hex') };
      viewers.set(session.token, viewer);
      if (config.mode === 'independent') startInstance(viewer.instanceId);
    }
    clearTimeout(viewer.disconnectTimer); viewer.disconnectGeneration = (viewer.disconnectGeneration || 0) + 1; unsubscribe(viewer);
    const previous = viewer.ws; viewer.ws = ws;
    if (previous && previous !== ws) { send(previous, { type: 'ghsSessionReplaced', message: '同一会话已在其他标签页连接，本页已停止自动重连。', reconnect: false }); previous.close(4002, 'Session reconnected'); }
    send(ws, { type: 'ghsAdmission', playerId: viewer.playerId, mode: config.mode, instanceId: viewer.instanceId, maxViewers: config.maxViewers });
    send(ws, { type: 'config', peerConnectionOptions: { iceServers: ice } });
    const instance = instances.get(viewer.instanceId);
    if (instance?.state === 'failed') send(ws, { type: 'ghsInstanceFailed', message: 'UE场景启动失败或意外退出，请在启动器停止后重新开启' });
    else notifyStage(viewer, instance?.state === 'ready' ? 'streamerReady' : 'waitingStreamer', instance?.state === 'ready' ? '场景已就绪，正在建立视频连接' : '正在启动UE场景，等待信令连接');
    log('访问者接入：' + viewer.playerId); broadcastCount();
    ws.on('message', bytes => {
      if (viewer.ws !== ws || viewers.get(viewer.token) !== viewer || session.evicted) return;
      let m; try { m = parseMessage(bytes, 'player'); } catch { return ws.close(1007, 'Invalid signalling message'); }
      const instance = instances.get(viewer.instanceId);
      if (m.type === 'listStreamers') return sendStreamerList(viewer);
      if (m.type === 'ping') return send(ws, { type: 'pong', time: m.time });
      if (m.type === 'subscribe') {
        if (m.streamerId !== viewer.instanceId || instance?.state !== 'ready') return send(ws, { type: 'warning', message: '所请求的实例不可用' });
        if (!viewer.subscribed) { viewer.subscribed = true; send(instance.ws, { type: 'playerConnected', playerId: viewer.playerId, dataChannel: true, sfu: false, sendOffer: true }); }
        return;
      }
      if (m.type === 'unsubscribe') return unsubscribe(viewer);
      if (viewer.subscribed && instance?.ws && ['offer', 'answer', 'iceCandidate'].includes(m.type)) send(instance.ws, { ...m, playerId: viewer.playerId });
    });
    ws.removeListener('message', ws.bufferMessage); for (const bytes of ws.pendingMessages) ws.emit('message', bytes); ws.pendingMessages = [];
    ws.on('close', () => {
      if (viewer.ws !== ws || viewers.get(viewer.token) !== viewer) return;
      viewer.ws = null; unsubscribe(viewer);
      const generation = ++viewer.disconnectGeneration;
      viewer.disconnectTimer = setTimeout(() => { admission = admission.then(() => { if (viewer.disconnectGeneration === generation && !viewer.ws) return release(viewer, '连接断开'); }).catch(e => log(e.message)); }, reconnectGraceMs);
      viewer.disconnectTimer.unref();
    });
  }
  function startInstance(id) {
    const instance = { id, streamerToken: crypto.randomBytes(32).toString('hex'), state: 'starting', child: null, ws: null, sequence: 0, targetFps: null, controlDir: null }; instances.set(id, instance);
    const failed = detail => {
      if (instance.state === 'stopping' || state === 'stopping' || state === 'stopped') return;
      clearTimeout(instance.startTimer); instance.state = 'failed'; state = 'degraded'; message = 'UE实例失败：' + detail; log(message);
      instance.ws?.close(1011, 'UE exited');
      rebalance();
      for (const v of viewers.values()) if (v.instanceId === id) { v.subscribed = false; send(v.ws, { type: 'ghsInstanceFailed', message }); }
    };
    try {
      const controlRoot = options.controlRoot || os.tmpdir(); fs.mkdirSync(controlRoot, { recursive: true });
      instance.controlDir = fs.mkdtempSync(path.join(controlRoot, 'ghs-instance-'));
      rebalance();
      // UE5.4 snapshots the capture ceiling into new RTP senders. Keep it at the configured
      // maximum; the private bridge limits rendering so existing peers can later recover.
      const child = spawnProcess(config.executablePath, buildUEArgs(config, id, instance.controlDir, instance.streamerToken), { cwd: path.dirname(config.executablePath), shell: false, windowsHide: !config.showWindow, stdio: ['ignore', 'pipe', 'pipe'] });
      instance.child = child; log('启动UE实例 ' + id + '，PID ' + child.pid);
      for (const stream of [child.stdout, child.stderr]) stream?.on('data', bytes => { const lines = bytes.toString().split(/\r?\n/).filter(Boolean); for (const line of lines.slice(-6)) if (/error|fatal|PixelStreaming|Signalling|Warning/i.test(line)) log('[' + id + '] ' + line); });
      child.once('error', e => failed('启动失败：' + e.message)); child.once('exit', (code, signal) => failed('实例 ' + id + ' 退出（' + (code ?? signal) + '）'));
      instance.startTimer = setTimeout(() => { failed('实例 ' + id + ' 在120秒内未连接信令服务器'); stopProcess(instance).catch(e => log(e.message)); }, 120000); instance.startTimer.unref();
    } catch (e) { failed('启动失败：' + e.message); }
    return instance;
  }
  async function stopProcess(instance) {
    const child = instance?.child;
    if (!child?.pid || child.exitCode !== null || child.signalCode !== null) return;
    // Only a still-owned child PID is targeted. The launcher JobObject is the final tree cleanup guard.
    if (process.platform === 'win32') await new Promise(resolve => { const killer = spawn(path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'taskkill.exe'), ['/PID', String(child.pid), '/T', '/F'], { shell: false, windowsHide: true, stdio: 'ignore' }); killer.once('error', () => { child.kill(); resolve(); }); killer.once('exit', code => { if (code !== 0) child.kill(); resolve(); }); });
    else child.kill('SIGTERM');
    if (child.exitCode === null && child.signalCode === null) await new Promise((resolve, reject) => { const forceTimer = setTimeout(() => child.kill('SIGKILL'), 3000); const failTimer = setTimeout(() => reject(Error('无法确认自有UE进程退出：' + child.pid)), 8000); child.once('exit', () => { clearTimeout(forceTimer); clearTimeout(failTimer); resolve(); }); });
  }
  async function stopInstance(instance) { if (!instance) return; instance.state = 'stopping'; clearTimeout(instance.startTimer); instance.ws?.terminate(); await stopProcess(instance); instances.delete(instance.id); if (instance.controlDir) fs.rmSync(instance.controlDir, { recursive: true, force: true }); rebalance(); }
  async function start() {
    try {
      await listen(streamerServer, config.streamerPort, '127.0.0.1'); await listen(publicServer, config.httpPort, config.trustProxy ? '127.0.0.1' : '0.0.0.0'); await listen(controlServer, 0, '127.0.0.1');
      state = 'running'; message = '服务已启动'; log('网页服务 ' + scheme + '://' + (config.trustProxy ? '127.0.0.1' : '0.0.0.0') + ':' + config.httpPort + '，UE信令仅本机:' + config.streamerPort);
      heartbeat = setInterval(() => { pruneSessions(); for (const server of [playersWS, streamersWS]) for (const ws of server.clients) { if (!ws.alive) { ws.terminate(); continue; } ws.alive = false; ws.ping(); } }, 10000); heartbeat.unref();
      budgetTimer = setInterval(rebalance, 2000); budgetTimer.unref();
      if (config.mode === 'shared') startInstance('shared');
      return status();
    } catch (e) { log(e.message); await stop(); throw e; }
  }
  function stop() {
    if (stopPromise) return stopPromise;
    stopPromise = (async () => {
      state = 'stopping'; message = '正在清理本服务的场景实例'; clearInterval(heartbeat); clearInterval(budgetTimer);
      clearTimeout(cloudAuthTimer); cloudAuthTimer = undefined;
      for (const pending of cloudAuthQueue.splice(0)) pending.finish(503);
      await admission;
      for (const v of viewers.values()) { clearTimeout(v.disconnectTimer); send(v.ws, { type: 'ghsShutdown', message: '启动器已停止服务', reconnect: false }); }
      for (const server of [playersWS, streamersWS]) for (const ws of server.clients) ws.terminate();
      viewers.clear(); await Promise.all([...instances.values()].map(stopInstance));
      await Promise.all([publicServer, streamerServer, controlServer].map(closeServer));
      playersWS.close(); streamersWS.close(); state = 'stopped'; message = '服务已停止'; log(message);
    })(); return stopPromise;
  }
  return { start, stop, status, get controlPort() { return controlServer.address()?.port; }, config };
}
module.exports = { createService, validateConfig, buildUEArgs };
