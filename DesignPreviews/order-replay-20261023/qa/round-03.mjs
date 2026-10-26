const task = await taskSpace(5);
const page = task.page('p1');
const win = await task.cdp('Browser.getWindowForTarget', {targetId:page.targetId});
console.log(win);
await task.cdp('Browser.setWindowBounds', {windowId:win.windowId,bounds:{windowState:'normal'}});
console.log({screenshot:await page.screenshot({path:'D:/UEPro/Test/DesignPreviews/order-replay-20261023/qa/01-query-1920.png'})});
await page.fill('#end-time','2026-10-22T08:30');
await page.click('loc=role:button[name="查询测试订单"]');
console.log(await page.snapshot());
