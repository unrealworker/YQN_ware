const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {boot}=require('./harness');

function overlay(){
 const app=boot(),w=app.window,doc=w.document;
 w.innerWidth=1500;w.innerHeight=168;w.twinSetViewport(1500,168);
 const card=doc.getElementById('replay-transport'),marks=doc.getElementById('replay-markers'),slider=doc.getElementById('replay-seek');
 let rebuilds=0;const sliderListeners={};
 slider.style.setProperty=function(key,value){this[key]=value;};
 slider.addEventListener=(name,listener)=>{sliderListeners[name]=listener;};
 marks.replaceChildren=function(){rebuilds++;this.children=[];};
 Object.defineProperty(marks,'clientWidth',{get(){return Math.max(0,(parseFloat(card.style.width)||1492)-50);}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../replay-overlay.js'),'utf8'),w,{filename:'replay-overlay.js'});
 const state={active:true,playing:true,time:230,duration:3600,rate:4,
  startUtc:'2026-10-23T16:00:00.000Z',endUtc:'2026-10-23T17:00:00.000Z',
  orderId:'TEST-OUT-001',followId:'REPLAY-FORK-01',trailMode:'all',
  devices:[{id:'REPLAY-FORK-01',type:'forklift',visible:true}],events:[],
  markers:Array.from({length:180},(_,i)=>({id:'e'+i,time:i*20,type:'pickup',title:'取货完成'}))};
 w.twinReplayReceive(state);app.commands.length=0;
 return{...app,card,marks,slider,sliderListeners,state,rebuilds:()=>rebuilds};
}

test('native panel progress changes content width immediately without scaling the CEF root or replay state',()=>{
 const a=overlay(),w=a.window;
 assert.equal(typeof w.twinReplayLayout,'function');
 w.twinReplayLayout(950,false);
 const before=JSON.stringify(w.twinReplayOverlay.getState()),rootStyle={...w.document.documentElement.style};
 for(const width of [960,1030,1200,1450,1490,1500]){
  w.twinReplayLayout(width,true);
  assert.equal(a.card.style.width,(width-8)+'px');
  assert.equal(JSON.stringify(w.twinReplayOverlay.getState()),before);
  assert.deepEqual({...w.document.documentElement.style},rootStyle);
 }
 w.twinReplayLayout(1500,false);
 for(const width of [1470,1300,1100,950]){w.twinReplayLayout(width,true);assert.equal(a.card.style.width,(width-8)+'px');}
 w.twinReplayLayout(950,false);
 assert.equal(a.commands.length,0,'Layout must not issue transport commands');
});

test('moving panel retains marker nodes until it settles, then aggregates once for its final width',()=>{
 const a=overlay(),w=a.window;
 w.twinReplayLayout(500,false);
 const initial=a.marks.children.slice(),count=a.rebuilds();
 for(const width of [510,650,900,1100,1300,1500]){
  w.twinReplayLayout(width,true);
  w.twinReplayReceive({...a.state,time:231});
  assert.deepEqual(a.marks.children,initial);
  assert.equal(a.rebuilds(),count);
 }
 w.twinReplayLayout(1500,false);
 assert.equal(a.rebuilds(),count+1);
 assert.ok(a.marks.children.length>initial.length,'The wider final timeline can show more distinct event groups');
 const stable=a.marks.children.slice();w.twinReplayLayout(1500,false);
 assert.deepEqual(a.marks.children,stable);
});

test('changed key events still update during motion without rebuilding markers for every width sample',()=>{
 const a=overlay(),w=a.window;w.twinReplayLayout(950,false);
 w.twinReplayLayout(1100,true);const count=a.rebuilds();
 w.twinReplayReceive({...a.state,markers:[{id:'fault',time:100,type:'fault',title:'车辆故障'}]});
 assert.equal(a.rebuilds(),count+1);assert.equal(a.marks.children.length,1);
 assert.equal(a.marks.children[0].className,'replay-marker fault');
 w.twinReplayLayout(1250,true);assert.equal(a.rebuilds(),count+1);
});

test('resizing and reversing the panel does not finish or cancel an active timeline drag',()=>{
 const a=overlay(),w=a.window;w.twinReplayLayout(950,false);
 a.sliderListeners.pointerdown();a.slider.value='700';a.sliderListeners.input();
 for(const width of [1000,1200,1100,950])w.twinReplayLayout(width,true);
 w.twinReplayReceive({...a.state,time:231});
 assert.equal(a.slider.value,'700');
 assert.deepEqual(a.commands,[{action:'replayPause'}]);
 w.twinReplayLayout(950,false);a.sliderListeners.change();
 assert.deepEqual(a.commands,[{action:'replayPause'},{action:'replaySeek',time:700},{action:'replayPlay'}]);
});

test('visible overlay width controls compact layout independently of its larger CEF viewport',()=>{
 const a=overlay(),w=a.window,root=w.document.documentElement;
 w.twinReplayLayout(640,false);assert.equal(root.getAttribute('data-replay-compact'),'true');
 assert.equal(root.getAttribute('data-replay-condensed'),'true');
 w.twinReplayLayout(750,true);assert.equal(root.getAttribute('data-replay-compact'),'false');
 assert.equal(root.getAttribute('data-replay-condensed'),'true');
 w.twinReplayLayout(1000,false);assert.equal(root.getAttribute('data-replay-condensed'),'false');
 for(const width of [0,-1,NaN,Infinity])w.twinReplayLayout(width,false);
 assert.equal(a.card.style.width,'992px');
 assert.equal(w.TwinViewport.getState().width,1500);
});

test('standalone overlay follows its real viewport until a native content width is supplied',()=>{
 const a=overlay(),w=a.window;
 assert.equal(a.card.style.width,'1492px');
 w.twinSetViewport(600,168);assert.equal(a.card.style.width,'592px');
 assert.equal(w.document.documentElement.getAttribute('data-replay-compact'),'true');
 w.twinReplayLayout(500,false);w.twinSetViewport(1600,168);
 assert.equal(a.card.style.width,'492px','A true browser resize must not override the native visible-width contract');
});

test('right-hand popup stays inside the visible timeline instead of its full-width browser',()=>{
 const a=overlay(),w=a.window;w.twinReplayLayout(950,false);
 const button=w.document.getElementById('replay-trails').querySelector('button');
 button.rect={left:850,top:115,right:940,bottom:145,width:90,height:30};
 a.listeners.click({target:button});
 assert.equal(w.TwinDropdown.isOpen(),true);
 assert.ok(w.TwinDropdown.getState().menu.right<=942);
 w.twinReplayLayout(930,true);
 assert.equal(w.TwinDropdown.isOpen(),false,'A moving anchor must not leave an orphaned popup');
 assert.equal(a.commands.length,0);
});
