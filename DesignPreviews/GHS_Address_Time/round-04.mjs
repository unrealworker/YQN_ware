const task = await taskSpace(1);
const page = task.page('p1');
await page.screenshot({path:'D:/UEPro/Test/DesignPreviews/GHS_Address_Time/preview-desktop.png',raw:true});
console.log('Screenshot saved');
