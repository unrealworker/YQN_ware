const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {boot}=require('./harness');
const dataPath=path.join(__dirname,'../../data/inventory');
const index=JSON.parse(fs.readFileSync(path.join(dataPath,'index.json'),'utf8'));
const frozen=index.locations.find(l=>l.code==='GHS-R24-69-02');
const empty=index.locations.find(l=>l.code.startsWith('GHS-R')&&l.state==='empty');
const shardFor=row=>({kind:'shard',shard:row.shard,...JSON.parse(fs.readFileSync(path.join(dataPath,row.shard),'utf8'))});
const acceptIndex=app=>app.window.GHSInventoryPayload({kind:'index',...index});
const scripts=app=>app.window.document.head.children;

test('overview uses the small current snapshot summary without requesting the location index',()=>{
 const app=boot({inventory:true}),summary=app.window.GHSInventorySummary;
 assert.equal(summary.snapshotId,index.snapshotId);
 assert.deepEqual(JSON.parse(JSON.stringify(summary.summary)),index.summary);
 assert.equal(scripts(app).length,0);
 for(const text of ['361,661','361,097','23,232','10,061','库存总量 / 件'])assert.ok(app.html().includes(text),text);
 assert.doesNotMatch(app.html(),/337,783|14,373|货主数/);
 assert.match(app.html(),/演示/);
});

test('real index search, state filtering, paging and detail use the same source snapshot',()=>{
 const app=boot({inventory:true});app.window.twinNavigate('inventory');
 assert.equal(scripts(app).length,1);acceptIndex(app);scripts(app)[0].onload();
 assert.ok(app.html().includes(index.source.exportedAt));assert.match(app.html(),/库存快照/);
 assert.match(app.html(),/91,106/);assert.equal((app.html().match(/data-action="inventory-location"/g)||[]).length,20);
 app.click({action:'inventory-state',value:'empty'});assert.equal(app.window.twinState.filters.inventory.page,1);
 assert.doesNotMatch(app.html(),/inventory-state occupied/);
 app.click({action:'page',scope:'inventory',value:'2'});assert.equal(app.window.twinState.filters.inventory.page,2);
 app.click({action:'inventory-state',value:'all'});
 app.listeners.input({target:{dataset:{search:'inventory'},value:frozen.code,selectionStart:13}});
 assert.equal((app.html().match(/data-action="inventory-location"/g)||[]).length,1);
 app.click({action:'inventory-location',id:frozen.id});assert.match(app.html(),/正在读取库存明细/);
 app.window.GHSInventoryPayload(shardFor(frozen));scripts(app)[0].onload();
 assert.match(app.html(),/GHS-R24-69-02/);assert.match(app.html(),/inventory-state occupied/);
 assert.match(app.html(),/冻结/);assert.doesNotMatch(app.html(),/编码匹配 · 待复核/);
 assert.equal(app.commands.filter(c=>c.action==='focus').length,0,'business detail must not imply a scene match');
 app.click({action:'back'});assert.match(app.html(),/搜索库位/);
});

test('scene bridge shows truthful empty stock and identifies rule-derived mapping',()=>{
 const app=boot({inventory:true}),l=shardFor(empty).locations[empty.id];
 app.window.twinSelect({equipment:[],facilities:[],selection:{kind:'material',id:'CAD-test',inventory:{mappingStatus:'mapped',source:index.source,location:l}}});
 assert.match(app.html(),/空货位/);assert.match(app.html(),/本次快照未关联库存记录/);
 assert.match(app.html(),/编码匹配 · 待复核/);
 assert.doesNotMatch(app.html(),/已现场确认|物料 SKU2038/);
 app.window.twinSelect({equipment:[],facilities:[],selection:{kind:'material',id:'CAD-unmatched',inventory:{mappingStatus:'unmapped'}}});
 assert.match(app.html(),/库位编码未匹配/);assert.doesNotMatch(app.html(),/inventory-state empty/);
 app.window.twinSelect({equipment:[],facilities:[],selection:{kind:'material',id:'CAD-unavailable',inventory:{mappingStatus:'unknown'}}});
 assert.match(app.html(),/库存明细暂不可用/);assert.doesNotMatch(app.html(),/库位编码未匹配/);
});

test('failed index remains stable until explicit retry instead of loading on each render',()=>{
 const app=boot({inventory:true});app.window.twinNavigate('inventory');scripts(app)[0].onerror();
 assert.equal(scripts(app).length,0);assert.match(app.html(),/库存文件读取失败/);
 for(let i=0;i<4;i++)app.window.TwinInventory.renderList({});
 assert.equal(scripts(app).length,0);
 app.click({action:'inventory-retry'});assert.equal(scripts(app).length,1);
 acceptIndex(app);scripts(app)[0].onload();assert.match(app.html(),/91,106/);
});

