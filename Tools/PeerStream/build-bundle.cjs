'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const project = path.resolve(__dirname, '../..');
const baselineSha = '8d587e5dcb88fbde862026c40a4cc8c3ccf2c52d8eb9c33238a208bbcd345c6d';
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function buildBundle(output, peerBuild = path.join(project, 'Saved/PeerComparison20261029/PeerStreamBuild')) {
  const destination = path.resolve(output);
  if (fs.existsSync(destination)) throw Error('Bundle output already exists; choose a new directory.');
  const saved = path.join(project, 'Saved') + path.sep;
  if (!destination.startsWith(saved)) throw Error('Comparison transfer bundles must be created under project Saved.');
  for (const file of ['host.cjs', 'service.cjs', 'signal.js', 'player-session.js', 'peer-stream.js', 'player.html']) {
    if (!fs.statSync(path.join(peerBuild, file), { throwIfNoEntry: false })?.isFile()) throw Error('Missing built peer file: ' + file);
  }
  const files = [], scripts = [];
  function copy(source, relative, entries) {
    const target = path.join(destination, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true }); fs.copyFileSync(source, target);
    entries.push({ path: relative.replace(/^payload\//, ''), bytes: fs.statSync(target).size, sha256: hash(target) });
  }
  function walk(dir, prefix = '') {
    for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!prefix && ['runtime', 'settings.json', 'logs', '.state'].includes(item.name)) continue;
      if (item.isSymbolicLink()) throw Error('Symlinks are not permitted in a transfer bundle.');
      const relative = prefix + item.name, source = path.join(dir, item.name);
      if (item.isDirectory()) walk(source, relative + '/');
      else if (item.isFile()) copy(source, 'payload/PeerStream/' + relative, files);
    }
  }
  walk(path.resolve(peerBuild));
  for (const file of ['service.js', 'peer-comparison-proxy.js']) copy(path.join(project, 'Tools/PixelStreaming/server', file), 'payload/server/' + file, files);
  const sidecar = path.join(destination, 'payload/server/peer-comparison.json');
  fs.writeFileSync(sidecar, JSON.stringify({ enabled: true, port: 8088 }, null, 2) + '\n');
  files.push({ path: 'server/peer-comparison.json', bytes: fs.statSync(sidecar).size, sha256: hash(sidecar) });
  for (const file of ['Comparison-Common.ps1', 'Install-PeerComparison.ps1', 'Rollback-PeerComparison.ps1']) copy(path.join(__dirname, 'deployment', file), file, scripts);
  const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: project, encoding: 'utf8', windowsHide: true }).trim();
  const sourceDirty = !!execFileSync('git', ['status', '--porcelain', '--', 'Tools/PeerStream', 'Tools/PixelStreaming/server'], { cwd: project, encoding: 'utf8', windowsHide: true }).trim();
  const manifest = { version: 1, bundleId: 'peer-comparison-' + crypto.randomUUID(), createdAt: new Date().toISOString(), sourceCommit, sourceDirty,
    expectedServiceSha256: baselineSha, width: 1920, height: 1080, fps: 60, files: files.sort((a, b) => a.path.localeCompare(b.path)), scripts };
  fs.writeFileSync(path.join(destination, 'bundle-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  console.log(JSON.stringify({ directory: destination, files: files.length, payloadBytes: files.reduce((total, f) => total + f.bytes, 0), sourceCommit, sourceDirty }));
  return destination;
}
module.exports = { buildBundle, baselineSha };
if (require.main === module) {
  const index = process.argv.indexOf('--output');
  if (index < 0 || !process.argv[index + 1]) throw Error('Required: --output Saved/<new-bundle-directory>');
  buildBundle(process.argv[index + 1]);
}
