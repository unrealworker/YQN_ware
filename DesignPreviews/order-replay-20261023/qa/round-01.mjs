const task = await taskSpace('GHS replay design 20261023');
const page = task.page('p1');
await page.goto('http://127.0.0.1:8770/');
console.log({spaceId:task.spaceId,page:page.label});
console.log(await page.snapshot());
