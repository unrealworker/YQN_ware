const task = await taskSpace(1);
const page = task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride',{width:1024,height:650,deviceScaleFactor:1,mobile:false});
await page.screenshot({path:'D:/UEPro/Test/DesignPreviews/GHS_Address_Time/preview-1024.png'});
console.log(await page.cdp('Page.getFrameTree'));
console.log(await page.evaluate(()=>({width:innerWidth,frames:[...document.querySelectorAll('iframe')].map(f=>({sandbox:f.getAttribute('sandbox'),width:f.clientWidth,height:f.clientHeight})),overflow:document.documentElement.scrollWidth>innerWidth})));
