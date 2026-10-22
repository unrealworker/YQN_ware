const test=require('node:test');
const assert=require('node:assert/strict');
const {boot:bootController}=require('./harness');
// These existing tests exercise scene browsing; verified ledger defaults have their own suite.
function boot(options){const app=bootController(options);app.window.twinState.filters.devices.view='scene';return app;}

test('all business filters render in the page instead of CEF native popup controls',()=>{
  const app=boot();
  for(const [page,keys]of [['inventory',[]],['orders',['orders.status']],['devices',['devices.type','devices.status']],['alerts',['alerts.severity']]]){
    app.window.twinNavigate(page);
    assert.doesNotMatch(app.html(),/<select\b/i,page+' must not invoke the mismatched native popup coordinate path');
    for(const key of keys)assert.match(app.html(),new RegExp('<button[^>]+data-filter="'+key.replace('.', '\\.')+'"[^>]+aria-haspopup="listbox"'),key);
  }
  app.window.twinNavigate('settings');assert.match(app.html(),/role="tab"[^>]+data-key="settings.density"/);
});

function control(app,key,rect={left:84,top:460,right:214,bottom:496,width:130,height:36}){
  const button=app.elements.page.querySelector('[data-filter="'+key+'"]');assert.ok(button,key);button.rect=rect;return button;
}
function open(app,key,rect){const button=control(app,key,rect);app.listeners.click({target:button});return button;}
function press(app,key){return app.listeners.keydown({key,target:app.window.document.activeElement});}

test('popup stays anchored in CSS pixels at every device scale and flips inside the viewport',()=>{
  const app=boot();assert.ok(app.window.TwinDropdown,'DOM dropdown controller must be present');
  app.window.twinNavigate('orders');
  for(const ratio of [1,1.25,1.5,2]){
    app.window.devicePixelRatio=ratio;open(app,'orders.status');const state=app.window.TwinDropdown.getState();
    assert.equal(state.menu.left,84);assert.equal(state.menu.top,502);assert.ok(state.menu.bottom<=1016);
    app.window.TwinDropdown.close();
  }
  open(app,'orders.status',{left:390,top:950,right:480,bottom:986,width:90,height:36});
  let state=app.window.TwinDropdown.getState();assert.equal(state.placement,'above');assert.equal(state.menu.bottom,944);assert.ok(state.menu.right<=472);
  app.window.TwinDropdown.close();app.window.innerWidth=240;app.window.innerHeight=160;
  app.window.document.documentElement.clientWidth=240;app.window.document.documentElement.clientHeight=160;
  open(app,'orders.status',{left:8,top:60,right:232,bottom:96,width:224,height:36});
  state=app.window.TwinDropdown.getState();assert.ok(state.menu.top>=8&&state.menu.bottom<=152);assert.ok(state.menu.left>=8&&state.menu.right<=232);
});

test('order pointer and keyboard choice use the existing filter change path',()=>{
  const app=boot();assert.ok(app.window.TwinDropdown);app.window.twinNavigate('orders');app.elements.main.scrollTop=210;
  let button=open(app,'orders.status');
  assert.equal(button.getAttribute('aria-expanded'),'true');
  const menu=app.window.document.body.children.at(-1),option=menu.querySelector('[data-dropdown-index="2"]');
  app.listeners.click({target:option});
  assert.equal(app.window.twinState.filters.orders.status,'executing');assert.equal(app.elements.main.scrollTop,210);
  assert.equal(app.window.TwinDropdown.isOpen(),false);assert.equal(app.window.document.activeElement.dataset.filter,'orders.status');
  assert.ok(app.html().includes('装车中'));
  app.window.twinNavigate('orders');app.window.twinState.filters.orders.page=3;
  button=control(app,'orders.status');button.focus();press(app,' ');press(app,'End');press(app,'Enter');
  assert.equal(app.window.twinState.filters.orders.status,'exception');assert.equal(app.window.twinState.filters.orders.page,1);
  assert.equal(app.window.TwinDropdown.isOpen(),false);
  open(app,'orders.status');assert.equal(app.window.TwinDropdown.getState().activeValue,'exception');
  assert.match(app.window.document.body.children.at(-1).innerHTML,/aria-selected="true"[^>]*data-dropdown-index="4"/);
});

test('Escape cancels without filtering and Tab continues from the trigger',()=>{
  const app=boot();assert.ok(app.window.TwinDropdown);app.window.twinNavigate('orders');
  const button=open(app,'orders.status');press(app,'ArrowDown');assert.equal(app.window.TwinDropdown.getState().activeValue,'completed');
  const escape=press(app,'Escape');assert.equal(escape.defaultPrevented,true);assert.equal(app.window.twinState.filters.orders.status,'all');assert.equal(app.window.document.activeElement,button);
  open(app,'orders.status');press(app,'End');press(app,'Home');assert.equal(app.window.TwinDropdown.getState().activeValue,'all');
  const tab=press(app,'Tab');assert.notEqual(tab.defaultPrevented,true);assert.equal(app.window.TwinDropdown.isOpen(),false);assert.equal(app.window.document.activeElement,button);
});

test('outside clicks scroll resize navigation and hidden panels cannot leave an orphan menu',()=>{
  const app=boot({reducedMotion:false});assert.ok(app.window.TwinDropdown);app.window.twinNavigate('orders');app.flush();
  const closeActions=[()=>app.listeners.click({target:app.window.document.body}),()=>app.listeners.scroll({target:app.elements.main}),()=>app.windowListeners.resize({}),()=>app.window.twinNavigate('inventory'),()=>app.window.twinSetVisibility(false)];
  for(const action of closeActions){app.window.twinSetVisibility(true);app.window.twinNavigate('orders');app.flush();open(app,'orders.status');action();assert.equal(app.window.TwinDropdown.isOpen(),false);}
});

test('telemetry preserves an open dropdown and flushes once after focus leaves',()=>{
  const app=boot();assert.ok(app.window.TwinDropdown);app.window.twinNavigate('devices');app.window.twinSetDiagnostics(false);
  const before=app.window.twinGetPerformance().htmlBuilds;open(app,'devices.status');
  app.window.twinReceive({equipment:[{id:'AGV-07',type:'agv',status:'running',value:'47%'}],facilities:[]});
  assert.equal(app.window.twinGetPerformance().htmlBuilds,before);assert.equal(app.window.TwinDropdown.isOpen(),true);
  app.window.TwinDropdown.close();app.window.document.activeElement=null;app.listeners.focusout({});app.flush();
  assert.equal(app.window.twinGetPerformance().htmlBuilds,before+1);assert.ok(app.html().includes('47%'));
});

test('closing after a queued snapshot flushes even when removing a focused popup emits no focusout',()=>{
  const app=boot();assert.ok(app.window.TwinDropdown);app.window.twinNavigate('devices');app.window.twinSetDiagnostics(false);
  const before=app.window.twinGetPerformance().htmlBuilds;open(app,'devices.status');
  app.window.twinReceive({equipment:[{id:'AGV-07',type:'agv',status:'running',value:'63%'}],facilities:[]});
  const menu=app.window.document.body.children.at(-1);
  menu.remove=()=>{menu.isConnected=false;app.window.document.body.children=app.window.document.body.children.filter(c=>c!==menu);app.window.document.activeElement=app.window.document.body;};
  app.listeners.scroll({target:app.elements.main});app.flush();
  assert.equal(app.window.TwinDropdown.isOpen(),false);assert.equal(app.window.twinGetPerformance().htmlBuilds,before+1);assert.ok(app.html().includes('63%'));
});
