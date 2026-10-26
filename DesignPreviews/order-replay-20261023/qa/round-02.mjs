const task = await taskSpace(5);
const page = task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride', {width:1920,height:1080,deviceScaleFactor:1,mobile:false});
console.log(await page.evaluate(()=>({inputs:[...document.querySelectorAll('input')].map(el=>({id:el.id,type:el.type,value:el.value})),buttons:[...document.querySelectorAll('button')].map(el=>({id:el.id,text:el.textContent.trim(),page:el.dataset.page})),images:[...document.images].map(el=>({src:el.getAttribute('src'),complete:el.complete,width:el.naturalWidth})),size:[innerWidth,innerHeight,document.documentElement.scrollWidth,document.documentElement.scrollHeight]})));
console.log({screenshot:await page.screenshot({path:'D:/UEPro/Test/DesignPreviews/order-replay-20261023/qa/01-query-1920.png'})});
