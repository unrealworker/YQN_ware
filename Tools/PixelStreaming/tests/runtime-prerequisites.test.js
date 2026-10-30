'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { stagePrerequisites, FILES, REDIST } = require('../runtime-prerequisites');
function fixture(t, minor = 8) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ghs-redist-')); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const engine = path.join(root, 'engine'); fs.mkdirSync(path.join(engine, 'Engine/Build'), { recursive: true }); fs.mkdirSync(path.join(engine, REDIST), { recursive: true });
  fs.writeFileSync(path.join(engine, 'Engine/Build/Build.version'), JSON.stringify({ MajorVersion: 5, MinorVersion: minor, PatchVersion: 4 }));
  for (const file of FILES) fs.writeFileSync(path.join(engine, REDIST, file), 'fixture-only:' + file);
  return { engine, output: path.join(root, 'delivery') };
}
test('UE5.8 packages VC++ x64 and GameInput from the selected engine with exact hashes', t => {
  const f = fixture(t), manifest = stagePrerequisites(f.engine, f.output); assert.equal(manifest.length, 2);
  for (const item of manifest) { assert.match(item.sha256, /^[a-f0-9]{64}$/); assert.deepEqual(fs.readFileSync(path.join(f.output, item.path)), fs.readFileSync(path.join(f.engine, REDIST, path.basename(item.path)))); }
  assert.equal(fs.existsSync(path.join(f.output, 'App/Windows', REDIST, 'UEPrereqSetup_x64.exe')), false);
  assert.equal(fs.existsSync(path.join(f.output, 'App/Windows', REDIST, 'vc_redist.arm64.exe')), false);
});
test('wrong engine or incomplete runtime set fails before staging any prerequisite', t => {
  const wrong = fixture(t, 4); assert.throws(() => stagePrerequisites(wrong.engine, wrong.output), /UE5.8/); assert.equal(fs.existsSync(wrong.output), false);
  const missing = fixture(t); fs.unlinkSync(path.join(missing.engine, REDIST, 'GameInputRedist.msi')); assert.throws(() => stagePrerequisites(missing.engine, missing.output), /缺失/); assert.equal(fs.existsSync(missing.output), false);
});
