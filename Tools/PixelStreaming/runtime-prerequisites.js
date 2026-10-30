'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const REDIST = 'Engine/Extras/Redist/en-us';
const FILES = ['vc_redist.x64.exe', 'GameInputRedist.msi'];
const digest = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

function stagePrerequisites(engineRoot, outputRoot) {
  const version = JSON.parse(fs.readFileSync(path.join(engineRoot, 'Engine/Build/Build.version'), 'utf8').replace(/^\uFEFF/, ''));
  if (version.MajorVersion !== 5 || version.MinorVersion !== 8) throw Error('运行组件必须来自 UE5.8 引擎目录');
  const sources = FILES.map(file => ({ file, source: path.join(engineRoot, REDIST, file), relative: 'App/Windows/' + REDIST + '/' + file }));
  for (const item of sources) if (!fs.statSync(item.source, { throwIfNoEntry: false })?.isFile()) throw Error('UE5.8 官方运行组件缺失：' + item.source);
  // Validate the complete source set before changing the delivery directory.
  const destination = path.join(outputRoot, 'App/Windows', REDIST); fs.mkdirSync(destination, { recursive: true });
  return sources.map(item => {
    const target = path.join(outputRoot, item.relative); fs.copyFileSync(item.source, target);
    const sha256 = digest(item.source); if (digest(target) !== sha256) throw Error('运行组件复制校验失败：' + item.file);
    return { path: item.relative, sha256, bytes: fs.statSync(target).size };
  });
}
module.exports = { stagePrerequisites, FILES, REDIST };
