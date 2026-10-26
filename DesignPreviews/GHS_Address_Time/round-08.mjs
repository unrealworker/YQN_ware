const task = await taskSpace(1);
const page = task.page('p1');
const results = await page.evaluate(async()=>{
  const source = document.getElementById('ghs-address-clock').outerHTML;
  const checks=[];
  for (const width of [320,736,1024,1920]) {
    const frame=document.createElement('iframe');
    frame.style.width=width+'px';frame.style.height='1200px';frame.style.border='0';
    const loaded=new Promise(resolve=>frame.onload=resolve);
    frame.srcdoc='<style>body{margin:0}</style>'+source;
    document.body.append(frame);
    await loaded;
    const doc=frame.contentDocument;
    const root=doc.getElementById('ghs-address-clock');
    const clipped=[...root.querySelectorAll('.ghs-header *,.ghs-poi *,.ghs-selector *')].filter(e=>e.children.length===0 && e.textContent.trim()).filter(e=>e.scrollWidth>e.clientWidth+1 && getComputedStyle(e).display!=='inline').map(e=>e.textContent.trim());
    const rects=[...root.querySelector('.ghs-header').children].filter(e=>getComputedStyle(e).display!=='none').map(e=>e.getBoundingClientRect());
    const overlaps=rects.some((a,i)=>rects.slice(i+1).some(b=>a.left<b.right-1 && a.right>b.left+1 && a.top<b.bottom-1 && a.bottom>b.top+1));
    checks.push({width,documentWidth:doc.documentElement.scrollWidth,clipped,headerOverlaps:overlaps});
    frame.remove();
  }
  return checks;
});
const fs=await import('node:fs/promises');
await fs.writeFile('D:/UEPro/Test/DesignPreviews/GHS_Address_Time/layout-check.json',JSON.stringify(results,null,2),'utf8');
console.log(results);
await task.finish({keep:[]});
