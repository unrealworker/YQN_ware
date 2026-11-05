'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { install, inspect, parseCLI, hashFile } = require('../deployment/install-ps2');

const EXE = 'App/Windows/Test/Binaries/Win64/TestGame-Win64-Shipping.exe';
const noProcesses = { processes: () => [] };
function write(root, relative, contents) { const file = path.join(root, ...relative.split('/')); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, contents); }
function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ghs-ps2-installer-'));
  const source = path.join(root, '新交付包'), target = path.join(root, '现有服务');
  fs.mkdirSync(source); fs.mkdirSync(target);
  const payload = [EXE, 'server/server.js', 'server/service.js', 'player/index.html', 'runtime/node.exe', 'node_modules/ws/package.json', '像素流服务启动器.exe', 'install-ps2.js'];
  for (const relative of payload) write(source, relative, 'new:' + relative);
  const manifest = { version: 1, engine: '5.8.4', pixelStreamingPlugin: 'PixelStreaming2', files: payload.map(relative => ({ path: relative, bytes: fs.statSync(path.join(source, relative)).size, sha256: hashFile(path.join(source, relative)) })) };
  const saveManifest = () => write(source, 'delivery-manifest.json', JSON.stringify(manifest)); saveManifest();
  write(source, 'launcher.config.json', JSON.stringify({ httpPort: 8080, width: 1920, accessProtectionEnabled: false }));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return { root, source, target, manifest, saveManifest, run: (mode = 'apply', deps = noProcesses) => install({ source, target, mode }, deps) };
}
function snapshot(root, prefix = '') {
  const entries = [];
  for (const item of fs.readdirSync(path.join(root, prefix), { withFileTypes: true })) {
    const relative = path.posix.join(prefix, item.name);
    if (item.isDirectory()) entries.push(...snapshot(root, relative));
    else entries.push([relative, hashFile(path.join(root, relative))]);
  }
  return entries.sort((a, b) => a[0].localeCompare(b[0]));
}

test('check verifies every manifest hash and makes no filesystem changes', t => {
  const f = fixture(t); write(f.target, 'keep.txt', 'unchanged');
  const before = snapshot(f.root), proof = f.run('check');
  assert.equal(proof.status, 'verified'); assert.equal(proof.fileCount, f.manifest.files.length);
  assert.deepEqual(snapshot(f.root), before);
  assert.equal(fs.existsSync(path.join(f.target, '_updates')), false);
});

test('corrupt payload and byte mismatch fail before creating target or stage', t => {
  const f = fixture(t); fs.rmSync(f.target, { recursive: true });
  const file = path.join(f.source, 'server/server.js');
  const original = fs.readFileSync(file); fs.writeFileSync(file, Buffer.alloc(original.length, 42));
  assert.throws(() => f.run(), /完整性校验失败/); assert.equal(fs.existsSync(f.target), false);
  fs.writeFileSync(file, original); f.manifest.files[0].bytes++; f.saveManifest();
  assert.throws(() => f.run(), /完整性校验失败/); assert.equal(fs.existsSync(f.target), false);
});

