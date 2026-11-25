// Independent, read-only reconciliation. No Python mapper/importer is invoked.
// This is the 2026-11-25 snapshot audit. Usage: node verify_binding_audit.cjs [mapping.json] [audit-output-directory] [baseline.json]
// Raw WMS codes are reversed into bay/column/height instead of calling expected_code.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const childProcess = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const work = path.join(root, 'output/ghs-inventory-reaudit-20261125');
const mappingPath = process.argv[2] || path.join(root, 'Content/GHSTwinUI/data/inventory-bindings.json');
const auditDir = process.argv[3] || work;
const output = path.join(work, 'existing-review');
const csvPath = 'D:/Data/仓库数据/GHS/ghs_ca_us_ue5_location_inventory_detail_20261125.csv';
const cadPath = 'D:/Data/仓库数据/GHS/平面布局图_GHS_0.23_20260710现状.dxf';
const json = p => JSON.parse(fs.readFileSync(path.isAbsolute(p) ? p : path.join(root, p), 'utf8').replace(/^\uFEFF/, ''));
const sha = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const errors = [];
const check = (condition, reason, detail) => { if (!condition) errors.push({reason, detail}); return condition; };
const near = (a, b, tolerance = 0.00001) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v, i) => Number.isFinite(v) && Math.abs(v - b[i]) <= tolerance);
const target = b => `${b.cadId}|${b.level}|${b.column}`;
const bump = (object, key) => { object[key] = (object[key] || 0) + 1; };

function csv(text) {
  const rows = []; let row = [], cell = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') { if (quoted && text[i + 1] === '"') { cell += c; i++; } else quoted = !quoted; }
    else if (c === ',' && !quoted) { row.push(cell); cell = ''; }
    else if ((c === '\n' || c === '\r') && !quoted) {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(cell); if (row.some(Boolean)) rows.push(row); row = []; cell = '';
    } else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  if (quoted) throw Error('Unclosed CSV field');
  const fields = rows.shift(); fields[0] = fields[0].replace(/^\uFEFF/, '');
  return rows.map((values, n) => { if (values.length !== fields.length) throw Error(`CSV width at ${n + 2}`); return Object.fromEntries(fields.map((field, i) => [field, values[i]])); });
}

function dxf() {
  const lines = fs.readFileSync(cadPath, 'utf8').split(/\r?\n/);
  const inserts = new Map(); let entity = {}, current = null;
  const flush = () => {
    if (entity['0'] === 'INSERT') {
      current = {block: entity['2'], attrs: {}, position: ['10', '20', '30'].map(k => +(entity[k] || 0)), rotation: +(entity['50'] || 0), scale: ['41', '42', '43'].map(k => +(entity[k] || 1))};
      check(!inserts.has(entity['5']), 'duplicate DXF handle', entity['5']); inserts.set(entity['5'], current);
    } else if (entity['0'] === 'ATTRIB' && current) current.attrs[entity['2']] = entity['1'];
    else current = null;
  };
  for (let i = 0; i + 1 < lines.length; i += 2) {
    const key = lines[i].trim().replace(/^\uFEFF/, '');
    if (key === '0') { flush(); entity = {}; } entity[key] = lines[i + 1];
  }
  flush(); return inserts;
}

function codeParts(code) {
  const m = /^GHS-(R|SR-)(\d+)-(\d+)-(\d+)$/.exec(code);
  if (!m) return null;
  const row = `${m[1] === 'R' ? 'R' : 'SR'}${String(+m[2]).padStart(2, '0')}`;
  const ordinal = +m[3], level = +m[4];
  if (+m[2] <= 0 || ordinal <= 0 || level <= 0) return null;
  return {row, ordinal, physical: level, bay: Math.ceil(ordinal / 3), column: (ordinal - 1) % 3 + 1, numeric: `${row}|${ordinal}|${level}`};
}

const baselinePath = process.argv[4] || path.join(work, 'baseline-bindings.json');
const mapping = json(mappingPath), baseline = fs.existsSync(baselinePath) ? json(baselinePath)
  : JSON.parse(childProcess.execFileSync('git', ['show', '2fa6fe45:Content/GHSTwinUI/data/inventory-bindings.json'], {cwd:root, maxBuffer:32*1024*1024, encoding:'utf8'}));
