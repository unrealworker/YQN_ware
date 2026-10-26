const task = await taskSpace(1);
const page = task.page('p1');
await page.goto('file:///D:/UEPro/Test/DesignPreviews/GHS_Address_Time/ghs-address-clock.html');
const result = await page.evaluate(async () => {
  const root = document.getElementById('ghs-address-clock');
  const firstTime = root.querySelector('.ghs-time').textContent;
  await new Promise(resolve=>setTimeout(resolve,1100));
  const secondTime = root.querySelector('.ghs-time').textContent;
  const image = root.querySelector('img');
  const checks = {
    clockTicks:firstTime!==secondTime,
    time:firstTime,
    nextTime:secondTime,
    date:root.querySelector('.ghs-date').textContent,
    sceneLoaded:image.complete && image.naturalWidth>0,
    address:root.querySelector('address').innerText,
    labels:[...root.querySelectorAll('.ghs-header div')].filter(e=>e.children.length===0).map(e=>({text:e.textContent.trim(),width:e.clientWidth,contentWidth:e.scrollWidth})),
    timezoneCases:['2026-07-22T15:00:00Z','2026-12-22T15:00:00Z','2026-10-22T01:00:00Z'].map(value=>({utc:value,local:new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',timeZoneName:'short',hourCycle:'h23'}).format(new Date(value))}))
  };
  return checks;
});
const fs = await import('node:fs/promises');
await fs.writeFile('D:/UEPro/Test/DesignPreviews/GHS_Address_Time/preview-check.json',JSON.stringify(result,null,2),'utf8');
console.log(result);
console.log(await page.snapshot());
