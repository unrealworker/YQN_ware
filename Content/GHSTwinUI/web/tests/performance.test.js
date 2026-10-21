const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {boot}=require('./harness');

const device=(id='AGV-07',value='82%')=>({id,type:'agv',status:'running',progress:82,value,location:'A 区',live:true,available:true});
const snapshot=(equipment=[device()],extra={})=>({connected:true,equipment,facilities:[],...extra});
const metrics=app=>app.window.twinGetPerformance();

test('identical snapshots and scene geometry changes do not regenerate business HTML',()=>{
  const app=boot();app.window.twinReceive(snapshot());app.window.twinNavigate('devices');app.flush();
  const before=metrics(app);
  for(let i=0;i<4;i++)app.window.twinReceive(snapshot([device()],{worldBounds:[i,2,3],mapName:'RuntimeMap'+i}));
  app.flush();const after=metrics(app);
  assert.equal(after.htmlBuilds,before.htmlBuilds);
  assert.equal(after.domWrites,before.domWrites);
  assert.equal(after.normalizedSnapshots-before.normalizedSnapshots,4);
  app.window.twinReceive(snapshot([device('AGV-07','73%')]));
  assert.equal(metrics(app).htmlBuilds,before.htmlBuilds+1);
  assert.ok(app.html().includes('73%'));
});

test('overview ignores telemetry values but refreshes state distribution',()=>{
  const app=boot();app.window.twinReceive(snapshot());const before=metrics(app).htmlBuilds;
  app.window.twinReceive(snapshot([device('AGV-07','73%')]));
  assert.equal(metrics(app).htmlBuilds,before);
  app.window.twinReceive(snapshot([{...device(),status:'fault'}]));
  assert.equal(metrics(app).htmlBuilds,before+1);
  assert.ok(app.html().includes('设备状态 · 1 台'));
});

test('open device detail updates only its own dependencies and Back sees latest list',()=>{
  const app=boot();app.window.twinReceive(snapshot([device(),device('AGV-08')]));app.window.twinNavigate('devices');
  app.window.twinSelect(snapshot([device(),device('AGV-08')],{selection:{kind:'device',id:'AGV-07'}}));
  const before=metrics(app).htmlBuilds;
  app.window.twinReceive(snapshot([device(),device('AGV-08','17%')],{selection:{kind:'device',id:'AGV-07'}}));
  assert.equal(metrics(app).htmlBuilds,before);
  app.window.twinReceive(snapshot([{...device(),location:'B 区'},device('AGV-08','17%')],{selection:{kind:'device',id:'AGV-07'}}));
  assert.equal(metrics(app).htmlBuilds,before+1);assert.ok(app.html().includes('B 区'));
  app.window.twinBack();assert.ok(app.html().includes('17%'));
});

test('static business pages ignore unrelated telemetry while preserving their images and charts',()=>{
  const app=boot();app.window.twinReceive(snapshot());
  for(const page of ['inventory','orders','settings']){
    app.window.twinNavigate(page);const before=metrics(app).htmlBuilds,html=app.html();
    app.window.twinReceive(snapshot([{...device(),status:'warning',progress:13,value:'13%'}]));
    assert.equal(metrics(app).htmlBuilds,before,page);assert.equal(app.html(),html,page);
  }
  app.window.twinNavigate('devices');assert.ok(app.html().includes('13%'));
});

