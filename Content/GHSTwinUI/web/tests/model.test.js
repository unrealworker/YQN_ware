const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('../model.js');

test('capacity, material, and both order queues reconcile with their actual rows', () => {
  const d = M.demo;
  assert.equal(d.capacity.occupied + d.capacity.available + d.capacity.lockedEmpty, d.capacity.total);
  assert.equal(d.material.quantity, d.material.available + d.material.allocated);
  assert.equal(d.material.quantity, d.material.boxes * d.material.perBox);
  for (const direction of ['inbound', 'outbound']) {
    const rows = M.makeOrders(direction);
    assert.equal(rows.length, d.orders[direction].total);
    for (const status of ['completed', 'executing', 'waiting', 'exception'])
      assert.equal(rows.filter(r => r.status === status).length, d.orders[direction][status]);
  }
});
test('scene snapshots, including an empty list, replace demonstration equipment', () => {
  assert.equal(M.equipmentFor(null).length, 106);
  assert.equal(M.equipmentFor({equipment: []}).length, 0);
  const rows = M.equipmentFor({equipment:[{id:'FORK-17',type:'mannedForklift',status:'离线',live:true,progress:null}]});
  assert.equal(rows.length,1);
  assert.equal(rows[0].id,'FORK-17');
  assert.equal(rows[0].type,'forklift');
  assert.equal(rows[0].progress,null);
  assert.equal(rows[0].status,'offline');
});
test('demonstration equipment and charging facilities match approved totals',()=>{
  assert.deepEqual(M.countStates(M.equipmentFor(null)),{idle:36,running:62,warning:5,fault:2,offline:1});
  assert.deepEqual(M.countStates(M.equipmentFor(null,true)),{charging:18,idle:36,offline:2});
  assert.equal(M.equipmentFor(null,true).find(e=>e.id==='CH-12').status,'idle');
});
test('unconnected telemetry and absent percentage remain unknown rather than zero or running',()=>{
  const a=M.normalizeEquipment({id:'AGV-07',status:'unknown',progress:0,available:false});
  assert.equal(a.status,'unknown');assert.equal(a.progress,null);
  const b=M.normalizeEquipment({id:'FORK-01',status:'running',progress:0,available:true});
  assert.equal(b.progress,null);
  assert.equal(M.normalizeEquipment({id:'CH-56',progress:NaN}).progress,null);
});
test('search and state filter combine; pagination cannot produce an invalid empty page', () => {
  const rows=M.equipmentFor(null);
  const result=M.filterEquipment(rows,'AGV','warning','all');
  assert.ok(result.length>0);
  assert.ok(result.every(r=>r.type==='agv' && r.status==='warning'));
  const page=M.paginate(result,99,5);
  assert.equal(page.page,page.pages);
  assert.ok(page.rows.length>0);
  assert.deepEqual(M.paginate([],3,5),{rows:[],page:1,pages:1,total:0,start:0,end:0});
});
test('stock matrix encodes the approved 36/8/4 distribution with no invented SKU binding', () => {
  const bins=M.rackBins();
  assert.equal(bins.filter(x=>x.status==='occupied').length,36);
  assert.equal(bins.filter(x=>x.status==='available').length,8);
  assert.equal(bins.filter(x=>x.status==='locked').length,4);
  assert.equal(bins.find(x=>x.id===12).sku,'SKU2038');
  assert.ok(bins.filter(x=>x.id!==12).every(x=>!x.sku));
});
test('navigation retains each page filter and back restores the selected list', () => {
  const s=M.createState();
  s.filters.devices.query='FORK';s.filters.devices.page=3;
  M.navigate(s,'devices');M.openDetail(s,{kind:'device',id:'FORK-17'});
  M.back(s);
  assert.equal(s.page,'devices');assert.equal(s.detail,null);
  assert.equal(s.filters.devices.query,'FORK');assert.equal(s.filters.devices.page,3);
  M.navigate(s,'inventory');M.navigate(s,'devices');
  assert.equal(s.filters.devices.page,3);
});
test('order trend time spacing and endpoints match the completed queue counts',()=>{
  const p=M.trendPoints();
  assert.ok(p[5].x-p[4].x < (p[1].x-p[0].x)/5);
  assert.equal(p.at(-1).inbound,96);assert.equal(p.at(-1).outbound,118);
});
