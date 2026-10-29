const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { spawn, execFile } = require('node:child_process');
let config, server, token, engineToken, serviceId, timer, stopping = false, stopError = null;
const owned = new Map();
const isLocal = address => ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(address);
function validate(raw, base = __dirname) {
  const c = { qualityProfile: 'balanced', mediaMinPort: 50000, mediaMaxPort: 50199, idleTimeoutSeconds: 8, ...raw };
  if (!['127.0.0.1', '0.0.0.0'].includes(c.host)) throw Error('host must be 127.0.0.1 or 0.0.0.0');
  const ranges = { port: [1024, 65535], width: [320, 7680], height: [240, 4320], instances: [1, 10], startupTimeoutSeconds: [15, 600], idleTimeoutSeconds: [5, 3600], mediaMinPort: [1024, 65535], mediaMaxPort: [1024, 65535] };
  for (const [key, [min, max]] of Object.entries(ranges)) if (!Number.isInteger(c[key]) || c[key] < min || c[key] > max) throw Error('Invalid setting: ' + key);
  if (!Number.isInteger(c.fps) || (c.fps !== 0 && (c.fps < 15 || c.fps > 120))) throw Error('fps must be 0 (uncapped) or 15–120');
  if (c.mediaMinPort > c.mediaMaxPort) throw Error('Invalid media port range');
  if (!['balanced', 'clear', 'ultra', 'custom'].includes(c.qualityProfile)) throw Error('Invalid qualityProfile');
  if (![c.minBitrateMbps, c.startBitrateMbps, c.maxBitrateMbps].every(n => Number.isFinite(n) && n > 0 && n <= 200) || c.minBitrateMbps > c.startBitrateMbps || c.startBitrateMbps > c.maxBitrateMbps) throw Error('Invalid bitrate range');
  if (!Array.isArray(c.iceServers)) throw Error('iceServers must be an array');
  c.executablePath = path.resolve(base, c.executablePath);
  if (!fs.statSync(c.executablePath, { throwIfNoEntry: false })?.isFile()) throw Error('Packaged UE executable not found: ' + c.executablePath);
  // Own the long-lived packaged game, not UE's short-lived bootstrap launcher.
  if (path.basename(c.executablePath).toLowerCase() === 'testgame.exe') {
    const shipping = path.join(path.dirname(c.executablePath), 'Test/Binaries/Win64/TestGame-Win64-Shipping.exe');
    if (fs.statSync(shipping, { throwIfNoEntry: false })?.isFile()) c.executablePath = shipping;
  }
  return c;
}
function ueArgs(c, slot, secret) {
  return [`-PixelStreamingURL=ws://127.0.0.1:${c.port}/${slot}?token=${secret}`, `-PixelStreamingID=peer-${slot}`,
    '-RenderOffscreen', '-Unattended', '-ForceRes', '-AudioMixer', '-NoSplash', '-NoVSync', '-GHSLowLatencyPlayout', '-StdOut', '-FullStdOutLogOutput',
    `-ResX=${c.width}`, `-ResY=${c.height}`, `-PixelStreamingWebRTCFps=${c.fps}`,
    `-PixelStreamingWebRTCMinBitrate=${c.minBitrateMbps * 1000000}`, `-PixelStreamingWebRTCStartBitrate=${c.startBitrateMbps * 1000000}`,
    `-PixelStreamingWebRTCMaxBitrate=${c.maxBitrateMbps * 1000000}`, `-PixelStreamingEncoderMaxBitrate=${c.maxBitrateMbps * 1000000}`, '-PixelStreamingEncoderCodec=H264', '-PixelStreamingEncoderRateControl=CBR',
    '-PixelStreamingWebRTCDegradationPreference=MAINTAIN_RESOLUTION', `-PixelStreamingWebRTCMinPort=${c.mediaMinPort}`, `-PixelStreamingWebRTCMaxPort=${c.mediaMaxPort}`,
    '-PixelStreamingEncoderPreset=' + (c.qualityProfile === 'balanced' ? 'DEFAULT' : 'HIGH_QUALITY'), '-PixelStreamingEncoderMinQP=0', '-PixelStreamingEncoderMaxQP=' + (c.qualityProfile === 'ultra' ? 28 : c.qualityProfile === 'clear' ? 32 : 36),
    `-ExecCmds=t.MaxFPS ${c.fps},r.VSync 0,PixelStreaming.DecoupleFramerate 0,r.ScreenPercentage 100,r.DynamicRes.OperationMode 0,r.MotionBlurQuality 0,r.DepthOfFieldQuality 0,r.Tonemapper.Sharpen 0.3`, `-abslog=${path.join(__dirname, 'logs', `ue-${slot}.log`)}`];
}
function initialize() {
  config = validate(JSON.parse(fs.readFileSync(path.join(__dirname, 'settings.json'), 'utf8').replace(/^\uFEFF/, '')));
  token = crypto.randomBytes(32).toString('hex'); engineToken = crypto.randomBytes(32).toString('hex'); serviceId = crypto.randomUUID();
  fs.mkdirSync(path.join(__dirname, '.state'), { recursive: true });
  fs.mkdirSync(path.join(__dirname, 'logs'), { recursive: true });
  process.on('SIGINT', stop); process.on('SIGTERM', stop);
  process.on('uncaughtException', e => { console.error(e); stop(1); });
  process.on('unhandledRejection', e => { console.error(e); stop(1); });
}
function signalConfig() {
  return { PORT: config.port, auth: false, one2one: true, UEVersion: 5, preload: 0, boot: false, exeUeCoolTime: 3,
    iceServers: config.iceServers, UE5: Array.from({ length: config.instances }, () => `managed -PixelStreamingURL=ws://127.0.0.1:${config.port}/`) };
}
function launchUE(slot) {
  if (stopping || owned.has(slot) || !/^\d+$/.test(slot) || +slot >= config.instances) return;
  const child = spawn(config.executablePath, ueArgs(config, slot, engineToken), { cwd: path.dirname(config.executablePath), windowsHide: true, stdio: 'ignore' });
  const item = { child, pid: child.pid, slot, started: Date.now(), idleSince: null, connected: false, ending: false };
  owned.set(slot, item);
  console.log(`[UE ${slot}] started PID ${child.pid}`);
  child.on('error', error => { console.error(`[UE ${slot}] ${error.message}`); owned.delete(slot); notifyFailure(slot); });
  child.on('exit', code => {
    console.log(`[UE ${slot}] exited ${code}`);
    if (!stopping && !item.ending) notifyFailure(slot);
    owned.delete(slot); const ue = engineFor(slot); if (ue) ue.close();
  });
}
function engineFor(slot) { return [...(global.ENGINE?.clients || [])].find(ue => ue.req.url === '/' + slot); }
function send(ws, data) { if (ws.readyState === 1) ws.send(JSON.stringify(data)); }
function notifyFailure(slot) {
  for (const ws of global.PLAYER?.clients || []) if (!ws.ue || ws.ue.req.url === '/' + slot) { send(ws, { type: 'deploymentError', message: 'UE instance could not start. See service logs.' }); ws.close(1011, 'UE failed to start'); }
}
function killOwned(item) {
  if (item.ending) return item.ending;
  item.ending = new Promise((resolve, reject) => {
    // Only a still-owned ChildProcess is eligible; never kill by image name or a stale PID file.
    if (!item.pid || item.child.exitCode !== null || item.child.signalCode !== null) return resolve();
    let finished = false;
    const complete = error => {
      if (finished) return; finished = true; clearTimeout(deadline);
      item.child.removeListener('exit', onExit);
      if (error) reject(error); else resolve();
    };
    const onExit = () => complete();
    const deadline = setTimeout(() => complete(Error(`UE ${item.slot} PID ${item.pid} did not exit`)), 8000);
    item.child.once('exit', onExit);
    execFile('taskkill.exe', ['/PID', String(item.pid), '/T', '/F'], { windowsHide: true }, error => {
      if (item.child.exitCode !== null || item.child.signalCode !== null) complete();
      else if (error) complete(error);
    });
  });
  item.ending.catch(() => { item.ending = false; });
  return item.ending;
}
function snapshot() {
  return { service: 'ghs-peer-stream', serviceId, state: stopping ? 'stopping' : stopError ? 'stop_failed' : 'running', error: stopError, pid: process.pid,
    users: global.PLAYER?.clients.size || 0, maxInstances: config.instances, width: config.width, height: config.height, fps: config.fps,
    instances: [...owned.values()].map(item => ({ slot: item.slot, pid: item.pid, connected: !!engineFor(item.slot), users: engineFor(item.slot)?.fe.size || 0 })),
    players: [...(global.PLAYER?.clients || [])].map(ws => ({ id: ws.req.socket.remotePort, instance: ws.ue?.req.url || null })) };
}
function authorized(req) {
  if (!isLocal(req.socket.remoteAddress)) return false;
  const supplied = Buffer.from(req.headers.authorization || ''); const expected = Buffer.from('Bearer ' + token);
  return supplied.length === expected.length && crypto.timingSafeEqual(supplied, expected);
}
function json(res, status, value) { res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(value)); }
async function serve(port) {
  server = http.createServer((req, res) => {
    let url; try { url = new URL(req.url, 'http://localhost'); } catch { return json(res, 400, {}); }
    if (url.pathname === '/health' && req.method === 'GET') {
      const state = snapshot();
      return json(res, 200, { service: state.service, serviceId, state: state.state, users: state.users, maxInstances: state.maxInstances, instanceCount: state.instances.length, width: state.width, height: state.height, fps: state.fps });
    }
    if (url.pathname.startsWith('/control/')) {
      if (!authorized(req)) return json(res, 403, { error: 'Local operator token required' });
      if (url.pathname === '/control/status' && req.method === 'GET') return json(res, 200, snapshot());
      if (url.pathname === '/control/stop' && req.method === 'POST') { json(res, 200, { state: 'stopping' }); setImmediate(stop); return; }
      return json(res, 404, {});
    }
    if (!['GET', 'HEAD'].includes(req.method)) return json(res, 405, {});
    const files = { '/': ['player.html', 'text/html; charset=utf-8'], '/player.html': ['player.html', 'text/html; charset=utf-8'], '/peer-stream.js': ['peer-stream.js', 'text/javascript; charset=utf-8'], '/player-session.js': ['player-session.js', 'text/javascript; charset=utf-8'] };
    const file = files[url.pathname]; if (!file) return json(res, 404, {});
    res.writeHead(200, { 'Content-Type': file[1], 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer' });
    if (req.method === 'HEAD') return res.end();
    fs.createReadStream(path.join(__dirname, file[0])).on('error', () => res.destroy()).pipe(res);
  });
  server.on('upgrade', (req, socket, head) => {
    let url; try { url = new URL(req.url, 'http://localhost'); } catch { return socket.destroy(); }
    if (stopping) return socket.destroy();
    const protocol = req.headers['sec-websocket-protocol'];
    if (protocol === 'peer-stream' && url.pathname === '/') {
      if (req.headers.origin) { try { if (new URL(req.headers.origin).host !== req.headers.host) return socket.destroy(); } catch { return socket.destroy(); } }
      if (global.PLAYER.clients.size >= config.instances + 20) return socket.destroy();
      global.PLAYER.handleUpgrade(req, socket, head, ws => { ws.on('error', () => {}); global.PLAYER.emit('connection', ws, req); });
    } else if (!protocol && isLocal(socket.remoteAddress) && url.searchParams.get('token') === engineToken && /^\/\d+$/.test(url.pathname) && owned.has(url.pathname.slice(1))) {
      req.url = url.pathname;
      global.ENGINE.handleUpgrade(req, socket, head, ws => {
        ws.on('error', () => {});
        ws.on('close', () => {
          if (stopping) return;
          for (const player of ws.fe || []) { send(player, { type: 'deploymentError', message: 'UE connection ended.' }); player.close(1011, 'UE disconnected'); }
        });
        global.ENGINE.emit('connection', ws, req);
      });
    } else socket.destroy();
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, config.host, resolve); });
  for (const group of [global.ENGINE, global.PLAYER, global.EXECUE]) group.options.maxPayload = 1024 * 1024;
  fs.writeFileSync(path.join(__dirname, '.state/control.json'), JSON.stringify({ pid: process.pid, serviceId, port, token }));
  console.log(`Peer Stream ready: http://127.0.0.1:${port}/ (bind ${config.host})`);
  timer = setInterval(() => {
    for (const item of owned.values()) {
      const engine = engineFor(item.slot);
      if (engine) item.connected = true;
      if (!engine && Date.now() - item.started > config.startupTimeoutSeconds * 1000) { notifyFailure(item.slot); killOwned(item).catch(error => console.error(error.message)); }
      else if (engine && !engine.fe.size) { item.idleSince ??= Date.now(); if (Date.now() - item.idleSince > config.idleTimeoutSeconds * 1000) killOwned(item).catch(error => console.error(error.message)); }
      else item.idleSince = null;
    }
  }, 1000);
}
async function stop(code = 0) {
  if (stopping) return; stopping = true; stopError = null;
  for (const ws of global.PLAYER?.clients || []) { send(ws, { type: 'deploymentStopped' }); ws.close(1001, 'Service stopped'); }
  try { await Promise.all([...owned.values()].map(killOwned)); }
  catch (error) { stopError = error.message; stopping = false; console.error('Stop failed: ' + stopError); return; }
  clearInterval(timer); server?.close(); server?.closeAllConnections?.();
  const stateFile = path.join(__dirname, '.state/control.json');
  try { if (JSON.parse(fs.readFileSync(stateFile)).pid === process.pid) fs.unlinkSync(stateFile); } catch {}
  process.exit(typeof code === 'number' ? code : 0);
}
module.exports = { initialize, validate, ueArgs, signalConfig, launchUE, serve };
