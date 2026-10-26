const task = await taskSpace(1);
const page = task.page('p1');
help('page.cdp');
help('task.cdp');
const shot = await page.cdp('Page.captureScreenshot',{format:'png',fromSurface:false,captureBeyondViewport:false});
const fs = await import('node:fs/promises');
await fs.writeFile('D:/UEPro/Test/DesignPreviews/GHS_Address_Time/preview-desktop.png',Buffer.from(shot.data,'base64'));
console.log('Screenshot saved');
