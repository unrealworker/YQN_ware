const test=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./harness');
const verifiedInventory=app=>app.html().split('<div data-verified="inventory">').slice(1).map(part=>part.split('<div class="unverified-design"')[0]).join('');

test('inventory displays verified current-query totals without inventing capacity or quantity units',()=>{
  const app=boot();app.window.twinNavigate('inventory');const html=verifiedInventory(app);
  for(const value of ['337,783','336,006','1,722','14,373','76,752','156','55'])assert.ok(html.includes(value),value);
  assert.ok(html.includes('单位待确认'));
  assert.ok(html.includes('2026-10-22 22:27'));
  assert.ok(html.includes('22:01:21'));
  assert.ok(app.html().includes('容量规则待确认'));assert.ok(html.includes('单位待确认'));
  assert.ok(!html.includes('480 件'));assert.ok(!html.includes('bin-grid'));
  assert.ok(!html.includes('占用率'));assert.ok(!html.includes('托位已用'));
  assert.ok(!html.includes('data-action="focus"'));
  for(const code of ['GHS-R','GHS-SR','GHS-T','GHS-MOVE','GHS-HL','GHS-WALL01','GHS-G','GHS-DG','GHS-DOCK01','GHS-TEMP'])assert.ok(html.includes(code),code);
});

test('inventory sample search preserves real zero and negative quantities and never fabricates detail fields',()=>{
  const app=boot();app.window.twinNavigate('inventory');
  assert.equal((app.html().match(/data-inventory-sample=/g)||[]).length,5);
  app.listeners.input({target:{dataset:{search:'inventory'},value:'10274458',selectionStart:8}});
  const html=verifiedInventory(app);assert.equal((html.match(/data-inventory-sample=/g)||[]).length,1);
  assert.ok(html.includes('10274458'));assert.ok(html.includes('>-1<'));
  assert.ok(!html.includes('SKU2038'));assert.ok(!html.includes('B20261018'));
  app.listeners.input({target:{dataset:{search:'inventory'},value:'7111566',selectionStart:7}});
  assert.ok(app.html().includes('7111566'));assert.ok(app.html().includes('>0<'));
  app.listeners.input({target:{dataset:{search:'inventory'},value:'absent',selectionStart:6}});
  assert.ok(app.html().includes('没有匹配的样例'));assert.ok(app.html().includes('337,783'));
});

test('default equipment view shows management ledger totals and only evidence-backed sample records',()=>{
  const app=boot();app.window.twinNavigate('devices');const html=app.html();
  assert.ok(html.includes('叉车台账'));assert.ok(html.includes('82'));
  for(const label of ['正常','禁用','维修中','62','20','电动托盘车','ORDER PICKER','REACH','Rider','坐式叉车'])assert.ok(html.includes(label),label);
  assert.ok(html.includes('管理状态'));assert.ok(html.includes('在线'));
  assert.ok(html.includes('SITDOWN-GHS-L-OUT-S1'));assert.ok(html.includes('SITDOWN-GHS-L-OUT-S2'));
  assert.equal((html.match(/data-ledger-sample=/g)||[]).length,5);
  for(const code of ['SITDOWN-GHS-L-IN-S3','SITDOWN-GHS-L-IN-S4','SITDOWN-GHS-L-IN-S5'])assert.ok(html.includes(code),code);
  assert.ok(html.includes('暂无'));assert.ok(!html.includes('data-action="focus"'));
  assert.ok(!html.includes('AGV-07'));assert.ok(!html.includes('data-action="device"'));
});

test('ledger uses its verified date rather than the separate inventory query time',()=>{
  const app=boot();app.window.twinNavigate('devices');
  assert.ok(app.html().includes('核验日期 2026-10-22'));
  assert.ok(!app.html().includes('22:27'));
  assert.ok(app.html().includes('2026-10-08 10:45:34'));
  app.window.twinNavigate('inventory');assert.ok(app.html().includes('查询核验 2026-10-22 22:27'));
});

test('diagnostics report verified provenance and current device view for native CEF validation',()=>{
  const app=boot();app.window.twinNavigate('devices');app.flush();
  const business=app.commands.at(-1).business;
  assert.ok(business);assert.equal(business.sourceMode,'verified-extract');assert.equal(business.live,false);
  assert.equal(business.warehouseCode,'GHS_CA_US');assert.equal(business.deviceView,'ledger');
  assert.equal(typeof business.visibleText,'string');assert.ok(business.visibleText.length<=6000);
  assert.equal(typeof business.inventorySampleRows,'number');assert.equal(typeof business.ledgerSampleRows,'number');
  assert.equal(typeof business.unverifiedSections,'number');
  app.window.twinFilterType('forklift');app.flush();assert.equal(app.commands.at(-1).business.deviceView,'scene');
});