test('hidden panel defers normalization HTML and reports then resumes once with newest snapshot',()=>{
  const app=boot();app.window.twinReceive(snapshot());app.window.twinNavigate('devices');app.flush();
  app.elements.main.scrollTop=285;app.window.twinSetVisibility(false);
  const before=metrics(app),commands=app.commands.length,html=app.html();
  for(let i=0;i<5;i++)app.window.twinReceive(snapshot([device('AGV-07',i+'%')]));
  app.flush();const hidden=metrics(app);
  assert.equal(hidden.normalizedSnapshots,before.normalizedSnapshots);
  assert.equal(hidden.htmlBuilds,before.htmlBuilds);assert.equal(app.html(),html);
  assert.equal(app.commands.length,commands);assert.equal(hidden.hiddenSnapshots-before.hiddenSnapshots,5);
  app.window.twinSetVisibility(true);app.flush();const after=metrics(app);
  assert.equal(after.normalizedSnapshots,before.normalizedSnapshots+1);
  assert.equal(after.htmlBuilds,before.htmlBuilds+1);assert.ok(app.html().includes('4%'));
  assert.equal(app.elements.main.scrollTop,285);
  app.window.twinSetVisibility(true);assert.equal(metrics(app).htmlBuilds,after.htmlBuilds);
});

test('hidden explicit selection and native clear never resurrect stale nested details',()=>{
  const app=boot();app.window.twinNavigate('devices');app.window.twinSelect(snapshot(undefined,{selection:{kind:'device',id:'AGV-07'}}));
  app.window.twinBack();app.window.twinSetVisibility(false);
  app.window.twinSelect(snapshot(undefined,{selection:{kind:'device',id:'AGV-07'}}));
  app.window.twinSetVisibility(true);assert.equal(app.window.twinState.detail.id,'AGV-07');
  app.window.twinSetVisibility(false);
  app.window.twinSelect(snapshot(undefined,{selection:{kind:'material',id:'CAD-2',instanceIndex:2}}));
  app.window.twinReceive(snapshot());app.window.twinClearSelection();app.window.twinSetVisibility(true);
  assert.equal(app.window.twinState.detail,null);assert.equal(app.window.twinState.stack.length,0);
  assert.ok(app.html().includes('<h1>设备监控</h1>'));
});

test('hidden navigation and telemetry settle once without restarting a page transition',()=>{
  const app=boot({reducedMotion:false});app.window.twinReceive(snapshot());app.flush();
  app.window.twinNavigate('devices');app.advance(60);app.window.twinSetVisibility(false);
  const before=metrics(app).htmlBuilds;
  app.window.twinNavigate('inventory');app.window.twinReceive(snapshot([]));app.window.twinNavigate('orders');app.flush();
  assert.equal(metrics(app).htmlBuilds,before);
  app.window.twinSetVisibility(true);app.flush();assert.ok(app.html().includes('今日出入库订单'));
  assert.equal(metrics(app).htmlBuilds,before+1);assert.equal(app.commands.at(-1).transition.phase,'idle');
});

test('diagnostic opt-out avoids layout reads and reporting while preserving 320 ms navigation',()=>{
  const app=boot({reducedMotion:false,search:'?diagnostics=0'});
  let reads=0;
  app.window.getComputedStyle=()=>{reads++;return{opacity:'1'};};
  app.window.document.querySelector=()=>{reads++;return null;};
  app.window.twinNavigate('devices');app.advance(119);assert.ok(app.html().includes('仓库运营总览'));
  app.advance(1);assert.ok(app.html().includes('设备监控'));app.flush();
  assert.equal(reads,0);assert.ok(!app.commands.some(x=>x.action==='report'));
  app.window.twinSetDiagnostics(true);app.flush();assert.ok(reads>0);assert.equal(app.commands.at(-1).action,'report');
  const reportCount=app.commands.filter(x=>x.action==='report').length;
  app.window.twinSetDiagnostics(false);reads=0;app.window.twinNavigate('orders');app.flush();
  assert.equal(reads,0);assert.equal(app.commands.filter(x=>x.action==='report').length,reportCount);
});

