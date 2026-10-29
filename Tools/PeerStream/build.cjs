const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const source = __dirname;
const root = path.resolve(source, '../..');
function replaceOnce(text, before, after) {
  if (text.split(before).length !== 2) throw Error('Upstream anchor changed: ' + before.slice(0, 70));
  return text.replace(before, after);
}
function adapt(text) {
  text = replaceOnce(text, 'Object.assign(global, require("./signal.json"));', 'Object.assign(global, require("./host.cjs").signalConfig());');
  // Keep the upstream UE5.4 signalling, one-to-one assignment and queue. Replace
  // deployment side effects and process execution with the scoped local host.
  text = text.slice(0, text.indexOf('//////////////////////////////////')) + text.slice(text.indexOf('const { Server }'));
  const start = text.indexOf('function StartExecUe()');
  const end = text.indexOf('\nInitUe5Pool();', start);
  if (start < 0 || end < 0) throw Error('Missing launch adapter anchors');
  text = text.slice(0, start) + 'function StartExecUe() {\n const item = GetFreeUe5();\n if (item) { item[4] = new Date(); require("./host.cjs").launchUE(String(item[2])); }\n}\n' + text.slice(end);
  const httpStart = text.indexOf('async function POST(');
  const httpEnd = text.indexOf('\nserve(PORT);', httpStart);
  if (httpStart < 0 || httpEnd < 0) throw Error('Missing HTTP adapter anchors');
  text = text.slice(0, httpStart) + 'global.serve = require("./host.cjs").serve;\n' + text.slice(httpEnd);
  text = replaceOnce(text, 'serve(PORT);', 'serve(PORT).catch(error => { console.error(error); process.exit(1); });');
  text = replaceOnce(text, 'child_process.exec(\n\t`start http://${address}:${PORT}/#signal.json`\n);', '// Browser opening is controlled by the operator.');
  const commandLine = text.indexOf('// command line');
  if (commandLine < 0) throw Error('Missing console adapter anchor');
  text = text.slice(0, commandLine);
  text = text.replaceAll('msg = JSON.parse(msg.data);', 'try { msg = JSON.parse(msg.data); } catch { return; }\n if (!msg || typeof msg !== "object" || Array.isArray(msg)) return;');
  text = text.replaceAll('console.clear();', '');
  return text;
}
function build(output) {
  const destination = path.resolve(output || path.join(root, 'Deployment/GHSPeerStream'));
  if (destination === source || destination.startsWith(source + path.sep)) throw Error('Output must not overwrite source');
  const manifest = JSON.parse(fs.readFileSync(path.join(source, 'upstream/manifest.json')));
  for (const [name, expected] of Object.entries(manifest.files)) {
    const actual = crypto.createHash('sha256').update(fs.readFileSync(path.join(source, 'upstream', name))).digest('hex');
    if (actual !== expected) throw Error('Upstream hash mismatch: ' + name);
  }
  fs.mkdirSync(destination, { recursive: true });
  const upstream = fs.readFileSync(path.join(source, 'upstream/signal.js'), 'utf8').replaceAll('\r\n', '\n');
  fs.writeFileSync(path.join(destination, 'signal.js'), adapt(upstream));
  fs.copyFileSync(path.join(source, 'upstream/peer-stream.js'), path.join(destination, 'peer-stream.js'));
  for (const file of ['host.cjs', 'service.cjs', 'player.html', 'player-session.js', 'Start.ps1', 'Stop.ps1', 'Status.ps1', 'Start.cmd', 'Stop.cmd', 'Status.cmd', 'README.md']) {
    fs.copyFileSync(path.join(source, file), path.join(destination, file));
  }
  if (!fs.existsSync(path.join(destination, 'settings.json'))) fs.copyFileSync(path.join(source, 'settings.example.json'), path.join(destination, 'settings.json'));
  const packages = JSON.parse(fs.readFileSync(path.join(root, 'Tools/PixelStreaming/dependency-pins.json'))).packages;
  const ws = packages.find(p => p.name === 'ws');
  const archive = path.join(root, 'Tools/PixelStreaming/vendor', ws.archive);
  if ('sha512-' + crypto.createHash('sha512').update(fs.readFileSync(archive)).digest('base64') !== ws.integrity) throw Error('ws archive integrity mismatch');
  const wsDir = path.join(destination, 'node_modules/ws');
  fs.mkdirSync(wsDir, { recursive: true });
  execFileSync('tar', ['-xf', archive, '-C', wsDir, '--strip-components=1'], { windowsHide: true });
  fs.mkdirSync(path.join(destination, 'runtime'), { recursive: true });
  fs.copyFileSync(path.join(root, 'Deployment/GHSPixelStreaming/runtime/node.exe'), path.join(destination, 'runtime/node.exe'));
  const license = path.join(root, 'Deployment/GHSPixelStreaming/runtime/LICENSE.txt');
  if (fs.existsSync(license)) fs.copyFileSync(license, path.join(destination, 'runtime/LICENSE.txt'));
  fs.copyFileSync(path.join(source, 'upstream/README.md'), path.join(destination, 'UPSTREAM-LICENSE-README.md'));
  fs.writeFileSync(path.join(destination, 'provenance.json'), JSON.stringify({ ...manifest, dependency: ws, adaptation: 'See Tools/PeerStream/build.cjs and README.md; upstream media SDK unchanged.' }, null, 2) + '\n');
  console.log(destination);
}
module.exports = { adapt, build };
if (require.main === module) {
  const index = process.argv.indexOf('--output');
  if (index >= 0 && !process.argv[index + 1]) throw Error('--output needs a directory');
  build(index < 0 ? undefined : process.argv[index + 1]);
}
