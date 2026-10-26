const task = await taskSpace(1);
const page = task.page('p1');
console.log(await page.evaluate(()=>({width:innerWidth,frames:[...document.querySelectorAll('iframe')].map(f=>({sandbox:f.getAttribute('sandbox'),width:f.clientWidth,height:f.clientHeight})),overflow:document.documentElement.scrollWidth>innerWidth})));
console.log(await page.cdp('Page.getFrameTree'));
help('page.screenshot');
