const test=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./harness');

test('CEF at Windows 150% and native HUD share 480 design units on a 640px panel',()=>{
  const app=boot(),w=app.window;
  w.innerWidth=427;w.innerHeight=1010;w.devicePixelRatio=1.5;
  assert.equal(typeof w.twinSetViewport,'function');
  w.twinSetViewport(480,1136);
  const state=w.TwinViewport.getState();
  assert.equal(state.width,480);assert.equal(state.height,1136);
  assert.ok(Math.abs(14*state.zoom*1.5-14*640/480)<.03,'14pt text matches native physical scale, not Windows DPI twice');
  assert.equal(w.document.documentElement.style.width,'480px');
  w.innerWidth=640;w.innerHeight=1515;w.devicePixelRatio=1;
  app.windowListeners.resize({});
  assert.ok(Math.abs(14*w.TwinViewport.getState().zoom-14*640/480)<.001);
});

test('popup geometry converts the zoomed anchor once and preserves keyboard filtering',()=>{
  const app=boot(),w=app.window;
  w.innerWidth=320;w.innerHeight=678;w.twinSetViewport(480,1016);
  w.twinNavigate('orders');
  const button=app.elements.page.querySelector('[data-filter="orders.status"]');
  button.rect={left:56,top:200,right:156,bottom:224,width:100,height:24};
  app.listeners.click({target:button});
  const menu=w.document.body.children.at(-1);
  assert.equal(parseFloat(menu.style.left),84);
  assert.equal(parseFloat(menu.style.top),342);
  app.listeners.keydown({key:'End',target:menu});
  app.listeners.keydown({key:'Enter',target:menu});
  assert.equal(w.twinState.filters.orders.status,'exception');
});

test('logical media breakpoints survive OS DPI changes and ignore invalid native size',()=>{
  const app=boot(),w=app.window;
  w.innerWidth=320;w.twinSetViewport(480,1016);
  assert.equal(w.document.documentElement.getAttribute('data-layout'),'');
  w.innerWidth=640;app.windowListeners.resize({});
  assert.equal(w.document.documentElement.getAttribute('data-layout'),'');
  const prior=JSON.stringify(w.TwinViewport.getState());
  w.twinSetViewport(0,NaN);
  assert.equal(JSON.stringify(w.TwinViewport.getState()),prior);
  w.twinSetViewport(380,600);
  assert.equal(w.document.documentElement.getAttribute('data-layout'),'compact short-rail');
});

test('diagnostics compare scroll widths in design units rather than CEF viewport pixels',()=>{
  const app=boot({search:'?diagnostics=1'}),w=app.window;
  w.innerWidth=320;w.innerHeight=678;w.twinSetViewport(480,1016);
  w.twinNavigate('inventory');app.flush();
  assert.equal(app.commands.filter(c=>c.action==='report').at(-1).overflow,false);
  w.document.documentElement.scrollWidth=482;
  w.twinNavigate('orders');app.flush();
  assert.equal(app.commands.filter(c=>c.action==='report').at(-1).overflow,true);
});
