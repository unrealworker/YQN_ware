const task = await taskSpace(1);
const page = task.page('p1');
console.log(await page.cdp('Page.bringToFront'));
console.log(await page.evaluate(()=>({visibility:document.visibilityState,width:innerWidth,height:innerHeight})));
console.log(await task.cdp('Target.getTargets'));