test('normalization is reused by multiple renders and diagnostics until another snapshot arrives',()=>{
  const app=boot();let reads=0;
  const row=device();Object.defineProperty(row,'type',{enumerable:true,get(){reads++;return'agv';}});
  app.window.twinReceive(snapshot([row]));const normalizedReads=reads;
  app.window.twinNavigate('devices');app.window.twinNavigate('alerts');app.window.twinNavigate('overview');app.flush();
  assert.ok(normalizedReads>0);assert.equal(reads,normalizedReads);
  const before=metrics(app).normalizedSnapshots;
  app.window.twinReceive(snapshot([row]));assert.equal(metrics(app).normalizedSnapshots,before+1);
});

test('focused search defers changed data until focus-out and keeps the current scroll',()=>{
  const app=boot();app.window.twinReceive(snapshot());app.window.twinNavigate('devices');app.flush();
  app.elements.main.scrollTop=285;app.window.document.activeElement={tagName:'INPUT'};
  const before=metrics(app).htmlBuilds;
  app.window.twinReceive(snapshot([device('AGV-07','47%')]));
  assert.equal(metrics(app).htmlBuilds,before);assert.ok(!app.html().includes('47%'));
  app.window.document.activeElement=null;app.listeners.focusout({});app.flush();
  assert.equal(metrics(app).htmlBuilds,before+1);assert.ok(app.html().includes('47%'));
  assert.equal(app.elements.main.scrollTop,285);
});

test('same CAD instance updates its metadata without adding a detail return frame',()=>{
  const app=boot(),selection={kind:'material',id:'CAD-2',instanceIndex:2,title:'物料 A',location:'一层'};
  app.window.twinSelect(snapshot(undefined,{selection}));const stack=app.window.twinState.stack.length;
  app.window.twinReceive(snapshot(undefined,{selection:{...selection,title:'物料 B',location:'二层'}}));
  assert.ok(app.html().includes('物料 B'));assert.ok(app.html().includes('二层'));
  assert.equal(app.window.twinState.stack.length,stack);
});

test('device trace refreshes its referenced state but unrelated devices do not rebuild it',()=>{
  const app=boot();app.window.twinReceive(snapshot([device(),device('AGV-08')]));
  Object.assign(app.window.twinState.filters.trace,{mode:'device',query:'AGV-07',queried:true});
  app.window.twinNavigate('trace');const before=metrics(app).htmlBuilds;
  app.window.twinReceive(snapshot([device(),{...device('AGV-08'),status:'fault'}]));
  assert.equal(metrics(app).htmlBuilds,before);
  app.window.twinReceive(snapshot([{...device(),status:'offline',location:'C 区'},device('AGV-08')]));
  assert.equal(metrics(app).htmlBuilds,before+1);assert.ok(app.html().includes('C 区'));
});

test('diagnostic bridge opt-out cancels an already scheduled report',()=>{
  const app=boot();app.window.twinSetDiagnostics(false);app.flush();
  assert.ok(!app.commands.some(x=>x.action==='report'));
  const copy=metrics(app);copy.htmlBuilds=9999;
  assert.notEqual(metrics(app).htmlBuilds,9999);
});

test('full CAD snapshots remove omitted optional fields instead of preserving stale levels',()=>{
  const app=boot(),selection={kind:'material',id:'CAD-2',instanceIndex:2,title:'物料 A',level:2,column:4};
  app.window.twinSelect(snapshot(undefined,{selection}));
  assert.ok(app.html().includes('货架层'));assert.ok(app.html().includes('货架列'));
  const before=metrics(app).htmlBuilds;
  app.window.twinReceive(snapshot(undefined,{selection:{kind:'material',id:'CAD-2',instanceIndex:2,title:'物料 A'}}));
  assert.equal(app.window.twinState.detail.level,undefined);assert.equal(app.window.twinState.detail.column,undefined);
  assert.ok(!app.html().includes('货架层'));assert.ok(!app.html().includes('货架列'));
  assert.equal(metrics(app).htmlBuilds,before+1);
});