test('overview and ledger remain verified when scene telemetry changes and model browsing stays separate',()=>{
  const app=boot();assert.ok(app.html().includes('337,783'));assert.ok(app.html().includes('336,006'));
  assert.ok(app.html().includes('叉车台账'));assert.ok(app.html().includes('演示'));
  const initial=app.html();app.window.twinReceive({equipment:[{id:'FORK-07',type:'forklift',status:'running',value:'14 km/h',live:true}],facilities:[]});
  assert.equal(app.html(),initial);
  app.window.twinNavigate('devices');const ledger=app.html();
  app.window.twinReceive({equipment:[],facilities:[]});assert.equal(app.html(),ledger);
  app.click({action:'tab',key:'devices.view',value:'scene'});
  assert.ok(app.html().includes('场景模型'));assert.ok(!app.html().includes('SITDOWN-GHS-L-OUT-S1'));
  app.window.twinFilterType('forklift');assert.equal(app.window.twinState.filters.devices.view,'scene');
});

test('global search finds verified sample identities without sending scene select or focus commands',()=>{
  const app=boot();const before=app.commands.length;
  app.window.twinSearch('2574');
  assert.equal(app.window.twinState.filters.devices.view,'ledger');assert.equal(app.window.twinState.detail,null);
  assert.equal((app.html().match(/data-ledger-sample=/g)||[]).length,1);
  assert.ok(app.html().includes('SITDOWN-GHS-L-OUT-S1'));
  app.window.twinSearch('SITDOWN-GHS-L-IN-S5');assert.ok(app.html().includes('叉车 ID 2578'));
  app.window.twinSearch('10274458');assert.equal(app.window.twinState.page,'inventory');
  assert.equal((app.html().match(/data-inventory-sample=/g)||[]).length,1);
  assert.ok(app.commands.slice(before).every(command=>!['select','focus'].includes(command.action)));
});

test('scene card source labels refresh when only their demo provenance changes',()=>{
  const app=boot(),row={id:'FORK-07',type:'forklift',status:'unknown',available:false,value:'—',demo:false};
  app.window.twinReceive({equipment:[row],facilities:[]});app.window.twinFilterType('forklift');
  assert.ok(app.html().includes('场景对象 · 遥测未接入'));
  app.window.twinReceive({equipment:[{...row,demo:true}],facilities:[]});
  assert.ok(app.html().includes('场景演示 · 数据未核验'));
  assert.ok(!app.html().includes('场景对象 · 遥测未接入'));
});

test('original capacity design is retained under explicit unverified labels without replacing verified totals',()=>{
  const app=boot(),overview=app.html();
  assert.ok(overview.includes('data-unverified="capacity"'));
  assert.ok(overview.includes('80.0%'));assert.ok(overview.includes('2,400'));
  assert.ok(overview.includes('数据未核验'));assert.ok(overview.includes('337,783'));
  app.window.twinNavigate('inventory');const verified=verifiedInventory(app),html=app.html();
  assert.ok(!verified.includes('1,920'));assert.ok(verified.includes('337,783'));
  assert.ok(html.includes('data-unverified="inventory-design"'));
  assert.ok(html.includes('data-filter="inventoryDemo.state"'));
  assert.equal((html.match(/data-action="demo-bin"/g)||[]).length,48);
  assert.ok(html.includes('数据未核验'));assert.ok(html.includes('1,920'));
  assert.ok(!html.includes('class="unknown-metrics"'));
  assert.ok(html.indexOf('337,783')<html.indexOf('1,920'));
  assert.ok(html.indexOf('data-unverified="inventory-design"')<html.indexOf('区域主数据'));
  assert.ok(html.indexOf('data-action="demo-bin"')<html.indexOf('data-inventory-sample='));
  assert.equal((html.match(/data-verified="inventory"/g)||[]).length,2);
});

