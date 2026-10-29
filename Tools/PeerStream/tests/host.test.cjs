const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { spawn } = require('node:child_process');
const { adapt } = require('../build.cjs');
const { validate, ueArgs } = require('../host.cjs');
const root = path.resolve(__dirname, '../../..');
const deployment = process.env.GHS_PEER_TEST_BUILD || path.join(root, 'Saved/PeerComparison20261029/PeerStreamBuild');
const WebSocket = require(path.join(root, 'Tools/PixelStreaming/node_modules/ws'));
const defaults = require('../settings.example.json');
test('invalid deployment settings fail before launching UE', () => {
  const valid = { ...defaults, executablePath: process.execPath };
  assert.equal(validate(valid).fps, 60);
  assert.equal(validate({ ...valid, fps: 0 }).fps, 0, 'uncapped remains an explicit supported option');
  for (const delta of [{ instances: 0 }, { instances: 11 }, { fps: 1 }, { fps: -1 }, { port: 88 }, { minBitrateMbps: 30 }, { host: 'example.com' }, { executablePath: 'missing.exe' }, { mediaMinPort: 50200, mediaMaxPort: 50199 }]) {
    assert.throws(() => validate({ ...valid, ...delta }));
  }
});

test('comparison launch preserves 1080p60, bitrate, codec and quality policy', () => {
  const config = validate({ ...defaults, executablePath: process.execPath });
  const args = ueArgs(config, '0', 'fixture');
  for (const expected of ['-PixelStreamingWebRTCFps=60', '-ResX=1920', '-ResY=1080', '-PixelStreamingEncoderCodec=H264', '-PixelStreamingWebRTCMinBitrate=1000000', '-PixelStreamingWebRTCStartBitrate=8000000', '-PixelStreamingWebRTCMaxBitrate=24000000', '-PixelStreamingEncoderMaxBitrate=24000000', '-PixelStreamingWebRTCMinPort=50000', '-PixelStreamingWebRTCMaxPort=50199', '-GHSLowLatencyPlayout', '-PixelStreamingWebRTCDegradationPreference=MAINTAIN_RESOLUTION', '-PixelStreamingEncoderPreset=DEFAULT', '-PixelStreamingEncoderMaxQP=36']) assert.ok(args.includes(expected), expected);
  assert.ok(args.some(a => a.startsWith('-ExecCmds=t.MaxFPS 60,') && a.includes('r.DynamicRes.OperationMode 0')));
  assert.ok(ueArgs({ ...config, fps: 0 }, '0', 'fixture').includes('-PixelStreamingWebRTCFps=0'));
});

test('known bootstrap resolves to owned shipping process when present', () => {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ghs-peer-exe-'));
  try {
    const bootstrap=path.join(dir,'TestGame.exe'), shipping=path.join(dir,'Test/Binaries/Win64/TestGame-Win64-Shipping.exe');
    fs.mkdirSync(path.dirname(shipping),{recursive:true}); fs.writeFileSync(bootstrap,'fixture'); fs.writeFileSync(shipping,'fixture');
    assert.equal(validate({...defaults,executablePath:bootstrap}).executablePath,shipping);
  } finally { fs.rmSync(dir,{recursive:true,force:true}); }
});
test('deployed signalling exposes only the player and authenticated local controls', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ghs-peer-stream-test-'));
  const probe = net.createServer();
  await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port; await new Promise(resolve => probe.close(resolve));
  for (const file of ['host.cjs', 'service.cjs', 'player.html', 'player-session.js', 'peer-stream.js']) fs.copyFileSync(path.join(deployment, file), path.join(directory, file));
  fs.cpSync(path.join(deployment, 'node_modules'), path.join(directory, 'node_modules'), { recursive: true });
  fs.writeFileSync(path.join(directory, 'signal.js'), adapt(fs.readFileSync(path.join(__dirname, '../upstream/signal.js'), 'utf8').replaceAll('\r\n', '\n')));
  fs.writeFileSync(path.join(directory, 'settings.json'), JSON.stringify({ ...defaults, port, executablePath: process.execPath }));
  const child = spawn(process.execPath, [path.join(directory, 'service.cjs')], { cwd: directory, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  let output = ''; child.stdout.on('data', b => output += b); child.stderr.on('data', b => output += b);
  const base = `http://127.0.0.1:${port}`;
  try {
    let ready = false;
    for (let i = 0; i < 60; i++) { try { ready = (await fetch(base + '/health')).ok; } catch {} if (ready) break; await new Promise(resolve => setTimeout(resolve, 100)); }
    assert.ok(ready, output);
    assert.equal((await fetch(base + '/')).status, 200);
    assert.equal((await fetch(base + '/peer-stream.js')).status, 200);
    assert.equal((await fetch(base + '/player-session.js')).status, 200);
    for (const name of ['/settings.json', '/.state/control.json', '/signal.js', '/signal.html', '/host.cjs']) assert.equal((await fetch(base + name)).status, 404);
    for (const name of ['/exec', '/eval', '/write', '/signal']) assert.equal((await fetch(base + name, { method: 'POST' })).status, 405);
    assert.equal((await fetch(base + '/control/stop', { method: 'POST' })).status, 403);
    await new Promise((resolve, reject) => {
      const ws = new WebSocket(base.replace('http:', 'ws:') + '/', 'exec-ue');
      ws.on('open', () => { ws.close(); reject(Error('remote executor must not be admitted')); });
      ws.on('error', () => resolve());
    });
    const state = JSON.parse(fs.readFileSync(path.join(directory, '.state/control.json')));
    const health=await (await fetch(base + '/health')).json();
    assert.equal(health.instanceCount, 0);
    assert.equal(health.fps, 60); assert.equal(health.width, 1920); assert.equal(health.height, 1080);
    assert.equal(health.pid, undefined); assert.equal(health.players, undefined); assert.equal(health.instances, undefined);
    const status = await fetch(base + '/control/status', { headers: { Authorization: 'Bearer ' + state.token } });
    assert.equal(status.status, 200);
    const exited = new Promise(resolve => child.once('exit', resolve));
    const stopped = await fetch(base + '/control/stop', { method: 'POST', headers: { Authorization: 'Bearer ' + state.token } });
    assert.equal(stopped.status, 200); await exited;
    assert.equal(fs.existsSync(path.join(directory, '.state/control.json')), false);
  } finally {
    if (child.exitCode === null) child.kill();
    // This is a unique temporary test directory, never a project/package directory.
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
