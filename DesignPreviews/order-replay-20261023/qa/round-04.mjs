const task = await taskSpace(5);
const page = task.page('p1');
console.log(await page.info());
console.log(await page.cdp('Browser.getWindowForTarget', {}));
await page.cdp('Page.bringToFront', {});
console.log({screenshot:await page.screenshot({path:'D:/UEPro/Test/DesignPreviews/order-replay-20261023/qa/01-query-1920.png'})});
