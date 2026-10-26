const task = await taskSpace(5);
const page = task.page('p1');
await page.click('[data-order="TEST-OUT-001"]');
console.log(await page.snapshot());
console.log(await page.evaluate(()=>({buttons:[...document.querySelectorAll('button')].filter(x=>x.checkVisibility()).map(x=>({id:x.id,text:x.textContent.trim(),follow:x.dataset.follow})),ranges:[...document.querySelectorAll('input[type=range]')].map(x=>({id:x.id,min:x.min,max:x.max,value:x.value}))})));