const inventory = json('Content/GHSTwinUI/data/inventory/index.json');
const sourceSha = sha(csvPath), sourceCadSha = sha(cadPath);
check(mapping.sourceInventorySha256 === sourceSha && inventory.snapshotId === sourceSha, 'snapshot identity', sourceSha);
check(mapping.sourceCadSha256 === sourceCadSha, 'CAD identity', sourceCadSha);
for (const [name, hash] of Object.entries(mapping.sourceHashes)) check(sha(path.join(root, name)) === hash, 'source hash', name);
const raw = csv(fs.readFileSync(csvPath, 'utf8'));
const locations = new Map(), numeric = new Map();
const quantityFields = ['quantity', 'available_quantity', 'allocation_quantity', 'freeze_quantity', 'wait_move_in_quantity', 'wait_move_out_quantity'];
const excludedMetadata = new Set([...quantityFields, 'inventory_item_id', 'sku', 'inventory_updated_at_utc8']);
const inventoryItemIds = new Set();
for (const r of raw) {
  check(r.warehouse_id === '108' && r.warehouse_code === 'GHS_CA_US', 'warehouse identity', r.location_id);
  let loc = locations.get(r.location_id);
  if (!loc) {
    loc = {raw: r, totals: Object.fromEntries(quantityFields.map(k => [k, 0])), items: 0}; locations.set(r.location_id, loc);
    const p = codeParts(r.location_code);
    if (p) { const all = numeric.get(p.numeric) || []; all.push(loc); numeric.set(p.numeric, all); }
  } else for (const field of Object.keys(r)) if (!excludedMetadata.has(field)) check(loc.raw[field] === r[field], 'duplicate metadata conflict', [r.location_id, field]);
  if (r.inventory_item_id) {
    check(!inventoryItemIds.has(r.inventory_item_id), 'duplicate inventory record', r.inventory_item_id); inventoryItemIds.add(r.inventory_item_id); loc.items++;
    for (const field of quantityFields) { check(r[field] !== '' && Number.isFinite(+r[field]) && +r[field] >= 0, 'invalid inventory quantity', [r.inventory_item_id, field]); loc.totals[field] += +r[field]; }
  }
}
check(locations.size === 91106 && raw.length === 96178, 'WMS coverage', {locations: locations.size, rows: raw.length});
const index = new Map(inventory.locations.map(x => [x.id, x]));
check(index.size === locations.size && index.size === inventory.locations.length, 'index coverage', index.size);
for (const [id, loc] of locations) {
  const state = loc.totals.quantity > 0 ? 'occupied' : 'empty'; loc.state = state;
  const i = index.get(id);
  check(i && i.code === loc.raw.location_code && i.quantity === loc.totals.quantity && i.availableQuantity === loc.totals.available_quantity && i.state === state && i.recordCount === loc.items, 'index versus raw CSV', id);
}

