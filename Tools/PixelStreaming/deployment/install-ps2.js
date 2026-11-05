'use strict';
// Run using the NEW package's runtime/node.exe; never the target runtime.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');

const MANAGED = ['App', 'server', 'player', 'runtime', 'node_modules'];
const EXE = 'App/Windows/Test/Binaries/Win64/TestGame-Win64-Shipping.exe';
const REQUIRED = [EXE, 'server/server.js', 'player/index.html', 'runtime/node.exe', 'node_modules/ws/package.json', '像素流服务启动器.exe'];
const PROTECTED = new Set(['launcher.config.json', 'delivery-manifest.json', '_updates', 'logs', 'sessions', 'certificates', 'peerstream']);
const MEDIA_SETTINGS = 'server/media-address.json';
const MIGRATION = { encoderAsync: true, encoder: 'NVIDIA', fixedFps: true, fps: 60, adaptiveResourceBudget: false, executablePath: EXE };
const same = (a, b) => process.platform === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b;
const within = (root, item) => same(root, item) || (process.platform === 'win32' ? item.toLowerCase().startsWith(root.toLowerCase() + path.sep) : item.startsWith(root + path.sep));

function hashFile(file) {
  const hash = crypto.createHash('sha256'), buffer = Buffer.allocUnsafe(1024 * 1024), fd = fs.openSync(file, 'r');
  try { let length; while ((length = fs.readSync(fd, buffer, 0, buffer.length, null)) > 0) hash.update(buffer.subarray(0, length)); }
  finally { fs.closeSync(fd); }
  return hash.digest('hex');
}
function stat(file) { try { return fs.lstatSync(file); } catch (error) { if (error.code === 'ENOENT') return null; throw error; } }
function noLinks(file) {
  const absolute = path.resolve(file), parsed = path.parse(absolute);
  let current = parsed.root;
  for (const part of absolute.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    const info = stat(current);
    if (info?.isSymbolicLink()) throw Error('拒绝符号链接或目录联接：' + current);
    if (info && !same(current, absolute) && !info.isDirectory()) throw Error('路径父级不是目录：' + current);
  }
}
function checkedRoot(input, label) {
  if (typeof input !== 'string' || !input.trim() || !path.isAbsolute(input)) throw Error(label + '必须为绝对路径');
  let root = path.resolve(input);
  if (same(root, path.parse(root).root)) throw Error(label + '不能为磁盘根目录');
  noLinks(root);
  if (stat(root) && !stat(root).isDirectory()) throw Error(label + '不是目录');
  // Canonicalize existing ancestors too, so Windows short names cannot bypass
  // overlap/process checks when the new target directory does not exist yet.
  let ancestor = root; const suffix = [];
  while (!stat(ancestor)) { suffix.unshift(path.basename(ancestor)); ancestor = path.dirname(ancestor); }
  root = path.join(fs.realpathSync.native(ancestor), ...suffix);
  return root;
}
function relativePath(value) {
  if (typeof value !== 'string' || !value || value.length > 1000 || /[\\\x00-\x1f<>:"|?*]/.test(value) || path.posix.isAbsolute(value)) throw Error('manifest 包含非法路径');
  const parts = value.split('/');
  for (const part of parts) {
    if (!part || part === '.' || part === '..' || /[. ]$/.test(part) || /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part)) throw Error('manifest 包含路径穿越或保留名称');
  }
  return parts;
}
function jsonObject(file, label) {
  let value;
  try { value = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '')); } catch { throw Error(label + '不是有效的 JSON'); }
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error(label + '必须为 JSON 对象');
  return value;
}
function verifyFile(root, entry) {
  const file = path.join(root, ...relativePath(entry.path));
  if (!within(root, file)) throw Error('manifest 路径越界');
  noLinks(file);
  const info = stat(file);
  if (!info?.isFile() || info.size !== entry.bytes || hashFile(file) !== entry.sha256.toLowerCase()) throw Error('文件完整性校验失败：' + entry.path);
}
function inspect(source, target) {
  const sourceRoot = checkedRoot(source, '源目录'), targetRoot = checkedRoot(target, '目标目录');
  if (!stat(sourceRoot)?.isDirectory()) throw Error('源目录不存在');
  if (within(sourceRoot, targetRoot) || within(targetRoot, sourceRoot)) throw Error('源目录和目标目录不能相同或相互嵌套');
  const manifestPath = path.join(sourceRoot, 'delivery-manifest.json');
  noLinks(manifestPath);
  if (!stat(manifestPath)?.isFile() || stat(manifestPath).size > 16 * 1024 * 1024) throw Error('交付清单不存在或过大');
  const manifest = jsonObject(manifestPath, '交付清单');
  if (manifest.version !== 1 || manifest.pixelStreamingPlugin !== 'PixelStreaming2' || !/^5\.8(?:\.|$)/.test(String(manifest.engine))) throw Error('仅接受 UE5.8 PixelStreaming2 交付包');
  if (!Array.isArray(manifest.files) || manifest.files.length === 0 || manifest.files.length > 100000) throw Error('交付清单文件列表无效');
  const names = new Set(), units = new Set(MANAGED);
  for (const entry of manifest.files) {
    if (!entry || typeof entry !== 'object' || !Number.isSafeInteger(entry.bytes) || entry.bytes < 0 || typeof entry.sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(entry.sha256)) throw Error('交付清单文件校验字段无效');
    const parts = relativePath(entry.path), key = entry.path.toLowerCase();
    if (names.has(key)) throw Error('交付清单包含重复文件路径');
    names.add(key);
    if (key === MEDIA_SETTINGS || PROTECTED.has(parts[0].toLowerCase()) || (parts.length > 1 && !MANAGED.includes(parts[0])) || (parts.length === 1 && MANAGED.includes(parts[0]))) throw Error('交付清单试图覆盖非受管路径：' + entry.path);
    if (parts.length === 1) units.add(parts[0]);
    verifyFile(sourceRoot, entry);
  }
  for (const file of REQUIRED) if (!names.has(file.toLowerCase())) throw Error('交付清单缺少必要文件：' + file);
  for (const unit of [...units, 'launcher.config.json', 'delivery-manifest.json', '_updates']) noLinks(path.join(targetRoot, unit));
  return { source: sourceRoot, target: targetRoot, manifest, manifestHash: hashFile(manifestPath), names, units: [...units] };
}
function processes() {
  if (process.platform !== 'win32') throw Error('安装器只支持 Windows；无法核对目标进程');
  const command = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); @(Get-CimInstance Win32_Process -ErrorAction Stop | Select-Object ProcessId,Name,ExecutablePath) | ConvertTo-Json -Compress";
  try { const result = JSON.parse(execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', command], { encoding: 'utf8', windowsHide: true, timeout: 30000 })); return Array.isArray(result) ? result : [result]; }
  catch { throw Error('无法读取 Windows 进程列表，拒绝在未确认停止的情况下更新'); }
}
function assertStopped(target, list) {
  if (within(target, path.resolve(process.execPath))) throw Error('请使用新包 source/runtime/node.exe 运行安装器，不能使用目标目录中的 Node');
  const active = list.filter(p => {
    const executable = p.ExecutablePath ?? p.executablePath;
    if (Number(p.ProcessId ?? p.pid) === process.pid || typeof executable !== 'string') return false;
    const absolute = path.resolve(executable), resolved = stat(absolute) ? fs.realpathSync.native(absolute) : absolute;
    return within(target, resolved);
  });
  if (active.length) throw Error('目标目录仍有运行进程，请先停止启动器和场景：' + active.map(p => String(p.ProcessId ?? p.pid)).join(','));
}
function oldOwnedPaths(target) {
  const file = path.join(target, 'delivery-manifest.json');
  if (!stat(file)) return null;
  const old = jsonObject(file, '现有交付清单');
  return new Set(Array.isArray(old.files) ? old.files.filter(f => typeof f?.path === 'string').map(f => f.path.toLowerCase()) : []);
}
function preserveServerSettings(plan, staged) {
  const directory = path.join(plan.target, 'server'), oldOwned = oldOwnedPaths(plan.target);
  if (!stat(directory)) return 0;
  let count = 0;
  function walk(dir, relative) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name), name = relative + '/' + entry.name;
      noLinks(file);
      if (entry.isDirectory()) walk(file, name);
      else if (entry.isFile() && !plan.names.has(name.toLowerCase()) && (name.toLowerCase() === MEDIA_SETTINGS || (oldOwned ? !oldOwned.has(name.toLowerCase()) : /(?:\.json|\.pem|\.crt|\.cer|\.pfx|\.p12|\.key|\.ini|\.conf|\.config|\.env)$/i.test(name)))) {
        const destination = path.join(staged, ...relativePath(name));
        fs.mkdirSync(path.dirname(destination), { recursive: true }); fs.copyFileSync(file, destination); count++;
      }
    }
  }
  walk(directory, 'server');
  return count;
}
function writeJSON(file, value) { fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n', { encoding: 'utf8', mode: 0o600 }); }
function install(options, dependencies = {}) {
  if (!['check', 'apply'].includes(options.mode)) throw Error('必须指定 --check 或 --apply');
  // All hashes, path checks and process checks precede the first write.
  const plan = inspect(options.source, options.target), processList = dependencies.processes || processes;
  assertStopped(plan.target, processList());
  const configFile = path.join(plan.target, 'launcher.config.json');
  const configExisted = !!stat(configFile), configHash = configExisted ? hashFile(configFile) : null;
  const mediaFile = path.join(plan.target, ...MEDIA_SETTINGS.split('/')); noLinks(mediaFile);
  const mediaHash = stat(mediaFile) ? hashFile(mediaFile) : null;
  const defaultsFile = path.join(plan.source, 'launcher.config.json');
  noLinks(defaultsFile);
  const configuration = configExisted ? jsonObject(configFile, '现有启动器配置') : stat(defaultsFile) ? jsonObject(defaultsFile, '新包启动器配置') : {};
  const nextConfiguration = { ...configuration, ...MIGRATION };
  const result = { operation: options.mode, status: options.mode === 'check' ? 'verified' : 'pending', engine: plan.manifest.engine, pixelStreamingPlugin: 'PixelStreaming2', source: plan.source, target: plan.target, manifestSha256: plan.manifestHash, fileCount: plan.manifest.files.length, bytes: plan.manifest.files.reduce((total, file) => total + file.bytes, 0), configPreserved: configExisted, changedConfigKeys: Object.keys(MIGRATION) };
  if (options.mode === 'check') return result;
  const updateName = 'PS2-' + new Date().toISOString().replace(/[:.]/g, '-') + '-' + crypto.randomBytes(4).toString('hex');
  const updateRoot = path.join(plan.target, '_updates', updateName), staged = path.join(updateRoot, 'staged'), backup = path.join(updateRoot, 'backup');
  noLinks(updateRoot);
  fs.mkdirSync(staged, { recursive: true }); fs.mkdirSync(backup);
  const proofPath = path.join(updateRoot, 'install-proof.json');
  const journal = [], rename = dependencies.rename || fs.renameSync;
  try {
    for (const entry of plan.manifest.files) {
      const destination = path.join(staged, ...relativePath(entry.path));
      fs.mkdirSync(path.dirname(destination), { recursive: true }); fs.copyFileSync(path.join(plan.source, ...entry.path.split('/')), destination);
      verifyFile(staged, entry);
    }
    result.preservedServerFiles = preserveServerSettings(plan, staged);
    fs.copyFileSync(path.join(plan.source, 'delivery-manifest.json'), path.join(staged, 'delivery-manifest.json'));
    if (hashFile(path.join(staged, 'delivery-manifest.json')) !== plan.manifestHash) throw Error('复制期间源清单发生变化');
    writeJSON(path.join(staged, 'launcher.config.json'), nextConfiguration);
    assertStopped(plan.target, processList());
    if ((stat(configFile) ? hashFile(configFile) : null) !== configHash) throw Error('准备期间配置发生变化，请重新执行更新');
    noLinks(mediaFile);
    if ((stat(mediaFile) ? hashFile(mediaFile) : null) !== mediaHash) throw Error('准备期间媒体配置发生变化，请重新执行更新');
    for (const unit of [...plan.units, 'launcher.config.json', 'delivery-manifest.json']) {
      const target = path.join(plan.target, unit), source = path.join(staged, unit), saved = path.join(backup, unit);
      noLinks(target); noLinks(source); noLinks(saved);
      const operation = { unit, oldMoved: false, newMoved: false }; journal.push(operation);
      if (stat(target)) { rename(target, saved); operation.oldMoved = true; }
      if (stat(source)) { rename(source, target); operation.newMoved = true; }
    }
    for (const entry of plan.manifest.files) verifyFile(plan.target, entry);
    result.status = 'installed'; result.backup = backup; result.completedAt = new Date().toISOString();
    writeJSON(proofPath, result);
    return { ...result, proof: proofPath };
  } catch (error) {
    const rollbackErrors = [];
    for (const operation of journal.reverse()) {
      try {
        const target = path.join(plan.target, operation.unit), saved = path.join(backup, operation.unit), failed = path.join(staged, operation.unit);
        noLinks(target); noLinks(saved); noLinks(failed);
        if (operation.newMoved && stat(target)) fs.renameSync(target, failed);
        if (operation.oldMoved && stat(saved)) fs.renameSync(saved, target);
      } catch { rollbackErrors.push(operation.unit); }
    }
    writeJSON(proofPath, { ...result, status: rollbackErrors.length ? 'rollback-incomplete' : 'rolled-back', failedAt: new Date().toISOString(), rollbackErrors });
    // Configuration values and native error messages are deliberately excluded from proof.
    throw Error((rollbackErrors.length ? '更新失败，部分回滚需检查备份' : '更新失败，已回滚受管文件') + '；记录：' + proofPath + '；原因：' + error.message);
  }
}
function parseCLI(argv) {
  const options = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--source' || arg === '--target') { if (options[arg.slice(2)] !== undefined || !argv[i + 1] || argv[i + 1].startsWith('--')) throw Error('参数缺失或重复：' + arg); options[arg.slice(2)] = argv[++i]; }
    else if (arg === '--check' || arg === '--apply') { if (options.mode) throw Error('只能选择一种执行模式'); options.mode = arg.slice(2); }
    else throw Error('未知参数：' + arg);
  }
  return options;
}
if (require.main === module) {
  try { console.log(JSON.stringify(install(parseCLI(process.argv.slice(2))), null, 2)); }
  catch (error) { console.error(JSON.stringify({ status: 'failed', message: error.message })); process.exitCode = 1; }
}
module.exports = { install, inspect, parseCLI, hashFile, assertStopped };
