// Exercise the real Chromium renderer embedded in an owned UE validation process.
// Start it with -game -RenderOffscreen -cefdebug=9337 before running this script.
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),output=path.join(root,'Saved/DropdownFix');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function main(){
  const targets=await (await fetch('http://127.0.0.1:9337/json')).json();
  const target=targets.find(t=>t.url.includes('/GHSTwinUI/web/index.html'));
  assert.ok(target,'Owned UE browser target must be loaded');
  const socket=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let serial=0;
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{const value=JSON.parse(event.data),request=pending.get(value.id);if(request){pending.delete(value.id);clearTimeout(request.timer);value.error?request.reject(new Error(JSON.stringify(value.error))):request.resolve(value.result);}});
  function send(method,params={}){return new Promise((resolve,reject)=>{const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method));},8000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});}
  async function evaluate(expression){const response=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(response.exceptionDetails)throw new Error(JSON.stringify(response.exceptionDetails));return response.result.value;}
  async function wait(expression){for(let n=0;n<60;n++){if(await evaluate(expression))return;await delay(100);}throw new Error('Condition timed out: '+expression);}
  async function click(selector){
    const point=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw new Error('Missing element');e.scrollIntoView({block:'nearest'});return true;})()`);
    await delay(120); // Flush the scroll event before opening; scroll intentionally closes menus.
    const rect=await evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2};})()`);
    await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...rect});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...rect});
    await delay(100);
  }
  async function key(key,code){await send('Input.dispatchKeyEvent',{type:'keyDown',key,windowsVirtualKeyCode:code});await send('Input.dispatchKeyEvent',{type:'keyUp',key,windowsVirtualKeyCode:code});}
  const results=[];
  async function geometry(label){
    const value=await evaluate('({state:TwinDropdown.getState(),width:innerWidth,height:innerHeight,dpr:devicePixelRatio})'),s=value.state;
    assert.ok(s.open,label+' menu must be open');
    const gap=s.placement==='above'?s.anchor.top-s.menu.bottom:s.menu.top-s.anchor.bottom;
    assert.ok(Math.abs(gap-6)<1.5,label+' menu must stay anchored');
    assert.ok(s.menu.left>=7&&s.menu.right<=value.width-7&&s.menu.top>=7&&s.menu.bottom<=value.height-7,label+' menu must remain within browser viewport');
    results.push({label,...value,gap});
  }
  try{
    await wait('!!window.TwinDropdown&&!!window.ue&&!!window.ue.twin');
    for(const [destination,filter] of [['inventory','inventory.state'],['orders','orders.status'],['devices','devices.type'],['devices','devices.status'],['alerts','alerts.severity']]){
      await evaluate(`twinNavigate(${JSON.stringify(destination)})`);await wait('!document.getElementById("main").hasAttribute("aria-busy")');
      const selector=`button[data-filter="${filter}"]`;
      await click(selector);await geometry('UE1080 '+filter);
      if(destination==='inventory'||destination==='orders'){
        const screenshot=await send('Page.captureScreenshot',{format:'png'});
        fs.writeFileSync(path.join(output,`cef-${destination}.png`),Buffer.from(screenshot.data,'base64'));
      }
      await key('Escape',27);assert.equal(await evaluate('TwinDropdown.isOpen()'),false);
      await click(selector);await key('End',35);await key('Enter',13);await delay(100);
      const selected=await evaluate(`(()=>{const b=document.querySelector(${JSON.stringify(selector)}),[scope,field]=b.dataset.filter.split('.'),v=JSON.parse(b.dataset.dropdownOptions).slice(-1)[0][0];return{expected:v,actual:twinState.filters[scope][field],closed:!TwinDropdown.isOpen()};})()`);
      assert.equal(selected.actual,selected.expected);assert.ok(selected.closed);
    }
    await evaluate("twinNavigate('inventory')");await wait('!document.getElementById("main").hasAttribute("aria-busy")');
    await click('button[data-filter="inventory.state"]');
    await evaluate('document.getElementById("main").scrollTop+=80');
    // 1080p may fit all inventory content. Explicitly test the scroll event too.
    await evaluate('document.getElementById("main").dispatchEvent(new Event("scroll"))');
    assert.equal(await evaluate('TwinDropdown.isOpen()'),false);
    await click('button[data-filter="inventory.state"]');await evaluate('twinSetVisibility(false)');
    assert.equal(await evaluate('TwinDropdown.isOpen()'),false);await evaluate('twinSetVisibility(true)');
    await click('button[data-filter="inventory.state"]');await evaluate("twinNavigate('orders')");
    assert.equal(await evaluate('TwinDropdown.isOpen()'),false);
    results.push({label:'UE scroll hidden and navigation close',passed:true});
    fs.writeFileSync(path.join(output,'cef-acceptance.json'),JSON.stringify({success:true,runtime:'UE 5.4 embedded CEF',target:target.url,results},null,2));
    console.log(JSON.stringify({success:true,checks:results.length,output}));
  }finally{socket.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