const inserts = dxf();
const racks = json('SourceAssets/GHS/RefinementV2/Layout/rack_spacing.json').racks;
const scene = json('Content/GHSTwinUI/data/scene-bindings.json').groups.filter(x => !x.mesh.endsWith('_Occ70'));
const slotMeshes = new Map(json('Content/GHSTwinUI/data/rack-slots.json').meshes.map(x => [x.name, x.cargo_stacks]));
const models = json('SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json').meshes;
const canonical = new Map(models.filter(x => x.canonical && !x.pass_variant).map(x => [x.spec_type, x.cargo_base_z_m]));
const modelByKey = new Map(models.map(x => [x.mapping_key, x]));
const capacity = new Map(json('Content/GHSTwinUI/data/storage-capacity.json').groups.map(x => [x.source_mesh, x]));
const registry = new Map();
for (const g of json('SourceAssets/GHS_Normal/ue_scene_registry.json').groups.filter(g => g.mesh.startsWith('SM_GHS_V2Rack_'))) for (const i of g.instances) {
  const key = `${g.mesh}|${i.id}`, old = registry.get(key);
  check(!old || near(old.position_m, i.position_m) && old.rotation_deg === i.rotation_deg && near(old.scale, i.scale), 'authored placement conflict', key); registry.set(key, i);
}
const resolved = new Map(), brackets = [];
function rawMatches(r) { const a = inserts.get(r.source_handles.at(-1))?.attrs; return a && a.BLOCK_CODE === r.row_code && +a.SEQ === +r.bay_sequence; }
for (const r of racks) {
  check(rawMatches(r), 'raw DXF attributes differ from layout', r.instance_id);
  let row = r.row_code, bay = +r.bay_sequence;
  if (r.pass_variant && Math.abs(r.rotation_deg) < .001 && /^(?:R|SR|S)\d{2}$/.test(row)) {
    // Search geometric neighbours, independently of emitted cadResolution.
    const aligned = racks.filter(o => !o.pass_variant && o.instance_id !== r.instance_id && o.spec_type === r.spec_type && Math.abs(o.rotation_deg - r.rotation_deg) < .001 && /^(?:R|SR)\d{2}$/.test(o.row_code) && Math.abs(o.physical_center_m[0] - r.physical_center_m[0]) < .0001);
    const below = aligned.filter(o => o.physical_center_m[1] < r.physical_center_m[1]).sort((a, b) => b.physical_center_m[1] - a.physical_center_m[1]);
    const above = aligned.filter(o => o.physical_center_m[1] > r.physical_center_m[1]).sort((a, b) => a.physical_center_m[1] - b.physical_center_m[1]);
    const lo = below[0], hi = above[0];
    if (lo && hi) {
      const d0 = r.physical_center_m[1] - lo.physical_center_m[1], d1 = hi.physical_center_m[1] - r.physical_center_m[1];
      const unique = (!below[1] || Math.abs(below[1].physical_center_m[1] - lo.physical_center_m[1]) >= .0001) && (!above[1] || Math.abs(above[1].physical_center_m[1] - hi.physical_center_m[1]) >= .0001);
      const special = /^S\d{2}$/.test(row), identity = special ? lo.row_code === 'SR' + row.slice(1) && bay === +lo.bay_sequence + 1 : lo.row_code === row;
      if (unique && identity && rawMatches(lo) && rawMatches(hi) && lo.row_code === hi.row_code && +hi.bay_sequence === +lo.bay_sequence + 2 && Math.abs(d0 - d1) < .0001 && d0 > 3.4 && d0 < 4.2 && d1 > 3.4 && d1 < 4.2) {
        if (row !== lo.row_code || bay !== +lo.bay_sequence + 1) brackets.push({cadId: r.instance_id, from: [row, bay], to: [lo.row_code, +lo.bay_sequence + 1], neighbors: [lo.instance_id, hi.instance_id]});
        row = lo.row_code; bay = +lo.bay_sequence + 1;
      }
    }
  }
  if (/^(?:R|SR)\d{2}$/.test(row) && bay > 0 && rawMatches(r)) resolved.set(r.instance_id, {...r, resolvedRow: row, resolvedBay: bay});
}
const byRow = new Map(), conflicts = new Set(), reversals = [];
for (const r of resolved.values()) { const all = byRow.get(r.resolvedRow) || []; all.push(r); byRow.set(r.resolvedRow, all); }
for (const [row, all] of byRow) {
  all.sort((a, b) => a.resolvedBay - b.resolvedBay || a.position_m[1] - b.position_m[1]);
  for (let i = 1; i < all.length; i++) {
    const a = all[i - 1], b = all[i];
    if (a.resolvedBay !== b.resolvedBay && b.position_m[1] <= a.position_m[1] + .001) { conflicts.add(a.instance_id); conflicts.add(b.instance_id); reversals.push({row, cadIds: [a.instance_id, b.instance_id], bays: [a.resolvedBay, b.resolvedBay], centersY: [a.position_m[1], b.position_m[1]]}); }
  }
}
const slotsByWmsPosition = new Map(), allTargets = new Map();
let sceneRackSlots = 0, sceneFloorSlots = 0;
for (const group of scene) {
  if (group.mesh.startsWith('SM_GHS_Presentation_Cargo')) {
    for (const i of group.instances) { allTargets.set(`${i.id}|1|1`, 'floor'); sceneFloorSlots++; }
  }
  if (!group.mesh.startsWith('SM_GHS_V2Rack_')) continue;
  for (const i of group.instances) {
    const r = resolved.get(i.id), authored = registry.get(`${group.mesh}|${i.id}`), cg = capacity.get(group.mesh), slots = slotMeshes.get(group.mesh);
    for (const localLevel of new Set(slots.map(s => s.level))) {
      const columns = slots.filter(s => s.level === localLevel).sort((a, b) => a.column - b.column);
      check(columns.length === 3 && columns.every((s, j) => s.column === j + 1) && columns[0].pallet_center_x_m < columns[1].pallet_center_x_m && columns[1].pallet_center_x_m < columns[2].pallet_center_x_m, 'three columns in increasing local X', [i.id, localLevel]);
    }
    for (const s of slots) {
      const t = `${i.id}|${s.level}|${s.column}`; check(!allTargets.has(t), 'duplicate scene target', t); allTargets.set(t, 'rack'); sceneRackSlots++;
      if (!r || conflicts.has(i.id) || Math.abs(r.rotation_deg) > .001) continue;
      check(near(i.position_m, [...r.position_m, 0]) && near(authored?.position_m, i.position_m), 'authored scene position', t);
      check(modelByKey.get(r.mapping_key)?.name === group.mesh && cg?.mesh.endsWith('_Capacity'), 'authored mesh', t);
      check(Math.abs((authored.rotation_deg - r.rotation_deg - 90) % 360) < .001, 'authored axes', t);
      const physical = canonical.get(r.spec_type).findIndex(z => Math.abs(z - s.base_z_m) < .001) + 1;
      if (!physical) continue;
      const p = `${r.resolvedRow}|${r.resolvedBay}|${s.column}|${physical}`, list = slotsByWmsPosition.get(p) || [];
      list.push({target: t, r, slot: s, group, instance: i, authored, capacity: cg, physical}); slotsByWmsPosition.set(p, list);
    }
  }
}
check(allTargets.size === 32586 && sceneRackSlots === 25056 && sceneFloorSlots === 7530, 'complete scene coverage', {all: allTargets.size, sceneRackSlots, sceneFloorSlots});
const expected = new Map();
for (const loc of locations.values()) {
  const p = codeParts(loc.raw.location_code); if (!p || numeric.get(p.numeric).length !== 1) continue;
  const list = slotsByWmsPosition.get(`${p.row}|${p.bay}|${p.column}|${p.physical}`);
  if (!list || list.length !== 1 || loc.raw.warehouse_area_id !== (p.row.startsWith('SR') ? '454' : '450') || +loc.raw.horizontal_num !== p.bay || +loc.raw.location_layer !== p.physical) continue;
  expected.set(list[0].target, {...list[0], loc, p});
}
const actual = new Map(), ids = new Set(), evidence = [], boundStates = {}, boundFamily = {};
for (const b of mapping.bindings) {
  const t = target(b); check(!actual.has(t) && !ids.has(b.locationId), 'duplicate binding', t); actual.set(t, b); ids.add(b.locationId);
  const exp = expected.get(t); if (!check(!!exp, 'binding absent in independent reverse lookup', t)) continue;
  check(b.locationId === exp.loc.raw.location_id && b.locationCode === exp.loc.raw.location_code, 'binding WMS identity', t);
  check(near(b.expectedPositionM, exp.instance.position_m) && near(b.expectedWorldRotationDeg, [0, -exp.authored.rotation_deg, 0]) && near(b.expectedWorldScale, exp.authored.scale) && b.expectedMesh === exp.capacity.mesh, 'binding transform contract', t);
  check(b.confidence === 'rule_inferred' && b.evidence === 'cad-row-bay-three-pallets-v3', 'binding evidence qualification', t);
  const bracket = brackets.find(x => x.cadId === b.cadId), cr = b.cadResolution;
  check(cr && cr.originalRow === exp.r.row_code && +cr.originalBay === +exp.r.bay_sequence && cr.resolvedRow === exp.p.row && +cr.resolvedBay === exp.p.bay && cr.method === (bracket ? 'collinear_bilateral_pass_bracket' : 'direct_cad_attributes'), 'CAD resolution evidence', t);
  if (bracket) check(near(cr.neighbors.map(x => +x.bay), [exp.p.bay - 1, exp.p.bay + 1]) && cr.neighbors.map(x => x.cadId).join('|') === bracket.neighbors.join('|'), 'CAD bilateral evidence', t);
  const generated = `GHS-${exp.p.row.startsWith('SR') ? 'SR-' + exp.p.row.slice(2) : exp.p.row}-${String(exp.p.ordinal).padStart(2, '0')}-${String(exp.p.physical).padStart(2, '0')}`;
  check(b.codeResolution?.generatedCode === generated && b.codeResolution?.sourceCode === b.locationCode && b.codeResolution?.method === (generated === b.locationCode ? 'exact' : 'same_family_numeric_width'), 'numeric width evidence', t);
  bump(boundStates, exp.loc.state); bump(boundFamily, exp.p.row.startsWith('SR') ? 'SR' : 'R');
  evidence.push({target: t, locationId: b.locationId, code: b.locationCode, row: exp.p.row, bay: exp.p.bay, column: exp.p.column, physicalLevel: exp.physical, localLevel: b.level, baseZ: exp.slot.base_z_m, rawCadRow: exp.r.row_code, rawCadBay: exp.r.bay_sequence, dxfHandles: exp.r.source_handles, state: exp.loc.state, mechanism: bracket ? (/^S\d{2}$/.test(bracket.from[0]) ? 'S通道双侧定位' : 'R通道档号双侧定位') : (generated !== b.locationCode ? '同族前导零' : '原属性')});
}
for (const t of expected.keys()) check(actual.has(t), 'independent eligible target omitted', t);
const old = new Map(baseline.bindings.map(b => [target(b), b]));
const added = evidence.filter(b => !old.has(b.target));
const removed = baseline.bindings.filter(b => !actual.has(target(b)));
const addedByReason = {}; for (const b of added) bump(addedByReason, b.mechanism);
const releasedOrdinary = added.filter(b => b.mechanism === '原属性');
check(releasedOrdinary.length === 12 && releasedOrdinary.every(b => /^R3[12]$/.test(b.row)), 'released ordinary rack locations', releasedOrdinary);
const reassigned = [];
for (const [t, b] of actual) if (old.has(t) && old.get(t).locationId !== b.locationId) reassigned.push(t);
check(actual.size === 21291 && expected.size === 21291 && added.length === 192 && removed.length === 144 && reassigned.length === 0, 'mapping delta', {actual: actual.size, expected: expected.size, added: added.length, removed: removed.length, reassigned});
check(addedByReason['S通道双侧定位'] === 162 && addedByReason['R通道档号双侧定位'] === 12 && addedByReason['原属性'] === 12 && addedByReason['同族前导零'] === 6, 'new mapping categories', addedByReason);
check(reversals.length === 8 && conflicts.size === 16 && removed.every(b => conflicts.has(b.cadId)), 'removed reversal endpoints', {reversals, conflictCount: conflicts.size});

