'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const net = require('node:net');
const { execFileSync } = require('node:child_process');
const { buildBundle, baselineSha } = require('../build-bundle.cjs');
const project = path.resolve(__dirname, '../../..');
const area = path.join(project, 'Saved/PeerComparison20261029');
const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const ps = (script, args = []) => execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', script, ...args], { encoding: 'utf8', windowsHide: true, timeout: 45000, stdio: ['ignore', 'pipe', 'pipe'] });
const json = file => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
function snapshot(root) {
  const result = {};
  function visit(dir) { for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, e.name), relative = path.relative(root, file);
    if (e.isDirectory()) { result[relative + '/'] = true; visit(file); }
    else result[relative] = { sha: sha(file), mtime: fs.statSync(file).mtimeMs };
  }} visit(root); return result;
}
function fixture(directory) {
  fs.mkdirSync(directory, { recursive: true });
  const files = {
    'server/service.js': fs.readFileSync(path.join(project, 'Package_PublicStreaming_Optimized_20261028/server/service.js')),
    'runtime/node.exe': 'fixture-only node runtime; never execute',
    'runtime/LICENSE.txt': 'fixture runtime license',
    'App/Windows/Test/Binaries/Win64/TestGame-Win64-Shipping.exe': 'unchanged fixture UE application',
    'App/Windows/Test/Content/Paks/Test.pak': 'unchanged scene fixture'
  };
  for (const [relative, value] of Object.entries(files)) { const target = path.join(directory, relative); fs.mkdirSync(path.dirname(target), { recursive: true }); fs.writeFileSync(target, value); }
  assert.equal(sha(path.join(directory, 'server/service.js')), baselineSha);
  const config = {
    executablePath: 'App/Windows/Test/Binaries/Win64/TestGame-Win64-Shipping.exe', httpPort: 8080, streamerPort: 8888,
    width: 1280, height: 720, fps: 0, adaptiveResourceBudget: true, maxViewers: 8,
    qualityProfile: 'clear', minBitrateMbps: 2, startBitrateMbps: 9, maxBitrateMbps: 25,
    accessCode: 'fixture-secret-do-not-log', turnUrl: 'turn:relay.invalid:3478', stunUrl: 'stun:stun.invalid:3478',
    turnUsername: 'fixture-user', turnPassword: 'fixture-password-do-not-log', publicUrl: 'https://warehouse.example/',
    unknownSetting: { unicode: '\u4fdd\u7559\u7528\u6237\u914d\u7f6e', enabled: false, children: [1, null, 'value'] }
  };
  fs.writeFileSync(path.join(directory, 'launcher.config.json'), '\ufeff' + JSON.stringify(config, null, 3));
  const manifest = { version: 1, sourceCommit: 'original-application-commit', mapSha256: sha(path.join(directory, 'App/Windows/Test/Content/Paks/Test.pak')), userField: 'preserved', files: Object.keys(files).map(relative => ({ path: relative, bytes: fs.statSync(path.join(directory, relative)).size, sha256: sha(path.join(directory, relative)) })) };
  fs.writeFileSync(path.join(directory, 'delivery-manifest.json'), JSON.stringify(manifest, null, 2));
  return { config, manifest };
}
function useStoppedPortProbeInFixture(bundle) {
  // A separate, already-running local legacy service owns 8088. Do not stop it
  // just to exercise filesystem transactions. This fixture-only test double
  // replaces ONLY the listener probe; production scripts have no bypass flag.
  // The unmodified production guard is exercised in the next test.
  const file = path.join(bundle, 'Comparison-Common.ps1'), content = fs.readFileSync(file, 'utf8');
  const anchor = '[Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()';
  assert.equal(content.split(anchor).length, 2);
  fs.writeFileSync(file, content.replace(anchor, '@()'));
  const manifestFile = path.join(bundle, 'bundle-manifest.json'), manifest = json(manifestFile);
  const entry = manifest.scripts.find(e => e.path === 'Comparison-Common.ps1'); entry.sha256 = sha(file); entry.bytes = fs.statSync(file).size;
  fs.writeFileSync(manifestFile, JSON.stringify(manifest));
}
test('portable bundle dry-run, apply and rollback preserve configuration and application', { timeout: 120000 }, async () => {
  fs.mkdirSync(area, { recursive: true });
  const root = fs.mkdtempSync(path.join(area, 'deployment-test-'));
  const bundle = buildBundle(path.join(root, 'bundle'));
  useStoppedPortProbeInFixture(bundle);
  const target = path.join(root, 'target'); const initial = fixture(target);
  const install = path.join(bundle, 'Install-PeerComparison.ps1');
  const original = snapshot(target);
  const manifest = json(path.join(bundle, 'bundle-manifest.json'));
  assert.ok(manifest.files.every(f => !/PeerStream\/(runtime|logs|\.state)\/|PeerStream\/settings.json/.test(f.path)));
  assert.ok(manifest.files.reduce((n, f) => n + f.bytes, 0) < 2 * 1024 * 1024, 'no large runtime/application transferred');
  const preflight = ps(install, ['-Target', target, '-DryRun']);
  assert.match(preflight, /DRY RUN OK/); assert.deepEqual(snapshot(target), original);
  const output = ps(install, ['-Target', target]);
  assert.match(output, /INSTALL OK/); assert.ok(!output.includes(initial.config.accessCode) && !output.includes(initial.config.turnPassword));
  const backup = output.match(/BACKUP=(.+)/)[1].trim();
  const actual = json(path.join(target, 'launcher.config.json'));
  assert.deepEqual(actual, { ...initial.config, width: 1920, height: 1080, fps: 60, adaptiveResourceBudget: false });
  const settings = json(path.join(target, 'PeerStream/settings.json'));
  assert.equal(settings.fps, 60); assert.equal(settings.width, 1920); assert.equal(settings.height, 1080);
  assert.equal(settings.instances, 8); assert.equal(settings.host, '127.0.0.1'); assert.equal(settings.port, 8088);
  assert.equal(settings.qualityProfile, 'clear'); assert.equal(settings.minBitrateMbps, 2); assert.equal(settings.startBitrateMbps, 9); assert.equal(settings.maxBitrateMbps, 25);
  assert.equal(settings.mediaMinPort, 50000); assert.equal(settings.mediaMaxPort, 50199); assert.equal(settings.idleTimeoutSeconds, 8);
  assert.equal(settings.executablePath, path.join(target, initial.config.executablePath));
  assert.deepEqual(settings.iceServers, [{ urls: [initial.config.stunUrl] }, { urls: [initial.config.turnUrl], username: initial.config.turnUsername, credential: initial.config.turnPassword }]);
  const applied = json(path.join(target, 'delivery-manifest.json'));
  assert.equal(applied.mapSha256, initial.manifest.mapSha256); assert.equal(applied.sourceCommit, initial.manifest.sourceCommit); assert.equal(applied.userField, 'preserved');
  for (const entry of applied.files) assert.equal(sha(path.join(target, entry.path)), entry.sha256, entry.path);
  assert.equal(sha(path.join(target, initial.config.executablePath)), original[path.normalize(initial.config.executablePath)].sha);
  assert.equal(sha(path.join(target, 'runtime/node.exe')), sha(path.join(target, 'PeerStream/runtime/node.exe')));
  assert.deepEqual(json(path.join(target, 'server/peer-comparison.json')), { enabled: true, port: 8088 });
  assert.throws(() => ps(install, ['-Target', target, '-DryRun']), /already exists/);
  const rollback = path.join(backup, 'Rollback-PeerComparison.ps1'), beforeRollback = snapshot(target);
  assert.match(ps(rollback, ['-Target', target, '-Backup', backup, '-DryRun']), /DRY RUN OK/);
  assert.deepEqual(snapshot(target), beforeRollback);
  assert.match(ps(rollback, ['-Target', target, '-Backup', backup]), /ROLLBACK OK/);
  for (const [relative, value] of Object.entries(original)) if (!relative.endsWith('/')) assert.equal(sha(path.join(target, relative)), value.sha, 'byte-exact restored: ' + relative);
  assert.equal(fs.existsSync(path.join(target, 'PeerStream')), false);
  assert.equal(fs.existsSync(path.join(backup, 'archive/PeerStream/player.html')), true);
  assert.equal(fs.existsSync(path.join(backup, 'archive/server/peer-comparison-proxy.js')), true);
  assert.equal(fs.existsSync(path.join(target, 'server/peer-comparison-proxy.js')), false);
  // Keep the isolated fixture and rollback record under Saved as reviewable evidence.
  fs.writeFileSync(path.join(root, 'result.json'), JSON.stringify({ passed: true, target, backup, bundle, payloadBytes: manifest.files.reduce((n, f) => n + f.bytes, 0) }, null, 2));
});

