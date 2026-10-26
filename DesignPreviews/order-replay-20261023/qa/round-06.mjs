const task = await taskSpace(5);
const page = task.page('p1');
await page.fill('#end-time','2026-10-22T09:00');
await page.click('loc=role:button[name="查询测试订单"]');
await page.waitForSelector('text=TEST-OUT-001');
console.log(await page.snapshot());
console.log(await page.evaluate(()=>[...document.querySelectorAll('[data-order]')].map(x=>({order:x.dataset.order,text:x.textContent.trim()}))));
