const task = await taskSpace(5);
const page = task.page('p1');
console.log(await page.evaluate(()=>[...document.querySelectorAll('[data-order]')].map(x=>({order:x.dataset.order,text:x.textContent.trim()}))));
console.log(await page.snapshot());