test('Back restores the latest full CAD record even when telemetry arrived on a child detail',()=>{
  const app=boot(),selection={kind:'material',id:'CAD-2',instanceIndex:2,title:'物料 A',location:'一层',level:2,column:4};
  app.window.twinSelect(snapshot(undefined,{selection}));app.click({action:'material'});
  const stackLength=app.window.twinState.stack.length;
  app.window.twinReceive(snapshot(undefined,{selection:{...selection,title:'物料 B',location:'二层',level:3,column:undefined}}));
  assert.equal(app.window.twinState.detail.kind,'material-demo');assert.equal(app.window.twinState.stack.length,stackLength);
  app.window.twinBack();assert.ok(app.html().includes('物料 B'));assert.ok(app.html().includes('二层'));
  assert.equal(app.window.twinState.detail.level,3);assert.equal(app.window.twinState.detail.column,undefined);
});

test('CAD return records match instance index as well as kind and ID',()=>{
  const app=boot(),selection={kind:'material',id:'CAD-2',instanceIndex:2,title:'实例 2'};
  app.window.twinSelect(snapshot(undefined,{selection}));
  app.window.twinSelect(snapshot(undefined,{selection:{...selection,instanceIndex:3,title:'实例 3'}}));
  app.window.twinReceive(snapshot(undefined,{selection:{...selection,instanceIndex:3,title:'实例 3 更新'}}));
  app.window.twinBack();assert.equal(app.window.twinState.detail.instanceIndex,2);
  assert.ok(app.html().includes('实例 2'));assert.ok(!app.html().includes('实例 3 更新'));
});

test('native hidden-selection bridge resumes on the new object without an outgoing stale detail',()=>{
  const app=boot({reducedMotion:false});
  const rows=[device('AGV-07'),device('AGV-08')];
  app.window.twinSelect(snapshot(rows,{selection:{kind:'device',id:'AGV-07'}}));app.flush();
  app.window.twinSetVisibility(false);
  // Read the native emitter's two operations and replay their source order into
  // the actual JS controller. UE/CEF execution still belongs to the runtime suite.
  const native=fs.readFileSync(path.join(__dirname,'../../../../Source/Test/GHSTwinHUDWidget.cpp'),'utf8');
  const emitter=native.split('void UGHSTwinHUDWidget::UpdateBrowserVisibility(')[1].split('FVector2D UGHSTwinHUDWidget::GetPanelVisualPosition')[0];
  const select=native.split('bool UGHSTwinHUDWidget::SelectObject(')[1].split('void UGHSTwinHUDWidget::ClearSelection')[0];
  assert.match(select,/if\(bOpening\) SetPanelCollapsed\(false,true\); else PushSnapshot\(true\);/);
  assert.match(emitter,/PushSnapshot\(bExplicitSelection,true\)/);
  const replaySelection=selection=>[
    [emitter.indexOf('PushSnapshot('),()=>app.window.twinSelect(snapshot(rows,{selection}))],
    [emitter.indexOf('Panel->Evaluate('),()=>app.window.twinSetVisibility(true)]
  ].sort((a,b)=>a[0]-b[0]).forEach(([,run])=>run());
  replaySelection({kind:'device',id:'AGV-08'});
  assert.ok(app.html().includes('AGV-08'));
  assert.ok(!app.html().includes('AGV-07'));
  const builds=metrics(app).htmlBuilds;app.advance(119);
  assert.ok(app.html().includes('AGV-08'));assert.equal(metrics(app).htmlBuilds,builds);
  app.flush();assert.equal(app.commands.at(-1).transition.phase,'idle');
  app.window.twinSetVisibility(false);const stack=app.window.twinState.stack.length;
  replaySelection({kind:'material',id:'CAD-2',instanceIndex:2,title:'最新 CAD 物料'});
  assert.ok(app.html().includes('最新 CAD 物料'));assert.ok(!app.html().includes('AGV-08'));
  assert.equal(app.window.twinState.stack.length,stack+1);app.flush();
  assert.equal(app.window.twinState.stack.length,stack+1);
});
