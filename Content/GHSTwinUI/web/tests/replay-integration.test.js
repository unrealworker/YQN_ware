const test=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./harness');
const active={active:true,playing:true,time:230,duration:3600,rate:1,startUtc:'2026-10-23T16:00:00.000Z',endUtc:'2026-10-23T17:00:00.000Z',orderId:'TEST-OUT-001',devices:[{id:'REPLAY-FORK-01',type:'forklift',title:'人工叉车',state:'pickup',visible:true}],events:[],markers:[]};
function replay(){const a=boot();assert.equal(typeof a.window.twinReplayReceive,'function','Production replay is not wired');a.window.twinReplayReceive(active);a.flush();return a;}
test('trace replaces the old material lookup with time-indexed test orders',()=>{
 const a=boot();a.window.twinNavigate('trace');a.flush();assert.match(a.html(),/选择时间段/);assert.ok(!a.html().includes('物料追溯'));
 const r=a.window.twinReplayUI;r.field('start','2026-10-23T09:00:00');r.field('end','2026-10-23T10:00:00');r.handle('query');a.flush();assert.equal((a.html().match(/data-id="TEST-OUT-/g)||[]).length,4);
 r.handle('start',{id:'TEST-OUT-002'});assert.deepEqual(JSON.parse(JSON.stringify(a.commands.at(-1))),{action:'replayStart',orderId:'TEST-OUT-002',startUtc:'2026-10-23T16:00:00.000Z',endUtc:'2026-10-23T17:00:00.000Z'});
});
test('active native navigation waits for confirmation and native callback',()=>{
 const a=replay();assert.equal(a.window.twinState.page,'trace');a.click({action:'nav',page:'inventory'});a.flush();assert.equal(a.window.twinState.page,'trace');assert.equal(a.commands.at(-1).action,'navigate');
 a.window.twinReplayReceive({...active,active:false,playing:false});a.window.twinNavigate('inventory');a.flush();assert.equal(a.window.twinState.page,'inventory');
});
test('active JavaScript detail action retains its ID and executes only on matching continuation',()=>{
 const a=replay();a.click({action:'order',id:'OUT-20261020-121'});a.flush();const token=a.commands.findLast(c=>c.action==='replayLeave').token;assert.equal(a.window.twinState.detail,null);
 a.window.twinReplayReceive({...active,exitPending:true});a.window.twinReplayReceive({...active,active:false,exitPending:false});a.window.twinReplayContinue(token);a.flush();assert.equal(a.window.twinState.detail.id,'OUT-20261020-121');
 const depth=a.window.twinState.stack.length;a.window.twinReplayContinue(token);assert.equal(a.window.twinState.stack.length,depth);
});
test('cancelled leave preserves replay progress and clears a stale detail target',()=>{
 const a=replay();a.click({action:'material'});const token=a.commands.findLast(c=>c.action==='replayLeave').token;a.window.twinReplayReceive({...active,exitPending:true});a.window.twinReplayReceive({...active,exitPending:false});a.window.twinReplayContinue(token);a.flush();assert.equal(a.window.twinState.detail,null);assert.equal(a.window.twinReplayUI.view().state.time,230);
});
test('scene selection snapshots cannot replace the replay panel while isolation is active',()=>{
 const a=replay();a.window.twinReceive({selection:{kind:'device',id:'FORK-01'},equipment:[],facilities:[]});a.flush();assert.equal(a.window.twinState.detail,null);assert.match(a.html(),/全时段设备回放/);
});
test('native event windows open the event tab and paginate within the requested time window',()=>{
 const a=replay(),events=Array.from({length:100},(_,i)=>({id:'e'+i,time:100+i,type:'pickup',deviceId:'REPLAY-FORK-01',title:'取货完成'}));
 a.window.twinReplayReceive({...active,eventsWindow:{start:100,end:800,total:200},events});a.flush();
 assert.equal(a.window.twinReplayUI.view().tab,'events');assert.match(a.html(),/200 个事件/);assert.match(a.html(),/查看后续/);
 a.window.twinReplayUI.handle('events-next');assert.deepEqual(JSON.parse(JSON.stringify(a.commands.at(-1))),{action:'replayEvents',start:199.001,end:800});
 a.window.twinReplayUI.handle('events-reset');assert.deepEqual(JSON.parse(JSON.stringify(a.commands.at(-1))),{action:'replayEvents',reset:true});
});
test('motion-only updates preserve the replay panel render key while visible device state changes invalidate it',()=>{
 const a=replay(),r=a.window.twinReplayUI,key=r.key();
 a.window.twinReplayReceive({...active,time:231,devices:[{...active.devices[0],position:[1,2,3],yaw:45,lift:20}]});assert.equal(r.key(),key);
 a.window.twinReplayReceive({...active,devices:[{...active.devices[0],loaded:true,state:'carrying'}]});assert.notEqual(r.key(),key);
});
test('a fresh request for the same event window reopens events without hijacking the device tab on ordinary updates',()=>{
 const a=replay(),r=a.window.twinReplayUI,w={start:100,end:800,total:200,revision:1};
 a.window.twinReplayReceive({...active,eventsWindow:w});assert.equal(r.view().tab,'events');r.handle('tab',{tab:'devices'});
 a.window.twinReplayReceive({...active,time:231,eventsWindow:w});assert.equal(r.view().tab,'devices');
 a.window.twinReplayReceive({...active,eventsWindow:{...w,revision:2}});assert.equal(r.view().tab,'events');
});
