'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const B=require('../business-data.js');

test('verified WMS totals reconcile without counting freezes or allocations twice',()=>{
  const i=B.snapshot.inventory;
  assert.equal(B.availableQuantity(i),336006);
  assert.equal(i.available,B.availableQuantity(i));
  assert.equal(i.onHand,337783);
  assert.equal(i.owners,156);
  assert.equal(i.skus,14373);
});
test('inventory formula preserves negatives and treats nullable deduction fields as zero',()=>{
  assert.equal(B.availableQuantity({onHand:-1}),-1);
  assert.equal(B.availableQuantity({onHand:4,allocated:1,frozen:null}),3);
  assert.equal(B.availableQuantity({onHand:1,frozen:1}),0);
  assert.equal(B.availableQuantity({}),null);
  assert.equal(B.availableQuantity({onHand:'bad'}),null);
  assert.equal(B.availableQuantity({onHand:1,allocated:'bad'}),null);
});
test('missing capacity, telemetry and mappings remain unknown, not zero or invented',()=>{
  const {inventory:i,forklifts:f}=B.snapshot;
  for(const k of ['unit','capacity','occupied','empty','locked'])assert.equal(i[k],null);
  assert.equal(B.locationStatus(3),'待确认');
  assert.equal(B.locationStatus(null),'待确认');
  assert.equal(B.locationStatus(0),'禁用');
  assert.equal(B.managementStatus(1),'正常');
  assert.equal(B.managementStatus(3),'禁用');
  assert.equal(B.managementStatus(null),'待确认');
  assert.equal(f.telemetryAvailable,false);
  assert.equal(f.sceneMappingConfirmed,false);
  for(const r of f.samples){assert.equal(r.sceneId,null);assert.equal(r.battery,null);assert.equal(r.online,null);}
});
test('provided samples never become full inventories or scene equipment',()=>{
  const {inventory:i,forklifts:f}=B.snapshot;
  assert.equal(i.samples.length,5);assert.equal(i.detailsComplete,false);
  assert.equal(f.samples.length,5);assert.equal(f.detailsComplete,false);
  assert.deepEqual(i.samples.map(r=>r.id),['8551268','7111566','8556512','8703069','10274458']);
  assert.equal(i.samples[4].onHand,-1);
  assert.ok(i.samples.every(r=>r.locationId===null&&r.sku===null&&r.ownerId===null));
  assert.equal(f.samples[4].code,'SITDOWN-GHS-L-IN-S5');
  assert.ok(f.samples.every(r=>r.status===1));
});
test('forklift category and management summaries agree, without declaring online counts',()=>{
  const f=B.snapshot.forklifts;
  assert.equal(f.types.reduce((n,r)=>n+r.count,0),82);
  assert.equal(f.types.reduce((n,r)=>n+r.normal,0),62);
  assert.equal(f.types.reduce((n,r)=>n+r.disabled,0),20);
  assert.equal(f.types.reduce((n,r)=>n+r.repair,0),0);
  assert.equal(f.normal+f.disabled+f.repair,f.total);
  assert.ok(f.types.every(r=>r.normal+r.disabled+r.repair===r.count));
  assert.equal(f.online,null);
});
test('extract scope, provenance and distinct timestamps are explicit and immutable',()=>{
  const s=B.snapshot;
  assert.equal(s.warehouse.id,108);assert.equal(s.warehouse.code,'GHS_CA_US');
  assert.equal(s.warehouse.timeZone,'America/Los_Angeles');
  assert.equal(s.source.live,false);assert.equal(s.source.mode,'verified-extract');
  assert.notEqual(s.source.queryTime,s.source.inventoryEtlTime);
  assert.notEqual(s.source.inventoryEtlTime,s.source.forkliftEtlTime);
  assert.equal(s.inventory.regions.length,10);
  assert.ok(s.inventory.regions.every(r=>r.onHand===null));
  assert.ok(s.source.cells.inventorySummary.includes('库存对接!E12'));
  assert.throws(()=>{s.inventory.onHand=0;},TypeError);
});
