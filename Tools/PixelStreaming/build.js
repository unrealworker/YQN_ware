'use strict';
const fs = require('node:fs'); const path = require('node:path'); const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { patchFrontendSDK } = require('./frontend-sdk-patch');
const root = __dirname;
const outputFlag = process.argv.indexOf('--output');
if (outputFlag >= 0 && !process.argv[outputFlag + 1]) throw Error('--output requires a directory');
const target = outputFlag >= 0 ? path.resolve(process.argv[outputFlag + 1]) : path.resolve(root, '../../Deployment/GHSPixelStreaming');
if (target === root || target.startsWith(root + path.sep)) throw Error('输出目录不能位于像素流源码中');
const pins = JSON.parse(fs.readFileSync(path.join(root, 'dependency-pins.json'), 'utf8'));
for (const pin of pins.packages) {
  const digest = 'sha512-' + crypto.createHash('sha512').update(fs.readFileSync(path.join(root, 'vendor', pin.archive))).digest('base64');
  if (digest !== pin.integrity) throw Error('依赖完整性校验失败：' + pin.name);
}
// Rebuild every module from verified offline archives. UE5.8 publishes ESM/CJS,
// so the pinned Windows bundler produces the browser bundle without npm install.
for (const [name, directory] of [
  ['@epicgames-ps/lib-pixelstreamingfrontend-ue5.8', 'vendor/ue58'],
  ['@epicgames-ps/lib-pixelstreamingcommon-ue5.8', 'vendor/common58'],
  ['@protobuf-ts/runtime', 'node_modules/@protobuf-ts/runtime'],
  ['@esbuild/win32-x64', 'vendor/esbuild'],
  ['sdp', 'vendor/sdp'], ['ws', 'node_modules/ws']
]) {
  const pin = pins.packages.find(p => p.name === name);
  if (!pin) throw Error('缺少固定依赖：' + name);
  const destination = path.join(root, directory);
  if (!destination.startsWith(root + path.sep)) throw Error('依赖输出越界');
  fs.rmSync(destination, { recursive: true, force: true });
  fs.mkdirSync(destination, { recursive: true });
  execFileSync('tar', ['-xzf', path.join(root, 'vendor', pin.archive), '-C', destination, '--strip-components=1']);
}
const playerVendor = path.join(root, 'player/vendor'); fs.mkdirSync(playerVendor, { recursive: true });
const browserModules = path.join(root, 'vendor/frontend-browser');
fs.rmSync(browserModules, { recursive: true, force: true });
fs.cpSync(path.join(root, 'vendor/ue58/dist/esm'), browserModules, { recursive: true });
const peerModule = 'PeerConnectionController/PeerConnectionController.js';
const patchedSDK = patchFrontendSDK(fs.readFileSync(path.join(browserModules, peerModule), 'utf8'));
fs.writeFileSync(path.join(browserModules, peerModule), patchedSDK.code);
const browserBundle = path.join(playerVendor, 'epic-ue5.8-0.1.3.js');
execFileSync(path.join(root, 'vendor/esbuild/esbuild.exe'), [path.join(browserModules, 'pixelstreamingfrontend.js'),
  '--bundle', '--platform=browser', '--target=es2020', '--format=iife', '--global-name=GHSPixelStreamingSDK', '--minify',
  '--legal-comments=inline', '--alias:@epicgames-ps/lib-pixelstreamingcommon-ue5.8=' + path.join(root, 'vendor/common58/dist/esm/pixelstreamingcommon.js'),
  '--alias:sdp=' + path.join(root, 'vendor/sdp/sdp.js'),
  '--footer:js=window["lib-pixelstreamingfrontend"]=GHSPixelStreamingSDK;', '--outfile=' + browserBundle
], { cwd: root, stdio: 'pipe' });
fs.writeFileSync(path.join(playerVendor, 'epic-sdp-patch.json'), JSON.stringify({ ...patchedSDK.manifest,
  bundleSha256: crypto.createHash('sha256').update(fs.readFileSync(browserBundle)).digest('hex'),
  buildScriptSha256: crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex'),
  patchScriptSha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'frontend-sdk-patch.js'))).digest('hex'),
  qualityPolicySha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'player/stream-quality.js'))).digest('hex') }, null, 2) + '\n');
// Remove only obsolete generated SDK files, including when rebuilding in-place.
for (const directory of [playerVendor, path.join(target, 'player/vendor')]) {
  for (const filename of fs.existsSync(directory) ? fs.readdirSync(directory) : []) {
    if (/^epic-ue5\.4-.*\.js$/.test(filename) || filename === 'sdp-3.2.1.js') fs.rmSync(path.join(directory, filename));
  }
}
fs.copyFileSync(path.join(root, 'vendor/sdp/LICENSE'), path.join(playerVendor, 'LICENSE-sdp.txt'));
fs.copyFileSync(path.join(root, 'node_modules/ws/LICENSE'), path.join(playerVendor, 'LICENSE-ws.txt'));
fs.copyFileSync(path.join(root, 'node_modules/@protobuf-ts/runtime/LICENSE'), path.join(playerVendor, 'LICENSE-protobuf-ts-runtime.txt'));
// Server EIP mappings belong to the destination host, never the build machine.
for (const folder of ['server', 'player', 'node_modules/ws']) fs.cpSync(path.join(root, folder), path.join(target, folder), { recursive: true, filter: source => path.relative(root, source).replace(/\\/g, '/').toLowerCase() !== 'server/media-address.json' });
for (const file of ['dependency-pins.json', 'package.json']) fs.copyFileSync(path.join(root, file), path.join(target, file));
console.log('已构建并复制服务、播放器、ws依赖到 ' + target);