test('unverified matrix search, filtering and detail do not mutate verified samples or scene selection',()=>{
  const app=boot();app.window.twinNavigate('inventory');
  app.listeners.input({target:{dataset:{search:'inventory'},value:'10274458',selectionStart:8}});
  const verified=verifiedInventory(app),before=app.commands.length;
  app.listeners.input({target:{dataset:{search:'inventoryDemo'},value:'absent',selectionStart:6}});
  assert.equal(verifiedInventory(app),verified);assert.ok(app.html().includes('未找到匹配物料'));
  app.click({action:'reset',scope:'inventoryDemo'});assert.equal(verifiedInventory(app),verified);
  app.listeners.change({target:{dataset:{filter:'inventoryDemo.state'},value:'available'}});
  assert.ok(app.html().includes('bin occupied filtered'));assert.equal(verifiedInventory(app),verified);
  app.click({action:'demo-bin',id:'6'});assert.ok(app.html().includes('A-03-06 · 空货位'));
  app.listeners.change({target:{dataset:{filter:'inventoryDemo.state'},value:'all'}});
  app.click({action:'demo-bin',id:'12'});app.click({action:'material'});
  assert.equal(app.window.twinState.detail.kind,'material-demo');assert.ok(app.html().includes('数据未核验'));
  assert.ok(app.commands.slice(before).every(command=>!['select','focus'].includes(command.action)));
});

test('legacy design shortcuts reset only design filters while verified sample searches retain design state',()=>{
  const app=boot();app.window.twinSearch('10274458');
  for(const query of ['A-03','A-03-12','SKU2038','B20261018']){
    Object.assign(app.window.twinState.filters.inventoryDemo,{query:'absent',bin:6,state:'available'});
    app.window.twinSearch(query);
    assert.equal(app.window.twinState.filters.inventory.query,'10274458');
    assert.equal(app.window.twinState.filters.inventoryDemo.query,'');
    assert.equal(app.window.twinState.filters.inventoryDemo.bin,12);
    assert.equal(app.window.twinState.filters.inventoryDemo.state,'all');
    if(app.window.twinState.detail)app.window.twinBack();
    assert.equal((app.html().match(/data-inventory-sample=/g)||[]).length,1);
    assert.ok(!app.html().includes('未找到匹配物料'));
  }
  Object.assign(app.window.twinState.filters.inventoryDemo,{query:'absent',bin:6,state:'available'});
  app.window.twinSearch('7111566');
  assert.equal(app.window.twinState.filters.inventory.query,'7111566');
  assert.equal(app.window.twinState.filters.inventoryDemo.query,'absent');
  assert.equal(app.window.twinState.filters.inventoryDemo.bin,6);
  assert.equal(app.window.twinState.filters.inventoryDemo.state,'available');
});

test('original order alert and trace pages identify their unchecked data while real ledger stays verified',()=>{
  const app=boot();for(const page of ['orders','alerts','trace']){app.window.twinNavigate(page);assert.ok(app.html().includes('数据未核验'),page);}
  app.window.twinNavigate('devices');assert.ok(app.html().includes('表格核验数据'));assert.ok(!app.html().includes('数据未核验'));
});

test('scene telemetry detail keeps its original design with an unverified badge and never fills missing telemetry',()=>{
  const app=boot();app.window.twinSelect({equipment:[{id:'FORK-07',type:'forklift',live:true,available:true,status:'running',value:'1.2 m/s'}],facilities:[],selection:{kind:'device',id:'FORK-07'}});
  assert.ok(app.html().includes('data-unverified="scene-device"'));assert.ok(app.html().includes('1.2 m/s'));
  app.click({action:'tab',key:'deviceTab',value:'task'});
  app.window.twinReceive({equipment:[{id:'FORK-07',type:'forklift',live:true,available:false,status:'running',value:'1.2 m/s'}],facilities:[],selection:{kind:'device',id:'FORK-07'}});
  assert.ok(!app.html().includes('data-unverified="scene-device"'));
  app.click({action:'tab',key:'deviceTab',value:'status'});
  app.window.twinReceive({equipment:[{id:'FORK-07',type:'forklift',live:true,available:false,status:'unknown'}],facilities:[],selection:{kind:'device',id:'FORK-07'}});
  assert.ok(app.html().includes('遥测未接入'));assert.ok(!app.html().includes('1.2 m/s'));assert.ok(!app.html().includes('0%'));
});

test('unconnected device event samples retain an independent unverified source label',()=>{
  const app=boot();app.window.twinSelect({equipment:[{id:'FORK-07',type:'forklift',demo:false,available:false,status:'unknown'}],facilities:[],selection:{kind:'device',id:'FORK-07'}});
  app.click({action:'tab',key:'deviceTab',value:'events'});
  assert.ok(app.html().includes('遥测未接入'));assert.ok(app.html().includes('行驶速度预警'));
  assert.ok(app.html().includes('data-unverified="device-events"'));assert.ok(app.html().includes('数据未核验'));
  assert.ok(!app.html().includes('data-unverified="scene-device"'));
});
