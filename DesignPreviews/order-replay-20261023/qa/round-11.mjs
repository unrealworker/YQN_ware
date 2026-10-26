const task = await taskSpace(5);
const page = task.page('p1');
await page.goto('http://127.0.0.1:8770/?state=paused&time=230');
await page.cdp('Emulation.setDeviceMetricsOverride',{width:1920,height:1080,deviceScaleFactor:1,mobile:false});
console.log({screenshot:await page.screenshot({path:'D:/UEPro/Test/DesignPreviews/order-replay-20261023/qa/02-replay-1920.png'})});
console.log(await page.evaluate(()=>({time:document.querySelector('#current-time').textContent,state:document.querySelector('#play-state').textContent,forklifts:document.querySelector('#forklift-list').textContent.trim(),trucks:document.querySelector('#truck-list').textContent.trim(),overflow:[innerWidth,document.documentElement.scrollWidth,innerHeight,document.documentElement.scrollHeight],visibleEvents:document.querySelectorAll('.event-marker').length})));