test('rollback preserves pre-existing proxy files and refuses later user edits', { timeout: 120000 }, () => {
  const root = fs.mkdtempSync(path.join(area, 'deployment-restore-')), bundle = buildBundle(path.join(root, 'bundle')), target = path.join(root, 'target');
  fixture(target); useStoppedPortProbeInFixture(bundle);
  const originalProxy = 'operator pre-existing proxy content', originalSidecar = '{"enabled":false,"operatorField":"keep"}';
  fs.writeFileSync(path.join(target, 'server/peer-comparison-proxy.js'), originalProxy);
  fs.writeFileSync(path.join(target, 'server/peer-comparison.json'), originalSidecar);
  const output = ps(path.join(bundle, 'Install-PeerComparison.ps1'), ['-Target', target]), backup = output.match(/BACKUP=(.+)/)[1].trim();
  const rollback = path.join(backup, 'Rollback-PeerComparison.ps1'), configFile = path.join(target, 'launcher.config.json'), installedConfig = fs.readFileSync(configFile);
  fs.appendFileSync(configFile, '\n ');
  const changed = snapshot(target);
  assert.throws(() => ps(rollback, ['-Target', target, '-Backup', backup]), /File changed after deployment/);
  assert.deepEqual(snapshot(target), changed);
  fs.writeFileSync(configFile, installedConfig);
  ps(rollback, ['-Target', target, '-Backup', backup]);
  assert.equal(fs.readFileSync(path.join(target, 'server/peer-comparison-proxy.js'), 'utf8'), originalProxy);
  assert.equal(fs.readFileSync(path.join(target, 'server/peer-comparison.json'), 'utf8'), originalSidecar);
});