test('failed or wrong-snapshot shard is not displayed or automatically retried',()=>{
 const app=boot({inventory:true});acceptIndex(app);app.window.twinNavigate('inventory');
 app.click({action:'inventory-location',id:frozen.id});scripts(app)[0].onerror();
 assert.match(app.html(),/读取失败/);assert.equal(scripts(app).length,0);
 app.window.TwinInventory.renderLocation(frozen.id);assert.equal(scripts(app).length,0);
 app.click({action:'inventory-retry-location',id:frozen.id});
 app.window.GHSInventoryPayload({...shardFor(frozen),snapshotId:'wrong'});scripts(app)[0].onload();
 assert.match(app.html(),/校验失败/);assert.equal(scripts(app).length,0);assert.doesNotMatch(app.html(),/inventory-state occupied/);
 app.click({action:'inventory-retry-location',id:frozen.id});app.window.GHSInventoryPayload(shardFor(frozen));scripts(app)[0].onload();
 assert.match(app.html(),/inventory-state occupied/);
});

test('loaded scripts with no payload and absent location ids finish in a truthful error state',()=>{
 const app=boot({inventory:true});app.window.twinNavigate('inventory');scripts(app)[0].onload();
 assert.match(app.html(),/缺少有效数据/);assert.equal(scripts(app).length,0);
 app.click({action:'inventory-retry'});acceptIndex(app);scripts(app)[0].onload();
 app.click({action:'inventory-location',id:'absent'});assert.match(app.html(),/未找到该库位/);
 assert.equal(scripts(app).length,0);
});

test('invalid index identity and paths are rejected before listing anything',()=>{
 for(const change of [r=>({...r,shard:'../../bad.json'}),r=>({...r,shard:'999.json'}),r=>({...r,id:''})]){
  const app=boot({inventory:true});app.window.twinNavigate('inventory');
  app.window.GHSInventoryPayload({kind:'index',...index,locations:[change(index.locations[0])]});scripts(app)[0].onload();
  assert.match(app.html(),/校验失败/);assert.doesNotMatch(app.html(),/data-action="inventory-location"/);
 }
});

test('real-inventory scene control contract survives settings reset',()=>{
 const app=boot({inventory:true});app.window.twinSceneControls({inventoryMode:true});app.window.twinNavigate('scene');
 function checkControls(){
  assert.equal(app.window.twinState.settings.inventoryMode,true);
  for(const id of ['rackCapacity','floorCapacity'])assert.ok(app.html().includes('data-capacity="'+id+'"'));
 }
 checkControls();app.click({action:'settings-reset'});checkControls();
});

test('global business-code search opens inventory without pretending an unbound code is a scene object',()=>{
 const app=boot({inventory:true});app.window.twinSearch(frozen.code);
 assert.equal(app.window.twinState.page,'inventory');assert.equal(app.window.twinState.filters.inventory.query,frozen.code);
 acceptIndex(app);scripts(app)[0].onload();assert.match(app.html(),/GHS-R24-69-02/);
 app.window.twinSearch(frozen.id);assert.equal(app.window.twinState.filters.inventory.query,frozen.id);
 assert.equal(app.commands.filter(c=>c.action==='focus'||c.action==='select').length,0);
});

test('floor selection reads zone totals and SKU records through the snapshot shard, keyed by CAD id',()=>{
 const app=boot({inventory:true});
 const select=cadId=>app.window.twinSelect({equipment:[],facilities:[],selection:{kind:'material',id:'selected-'+cadId,cadId,title:'GHS-G01-46',inventory:{mappingStatus:'unmapped'}}});
 select('CAD_24_41852B');
 assert.match(app.html(),/地堆区库存/);
 assert.match(app.html(),/GHS-G01-01/);
 assert.match(app.html(),/区内托位数<\/span><strong>17/);
 assert.match(app.html(),/本托序号<\/span><strong>01/);
 assert.match(app.html(),/正在读取库位索引/);
 const indexScript=scripts(app)[0];
 acceptIndex(app);indexScript.onload();
 const row=index.locations.find(r=>r.code==='GHS-G01-01');
 const shardScript=scripts(app)[0];
 app.window.GHSInventoryPayload(shardFor(row));shardScript.onload();
 assert.match(app.html(),/区内有库存/);assert.match(app.html(),/1,242/);
 assert.match(app.html(),/全区 SKU · 2/);assert.match(app.html(),/S03-BLACK/);
 select('CAD_24_4184BB');
 const emptyRow=index.locations.find(r=>r.code==='GHS-G01-15');
 const second=scripts(app)[0];
 if(second){app.window.GHSInventoryPayload(shardFor(emptyRow));second.onload();}
 assert.match(app.html(),/本次快照全区无库存/);
 select('CAD_24_4183C3');
 assert.match(app.html(),/GHS-G01-46/);assert.match(app.html(),/本次快照缺少该区档案/);
 assert.doesNotMatch(app.html(),/全区无库存|1,242|SKU2038/);
 select('unrelated-instance');
 assert.doesNotMatch(app.html(),/地堆区库存/);
});