test('full update replaces managed payload, preserves network secrets and unknown state, and records secret-free proof', t => {
  const f = fixture(t);
  const originalConfig = { httpPort: 8080, streamerPort: 8888, mode: 'independent', maxViewers: 10, networkMode: 'public', publicUrl: 'https://warehouse.example/', externalTlsTermination: true, accessProtectionEnabled: true, accessCode: 'private-test-secret', turnPassword: 'private-turn-secret', tlsCertPath: 'certificates/site.pem', tlsKeyPath: 'certificates/site.key', customObject: { future: true }, encoder: 'Auto', fps: 30, fixedFps: false, adaptiveResourceBudget: true, executablePath: 'old.exe' };
  const originalText = JSON.stringify(originalConfig, null, 4);
  write(f.target, 'launcher.config.json', originalText);
  write(f.target, EXE, 'old-exe'); write(f.target, 'App/obsolete.pak', 'obsolete');
  write(f.target, 'server/server.js', 'old-server'); write(f.target, 'server/private-settings.json', '{"localSecret":"server-secret"}');
  write(f.target, 'certificates/site.pem', 'certificate'); write(f.target, 'certificates/site.key', 'private-key');
  write(f.target, 'PeerStream/keep.txt', 'legacy awaits validation'); write(f.target, 'logs/old.log', 'history');
  write(f.target, 'custom-top-level.txt', 'unmanaged'); write(f.target, '_updates/older-backup/keep.txt', 'history');
  const result = f.run();
  assert.equal(result.status, 'installed');
  for (const entry of f.manifest.files) assert.equal(hashFile(path.join(f.target, entry.path)), entry.sha256);
  assert.equal(fs.existsSync(path.join(f.target, 'App/obsolete.pak')), false);
  assert.equal(fs.readFileSync(path.join(result.backup, 'App/obsolete.pak'), 'utf8'), 'obsolete');
  assert.equal(fs.readFileSync(path.join(result.backup, 'launcher.config.json'), 'utf8'), originalText);
  const actual = JSON.parse(fs.readFileSync(path.join(f.target, 'launcher.config.json'), 'utf8'));
  for (const key of ['httpPort', 'streamerPort', 'mode', 'maxViewers', 'networkMode', 'publicUrl', 'externalTlsTermination', 'accessProtectionEnabled', 'accessCode', 'turnPassword', 'tlsCertPath', 'tlsKeyPath', 'customObject']) assert.deepEqual(actual[key], originalConfig[key], key);
  assert.deepEqual([actual.encoderAsync, actual.encoder, actual.fixedFps, actual.fps, actual.adaptiveResourceBudget, actual.executablePath], [true, 'NVIDIA', true, 60, false, EXE]);
  for (const relative of ['server/private-settings.json', 'certificates/site.pem', 'certificates/site.key', 'PeerStream/keep.txt', 'logs/old.log', 'custom-top-level.txt', '_updates/older-backup/keep.txt']) assert.equal(fs.existsSync(path.join(f.target, relative)), true, relative);
  const proofText = fs.readFileSync(result.proof, 'utf8');
  assert.doesNotMatch(proofText, /private-test-secret|private-turn-secret|server-secret|private-key/);
  assert.equal(JSON.parse(proofText).manifestSha256, hashFile(path.join(f.target, 'delivery-manifest.json')));
});

test('new installation uses package defaults plus required PS2 settings', t => {
  const f = fixture(t); const result = f.run();
  const configuration = JSON.parse(fs.readFileSync(path.join(f.target, 'launcher.config.json'), 'utf8'));
  assert.equal(result.configPreserved, false); assert.equal(configuration.httpPort, 8080);
  assert.equal(configuration.accessProtectionEnabled, false); assert.equal(configuration.fps, 60);
  assert.equal(configuration.executablePath, EXE);
});

test('deployment-owned media address is preserved byte-for-byte even if a legacy manifest claimed it', t => {
  const f = fixture(t), relative = 'server/media-address.json', contents = '{ "privateIp": "10.1.2.3", "publicIp": "8.8.4.4" }\r\n';
  write(f.target, relative, contents); write(f.target, 'delivery-manifest.json', JSON.stringify({ files: [{ path: relative }] }));
  const result = f.run(); assert.equal(fs.readFileSync(path.join(f.target, relative), 'utf8'), contents);
  assert.equal(result.preservedServerFiles, 1); assert.equal(fs.readFileSync(path.join(result.backup, relative), 'utf8'), contents);
});

test('new packages cannot claim or replace deployment-specific media address settings', t => {
  const f = fixture(t), relative = 'server/media-address.json'; write(f.source, relative, '{}');
  f.manifest.files.push({ path: relative, bytes: 2, sha256: hashFile(path.join(f.source, relative)) }); f.saveManifest();
  assert.throws(() => f.run(), /覆盖|部署/); assert.deepEqual(fs.readdirSync(f.target), []);
});

test('media address changes during staging abort before replacing any application files', t => {
  const f = fixture(t); write(f.target, EXE, 'original'); write(f.target, 'server/media-address.json', '{"version":1}'); let checks = 0;
  assert.throws(() => f.run('apply', { processes() { if (++checks === 2) write(f.target, 'server/media-address.json', '{"version":2}'); return []; } }), /配置发生变化/);
  assert.equal(fs.readFileSync(path.join(f.target, EXE), 'utf8'), 'original'); assert.equal(fs.readFileSync(path.join(f.target, 'server/media-address.json'), 'utf8'), '{"version":2}');
});

