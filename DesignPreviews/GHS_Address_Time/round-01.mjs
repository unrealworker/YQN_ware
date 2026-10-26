const task = await taskSpace('GHS address clock design');
console.log({spaceId:task.spaceId});
const page = task.page('p1');
await page.goto('file:///D:/UEPro/Test/DesignPreviews/GHS_Address_Time/preview-wrapper.html');
console.log(await page.snapshot());
