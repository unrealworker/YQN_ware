const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const file=path.join(__dirname,'../replay-core.js');
const R=fs.existsSync(file)?require(file):null;
test('production replay exposes real elapsed-time validation and a guarded transport',()=>assert.ok(R,'Replay core is not implemented'));
if(R){
test('at least one real hour is required without losing invalid local input',()=>{
 assert.equal(R.validateRange('2026-10-23T09:00:00','2026-10-23T09:59:59').ok,false);
 const r=R.validateRange('2026-10-23T09:00:00','2026-10-23T10:00:00');
 assert.equal(r.ok,true);assert.equal(r.duration,3600);assert.equal(r.startUtc,'2026-10-23T16:00:00.000Z');
 assert.equal(R.validateRange('2026-02-30T09:00','2026-03-01T12:00').ok,false);
});
test('Los Angeles spring gap is rejected and autumn repeated times require explicit offsets',()=>{
 assert.equal(R.localCandidates('2026-03-08T02:30').length,0);
 assert.equal(R.localCandidates('2026-11-01T01:30').length,2);
 assert.equal(R.validateRange('2026-11-01T01:00','2026-11-01T02:00').ok,false);
 const across=R.validateRange('2026-11-01T01:00','2026-11-01T01:00','PDT','PST');
 assert.equal(across.ok,true);assert.equal(across.duration,3600);
 const spring=R.validateRange('2026-03-08T01:30','2026-03-08T03:30');
 assert.equal(spring.duration,3600);
});
test('arbitrary valid periods resolve to the same four explicitly test orders',()=>{
 assert.deepEqual(R.orders().map(x=>x.id),['TEST-OUT-001','TEST-OUT-002','TEST-OUT-003','TEST-OUT-004']);
 assert.ok(R.orders().every(x=>x.isTest));
});
test('leave token preserves the original operation exactly once and cancellation discards it',()=>{
 const sent=[];let active=true,count=0,target='';const g=R.createLeaveGuard(x=>sent.push(x),()=>active);
 g.request('查看订单',()=>{count++;target='OUT-121'});const token=sent[0].token;
 assert.equal(count,0);g.receive({active:true,exitPending:true});g.receive({active:false,exitPending:false});
 g.continue(token);g.continue(token);assert.equal(count,1);assert.equal(target,'OUT-121');
 g.request('另一个目标',()=>count++);const cancelled=sent.at(-1).token;
 g.receive({active:true,exitPending:true});g.receive({active:true,exitPending:false});g.continue(cancelled);assert.equal(count,1);
 active=false;g.request('直接执行',()=>count++);assert.equal(count,2);
});
test('scrub pauses once, commits once on blur/release and preserves the original play state',()=>{
 const commands=[];let s={active:true,playing:true,time:100,duration:3600};const t=R.createTimeline(x=>commands.push(x),()=>s);
 t.begin();t.preview(250);t.preview(260);t.finish();t.finish();
 assert.deepEqual(commands,[{action:'replayPause'},{action:'replaySeek',time:260},{action:'replayPlay'}]);
 commands.length=0;s.playing=false;t.begin();t.preview(300);t.finish();assert.deepEqual(commands,[{action:'replaySeek',time:300}]);
 commands.length=0;s.playing=true;t.begin();t.preview(3600);t.finish();assert.deepEqual(commands,[{action:'replayPause'},{action:'replaySeek',time:3600}]);
});
test('event jumps pause and select without changing the camera follow target',()=>{
 const sent=[];const t=R.createTimeline(x=>sent.push(x),()=>({active:true,time:10,duration:3600,followId:'FORK-02'}));
 t.event({time:500,deviceId:'FORK-04'});
 assert.deepEqual(sent,[{action:'replayPause'},{action:'replaySeek',time:500},{action:'replaySelect',id:'FORK-04'}]);
});
test('preparing and exit-confirmation states cannot start a timeline drag',()=>{
 const sent=[];let state={active:true,preparing:true,exitPending:false,time:20,duration:3600};const t=R.createTimeline(x=>sent.push(x),()=>state);
 t.begin();assert.equal(t.isDragging(),false);state={...state,preparing:false,exitPending:true};t.begin();assert.equal(t.isDragging(),false);assert.equal(sent.length,0);
});
test('marker groups remain bounded for long ranges and retain fault priority',()=>{
 const marks=Array.from({length:10000},(_,i)=>({id:'e'+i,time:i,type:i===1?'fault':'pickup',title:'event'}));
 const groups=R.aggregateMarkers(marks,1000000,1000,80);
 assert.ok(groups.length<=80);assert.equal(groups[0].type,'fault');assert.equal(groups.reduce((s,g)=>s+g.count,0),10000);
});
test('native aggregated markers preserve exact counts and merge their visible time windows',()=>{
 const groups=R.aggregateMarkers([{id:'a',time:20,type:'pickup',count:35,rangeStart:10,rangeEnd:80},{id:'b',time:25,type:'fault',count:12,rangeStart:20,rangeEnd:90}],3600,100,8);
 assert.equal(groups.length,1);assert.equal(groups[0].count,47);assert.equal(groups[0].rangeStart,10);assert.equal(groups[0].rangeEnd,90);assert.equal(groups[0].type,'fault');
 const sent=[];R.createTimeline(x=>sent.push(x),()=>({active:true,duration:3600})).event(groups[0]);
 assert.deepEqual(sent.at(-1),{action:'replayEvents',start:10,end:90});
});
}