test('preflight rejects tampering, existing PeerStream and active streaming listener without writes', { timeout: 120000 }, async () => {
  const root = fs.mkdtempSync(path.join(area, 'deployment-guards-')), bundle = buildBundle(path.join(root, 'bundle')), target = path.join(root, 'target');
  fixture(target); const install = path.join(bundle, 'Install-PeerComparison.ps1');
  fs.mkdirSync(path.join(target, 'PeerStream')); fs.writeFileSync(path.join(target, 'PeerStream/user.txt'), 'keep');
  const occupied = snapshot(target); assert.throws(() => ps(install, ['-Target', target, '-DryRun']), /already exists/); assert.deepEqual(snapshot(target), occupied);
  const cleanTarget = path.join(root, 'clean-target'); fixture(cleanTarget); const clean = snapshot(cleanTarget);
  const listener = net.createServer(); let ownListener = true;
  await new Promise((resolve, reject) => listener.once('error', error => { if (error.code === 'EADDRINUSE') { ownListener = false; resolve(); } else reject(error); }).listen(8088, '127.0.0.1', resolve));
  try { assert.throws(() => ps(install, ['-Target', cleanTarget, '-DryRun']), /TCP listeners active/); assert.deepEqual(snapshot(cleanTarget), clean); }
  finally { if (ownListener) await new Promise(resolve => listener.close(resolve)); }
  fs.appendFileSync(path.join(bundle, 'payload/PeerStream/player.html'), '\nTAMPERED');
  assert.throws(() => ps(install, ['-Target', cleanTarget, '-DryRun']), /SHA256 mismatch/); assert.deepEqual(snapshot(cleanTarget), clean);
  fs.copyFileSync(path.join(project, 'Saved/PeerComparison20261029/PeerStreamBuild/player.html'), path.join(bundle, 'payload/PeerStream/player.html'));
  const manifestFile = path.join(bundle, 'bundle-manifest.json'), manifest = json(manifestFile);
  manifest.files.unshift({ path: 'PeerStream/../../escape.txt', sha256: baselineSha, bytes: 0 });
  fs.writeFileSync(manifestFile, JSON.stringify(manifest));
  assert.throws(() => ps(install, ['-Target', cleanTarget, '-DryRun']), /Unsafe deployment path/); assert.deepEqual(snapshot(cleanTarget), clean);
});
