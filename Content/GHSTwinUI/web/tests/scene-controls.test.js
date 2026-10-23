const test=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./harness');
function open(){const app=boot();app.window.twinNavigate('settings');app.flush();return app;}
test('scene settings start at 80/100 with four immediate layers and no apply button',()=>{
  const a=open(),s=a.window.twinState.settings;
  assert.equal(s.building,true);assert.equal(s.rackCapacity,.8);assert.equal(s.floorCapacity,1);
  assert.equal((a.html().match(/role="switch"/g)||[]).length,4);
  assert.ok(!a.html().includes('settings-apply'));assert.ok(a.html().includes('data-capacity="rackCapacity"'));
});
test('layer switch immediately sends its target and preserves hidden storage capacity',()=>{
 const a=open();a.window.twinState.settings.rackCapacity=.35;
 a.click({action:'toggle',key:'racks'});
 assert.equal(a.commands.filter(c=>c.action==='layers').at(-1).racks,false);
 assert.equal(a.window.twinState.settings.rackCapacity,.35);assert.ok(a.html().includes('disabled'));
});
test('slider coalesces rapid inputs and flushes final value without opening roof',()=>{
 const a=open();const input={dataset:{capacity:'rackCapacity'},value:'50',disabled:false,style:{setProperty(){}}};
 for(let i=0;i<100;i++){input.value=String(i);a.listeners.input({target:input});a.advance(1);}
 input.value='37';a.listeners.change({target:input});
 const sends=a.commands.filter(c=>c.action==='capacity');
 assert.ok(sends.length<=5);assert.equal(sends.at(-1).rack,.37);
 a.advance(100);assert.equal(a.commands.filter(c=>c.action==='capacity').at(-1).rack,.37);
 assert.ok(!a.commands.some(c=>c.action==='openWarehouse'));
});
test('restore defaults cancels a pending drag value and uses one reset action',()=>{
 const a=open();a.listeners.input({target:{dataset:{capacity:'floorCapacity'},value:'24',style:{setProperty(){}}}});
 a.click({action:'settings-reset'});a.advance(100);
 assert.equal(a.window.twinState.settings.floorCapacity,1);
 assert.equal(a.commands.filter(c=>['capacity','settingsReset'].includes(c.action)).at(-1).action,'settingsReset');
});
test('native state synchronizes auto-enabled layer and roof without refreshing business data',()=>{
 const a=open();a.window.twinSceneControls({building:true,racks:true,equipment:false,pois:false,density:'auto',rackCapacity:.4,floorCapacity:.6,roofClosed:false,roofOpening:false});
 assert.equal(a.window.twinState.settings.pois,false);assert.equal(a.window.twinState.settings.rackCapacity,.4);
 assert.ok(a.html().includes('屋顶已打开'));assert.ok(!a.html().includes('打开屋顶查看'));
});

test('roof completion during a drag appears when the drag ends even if final ack is unchanged',()=>{
 const a=open();a.window.twinSceneControls({roofClosed:false,roofOpening:true});
 const input={dataset:{capacity:'rackCapacity'},value:'45',style:{setProperty(){}}};
 a.listeners.input({target:input});
 a.window.twinSceneControls({roofClosed:false,roofOpening:false,rackCapacity:.45});
 assert.ok(a.html().includes('屋顶正在打开'));
 a.listeners.change({target:input});
 a.window.twinSceneControls({roofClosed:false,roofOpening:false,rackCapacity:.45});
 assert.ok(a.html().includes('屋顶已打开'));assert.ok(!a.html().includes('屋顶正在打开'));
});

test('reverse roof restoration remains closing until the native closed state arrives',()=>{
 const a=open();
 a.window.twinSceneControls({roofClosed:false,roofOpening:false,roofClosing:true});
 assert.equal(a.window.twinState.settings.roofClosing,true);
 assert.ok(a.html().includes('屋顶正在恢复'));
 assert.ok(!a.html().includes('屋顶已打开'));assert.ok(!a.html().includes('打开屋顶查看'));
 a.window.twinSceneControls({roofClosed:true,roofOpening:false,roofClosing:false});
 assert.ok(a.html().includes('屋顶已关闭'));assert.ok(a.html().includes('打开屋顶查看'));
 assert.ok(!a.html().includes('屋顶正在恢复'));
});

test('navigation reversing roof restoration shows opening and then fully open',()=>{
 const a=open();
 a.window.twinSceneControls({roofClosed:false,roofOpening:false,roofClosing:true});
 a.window.twinSceneControls({roofClosed:false,roofOpening:true,roofClosing:false});
 assert.ok(a.html().includes('屋顶正在打开'));assert.ok(!a.html().includes('屋顶正在恢复'));
 assert.ok(!a.html().includes('打开屋顶查看'));
 a.window.twinSceneControls({roofClosed:false,roofOpening:false,roofClosing:false});
 assert.ok(a.html().includes('屋顶已打开'));
});

test('roof restoration during a capacity drag renders the final closed state after release',()=>{
 const a=open();
 a.window.twinSceneControls({roofClosed:false,roofOpening:false,roofClosing:false});
 const input={dataset:{capacity:'floorCapacity'},value:'65',style:{setProperty(){}}};
 a.listeners.input({target:input});
 a.window.twinSceneControls({roofClosed:false,roofOpening:false,roofClosing:true});
 a.window.twinSceneControls({roofClosed:true,roofOpening:false,roofClosing:false});
 a.listeners.change({target:input});
 assert.ok(a.html().includes('屋顶已关闭'));assert.ok(a.html().includes('打开屋顶查看'));
 assert.equal(a.commands.filter(c=>c.action==='capacity').at(-1).floor,.65);
});

test('restoring display defaults preserves an in-progress roof restoration',()=>{
 const a=open();
 a.window.twinSceneControls({roofClosed:false,roofOpening:false,roofClosing:true});
 a.click({action:'settings-reset'});
 assert.equal(a.window.twinState.settings.roofClosing,true);
 assert.ok(a.html().includes('屋顶正在恢复'));assert.ok(!a.html().includes('屋顶已打开'));
 assert.equal(a.commands.at(-1).action,'settingsReset');
});
