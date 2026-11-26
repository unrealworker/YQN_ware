const test=require('node:test');
const assert=require('node:assert/strict');
const policy=require('../entry-policy.js');
const globe=require('../globe-policy.js');
const catalog=require('../../data/warehouses.json').warehouses;

test('only the two connected warehouses appear, with stable order and real addresses',()=>{
  const extra={id:'demo',name:'示例仓库'};
  assert.deepEqual(policy.catalog([extra,...catalog.slice().reverse()]).map(row=>row.id),['ghs-ca','mpr-nj']);
  assert.equal(policy.filter(catalog,'Middlesex')[0].id,'mpr-nj');
  assert.equal(policy.filter(catalog,'GHS','北美')[0].id,'ghs-ca');
  assert.equal(policy.filter(catalog,'','亚洲').length,0);
});
test('enter remains locked through stale idle updates, loading and revealing',()=>{
  let gate='idle';
  assert.equal(policy.canEnter('idle',gate,'mpr-nj',catalog),true);
  gate=policy.advanceGate(gate,'request');
  gate=policy.advanceGate(gate,'idle');
  assert.equal(policy.canEnter('idle',gate,'ghs-ca',catalog),false);
  for(const phase of ['loading','flying','revealing']){
    gate=policy.advanceGate(gate,phase);
    assert.equal(policy.canEnter(phase,gate,'ghs-ca',catalog),false);
  }
  gate=policy.advanceGate(gate,'warehouse');
  assert.equal(policy.canEnter('warehouse',gate,'ghs-ca',catalog),false);
  assert.equal(policy.canEnter('selected',gate,'ghs-ca',catalog),true);
});
test('cancel waits for native return to browsing; error permits retry',()=>{
  let gate=policy.advanceGate('acknowledged','cancel-request');
  assert.equal(policy.advanceGate(gate,'loading'),'cancelling');
  assert.equal(policy.canEnter('loading',gate,'ghs-ca',catalog),false);
  gate=policy.advanceGate(gate,'idle');
  assert.equal(policy.canEnter('idle',gate,'mpr-nj',catalog),true);
  assert.equal(policy.advanceGate('pending','error'),'idle');
  assert.equal(policy.canEnter('error','idle','unknown',catalog),false);
  assert.equal(policy.advanceGate('cancelling','failed'),'idle','a rejected cancellation releases the UI lock');
});
test('curtain only acknowledges the current opaque full-size entering or returning frame',()=>{
  const t={awaitingCurtain:true,opacity:1,generation:3,width:1920,height:1080};
  assert.equal(policy.curtainReady('flying',t,1920,1080,null),true);
  assert.equal(policy.curtainReady('returning',t,1920,1080,null),true);
  assert.equal(policy.curtainReady('flying',t,200,44,null),false);
  assert.equal(policy.curtainReady('flying',t,1920,1080,3),false);
  assert.equal(policy.curtainReady('flying',{...t,opacity:.99},1920,1080,null),false);
  assert.equal(policy.curtainReady('warehouse',t,1920,1080,null),false);
  assert.equal(policy.curtainReady('flying',{...t,generation:NaN},1920,1080,null),false);
});
test('catalog must cover the full viewport and finish its entrance before acknowledging a frame',()=>{
  const frame={page:'warehouses',visible:true,opaque:true,stable:true,
    portal:{left:0,top:0,width:1920,height:1080},
    header:{left:0,top:0,width:1920,height:64},
    content:{left:0,top:64,width:1920,height:1016}};
  assert.equal(policy.catalogFrameReady(frame,1920,1080),true);
  for(const key of ['visible','opaque','stable'])assert.equal(policy.catalogFrameReady({...frame,[key]:false},1920,1080),false,key);
  assert.equal(policy.catalogFrameReady({...frame,page:'login'},1920,1080),false);
  assert.equal(policy.catalogFrameReady({...frame,portal:{left:0,top:0,width:200,height:44}},1920,1080),false);
  assert.equal(policy.catalogFrameReady({...frame,content:{...frame.content,top:70}},1920,1080),false);
  assert.equal(policy.catalogFrameReady({...frame,header:{...frame.header,height:NaN}},1920,1080),false);
  assert.equal(policy.catalogFrameReady({...frame,content:{...frame.content,width:1910}},1920,1080),false);
});
test('only a requested or entering warehouse shows a card spinner; returning and cancellation never do',()=>{
  assert.equal(policy.entering('idle','pending'),true);
  for(const phase of ['loading','flying','revealing'])assert.equal(policy.entering(phase,'acknowledged'),true);
  for(const phase of ['idle','selected','error','warehouse','returning'])assert.equal(policy.entering(phase,'idle'),false);
  assert.equal(policy.entering('returning','pending'),false);
  assert.equal(policy.entering('loading','cancelling'),false);
});
test('catalog only uncovers a ready arrival; missing or non-boolean readiness never uncovers revealing',()=>{
  for(const transition of [undefined,null,{}, {opacity:0,waitingForDestination:false},
    {arrivalStarted:false},{arrivalStarted:'true'},{arrivalStarted:1}]){
    assert.equal(policy.sceneVisible('revealing',transition),false);
  }
  const initial={phase:'loading',stageVisible:false,selectedId:'mpr-nj',warehouses:catalog,pois:[],countries:[],transition:{opacity:1}};
  let current=initial;
  for(const [phase,arrivalStarted,visible] of [
    ['loading',false,false],['flying',true,false],['revealing',false,false],
    ['revealing',true,true],['warehouse',false,true],['returning',true,false],['selected',false,false]
  ]){
    current=globe.nextState(current,JSON.stringify({phase,transition:{opacity:0,arrivalStarted}}));
    assert.ok(current,'native readiness flag survives the bridge state parser');
    assert.equal(policy.sceneVisible(current.phase,current.transition),visible,phase);
    if(phase==='revealing')assert.equal(policy.canEnter(phase,'acknowledged','ghs-ca',catalog),false);
  }
  assert.equal(policy.sceneVisible('warehouse',undefined),true);
});
test('native catalog and phase validation rejects malformed updates without losing the last catalog',()=>{
  const initial={phase:'idle',stageVisible:true,selectedId:'',warehouses:catalog,pois:[],countries:[],transition:{opacity:0}};
  assert.equal(globe.nextState(initial,{phase:'loading'}).warehouses,catalog);
  assert.equal(globe.nextState(initial,{phase:'surprise'}),null);
  assert.equal(globe.nextState(initial,{transition:{opacity:1,awaitingCurtain:true,generation:1,width:0,height:0}}),null);
  assert.equal(globe.nextState(initial,{warehouses:[{id:7,name:'invalid'}]}),null);
  assert.equal(globe.nextState(initial,JSON.stringify({phase:'selected',selectedId:'mpr-nj'})).selectedId,'mpr-nj','FString getstate replies are decoded');
  assert.equal(globe.nextState(initial,'not JSON'),null);
});
test('preview images are restricted to bundled asset paths',()=>{
  assert.equal(policy.imagePath('assets/mpr-warehouse-overview.png'),'assets/mpr-warehouse-overview.png');
  for(const unsafe of ['https://example.com/photo.png','assets/../secret.png','javascript:alert(1)','assets/x.svg',null])assert.equal(policy.imagePath(unsafe),'');
});
