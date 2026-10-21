const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {boot}=require('./harness');

test('all seven native navigation destinations render real content and source labels',()=>{
  const app=boot();
  for(const [name,title]of[['overview','仓库运营总览'],['inventory','库存与货位'],['orders','今日出入库订单'],['devices','设备监控'],['alerts','设备告警中心'],['trace','追溯查询'],['settings','场景设置']]){
    app.window.twinNavigate(name);
    assert.ok(app.html().includes('<h1>'+title+'</h1>'),name);
    assert.ok(app.html().includes('source'),name);
    app.flush();
    assert.equal(app.commands.at(-1).action,'report');
    assert.equal(app.commands.at(-1).page,name);
  }
  assert.ok(app.commands.some(c=>c.action==='ready'));
});
test('native unknown device keeps model picture and missing telemetry, and does not reopen on refresh after back',()=>{
  const app=boot();
  const snapshot={connected:true,mapName:'GHS',equipment:[{id:'AGV-07',type:'agv',status:'unknown',available:false,progress:0}],facilities:[],selection:{kind:'device',id:'AGV-07'}};
  app.window.twinReceive(snapshot);
  assert.ok(app.html().includes('assets/agv.png'));
  assert.ok(app.html().includes('遥测未接入'));
  assert.ok(!app.html().includes('82%'));
  app.window.twinBack();app.window.twinReceive(snapshot);
  assert.equal(app.window.twinState.detail,null);
  app.flush();assert.equal(app.commands.at(-1).equipmentCount,1);
});
test('actual CAD material selection never displays the demonstration SKU as its inventory',()=>{
  const app=boot();app.window.twinReceive({equipment:[],facilities:[],selection:{kind:'material',id:'CAD-RACK-12',cadId:'DXF-07',instanceIndex:123,level:2,column:4}});
  assert.ok(app.html().includes('场景物料详情'));
  assert.ok(app.html().includes('DXF-07'));
  assert.ok(app.html().includes('123'));
  assert.ok(app.html().includes('查看演示物料'));
  assert.ok(!app.html().includes('480 件'));
});
test('native type chips and global search apply device filters and use real snapshot counts',()=>{
  const app=boot();app.window.twinReceive({equipment:[],facilities:[]});
  app.window.twinFilterType('charger');
  assert.equal(app.window.twinState.filters.devices.facility,true);
  assert.ok(app.html().includes('充电设施 0'));
  app.window.twinSearch('FORK-17');
  assert.equal(app.window.twinState.filters.devices.query,'FORK-17');
  assert.equal(app.window.twinState.filters.devices.facility,false);
  assert.ok(app.html().includes('没有匹配的设备'));
});
test('frequent native snapshot updates never render over focused search input',()=>{
  const app=boot();app.window.twinNavigate('devices');const original=app.html();
  app.window.document.activeElement={tagName:'INPUT'};
  app.window.twinReceive({equipment:[],facilities:[]});
  assert.equal(app.html(),original);
});
test('explicitly reselecting the same native object reopens details after back or navigation',()=>{
  const app=boot();
  const snapshot={equipment:[{id:'AGV-07',type:'agv',status:'unknown',available:false}],facilities:[],selection:{kind:'device',id:'AGV-07'}};
  app.window.twinReceive(snapshot);app.window.twinBack();
  app.window.twinReceive(snapshot);assert.equal(app.window.twinState.detail,null);
  app.window.twinSelect(snapshot);assert.equal(app.window.twinState.detail.id,'AGV-07');
  app.window.twinNavigate('inventory');app.window.twinReceive(snapshot);
  assert.equal(app.window.twinState.detail,null);
  app.window.twinSelect(snapshot);assert.equal(app.window.twinState.detail.id,'AGV-07');
  const rack={equipment:[],facilities:[],selection:{kind:'material',id:'CAD-A',instanceIndex:13}};
  app.window.twinSelect(rack);app.window.twinBack();app.window.twinSelect(rack);
  assert.equal(app.window.twinState.detail.id,'CAD-A');
});
test('native clear selection discards nested device and material details but preserves the business list',()=>{
  const app=boot({reducedMotion:false});app.window.twinNavigate('devices');app.flush();
  app.window.twinState.filters.devices.query='AGV';app.window.twinState.filters.devices.type='agv';
  app.elements.main.scrollTop=285;
  const snapshot={equipment:[{id:'AGV-07',type:'agv',status:'unknown'}],facilities:[]};
  app.window.twinSelect({...snapshot,selection:{kind:'device',id:'AGV-07'}});app.flush();
  app.window.twinSelect({...snapshot,selection:{kind:'material',id:'CAD-RACK-12',cadId:'DXF-07',instanceIndex:123}});app.flush();
  assert.equal(app.window.twinState.detail.kind,'material');assert.equal(app.window.twinState.stack.length,2);
  app.window.twinReceive({...snapshot,selection:null});
  const before=app.commands.length;app.window.twinClearSelection();app.flush();
  assert.equal(app.window.twinState.detail,null);assert.equal(app.window.twinState.stack.length,0);
  assert.equal(app.window.twinState.page,'devices');assert.equal(app.window.twinState.filters.devices.query,'AGV');
  assert.equal(app.window.twinState.filters.devices.type,'agv');assert.equal(app.elements.main.scrollTop,285);
  assert.ok(app.html().includes('<h1>设备监控</h1>'));
  assert.ok(app.commands.slice(before).every(command=>command.action==='report'));
  app.window.twinBack();app.flush();assert.equal(app.window.twinState.detail,null);
});
test('global search routes known material examples to clearly marked demonstration details',()=>{
  const app=boot();app.window.twinReceive({equipment:[],facilities:[]});
  for(const query of ['SKU2038',' 电机安装支架 ','BH-M8','b20261018']){
    app.window.twinSearch(query);
    assert.equal(app.window.twinState.page,'inventory');
    assert.equal(app.window.twinState.detail.kind,'material-demo');
    assert.ok(app.html().includes('演示物料'));
    assert.ok(app.html().includes('尚未绑定 WMS'));
  }
  app.window.twinSearch('A-03');
  assert.equal(app.window.twinState.page,'inventory');assert.equal(app.window.twinState.detail,null);
  assert.ok(app.html().includes('演示分布'));
  app.window.twinSearch('SKU-NOT-EXISTS');
  assert.equal(app.window.twinState.page,'devices');assert.equal(app.window.twinState.detail,null);
  assert.ok(app.html().includes('没有匹配的设备'));
});
test('action visibility tolerates only fractional viewport rounding and reports raw overflow',()=>{
  const app=boot();app.window.devicePixelRatio=1.5;
  let bounds={left:0,top:480,right:480.5,bottom:1016.5,width:480.5,height:536.5};
  app.window.document.querySelector=selector=>selector==='.device-actions'?{getBoundingClientRect:()=>bounds}:null;
  app.window.twinNavigate('devices');app.flush();
  let report=app.commands.at(-1);
  assert.equal(report.detailActionsVisible,true);assert.equal(report.detailActionsStrictlyVisible,false);
  assert.equal(report.detailActionBounds.right,480.5);assert.equal(report.viewport.devicePixelRatio,1.5);
  bounds={...bounds,right:482};app.window.twinNavigate('devices');app.flush();
  report=app.commands.at(-1);assert.equal(report.detailActionsVisible,false);
  app.elements.navigation.scrollWidth=481;app.window.twinNavigate('devices');app.flush();
  assert.equal(app.commands.at(-1).overflow,true);
});
test('native technical map names never replace readable business page subtitles',()=>{
  const app=boot(),mapName='UEDPIE_0_GHS_CAD_NormalWarehouse_CADScene_WithLongTechnicalSuffix';
  app.window.twinReceive({connected:true,mapName,equipment:[],facilities:[]});
  for(const [page,subtitle]of[['devices','普通仓库 · 场景设备'],['settings','普通仓库 · 场景视图']]){
    app.window.twinNavigate(page);
    assert.ok(app.html().includes(subtitle));
    assert.ok(!app.html().includes(mapName));
    assert.ok(app.html().includes('场景数据'));
  }
});
test('page navigation keeps outgoing content until fade-out and coalesces telemetry refreshes',()=>{
  const app=boot({reducedMotion:false}),old=app.html();
  app.window.twinNavigate('devices');assert.equal(app.html(),old);
  app.advance(60);app.window.twinReceive({equipment:[{id:'AGV-07',type:'agv'}],facilities:[]});
  assert.equal(app.html(),old);app.advance(59);assert.equal(app.html(),old);
  app.advance(1);assert.ok(app.html().includes('作业设备 1'));
  const entering=app.html();app.window.twinReceive({equipment:[],facilities:[]});
  assert.equal(app.html(),entering);app.advance(199);assert.equal(app.html(),entering);
  app.advance(1);assert.ok(app.html().includes('作业设备 0'));
  app.flush();assert.equal(app.commands.at(-1).page,'devices');
});
test('completed transition reports preserve measured exit entry and idle diagnostics',()=>{
  const app=boot({reducedMotion:false});app.window.twinNavigate('devices');app.flush();
  let transition=app.commands.at(-1).transition;
  assert.equal(transition.phase,'idle');assert.equal(transition.durationMs,320);
  assert.deepEqual(transition.recentPhases.map(sample=>sample.phase),['out','in','idle']);
  assert.deepEqual(transition.recentPhases.map(sample=>sample.atMs),[0,120,320]);
  assert.ok(transition.recentPhases.every(sample=>typeof sample.opacity==='number'));
  app.window.twinReceive({equipment:[],facilities:[]});app.flush();
  assert.deepEqual(app.commands.at(-1).transition.recentPhases,transition.recentPhases);
  app.window.twinNavigate('settings');app.flush();transition=app.commands.at(-1).transition;
  assert.deepEqual(transition.recentPhases.map(sample=>sample.phase),['out','in','idle']);
  assert.equal(transition.recentPhases.at(-1).displayedView,'scene');
});
test('unchanged telemetry keeps the displayed DOM while changed equipment updates it',()=>{
  const app=boot(),snapshot={equipment:[],facilities:[]};app.window.twinReceive(snapshot);app.window.twinNavigate('devices');
  let writes=0,html=app.elements.page.innerHTML;
  // Browsers normalize serialized markup; comparison must not depend on innerHTML round-tripping.
  Object.defineProperty(app.elements.page,'innerHTML',{get:()=>html+'\n',set:value=>{html=value;writes++;}});
  app.window.twinReceive(snapshot);assert.equal(writes,0);
  app.window.twinReceive({equipment:[{id:'AGV-07',type:'agv'}],facilities:[]});
  assert.equal(writes,1);assert.ok(app.html().includes('作业设备 1'));
});
test('rapid navigation during both transition phases settles on the final destination',()=>{
  const app=boot({reducedMotion:false}),old=app.html();
  app.window.twinNavigate('inventory');app.advance(60);app.window.twinNavigate('orders');
  assert.equal(app.html(),old);app.advance(60);assert.ok(app.html().includes('今日出入库订单'));
  app.advance(40);app.window.twinNavigate('devices');app.advance(20);app.window.twinNavigate('settings');
  app.flush();assert.ok(app.html().includes('<h1>场景设置</h1>'));
  assert.equal(app.window.twinState.page,'scene');assert.equal(app.commands.at(-1).page,'settings');
});
test('scroll and search focus survive navigating away and back, including queued refresh',()=>{
  const app=boot({reducedMotion:false});app.window.twinNavigate('devices');app.flush();
  const input={insidePage:true,tagName:'INPUT',dataset:{search:'devices'},selectionStart:2,selectionEnd:4,focus(){app.window.document.activeElement=this;},setSelectionRange(a,b){this.range=[a,b];}};
  app.elements.page.querySelector=()=>input;app.window.document.activeElement=input;app.elements.main.scrollTop=285;
  app.window.twinNavigate('orders');app.flush();app.window.document.activeElement=null;app.elements.main.scrollTop=94;
  app.window.twinNavigate('devices');app.advance(150);app.window.twinReceive({equipment:[],facilities:[]});app.flush();
  assert.equal(app.elements.main.scrollTop,285);assert.equal(app.window.document.activeElement,input);assert.deepEqual(input.range,[2,4]);
});
test('reduced motion skips delays and changing preference cancels an active transition safely',()=>{
  const immediate=boot();immediate.window.twinNavigate('devices');assert.ok(immediate.html().includes('<h1>设备监控</h1>'));
  const app=boot({reducedMotion:false});app.window.twinNavigate('orders');app.advance(50);app.reduceMotion();
  assert.ok(app.html().includes('今日出入库订单'));app.window.twinNavigate('settings');app.flush();
  assert.ok(app.html().includes('<h1>场景设置</h1>'));assert.equal(app.commands.at(-1).page,'settings');
});
test('enabling reduced motion during entry preserves scrolling performed on the new page',()=>{
  const app=boot({reducedMotion:false});app.window.twinState.scroll.devices=285;
  app.window.twinNavigate('devices');app.advance(150);assert.equal(app.elements.main.scrollTop,285);
  app.elements.main.scrollTop=440;app.reduceMotion();
  assert.equal(app.elements.main.scrollTop,440);app.flush();assert.equal(app.elements.main.scrollTop,440);
});
test('pagination leaves the old scroll position through fade-out and starts the new page at top',()=>{
  const app=boot({reducedMotion:false});app.window.twinNavigate('devices');app.flush();
  app.elements.main.scrollTop=420;const old=app.html();
  app.click({action:'page',scope:'devices',value:'2'});
  assert.equal(app.elements.main.scrollTop,420);assert.equal(app.html(),old);
  app.advance(120);assert.equal(app.elements.main.scrollTop,0);
  app.flush();assert.equal(app.window.twinState.filters.devices.page,2);
});
test('scene presets use actual rack and floor images and dispatch the corresponding region IDs',()=>{
  const app=boot();app.window.twinNavigate('settings');
  for(const [id,label,file]of[['racks','货架区域','warehouse-racks'],['floor','地堆区域','warehouse-storage']]){
    assert.ok(app.html().includes(label));assert.ok(app.html().includes('assets/'+file+'.png'));
    assert.ok(fs.existsSync(path.join(__dirname,'../assets',file+'.png')));
    app.click({action:'preset',value:id});
    assert.equal(app.commands.at(-1).action,'preset');assert.equal(app.commands.at(-1).value,id);
  }
  assert.ok(!app.html().includes('入库月台'));assert.ok(!app.html().includes('出库月台'));
});
