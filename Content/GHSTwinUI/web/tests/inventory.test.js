const test=require('node:test');
const assert=require('node:assert/strict');
const inventory=require('../inventory.js');
const source={exportedAt:'2026-11-25 14:00:46 UTC+08:00'};
function location(){return {id:'1',code:'GHS-R24-69-02',state:'occupied',fields:{location_status:'3'},totals:{quantity:2,availableQuantity:0,allocationQuantity:0,freezeQuantity:2},items:[{id:'001',sku:'00038',quantity:2,availableQuantity:0,freezeQuantity:2}],recordCount:1,skuCount:1};}
test('positive frozen stock is occupied despite zero available and raw status',()=>{
 const html=inventory.renderDetail({mappingStatus:'mapped',source,location:location()});
 assert.match(html,/有货/);assert.match(html,/00038/);assert.match(html,/冻结/);assert.doesNotMatch(html,/inventory-state empty/);assert.match(html,/2026-11-25/);
});
test('empty without records states snapshot evidence and does not promise availability',()=>{
 const l={...location(),state:'empty',emptyReason:'no_inventory_record',items:[],totals:{quantity:0,availableQuantity:0},recordCount:0,skuCount:0};
 const html=inventory.renderDetail({mappingStatus:'mapped',source,location:l});
 assert.match(html,/空货位/);assert.match(html,/未关联库存记录/);assert.doesNotMatch(html,/>可入库<|>可用库位</);
});
test('unmapped is never an empty location and data cannot inject markup',()=>{
 assert.match(inventory.renderDetail({mappingStatus:'unmapped'}),/未匹配/);
 const l=location();l.code='<img src=x onerror=alert(1)>';l.items[0].sku='<script>bad()</script>';
 const html=inventory.renderDetail({mappingStatus:'mapped',source,location:l});
 assert.doesNotMatch(html,/<img|<script>/);assert.match(html,/&lt;script&gt;/);
});
test('paged search preserves exact business codes and limits rendered rows',()=>{
 const rows=Array.from({length:55},(_,i)=>({id:String(i),code:'GHS-R02-'+String(i).padStart(2,'0')+'-01',state:i%2?'occupied':'empty',quantity:i}));
 assert.equal(inventory.filterPage(rows,{query:'GHS-R02-01-01',page:1}).total,1);
 const p=inventory.filterPage(rows,{state:'empty',page:2},10);assert.equal(p.total,28);assert.equal(p.rows.length,10);assert.equal(p.page,2);
});
test('unknown quantity stays unknown in details',()=>{
 const l={...location(),state:'unknown',totals:{quantity:null,availableQuantity:null}};
 const html=inventory.renderDetail({mappingStatus:'mapped',source,location:l});
 assert.match(html,/待核验/);assert.match(html,/—/);assert.doesNotMatch(html,/inventory-state empty/);
});
