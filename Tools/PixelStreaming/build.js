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
// Rebuild extracted dependencies from the verified archives, including on a clean checkout.
for (const [archive, directory] of [['epic-ue5.4-1.1.6.tgz', 'vendor/package'], ['sdp-3.2.1.tgz', 'vendor/sdp'], ['ws-8.18.3.tgz', 'node_modules/ws']]) {
  const destination = path.join(root, directory);
  fs.mkdirSync(destination, { recursive: true });
  execFileSync('tar', ['-xzf', path.join(root, 'vendor', archive), '-C', destination, '--strip-components=1']);
}
const playerVendor = path.join(root, 'player/vendor'); fs.mkdirSync(playerVendor, { recursive: true });
const patchedSDK = patchFrontendSDK(fs.readFileSync(path.join(root, 'vendor/package/dist/lib-pixelstreamingfrontend.js'), 'utf8'));
fs.writeFileSync(path.join(playerVendor, 'epic-ue5.4-1.1.6.js'), patchedSDK.code);
fs.writeFileSync(path.join(playerVendor, 'epic-sdp-patch.json'), JSON.stringify({ ...patchedSDK.manifest,
  patchScriptSha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'frontend-sdk-patch.js'))).digest('hex'),
  qualityPolicySha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'player/stream-quality.js'))).digest('hex') }, null, 2) + '\n');
fs.writeFileSync(path.join(playerVendor, 'sdp-3.2.1.js'), '(function(){\n' + fs.readFileSync(path.join(root, 'vendor/sdp/sdp.js'), 'utf8') + '\nwindow.sdp = SDPUtils;\n})();\n');
fs.copyFileSync(path.join(root, 'vendor/sdp/LICENSE'), path.join(playerVendor, 'LICENSE-sdp.txt'));
fs.copyFileSync(path.join(root, 'node_modules/ws/LICENSE'), path.join(playerVendor, 'LICENSE-ws.txt'));
for (const folder of ['server', 'player', 'node_modules/ws']) fs.cpSync(path.join(root, folder), path.join(target, folder), { recursive: true });
for (const file of ['dependency-pins.json', 'package.json']) fs.copyFileSync(path.join(root, file), path.join(target, file));
console.log('已构建并复制服务、播放器、ws依赖到 ' + target);