test('a configuration change during staging aborts before replacing the application', t => {
  const f = fixture(t); write(f.target, EXE, 'original'); write(f.target, 'launcher.config.json', '{"networkMode":"lan"}');
  let checks = 0;
  assert.throws(() => f.run('apply', { processes() {
    if (++checks === 2) write(f.target, 'launcher.config.json', '{"networkMode":"public","accessCode":"latest-secret"}');
    return [];
  } }), /配置发生变化/);
  assert.equal(fs.readFileSync(path.join(f.target, EXE), 'utf8'), 'original');
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.target, 'launcher.config.json'), 'utf8')).accessCode, 'latest-secret');
});

test('a failed replacement rolls all prior managed units and configuration back', t => {
  const f = fixture(t); write(f.target, EXE, 'old-app'); write(f.target, 'server/server.js', 'old-server'); write(f.target, 'launcher.config.json', '{"accessCode":"rollback-secret"}');
  const before = snapshot(f.target); let failed = false;
  assert.throws(() => f.run('apply', { processes: () => [], rename(source, target) {
    if (!failed && source.endsWith(path.join('staged', 'player'))) { failed = true; throw Error('injected copy failure'); }
    fs.renameSync(source, target);
  } }), /已回滚/);
  assert.deepEqual(snapshot(f.target).filter(([name]) => !name.startsWith('_updates/')), before);
  const updates = fs.readdirSync(path.join(f.target, '_updates'));
  const proof = JSON.parse(fs.readFileSync(path.join(f.target, '_updates', updates[0], 'install-proof.json'), 'utf8'));
  assert.equal(proof.status, 'rolled-back'); assert.deepEqual(proof.rollbackErrors, []);
  assert.doesNotMatch(JSON.stringify(proof), /rollback-secret/);
});

test('path traversal, protected paths, duplicate case names and non-PS2 bundles are rejected without changes', t => {
  for (const bad of ['../outside.txt', '/outside.txt', 'C:/outside.txt', 'server\\outside.txt', 'server/../outside.txt', 'server/file.txt:stream', 'server/NUL.txt', 'server/trailing. ', 'launcher.config.json', 'certificates/site.key', 'PeerStream/server.js']) {
    const f = fixture(t); f.manifest.files[0].path = bad; f.saveManifest();
    assert.throws(() => f.run(), /路径|覆盖|保留/); assert.deepEqual(fs.readdirSync(f.target), []);
  }
  const duplicate = fixture(t); duplicate.manifest.files.push({ ...duplicate.manifest.files[0], path: EXE.toLowerCase() }); duplicate.saveManifest();
  assert.throws(() => duplicate.run(), /重复/);
  const legacy = fixture(t); legacy.manifest.pixelStreamingPlugin = 'PixelStreaming'; legacy.saveManifest();
  assert.throws(() => legacy.run(), /PixelStreaming2/);
});

test('volume roots, nested deployments and live target processes cannot be updated', t => {
  const f = fixture(t);
  assert.throws(() => inspect(f.source, path.parse(f.target).root), /根目录/);
  assert.throws(() => inspect(f.source, f.source), /嵌套/);
  assert.throws(() => inspect(f.source, path.join(f.source, 'nested')), /嵌套/);
  assert.throws(() => f.run('apply', { processes: () => [{ ProcessId: 555, Name: 'node.exe', ExecutablePath: path.join(f.target, 'runtime/node.exe') }] }), /运行进程.*555/);
  assert.deepEqual(fs.readdirSync(f.target), []);
});

test('source links and destination directory junctions are rejected', t => {
  const f = fixture(t), outside = path.join(f.root, 'outside'); fs.mkdirSync(outside);
  const nested = path.join(f.source, 'server'); fs.renameSync(nested, path.join(outside, 'server'));
  fs.symlinkSync(path.join(outside, 'server'), nested, process.platform === 'win32' ? 'junction' : 'dir');
  assert.throws(() => f.run(), /符号链接|目录联接/);
  fs.rmSync(nested); fs.renameSync(path.join(outside, 'server'), nested);
  fs.symlinkSync(outside, path.join(f.target, 'server'), process.platform === 'win32' ? 'junction' : 'dir');
  assert.throws(() => f.run(), /符号链接|目录联接/);
});

test('CLI requires explicit mode and refuses duplicate or unknown flags', () => {
  assert.deepEqual(parseCLI(['--source', 'C:\\Source', '--target', 'C:\\Target', '--check']), { source: 'C:\\Source', target: 'C:\\Target', mode: 'check' });
  assert.throws(() => parseCLI(['--check', '--apply']), /一种/);
  assert.throws(() => parseCLI(['--source', '--apply']), /缺失/);
  assert.throws(() => parseCLI(['--force']), /未知/);
});
