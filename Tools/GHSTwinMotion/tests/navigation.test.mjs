import test from 'node:test';
import assert from 'node:assert/strict';
import { createNavigation } from '../src/navigation.js';

function setup() {
  const buttons = [20, 96, 172].map(y => ({offsetLeft:4,offsetTop:y,offsetWidth:46,offsetHeight:68}));
  let selected = 0, animate = true, reads = 0, writes = [], observed = [], resized;
  const events = new Map();
  const pill = {className:'',setAttribute(){},style:new Proxy({}, {set(o,k,v){writes.push([k,v]);o[k]=v;return true;}})};
  Object.defineProperty(pill,'offsetWidth',{get(){reads++;return 46;}});
  const doc = {createElement:()=>pill,addEventListener:(n,f)=>events.set(n,f),removeEventListener:n=>events.delete(n)};
  const nav = {prepend(){},classList:{add(){}},querySelector:()=>buttons[selected],querySelectorAll:()=>buttons};
  class RO {constructor(f){resized=f;}observe(n){observed.push(n);}disconnect(){observed=[];}}
  const controller = createNavigation(nav,{document:doc,ResizeObserver:RO,canAnimate:()=>animate});
  return {controller,pill,buttons,events,get reads(){return reads;},get observed(){return observed;},get writes(){return writes;},clear(){writes=[];},select:i=>selected=i,reduce:()=>animate=false,resize:()=>resized()};
}

test('selection commits synchronously and repeated retargets leave interpolation to CSS',()=>{
  const a=setup();a.controller.update();assert.equal(a.pill.style.transform,'translate3d(4px,20px,0)');
  assert.equal(a.reads,1);a.clear();
  a.select(1);a.controller.update();a.select(2);a.controller.update();
  assert.equal(a.pill.style.transform,'translate3d(4px,172px,0)');assert.equal(a.reads,1);
  assert.ok(!a.writes.some(([k,v])=>k==='transition'&&v==='none'));
  a.clear();a.controller.update();assert.deepEqual(a.writes,[]);
});

test('hover and focus have no selected-layer handlers; unchanged viewport cannot cancel a glide',()=>{
  const a=setup();a.controller.update();a.select(1);a.controller.update();a.clear();
  a.events.get('twin-viewport-change')();a.resize();
  assert.deepEqual(a.writes,[]);assert.deepEqual([...a.events.keys()],['twin-viewport-change']);
});

test('DPI/layout alignment uses design offsets and observes child dimensions',()=>{
  const a=setup();a.controller.update();assert.equal(a.observed.length,4);
  a.buttons[0].offsetLeft=102;a.buttons[0].offsetWidth=58;a.resize();
  assert.equal(a.pill.style.transform,'translate3d(102px,20px,0)');assert.equal(a.pill.style.width,'58px');assert.equal(a.reads,2);
});

test('reduced motion and hiding settle the selected layer immediately; disposal removes listeners',()=>{
  const a=setup();a.controller.update();a.reduce();a.select(2);a.controller.update();
  assert.equal(a.reads,2);assert.ok(a.writes.some(([k,v])=>k==='transition'&&v==='none'));
  a.controller.settle();assert.equal(a.reads,3);
  a.controller.dispose();assert.equal(a.observed.length,0);assert.equal(a.events.size,0);
});
