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
const { BudgetPolicy, readMetrics, writeBudget, freshMetrics, standbyHeadroom } = require('./resource-budget');
const { loadMediaAddress, publicMediaCandidate } = require('./media-address');
const { createGpuCapacityProbe } = require('./gpu-capacity');

const EVICTED = '管理员已断开此连接，已停止自动重连。需要再次访问时请主动重新进入。';
const DEFAULTS = { ...NETWORK_DEFAULTS, httpPort: 8080, streamerPort: 8888, showWindow: false, width: 1920, height: 1080, mode: 'shared', fps: 60, fixedFps: true, encoderAsync: true, encoder: 'NVIDIA', minBitrateMbps: 1, startBitrateMbps: 8, maxBitrateMbps: 24, qualityProfile: 'clear', adaptiveResourceBudget: false, warmStandbyEnabled: false };
function validateConfig(raw) {
  const config = { ...DEFAULTS, ...raw };
  if (Object.hasOwn(raw, 'fps') && !Object.hasOwn(raw, 'fixedFps')) { config.fixedFps = false; if (!Object.hasOwn(raw, 'adaptiveResourceBudget')) config.adaptiveResourceBudget = true; }
  for (const key of ['httpPort', 'streamerPort']) if (!Number.isInteger(config[key]) || config[key] < 1 || config[key] > 65535) throw Error('端口必须是1至65535的整数：' + key);
  if (config.httpPort === config.streamerPort) throw Error('网页端口和信令端口必须不同');
  if (!['shared', 'independent'].includes(config.mode)) throw Error('模式必须为 shared 或 independent');
  if (typeof config.showWindow !== 'boolean') throw Error('showWindow 必须是布尔值');
  if (typeof config.adaptiveResourceBudget !== 'boolean') throw Error('adaptiveResourceBudget 必须是布尔值');
  for (const key of ['fixedFps', 'encoderAsync', 'warmStandbyEnabled']) if (typeof config[key] !== 'boolean') throw Error(key + ' 必须是布尔值');
  if (!['NVIDIA', 'Auto'].includes(config.encoder)) throw Error('编码器必须为 NVIDIA 或 Auto');
  if (config.fixedFps && config.fps === 0) throw Error('固定目标帧率必须为15至120');
  if (config.fixedFps && config.adaptiveResourceBudget) throw Error('固定目标帧率与自动分配资源不能同时启用');
  if (!['balanced', 'clear', 'ultra', 'custom'].includes(config.qualityProfile)) throw Error('无效画质档位');
  if (![config.width, config.height].every(n => Number.isInteger(n) && n >= 320 && n <= 7680)) throw Error('分辨率必须为320至7680的整数');
  if (!Number.isInteger(config.fps) || (config.fps !== 0 && (config.fps < 15 || config.fps > 120))) throw Error('帧率必须为0（无固定上限）或15至120');
  if (![config.minBitrateMbps, config.startBitrateMbps, config.maxBitrateMbps].every(n => Number.isFinite(n) && n >= 1 && n <= 200) || config.minBitrateMbps > config.startBitrateMbps || config.startBitrateMbps > config.maxBitrateMbps) throw Error('码率必须满足 1 ≤ 最小 ≤ 初始 ≤ 最大 ≤ 200 Mbps');
  if (typeof config.executablePath !== 'string' || !path.isAbsolute(config.executablePath) || !fs.statSync(config.executablePath, { throwIfNoEntry: false })?.isFile()) throw Error('UE可执行文件不存在，请选择完整EXE路径');
  return validateNetwork(config);
}
function buildUEArgs(c, id, controlDir, streamerToken) {
  const quality = c.qualityProfile || 'clear';
  const args = ['-PixelStreamingConnectionURL=ws://127.0.0.1:' + c.streamerPort + (streamerToken ? '/?streamerToken=' + encodeURIComponent(streamerToken) : ''), '-PixelStreamingID=' + id,
    '-ResX=' + c.width, '-ResY=' + c.height, '-ForceRes', '-AudioMixer', '-Unattended', '-NoSplash', '-NoVSync', '-StdOut', '-FullStdOutLogOutput',
    c.showWindow ? '-Windowed' : '-RenderOffscreen', '-PixelStreamingWebRTCFps=' + (c.fps > 0 ? c.fps : 120),
    '-PixelStreamingWebRTCMinBitrate=' + c.minBitrateMbps * 1000000, '-PixelStreamingWebRTCStartBitrate=' + c.startBitrateMbps * 1000000,
    '-PixelStreamingWebRTCMaxBitrate=' + c.maxBitrateMbps * 1000000,
    '-PixelStreamingWebRTCMinPort=50000', '-PixelStreamingWebRTCMaxPort=50199',
    '-PixelStreamingEncoderQualityPreset=' + (quality === 'balanced' ? 'DEFAULT' : 'HIGH_QUALITY'),
    '-PixelStreamingEncoderLatencyMode=ULTRA_LOW_LATENCY', '-PixelStreamingEncoderMaxQuality=100',
    '-PixelStreamingEncoderMinQuality=' + (quality === 'ultra' ? 45 : quality === 'clear' ? 37 : 29),
    '-PixelStreamingDecoupleFramerate=' + c.encoderAsync,
    '-PixelStreamingEncoder=' + c.encoder,
    '-ExecCmds=t.MaxFPS ' + c.fps + ',r.VSync 0,r.ScreenPercentage 100,r.DynamicRes.OperationMode 0,r.MotionBlurQuality 0,r.DepthOfFieldQuality 0,r.Tonemapper.Sharpen 0.3'];
  if (c.fixedFps) args.push('-FixedFPS=' + c.fps);
  if (controlDir) args.push('-GHSStreamControlDir=' + controlDir);
  return args;
}
const send = (ws, message) => { if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message)); };
function parseMessage(bytes, side) {
  const m = JSON.parse(bytes);
  if (!m || typeof m !== 'object' || Array.isArray(m) || typeof m.type !== 'string') throw Error('Expected message object');
  const allowed = side === 'player' ? ['listStreamers', 'subscribe', 'unsubscribe', 'layerPreference', 'ghsFirstFrame', 'offer', 'answer', 'iceCandidate', 'ping', 'pong'] : ['endpointId', 'offer', 'answer', 'iceCandidate', 'disconnectPlayer', 'ping', 'pong'];
  if (!allowed.includes(m.type)) throw Error('Unsupported message type');
  if (m.type === 'ghsFirstFrame' && (m.displayed !== true || !Number.isSafeInteger(m.attemptId) || m.attemptId < 1 || ['attemptElapsedMs', 'navigationTotalMs'].some(key => m[key] !== null && (!Number.isFinite(m[key]) || m[key] < 0 || m[key] > (key === 'attemptElapsedMs' ? 900000 : 86400000))))) throw Error('Invalid first-frame report');
  if (m.type === 'subscribe' && (typeof m.streamerId !== 'string' || m.streamerId.length > 100)) throw Error('Invalid streamer ID');
  if (m.type === 'endpointId' && (typeof m.id !== 'string' || m.id.length > 100)) throw Error('Invalid endpoint ID');
  // UE5.8 sends this when initializing PreferredQuality, including direct
  // connections. Match the official int32/string shape; it is SFU-only and
  // never grants routing authority from a client-supplied playerId.
  if (m.type === 'layerPreference' && (['spatialLayer', 'temporalLayer'].some(key => !Number.isInteger(m[key]) || m[key] < -2147483648 || m[key] > 2147483647) || (m.playerId !== undefined && (typeof m.playerId !== 'string' || m.playerId.length > 100)))) throw Error('Invalid layer preference');
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
  const mediaAddress = loadMediaAddress(config.networkMode, options.mediaAddress);
  const logs = []; let state = 'starting', message = '正在启动服务', order = 0, nextPlayer = 1, stopPromise, admission = Promise.resolve(), heartbeat, budgetTimer, startingInstance;
  const budgetPolicy = new BudgetPolicy(config);
  const warmEnabled = config.mode === 'independent' && config.warmStandbyEnabled;
  const readTelemetry = options.readMetrics || readMetrics;
  const gpuCapacity = warmEnabled && !options.resourceSnapshot ? createGpuCapacityProbe({ onLog: log }) : null;
  const resourceSnapshot = options.resourceSnapshot || (() => ({ freeMemoryBytes: os.freemem(), totalMemoryBytes: os.totalmem(), ...gpuCapacity?.snapshot() }));
  const warmStableMs = options.warmStableMs ?? 1000, warmBackoffMs = options.warmBackoffMs ?? 30000, activationTimeoutMs = options.activationTimeoutMs ?? 10000;
  const firstFrameStableMs = options.firstFrameStableMs ?? 3000, resourcePressureMs = options.resourcePressureMs ?? 10000;
  const budgetIntervalMs = options.budgetIntervalMs ?? (warmEnabled ? 500 : 2000);
  for (const value of [warmStableMs, warmBackoffMs, activationTimeoutMs, budgetIntervalMs, firstFrameStableMs, resourcePressureMs]) if (!Number.isInteger(value) || value < 1 || value > 120000) throw Error('无效的预热时序');
  let warmRetryAt = 0, warmFailures = 0, warmBlockedReason = warmEnabled ? '' : config.warmStandbyEnabled ? 'shared' : 'disabled';
  const reconnectGraceMs = options.reconnectGraceMs ?? 8000;
  // Internal clock overrides support bounded loopback lifecycle tests, never
  // public settings. Initialization keeps its original 120-second total budget.
  const startupTimeoutMs = options.startupTimeoutMs ?? 120000;
  const identificationTimeoutMs = options.identificationTimeoutMs ?? 10000;
  const heartbeatIntervalMs = options.heartbeatIntervalMs ?? 10000;
  for (const [value, maximum] of [[startupTimeoutMs, 120000], [identificationTimeoutMs, 10000], [heartbeatIntervalMs, 10000]]) if (!Number.isInteger(value) || value < 1 || value > maximum) throw Error('无效的内部连接期限');
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
  function initializing(i) { return i && instances.get(i.id) === i && i.state === 'starting' && i.child && i.startDeadline > performance.now(); }
  function startupElapsed(i) { return i.startedAt === undefined ? null : Math.max(0, Math.round((i.startEndedAt ?? performance.now()) - i.startedAt)); }
  function identityWait(i) { return i.pendingWS ? Math.max(0, Math.round(performance.now() - i.identityStartedAt)) : i.identityWaitMs ?? null; }
  function logStartup(i, phase, detail = '') { log('GHS_STARTUP id=' + i.id + ' phase=' + phase + ' elapsedMs=' + startupElapsed(i) + ' identityWaitMs=' + identityWait(i) + (detail ? ' ' + detail : '')); }
  function closePendingIdentity(i) {
    clearTimeout(i.identityTimer); i.identityTimer = undefined;
    const ws = i.pendingWS;
    if (ws) { i.identityWaitMs = identityWait(i); i.pendingWS = null; ws.terminate(); }
  }
  function budgetAcknowledged(i, mode = i.budgetMode) { return freshMetrics(i.metrics) && i.metrics.sequence === i.sequence && i.metrics.appliedFps === i.targetFps && (!i.standbyCapable || i.metrics.standbyMode === mode); }
  function stableWarmSample(i) { return budgetAcknowledged(i) && i.metrics.psoActivePrecacheRequests === 0 && i.metrics.actualFps >= (i.targetFps > 0 ? i.targetFps * .85 : 30); }
  function warmAvailable(i) { return !!i.standby && i.state === 'ready' && i.ws?.readyState === WebSocket.OPEN && i.warmReady && i.budgetMode === 'standby' && stableWarmSample(i); }
  function setBudget(i, fps, mode) {
    if (!i.controlDir || (i.targetFps === fps && i.sequence && i.budgetMode === mode)) return;
    writeBudget(i.controlDir, config, fps, i.sequence + 1, i.standbyCapable ? mode : undefined);
    i.sequence++; i.targetFps = fps; i.budgetMode = mode;
  }
  function signalReady(i) {
    i.state = 'ready'; i.startupStage = 'ready'; i.activationPending = false; i.readyAt = Date.now();
    if (![...instances.values()].some(other => !other.standby && other.state === 'failed')) { state = 'running'; message = '像素流服务运行中'; }
    for (const viewer of viewers.values()) if (viewer.instanceId === i.id) { notifyStage(viewer, 'streamerReady', '场景已启动，正在建立视频连接'); sendStreamerList(viewer); }
  }
  function awaitActivation(i) {
    i.state = 'activating'; i.startupStage = 'activating'; i.activationDeadline = performance.now() + activationTimeoutMs;
    for (const viewer of viewers.values()) if (viewer.instanceId === i.id) notifyStage(viewer, 'activatingStreamer', '预热场景已分配，正在恢复渲染帧率');
  }
  function claimStandby() {
    if (!warmEnabled) return null;
    const claimStartedAt = performance.now();
    const i = [...instances.values()].find(candidate => candidate.standby && !['failed', 'stopping', 'reconnecting'].includes(candidate.state));
    if (!i) return null;
    i.metrics = readTelemetry(i.controlDir); const warmHit = warmAvailable(i), now = performance.now();
    const timings = { instanceStartupMs: startupElapsed(i), standbyReadyAgeMs: warmHit ? Math.max(0, Math.round(now - i.warmReadyAt)) : null, admissionToLeaseMs: 0 };
    // A pristine instance can be consumed once, even if a user beats its warmup.
    // Never return a leased process (and its user state) to the standby pool.
    try { setBudget(i, config.fps, 'active'); }
    catch { i.fail?.('无法写入备用场景的激活预算'); return null; }
    i.standby = false; i.standbyState = 'leased'; i.warmReady = false; i.activationPending = true;
    if (i.ws?.readyState === WebSocket.OPEN && i.state === 'ready') awaitActivation(i);
    logStartup(i, 'leased', 'warmHit=' + warmHit);
    timings.admissionToLeaseMs = Math.max(0, Math.round(performance.now() - claimStartedAt));
    return { instance: i, warmHit, timings };
  }
  function maintainStandby() {
    if (!warmEnabled || ['stopping', 'stopped'].includes(state)) return;
    const now = performance.now();
    const active = [...instances.values()].filter(i => !i.standby && !['failed', 'stopping'].includes(i.state));
    let resources; try { resources = resourceSnapshot(); } catch { resources = null; }
    const headroom = standbyHeadroom(active.map(i => i.state === 'ready' && budgetAcknowledged(i) ? i.metrics : null), resources);
    for (const i of instances.values()) {
      if (!i.standby || ['queued', 'failed', 'stopping'].includes(i.state)) continue;
      if (!i.everWarmReady && now >= i.startDeadline) { i.fail?.('备用场景在启动期限内未完成预热'); continue; }
      if (i.state !== 'ready' || i.ws?.readyState !== WebSocket.OPEN) continue;
      const healthy = stableWarmSample(i);
      if (i.standbyState === 'idle') {
        i.warmReady = healthy && i.metrics.standbyMode === 'standby';
        if (i.warmReady && !i.everWarmReady) { i.everWarmReady = true; i.warmReadyAt = now; warmFailures = 0; logStartup(i, 'warmReady'); }
        // Spare work is expendable. Sustained pressure retires it without
        // reducing user budgets, while short telemetry gaps do not churn UE.
        if (headroom.allowed) i.resourcePressureSince = undefined;
        else {
          i.resourcePressureSince ??= now;
          if (now - i.resourcePressureSince >= resourcePressureMs) {
            warmRetryAt = now + warmBackoffMs;
            logStartup(i, 'standbyRetired', 'reason=' + headroom.reason);
            stopInstance(i).catch(e => log('清理备用场景失败：' + e.message));
          }
        }
        continue;
      }
      if (!healthy || i.metrics.standbyMode !== 'warming') { i.warmStableSince = undefined; continue; }
      if (i.warmStableSince === undefined) { i.warmStableSince = i.metrics.receivedAt; i.warmLastSample = i.metrics.receivedAt; }
      else if (i.metrics.receivedAt > i.warmLastSample && i.metrics.receivedAt - i.warmStableSince >= warmStableMs) {
        try { setBudget(i, 5, 'standby'); i.standbyState = 'idle'; i.warmReady = false; }
        catch { i.fail?.('无法写入备用场景的空闲预算'); }
      }
      i.warmLastSample = i.metrics.receivedAt;
    }
    if ([...instances.values()].some(i => i.standby)) { warmBlockedReason = ''; return; }
    if (viewers.size >= config.maxViewers || instances.size >= config.maxViewers) { warmBlockedReason = 'capacity'; return; }
    if (startingInstance || [...instances.values()].some(i => !i.standby && ['queued', 'starting', 'activating'].includes(i.state))) { warmBlockedReason = 'demand'; return; }
    if (now < warmRetryAt) { warmBlockedReason = 'backoff'; return; }
    if ([...viewers.values()].some(v => !v.ws || !v.subscribed || v.firstFrameReceivedAt === undefined || now - v.firstFrameReceivedAt < firstFrameStableMs)) { warmBlockedReason = 'first-frame'; return; }
    if (!headroom.allowed) { warmBlockedReason = headroom.reason; return; }
    warmBlockedReason = ''; startInstance('warm-' + crypto.randomBytes(6).toString('hex'), true);
  }
  function urls() { if (config.networkMode === 'public') return [config.publicUrl + '/']; const ips = Object.values(os.networkInterfaces()).flat().filter(x => x && x.family === 'IPv4' && !x.internal).map(x => x.address); return [...new Set(ips)].map(ip => `${scheme}://${ip}:${config.httpPort}/`); }
  function status() { return { state, message, mode: config.mode, networkMode: config.networkMode, publicUrl: config.publicUrl, accessProtectionEnabled: config.accessProtectionEnabled, tlsEnabled: !!config.tlsCertPath, trustProxy: config.trustProxy, externalTlsTermination: config.externalTlsTermination, qualityProfile: config.qualityProfile, fixedFps: config.fixedFps, captureFps: config.fps > 0 ? config.fps : 120, encoderAsync: config.encoderAsync, encoder: config.encoder, adaptiveResourceBudget: config.adaptiveResourceBudget, warmStandbyEnabled: config.warmStandbyEnabled, warmReadyCount: [...instances.values()].filter(warmAvailable).length, warmStartingCount: [...instances.values()].filter(i => i.standby && !['failed', 'stopping'].includes(i.state) && !warmAvailable(i)).length, warmBlockedReason, viewerCount: viewers.size, maxViewers: config.maxViewers,
    viewers: [...viewers.values()].map(v => ({ playerId: v.playerId, displayName: v.displayName, address: v.address, userAgent: v.userAgent, connectedAt: v.connectedAt, firstFrameReceived: v.firstFrameReceivedAt !== undefined, state: !v.ws ? 'reconnecting' : v.subscribed ? 'connected' : instances.get(v.instanceId)?.state === 'failed' ? 'failed' : instances.get(v.instanceId)?.state === 'queued' ? 'queued' : 'starting', instanceId: v.instanceId })),
    instances: [...instances.values()].map(i => ({ id: i.id, pid: i.child?.pid || null, state: i.state, standby: !!i.standby, standbyState: i.standbyState || null, startupStage: i.startupStage || i.state, startupElapsedMs: startupElapsed(i), identityWaitMs: identityWait(i), targetFps: i.targetFps, actualFps: i.metrics?.actualFps ?? null, gpuMs: i.metrics?.gpuMs ?? null, budgetAcknowledged: budgetAcknowledged(i), psoActivePrecacheRequests: i.metrics?.psoActivePrecacheRequests ?? null, screenPercentage: i.metrics?.screenPercentage ?? null })), urls: urls(), localUrl: `${scheme}://127.0.0.1:${config.httpPort}/`, logs: [...logs] }; }
  function rebalance() {
    if (state === 'stopping' || state === 'stopped') return;
    const running = [...instances.values()].filter(i => !['queued', 'stopping', 'failed'].includes(i.state));
    for (const i of running) i.metrics = readTelemetry(i.controlDir);
    const active = running.filter(i => !i.standby);
    const budgetFps = budgetPolicy.update(active.map(i => i.readyAt && Date.now() - i.readyAt >= 5000 && i.metrics?.sequence === i.sequence ? { ...i.metrics, id: i.id } : null));
    for (const i of running) {
      try { setBudget(i, i.standby ? i.standbyState === 'idle' ? 5 : config.fps : budgetFps, i.standby ? i.standbyState === 'idle' ? 'standby' : 'warming' : 'active'); }
      catch (e) { log('写入实例资源预算失败：' + e.message); }
      if (i.state === 'activating') {
        if (budgetAcknowledged(i, 'active')) { logStartup(i, 'activationReady'); signalReady(i); }
        else if (performance.now() >= i.activationDeadline) i.fail?.('预热场景未在期限内确认恢复配置帧率');
      }
    }
    maintainStandby();
  }
  const sameOrigin = req => requestSameOrigin(req, config);
  function publicSession(s) { return { token: s.token, evicted: !!s.evicted, message: s.evicted ? EVICTED : '', mode: config.mode, maxViewers: config.maxViewers, width: config.width, height: config.height, fps: config.fps, captureFps: config.fps > 0 ? config.fps : 120, minBitrateMbps: config.minBitrateMbps, startBitrateMbps: config.startBitrateMbps, maxBitrateMbps: config.maxBitrateMbps }; }
  function pruneSessions() { const now = Date.now(); for (const [id, s] of sessions) if (!viewers.has(id) && now - s.created > 12 * 60 * 60 * 1000) sessions.delete(id); for (const [ip, attempt] of authAttempts) if (now > attempt.until) authAttempts.delete(ip); }
  const handlePublic = async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      if (req.method === 'GET' && url.pathname === '/health') return json(res, 200, { state, mode: config.mode, viewerCount: viewers.size, maxViewers: config.maxViewers, accessRequired: config.accessProtectionEnabled });
      if (req.method === 'POST' && url.pathname === '/api/session') {
        if (!sameOrigin(req)) return json(res, 403, { error: '仅允许已配置地址的同源连接' });
        const body = await readJSON(req); if (!body || typeof body !== 'object' || Array.isArray(body)) return json(res, 400, { error: '无效会话请求' });
        pruneSessions();
        if (typeof body.token === 'string' && sessions.has(body.token)) return json(res, 200, publicSession(sessions.get(body.token)));
        if (body.token) return json(res, 409, { error: '会话已过期，请重新进入', expired: true });
        if (config.accessProtectionEnabled) {
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
    // Native UE libwebsockets supplies a loopback Origin; browsers must not
    // bootstrap onto this local control channel, even from a malicious website.
    const origins = [undefined, '127.0.0.1', 'http://127.0.0.1', 'http://127.0.0.1:' + config.streamerPort];
    let url; try { url = new URL(req.url, 'http://localhost'); } catch { return socket.destroy(); }
    const suppliedToken = url.searchParams.get('streamerToken');
    const expectedInstance = [...instances.values()].find(i => suppliedToken && secretEqual(suppliedToken, i.streamerToken));
    if (!origins.includes(req.headers.origin) || !expectedInstance?.child || !['starting', 'ready', 'activating', 'reconnecting'].includes(expectedInstance.state) || expectedInstance.pendingWS || (expectedInstance.state === 'starting' && !initializing(expectedInstance)) || ['stopping', 'stopped'].includes(state)) {
      socket.write('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); return socket.destroy();
    }
    streamersWS.handleUpgrade(req, socket, head, ws => {
    ws.alive = true; ws.on('pong', () => { ws.alive = true; }); ws.on('error', () => {}); let instance;
    expectedInstance.pendingWS = ws; expectedInstance.identityStartedAt = performance.now(); ws.initializingInstance = expectedInstance;
    const startupGrace = initializing(expectedInstance);
    // Only the token-authenticated, already-spawned process inherits its own
    // remaining initialization budget. Reconnects cannot reset that deadline.
    const identityBudget = startupGrace ? Math.max(1, expectedInstance.startDeadline - performance.now()) : identificationTimeoutMs;
    if (startupGrace) expectedInstance.startupStage = 'waitingIdentity';
    logStartup(expectedInstance, startupGrace ? 'waitingIdentity' : 'reconnectIdentity', 'deadlineRemainingMs=' + Math.round(identityBudget));
    // The original process-start timer owns initial failure and cleanup; do not
    // race it with a second timer or restart it after a transport reconnect.
    const identityTimeout = startupGrace ? undefined : setTimeout(() => {
      if (instance) return;
      logStartup(expectedInstance, 'identityTimeout');
      ws.close(1008, 'Identification required');
    }, identityBudget); identityTimeout?.unref(); expectedInstance.identityTimer = identityTimeout;
    if (startupGrace) for (const viewer of viewers.values()) if (viewer.instanceId === expectedInstance.id) notifyStage(viewer, 'initializingStreamer', '场景进程已连接，正在完成资源和界面初始化');
    send(ws, { type: 'identify' });
    ws.on('message', bytes => {
      let m; try { m = parseMessage(bytes, 'streamer'); } catch { return ws.close(1007, 'Invalid signalling message'); }
      if (m.type === 'endpointId') {
        const candidate = instances.get(m.id);
        if (!candidate || candidate !== expectedInstance || candidate.state === 'stopping' || candidate.state === 'failed' || (candidate.state === 'starting' && !initializing(candidate)) || (candidate.ws && candidate.ws !== ws)) return ws.close(1008, 'Unknown or duplicate streamer');
        if (instance === candidate) return; // Duplicate acknowledgments do not restart readiness or release more queued work.
        instance = candidate; instance.identityWaitMs = identityWait(instance); instance.pendingWS = null; instance.identityTimer = undefined;
        instance.ws = ws; ws.alive = true; instance.state = 'ready'; instance.startupStage = 'ready'; instance.readyAt = Date.now(); instance.startEndedAt ??= performance.now(); clearTimeout(instance.startTimer); clearTimeout(identityTimeout);
        logStartup(instance, 'ready');
        releaseStartupSlot(instance);
        send(ws, { type: 'config', peerConnectionOptions: { iceServers: ice } });
        log('UE信令已连接：' + instance.id);
        instance.metrics = readTelemetry(instance.controlDir);
        if (instance.activationPending && !budgetAcknowledged(instance, 'active')) awaitActivation(instance);
        else signalReady(instance);
        rebalance();
        return;
      }
      if (m.type === 'ping') return send(ws, { type: 'pong', time: m.time });
      if (!instance) return;
      const viewer = [...viewers.values()].find(v => v.playerId === String(m.playerId) && v.instanceId === instance.id && v.subscribed);
      if (!viewer) return;
      if (m.type === 'disconnectPlayer') { send(viewer.ws, { type: 'ghsInstanceFailed', message: '场景已断开当前视频连接' }); viewer.ws?.close(1011, 'Streamer disconnected player'); return; }
      if (['offer', 'answer', 'iceCandidate'].includes(m.type)) {
        const outgoing = { ...m }; delete outgoing.playerId; send(viewer.ws, outgoing);
        // Only augment authenticated UE candidates already scoped to this viewer.
        // Keep native candidates so local/VPN viewers can still use their route.
        if (m.type === 'iceCandidate') {
          const mapped = publicMediaCandidate(m.candidate, mediaAddress);
          if (mapped) send(viewer.ws, { ...outgoing, candidate: mapped });
        }
      }
    });
    ws.on('close', code => {
      clearTimeout(identityTimeout);
      if (expectedInstance.pendingWS === ws) {
        expectedInstance.identityWaitMs = identityWait(expectedInstance); expectedInstance.pendingWS = null; expectedInstance.identityTimer = undefined;
        if (expectedInstance.state === 'starting') expectedInstance.startupStage = 'processStarting';
        logStartup(expectedInstance, 'identitySocketClosed', 'code=' + code);
      }
      if (!instance || instance.ws !== ws) return;
      instance.ws = null;
      if (instance.standby && !['stopping', 'failed'].includes(instance.state) && state !== 'stopping') { instance.fail?.('备用场景信令连接断开'); return; }
      if (!['stopping', 'failed'].includes(instance.state) && state !== 'stopping') { instance.state = 'reconnecting'; instance.startupStage = 'reconnecting'; log('UE信令连接断开：' + instance.id); for (const viewer of viewers.values()) if (viewer.instanceId === instance.id) { unsubscribe(viewer); notifyStage(viewer, 'waitingStreamer', '场景信令连接断开，等待恢复'); } }
    });
    });
  });
  function notifyStage(viewer, stage, text) { send(viewer.ws, { type: 'ghsStage', stage, message: text, mode: config.mode }); }
  function sendStreamerList(viewer) { const i = instances.get(viewer.instanceId); send(viewer.ws, { type: 'streamerList', ids: i?.state === 'ready' ? [i.id] : [] }); }
  function broadcastCount() { for (const v of viewers.values()) send(v.ws, { type: 'playerCount', count: viewers.size }); }
  function unsubscribe(v) { if (v.subscribed) send(instances.get(v.instanceId)?.ws, { type: 'playerDisconnected', playerId: v.playerId }); v.subscribed = false; v.firstFrameReceivedAt = undefined; }
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
      const claimed = config.mode === 'independent' ? claimStandby() : null;
      viewer = { displayName: session.displayName, address: clientAddress(req, config), userAgent: String(req.headers['user-agent'] || '').replace(/[\x00-\x1f\x7f]/g, '').slice(0, 240), connectedAt: new Date().toISOString(), token: session.token, playerId: String(nextPlayer++), order: ++order, instanceId: config.mode === 'shared' ? 'shared' : claimed?.instance.id || 'viewer-' + crypto.randomBytes(6).toString('hex'), warmHit: claimed?.warmHit || false, timings: claimed?.timings || { instanceStartupMs: null, standbyReadyAgeMs: null, admissionToLeaseMs: 0 } };
      viewers.set(session.token, viewer);
      if (config.mode === 'independent' && !claimed) startInstance(viewer.instanceId);
    }
    clearTimeout(viewer.disconnectTimer); viewer.disconnectGeneration = (viewer.disconnectGeneration || 0) + 1; unsubscribe(viewer);
    const previous = viewer.ws; viewer.ws = ws; viewer.firstFrameReceivedAt = undefined;
    if (previous && previous !== ws) { send(previous, { type: 'ghsSessionReplaced', message: '同一会话已在其他标签页连接，本页已停止自动重连。', reconnect: false }); previous.close(4002, 'Session reconnected'); }
    send(ws, { type: 'ghsAdmission', playerId: viewer.playerId, mode: config.mode, instanceId: viewer.instanceId, maxViewers: config.maxViewers, warmHit: viewer.warmHit, timings: viewer.timings });
    send(ws, { type: 'config', peerConnectionOptions: { iceServers: ice } });
    const instance = instances.get(viewer.instanceId);
    if (instance?.state === 'failed') send(ws, { type: 'ghsInstanceFailed', message: 'UE场景启动失败或意外退出，请在启动器停止后重新开启' });
    else notifyStage(viewer, instance?.state === 'activating' ? 'activatingStreamer' : instance?.state === 'ready' ? 'streamerReady' : instance?.state === 'queued' ? 'queued' : instance?.startupStage === 'waitingIdentity' ? 'initializingStreamer' : 'waitingStreamer', instance?.state === 'activating' ? '预热场景已分配，正在恢复渲染帧率' : instance?.state === 'ready' ? '场景已就绪，正在建立视频连接' : instance?.state === 'queued' ? '场景正在排队，前序场景就绪后开始启动' : instance?.startupStage === 'waitingIdentity' ? '场景进程已连接，正在完成资源和界面初始化' : '正在启动UE场景，等待信令连接');
    log('访问者接入：' + viewer.playerId); broadcastCount();
    ws.on('message', bytes => {
      if (viewer.ws !== ws || viewers.get(viewer.token) !== viewer || session.evicted) return;
      let m; try { m = parseMessage(bytes, 'player'); } catch { return ws.close(1007, 'Invalid signalling message'); }
      const instance = instances.get(viewer.instanceId);
      if (m.type === 'listStreamers') return sendStreamerList(viewer);
      if (m.type === 'ping') return send(ws, { type: 'pong', time: m.time });
      if (m.type === 'ghsFirstFrame') {
        if (viewer.subscribed && instance?.state === 'ready' && viewer.firstFrameReceivedAt === undefined) {
          viewer.firstFrameReceivedAt = performance.now();
          logStartup(instance, 'firstFrame', 'playerId=' + viewer.playerId + ' attemptId=' + m.attemptId + ' attemptElapsedMs=' + m.attemptElapsedMs + ' navigationTotalMs=' + m.navigationTotalMs);
        }
        return;
      }
      // This service connects each player directly to its owned UE, not an SFU.
      if (m.type === 'layerPreference') return;
      if (m.type === 'subscribe') {
        if (m.streamerId !== viewer.instanceId || instance?.state !== 'ready') return send(ws, { type: 'warning', message: '所请求的实例不可用' });
        if (!viewer.subscribed) {
          // Gate each actual media subscription, not each repeated subscribe message.
          viewer.firstFrameReceivedAt = undefined; viewer.subscribed = true;
          send(instance.ws, { type: 'playerConnected', playerId: viewer.playerId, dataChannel: true, sfu: false, sendOffer: true });
        }
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
  function startInstance(id, standby = false) {
    const instance = { id, streamerToken: crypto.randomBytes(32).toString('hex'), state: 'queued', child: null, ws: null, sequence: 0, targetFps: config.fps, controlDir: null, standby, standbyCapable: standby, standbyState: standby ? 'warming' : null, warmReady: false }; instances.set(id, instance);
    pumpStartupQueue(); return instance;
  }
  function pumpStartupQueue() {
    if (startingInstance || ['stopping', 'stopped'].includes(state)) return;
    const next = [...instances.values()].find(i => i.state === 'queued' && !i.standby) || [...instances.values()].find(i => i.state === 'queued');
    if (!next) return;
    const processes = [...instances.values()].filter(i => i.child && i.child.exitCode === null && i.child.signalCode === null).length;
    if (processes >= config.maxViewers) return;
    startingInstance = next; next.state = 'starting'; launchInstance(next);
  }
  function releaseStartupSlot(instance) {
    if (startingInstance !== instance) return;
    startingInstance = null; pumpStartupQueue();
  }
  function launchInstance(instance) {
    const id = instance.id;
    const failed = detail => {
      if (['stopping', 'failed'].includes(instance.state) || state === 'stopping' || state === 'stopped') return;
      clearTimeout(instance.startTimer); instance.state = 'failed'; instance.startupStage = 'failed'; instance.startEndedAt ??= performance.now();
      if (instance.standby) {
        warmRetryAt = performance.now() + Math.min(120000, warmBackoffMs * 2 ** Math.min(warmFailures++, 3)); warmBlockedReason = 'backoff';
        log('备用场景预热失败：' + detail); closePendingIdentity(instance); instance.ws?.terminate();
        stopInstance(instance).catch(e => log('清理备用场景失败：' + e.message)); return;
      }
      state = 'degraded'; message = 'UE实例失败：' + detail; log(message);
      logStartup(instance, 'failed'); closePendingIdentity(instance);
      instance.ws?.close(1011, 'UE exited');
      rebalance();
      for (const v of viewers.values()) if (v.instanceId === id) { v.subscribed = false; send(v.ws, { type: 'ghsInstanceFailed', message }); }
      // Release initialization capacity only after the failed owned process is gone.
      stopProcess(instance).then(() => releaseStartupSlot(instance)).catch(e => log('清理失败实例：' + e.message));
    };
    instance.fail = failed;
    try {
      const controlRoot = options.controlRoot || os.tmpdir(); fs.mkdirSync(controlRoot, { recursive: true });
      instance.controlDir = fs.mkdtempSync(path.join(controlRoot, 'ghs-instance-'));
      // The initial mode must exist before UE starts; a missing warm permit budget
      // would otherwise let the engine permanently enter active mode on its first tick.
      setBudget(instance, config.fps, instance.standby ? 'warming' : 'active');
      rebalance();
      // PS2 capture negotiation stays positive; 0 only uncaps rendering.
      // Fixed targets prevent the private resource bridge from lowering FPS.
      instance.startedAt = performance.now(); instance.startDeadline = instance.startedAt + startupTimeoutMs; instance.startupStage = 'processStarting';
      const args = buildUEArgs(config, id, instance.controlDir, instance.streamerToken); if (instance.standbyCapable) args.push('-GHSStandbyCapable');
      const child = spawnProcess(config.executablePath, args, { cwd: path.dirname(config.executablePath), shell: false, windowsHide: !config.showWindow, stdio: ['ignore', 'pipe', 'pipe'] });
      instance.child = child; log('启动UE实例 ' + id + '，PID ' + child.pid);
      logStartup(instance, 'processStarting');
      // Immediate starts are reported after admit binds viewer.ws. Queued starts
      // have an existing socket and must advance their stage now, exactly once.
      for (const v of viewers.values()) if (v.instanceId === id && v.ws) notifyStage(v, 'waitingStreamer', '正在启动UE场景，等待信令连接');
      for (const stream of [child.stdout, child.stderr]) stream?.on('data', bytes => { const lines = bytes.toString().split(/\r?\n/).filter(Boolean); for (const line of lines.slice(-6)) if (/error|fatal|PixelStreaming|Signalling|Warning/i.test(line)) log('[' + id + '] ' + line); });
      child.once('error', e => failed('启动失败：' + e.message)); child.once('exit', (code, signal) => failed('实例 ' + id + ' 退出（' + (code ?? signal) + '）'));
      instance.startTimer = setTimeout(() => failed('实例 ' + id + ' 在' + (startupTimeoutMs / 1000) + '秒内未完成' + (instance.pendingWS ? '信令身份确认' : '信令连接')), Math.max(1, instance.startDeadline - performance.now())); instance.startTimer.unref();
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
  async function stopInstance(instance) { if (!instance) return; instance.state = 'stopping'; instance.startupStage = 'stopping'; instance.startEndedAt ??= performance.now(); clearTimeout(instance.startTimer); closePendingIdentity(instance); instance.ws?.terminate(); await stopProcess(instance); instances.delete(instance.id); if (instance.controlDir) fs.rmSync(instance.controlDir, { recursive: true, force: true }); rebalance(); releaseStartupSlot(instance); pumpStartupQueue(); }
  async function start() {
    try {
      await listen(streamerServer, config.streamerPort, '127.0.0.1'); await listen(publicServer, config.httpPort, config.trustProxy ? '127.0.0.1' : '0.0.0.0'); await listen(controlServer, 0, '127.0.0.1');
      state = 'running'; message = '服务已启动'; log('网页服务 ' + scheme + '://' + (config.trustProxy ? '127.0.0.1' : '0.0.0.0') + ':' + config.httpPort + '，UE信令仅本机:' + config.streamerPort);
      gpuCapacity?.start();
      heartbeat = setInterval(() => { pruneSessions(); for (const server of [playersWS, streamersWS]) for (const ws of server.clients) {
        // A native initialization stall may also delay pong dispatch. Only this
        // one owned pending socket shares the same absolute startup deadline.
        const ownedInitialization = ws.initializingInstance?.pendingWS === ws && initializing(ws.initializingInstance);
        if (!ws.alive && !ownedInitialization) { ws.terminate(); continue; }
        ws.alive = false; if (ws.readyState === WebSocket.OPEN) ws.ping();
      } }, heartbeatIntervalMs); heartbeat.unref();
      budgetTimer = setInterval(rebalance, budgetIntervalMs); budgetTimer.unref();
      if (config.mode === 'shared') startInstance('shared');
      else maintainStandby();
      return status();
    } catch (e) { log(e.message); await stop(); throw e; }
  }
  function stop() {
    if (stopPromise) return stopPromise;
    stopPromise = (async () => {
      state = 'stopping'; message = '正在清理本服务的场景实例'; clearInterval(heartbeat); clearInterval(budgetTimer);
      gpuCapacity?.stop();
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
