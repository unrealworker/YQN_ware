'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { createService } = require('./service');
async function main() {
  const args = process.argv.slice(2); const value = key => { const i = args.indexOf(key); if (i < 0 || !args[i + 1]) throw Error('缺少参数 ' + key); return args[i + 1]; };
  const configPath = path.resolve(value('--config')); const controlPath = path.resolve(value('--control-file'));
  const config = JSON.parse(fs.readFileSync(configPath, 'utf8').replace(/^\uFEFF/, ''));
  if (config.executablePath && !path.isAbsolute(config.executablePath)) config.executablePath = path.resolve(path.dirname(configPath), config.executablePath);
  const service = createService(config, { controlRoot: path.join(path.dirname(controlPath), 'instances'), onLog: line => console.log(line), onStopped: () => shutdown(0) });
  let stopping = false;
  const shutdown = async code => { if (stopping) return; stopping = true; await service.stop(); try { fs.unlinkSync(controlPath); } catch {} process.exit(code); };
  process.on('SIGINT', () => shutdown(0)); process.on('SIGTERM', () => shutdown(0));
  process.on('uncaughtException', e => { console.error(e.stack); shutdown(1); });
  process.on('unhandledRejection', e => { console.error(e); shutdown(1); });
  try {
    await service.start();
    fs.mkdirSync(path.dirname(controlPath), { recursive: true });
    fs.writeFileSync(controlPath + '.tmp', JSON.stringify({ controlPort: service.controlPort, pid: process.pid, httpPort: service.config.httpPort, streamerPort: service.config.streamerPort }));
    fs.renameSync(controlPath + '.tmp', controlPath);
  } catch (e) { console.error('启动失败：' + e.message); await shutdown(1); }
}
main().catch(e => { console.error(e.message); process.exitCode = 1; });
