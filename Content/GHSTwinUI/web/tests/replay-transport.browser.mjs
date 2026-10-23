// Run through ego-browser nodejs; exports a real-browser layout regression check.
// The fixture is native replay state, not a replacement renderer.
export async function inspectTransport(page,width,screenshotPath){
 await page.goto('file:///D:/UEPro/Test/Content/GHSTwinUI/web/replay-overlay.html');
 await page.waitForFunction(()=>typeof window.twinReplayReceive==='function');
 await page.cdp('Emulation.setDeviceMetricsOverride',{width,height:168,deviceScaleFactor:1,mobile:false});
 await page.evaluate(()=>{
  window.__replayQaCommands=[];
  window.ue={twin:{command:value=>window.__replayQaCommands.push(JSON.parse(value))}};
  window.twinReplayReceive({active:true,playing:true,time:230,duration:3600,rate:1,
   startUtc:'2026-10-23T16:00:00.000Z',endUtc:'2026-10-23T17:00:00.000Z',
   orderId:'TEST-OUT-001',followId:'REPLAY-FORK-01',trailMode:'selected',
   devices:[...Array.from({length:5},(_,i)=>({id:'REPLAY-FORK-0'+(i+1),type:'forklift',visible:true})),
    ...['A','B','C'].map(id=>({id:'REPLAY-TRUCK-'+id,type:'truck',visible:true}))],events:[],markers:[]});
 });
 const result=await page.evaluate(()=>{
  const controls=[...document.querySelectorAll('.replay-transport-controls button')].map(n=>{
   const r=n.getBoundingClientRect();return {label:n.getAttribute('aria-label')||n.textContent.trim(),
    x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height,
    clipped:r.x<0||r.y<0||r.right>innerWidth||r.bottom>innerHeight||r.width<20||r.height<20};
  });
  const top=document.querySelector('.replay-transport-top');
  return{width:innerWidth,height:innerHeight,controls,topOverflow:top.scrollWidth>top.clientWidth,
   allVisible:controls.length===7&&controls.every(c=>!c.clipped),controlRows:new Set(controls.map(c=>Math.round(c.y))).size};
 });
 if(screenshotPath)await page.screenshot({path:screenshotPath});
 return result;
}

export async function exerciseTransport(page){
 for(const label of ['播放倍率','跟随设备','叉车轨迹显示']){
  await page.click('loc=css:button[aria-label="'+label+'"]');
  await page.keyboard.press('End');
  await page.keyboard.press('Enter');
 }
 await page.click('loc=css:#replay-play');
 const commands=await page.evaluate(()=>window.__replayQaCommands);
 const expected=[{action:'replayRate',rate:64},{action:'replayFollow',id:'REPLAY-TRUCK-C'},
  {action:'replayTrails',mode:'off'},{action:'replayPause'}];
 for(const item of expected)if(!commands.some(c=>JSON.stringify(c)===JSON.stringify(item)))throw Error('Missing command '+JSON.stringify(item));
 return commands;
}