const auditExports = {};
for (const [file, expectedCount] of [['全部场景库位核对.csv', 32586], ['全部WMS库位核对.csv', 91106]]) {
  const full = path.join(auditDir, file);
  if (!fs.existsSync(full)) { auditExports[file] = {present: false}; continue; }
  const rows = csv(fs.readFileSync(full, 'utf8')), seen = new Set();
  check(rows.length === expectedCount, 'audit export row count', [file, rows.length]);
  for (const r of rows) {
    if (file.startsWith('全部场景')) {
      const t = `${r.CAD标识}|${r.模型局部层}|${r.模型列}`, b = actual.get(t);
      check(allTargets.has(t) && !seen.has(t), 'audit scene target coverage', t); seen.add(t);
      check((r.分类 === 'mapped') === !!b && r.WMS库位ID === (b?.locationId || '') && r.已绑定WMS编码 === (b?.locationCode || '') && r.物理位置已现场确认 === '否', 'audit scene binding fields', t);
      check(r.库存状态 === (b ? locations.get(b.locationId).state : 'unmatched'), 'audit scene state', t);
      check(r.本轮变化 === (b ? (old.has(t) ? '保持绑定' : '新增绑定') : (old.has(t) ? '暂停绑定' : '保持未匹配')), 'audit scene delta', t);
    } else {
      const loc = locations.get(r.库位ID); check(!!loc && !seen.has(r.库位ID), 'audit WMS coverage', r.库位ID); seen.add(r.库位ID);
      if (loc) check(r.完整库位编码 === loc.raw.location_code && +r.数量 === loc.totals.quantity && +r.可用数量 === loc.totals.available_quantity && r.库存状态 === loc.state && !!r.CAD标识 === ids.has(r.库位ID), 'audit WMS fields', r.库位ID);
    }
  }
  auditExports[file] = {present: true, rows: rows.length, unique: seen.size, sha256: sha(full)};
}
fs.mkdirSync(output, {recursive: true});
const report = {passed: errors.length === 0, time: new Date().toISOString(), method: 'Raw CSV and DXF independently parsed in Node; reverse WMS code -> bay/column, actual model base height -> physical layer. No Python mapper or audit functions imported.', mappingPath, mappingSha256: sha(mappingPath), csvSha256: sourceSha, cadSha256: sourceCadSha, wmsRows: raw.length, wmsLocations: locations.size, inventoryRecords: inventoryItemIds.size, sceneRackSlots, sceneFloorSlots, sceneTargets: allTargets.size, independentEligibleBindings: expected.size, actualBindings: actual.size, preservedBindings: actual.size - added.length, addedBindings: added.length, addedByReason, removedBindings: removed.length, reassigned, boundStates, boundFamily, brackets, reversals, exports: auditExports, physicalLabelDirectionVerified: false, fieldConfirmed: 0, errors};
fs.writeFileSync(path.join(output, 'new-bindings-independent-review.json'), JSON.stringify(report, null, 2) + '\n');
fs.writeFileSync(path.join(output, 'new-bindings-independent-proof.json'), JSON.stringify({all: evidence, added, removed}, null, 2) + '\n');
console.log(JSON.stringify({...report, brackets: report.brackets.length, reversals: report.reversals.length, errors: errors.slice(0, 20)}, null, 2));
process.exitCode = errors.length ? 1 : 0;
