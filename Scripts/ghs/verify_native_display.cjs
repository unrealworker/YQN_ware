// Validate the packaged application's embedded CEF, never a Pixel Streaming page.
// Launch the owned test EXE with -cefdebug=9341 (no resolution/window overrides).
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const output=path.resolve(__dirname,'../../Saved/NativeDisplayFix');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function main(){
  const targets=await(await fetch('http://127.0.0.1:9341/json')).json();
  const target=targets.find(t=>t.url.includes('/GHSTwinUI/web/index.html'));
  assert.ok(target,'Packaged embedded panel is available');
  const socket=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let id=0;
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data),p=pending.get(message.id);if(!p)return;pending.delete(message.id);clearTimeout(p.timer);message.error?p.reject(Error(JSON.stringify(message.error))):p.resolve(message.result);});
  function send(method,params={}){return new Promise((resolve,reject)=>{const serial=++id,timer=setTimeout(()=>{pending.delete(serial);reject(Error(method+' timeout'));},10000);pending.set(serial,{resolve,reject,timer});socket.send(JSON.stringify({id:serial,method,params}));});}
  async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
  async function click(selector){
    await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'nearest'})`);await pause(150);
    const xy=await evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2}})()`);
    for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,...xy});
    await pause(150);
  }
  const checks=[];
  try{
    if(process.argv.includes('--reload')){await send('Page.reload');await pause(1800);}
    const viewport=await evaluate(`({css:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio},design:TwinViewport.getState(),shell:(()=>{const r=document.getElementById('shell').getBoundingClientRect();return{width:r.width,height:r.height}})(),font:getComputedStyle(document.body).fontSize})`);
    console.log(JSON.stringify(viewport));
    const layout=await evaluate(`({nav:getComputedStyle(document.getElementById('navigation')).width,modes:document.documentElement.getAttribute('data-layout')})`);
    assert.equal(layout.nav,'56px');assert.equal(layout.modes,'');
    assert.ok(Math.abs(viewport.design.width-480)<.01);assert.ok(Math.abs(viewport.design.height-1136)<.01);
    assert.ok(Math.abs(viewport.shell.width-viewport.css.width)<2,'Panel fills actual CEF width');
    assert.ok(Math.abs(viewport.shell.height-viewport.css.height)<2,'Panel fills actual CEF height');
    checks.push({name:'2560x1600_scaled_panel',...viewport});console.log(JSON.stringify(checks.at(-1)));
    for(const [page,filter]of [['inventory','inventory.state'],['orders','orders.status'],['devices','devices.type'],['devices','devices.status'],['alerts','alerts.severity']]){
      await evaluate(`twinNavigate('${page}')`);await pause(450);
      await click(`[data-filter="${filter}"]`);
      const menu=await evaluate('({state:TwinDropdown.getState(),view:TwinViewport.getState(),width:innerWidth,height:innerHeight})');
      assert.ok(menu.state.open,filter+' pointer hit opens dropdown');
      const s=menu.state,gap=s.placement==='above'?s.anchor.top-s.menu.bottom:s.menu.top-s.anchor.bottom;
      assert.ok(Math.abs(gap-6*menu.view.zoom)<1.5,filter+' dropdown remains anchored');
      assert.ok(s.menu.left>=0&&s.menu.top>=0&&s.menu.right<=menu.width+1&&s.menu.bottom<=menu.height+1,filter+' menu fits viewport');
      checks.push({name:filter,gap,...menu});console.log(JSON.stringify(checks.at(-1)));
      for(const key of [{key:'End',windowsVirtualKeyCode:35},{key:'Enter',windowsVirtualKeyCode:13}])for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,...key});
      assert.equal(await evaluate('TwinDropdown.isOpen()'),false);
    }
    await evaluate(`window.ue.twin.command(JSON.stringify({action:'select',id:'FORK-07'}));void 0`);await pause(1300);
    const actions=await evaluate(`(()=>{const e=document.querySelector('.device-actions'),r=e&&e.getBoundingClientRect();return{width:innerWidth,height:innerHeight,actions:r&&{left:r.left,top:r.top,right:r.right,bottom:r.bottom}}})()`);
    assert.ok(actions.actions,'Device detail is open');
    assert.ok(actions.actions.left>=-1&&actions.actions.right<=actions.width+1&&actions.actions.bottom<=actions.height+1,'Fixed detail actions fit after zoom');
    checks.push({name:'detail_actions_visible',...actions});
    const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,'cef-detail.png'),Buffer.from(shot.data,'base64'));
    await evaluate(`window.ue.twin.command(JSON.stringify({action:'overview'}));twinNavigate('overview')`);
    fs.writeFileSync(path.join(output,'cef-report.json'),JSON.stringify({success:true,checks},null,2));
    console.log(JSON.stringify({success:true,checks:checks.length,output}));
  }finally{socket.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
