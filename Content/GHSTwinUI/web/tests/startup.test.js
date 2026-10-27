const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../startup.js'),'utf8');
function boot({native=true,fonts=false}={}){
  const listeners={},attributes={},queue=new Map(),timers=new Map();let serial=0,fontFinish;
  const document={documentElement:{setAttribute:(k,v)=>attributes[k]=v,removeAttribute:k=>delete attributes[k]},
    addEventListener:(k,fn)=>listeners[k]=fn,removeEventListener:k=>delete listeners[k],dispatchEvent:e=>listeners[e.type]?.(),
    fonts:fonts?{load:()=>({then:fn=>fontFinish=fn})}:undefined};
  const window={innerWidth:1,innerHeight:1,document,ue:native?{twin:{}}:undefined,
    addEventListener:(k,fn)=>listeners[k]=fn,removeEventListener:k=>delete listeners[k]};
  const design={width:1,height:1,native:false};
  window.TwinViewport={getState:()=>design,hasNativeViewport:()=>design.native};
  vm.runInNewContext(source,{window,document,Event:class{constructor(type){this.type=type;}},
    requestAnimationFrame:fn=>{queue.set(++serial,fn);return serial;},
    setTimeout:fn=>{timers.set(++serial,fn);return serial;},clearTimeout:id=>timers.delete(id)});
  return {window,design,attributes,listeners,queue,timers,font:()=>fontFinish?.(),
    event:type=>listeners[type]?.(),frame:()=>{const batch=[...queue.values()];queue.clear();batch.forEach(fn=>fn());},
    size(width=320,height=678){window.innerWidth=width;window.innerHeight=height;Object.assign(design,{width:480,height:1016});listeners.resize?.();}};
}
test('a native 1px surface never renders content, including after font timeout',()=>{
  const app=boot({fonts:true});let rendered=0;
  app.window.TwinStartup.whenReady(()=>rendered++);
  [...app.timers.values()].forEach(fn=>fn());app.frame();app.frame();
  assert.equal(rendered,0);assert.equal(app.queue.size,0);assert.ok('data-ui-pending' in app.attributes);
  app.size();app.frame();app.frame();assert.equal(rendered,0,'native design viewport is still missing');
  app.design.native=true;app.event('twin-viewport-change');app.frame();app.frame();
  assert.equal(rendered,1);assert.equal(app.window.TwinStartup.presented,false);
  app.frame();app.frame();assert.equal(app.window.TwinStartup.presented,true);assert.ok(!('data-ui-pending' in app.attributes));
});
test('resizing during preparation restarts stability and only reveals the completed dimensions',()=>{
  const app=boot();app.design.native=true;app.size();app.frame();
  app.size(360,720);app.frame();assert.equal(app.window.TwinStartup.ready,false);
  app.frame();assert.equal(app.window.TwinStartup.ready,true);
  app.size(400,800);app.frame();assert.equal(app.window.TwinStartup.presented,false);
  app.frame();assert.equal(app.window.TwinStartup.presented,true);
  assert.equal(app.window.TwinStartup.diagnostics().presentedViewport.width,400);
  assert.equal(app.listeners.resize,undefined);
});
test('font readiness gates the first render and late subscriptions cannot miss ready',()=>{
  const app=boot({fonts:true});app.design.native=true;app.size();app.frame();app.frame();
  assert.equal(app.window.TwinStartup.ready,false);
  app.font();app.frame();app.frame();let called=0;app.window.TwinStartup.whenReady(()=>called++);
  assert.equal(called,1);app.frame();app.frame();assert.equal(app.window.TwinStartup.presented,true);
});
test('a standalone browser does not wait for an Unreal bridge or native viewport',()=>{
  const app=boot({native:false});app.size();app.frame();app.frame();app.frame();app.frame();
  assert.equal(app.window.TwinStartup.presented,true);
});

test('the page handshakes immediately but renders only the newest data and navigation after startup',()=>{
  const startup={ready:false,presented:false,whenReady(callback){this.release=()=>{this.ready=true;callback();};}};
  const app=require('./harness').boot({startup,reducedMotion:false});
  assert.ok(app.commands.some(c=>c.action==='ready'),'native viewport delivery must not deadlock');
  assert.ok(app.commands.some(c=>c.action==='replayReady'));
  assert.equal(app.html(),'');assert.equal(app.elements.navigation.innerHTML,'');
  app.window.twinNavigate('inventory');app.window.twinNavigate('devices');
  app.window.twinState.filters.devices.view='scene';
  for(const value of ['12%','73%'])app.window.twinReceive({connected:true,equipment:[{id:'AGV-07',type:'agv',status:'running',value,available:true}],facilities:[]});
  app.flush();assert.equal(app.html(),'');assert.equal(app.window.twinGetPerformance().domWrites,0);
  startup.release();app.flush();
  assert.ok(app.html().includes('73%'));assert.ok(!app.html().includes('12%'));
  assert.equal(app.window.twinGetPerformance().domWrites,1);
  assert.ok(!app.commands.some(c=>c.action==='report'),'reports must describe the visible frame');
  startup.presented=true;app.listeners['twin-ui-presented']();app.flush();
  assert.equal(app.commands.filter(c=>c.action==='report').at(-1).page,'devices');
});

test('a sidebar hidden during startup resumes once with the latest queued snapshot',()=>{
  const startup={ready:false,presented:false,whenReady(callback){this.release=()=>{this.ready=true;callback();};}};
  const app=require('./harness').boot({startup});
  app.window.twinSetVisibility(false);app.window.twinNavigate('devices');
  app.window.twinState.filters.devices.view='scene';
  app.window.twinReceive({connected:true,equipment:[{id:'AGV-09',type:'agv',status:'running',value:'91%',available:true}],facilities:[]});
  startup.release();assert.equal(app.html(),'');
  startup.presented=true;app.listeners['twin-ui-presented']();app.flush();
  assert.ok(!app.commands.some(c=>c.action==='report'));
  app.window.twinSetVisibility(true);app.flush();
  assert.ok(app.html().includes('91%'));assert.equal(app.window.twinGetPerformance().domWrites,1);
});
