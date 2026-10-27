/* CEF starts with a 1x1 backing surface. Do not paint business content into
   that texture: Slate can stretch its single blue/white pixel over the panel. */
(function(){
'use strict';
const root=document.documentElement,callbacks=[];
let ready=false,presented=false,fontsReady=false,frame=0,previous='',stable=0;
let renderViewport=null,presentedViewport=null;
const nativeHost=()=>!!(window.ue&&window.ue.twin);
function geometry(){
  const design=window.TwinViewport&&window.TwinViewport.getState();
  return {width:window.innerWidth,height:window.innerHeight,designWidth:design?design.width:0,designHeight:design?design.height:0,
    native:!!(window.TwinViewport&&window.TwinViewport.hasNativeViewport())};
}
function valid(view){
  return [view.width,view.height,view.designWidth,view.designHeight].every(n=>Number.isFinite(n)&&n>=64)
    &&(!nativeHost()||view.native);
}
function cleanup(){
  window.removeEventListener('resize',schedule);
  document.removeEventListener('twin-viewport-change',schedule);
}
function tick(){
  frame=0;if(presented)return;
  const view=geometry(),key=JSON.stringify(view);
  if(!fontsReady||!valid(view)){stable=0;previous='';return;}
  stable=key===previous?stable+1:1;previous=key;
  if(stable<2){schedule();return;}
  if(!ready){
    ready=true;renderViewport=view;
    // Render at the final dimensions while hidden, then allow two layout/paint
    // opportunities for React/ECharts before exposing the browser's new frame.
    while(callbacks.length)callbacks.shift()();
    stable=0;previous='';schedule();return;
  }
  presented=true;presentedViewport=view;
  root.removeAttribute('data-ui-pending');cleanup();
  document.dispatchEvent(new Event('twin-ui-presented'));
}
function schedule(){if(!presented&&!frame)frame=requestAnimationFrame(tick);}
window.TwinStartup={
  get ready(){return ready;},get presented(){return presented;},
  whenReady(callback){if(ready)callback();else callbacks.push(callback);},
  diagnostics(){return{ready,presented,renderViewport,presentedViewport};}
};
window.addEventListener('resize',schedule);
document.addEventListener('twin-viewport-change',schedule);
root.setAttribute('data-ui-pending','');
// Explicitly request the CJK font: fonts.ready alone resolves before any text
// exists. Font failure may use the system fallback; a tiny viewport never may.
let fontTimer;
function finishFonts(){if(fontsReady)return;fontsReady=true;clearTimeout(fontTimer);schedule();}
if(document.fonts&&document.fonts.load){
  fontTimer=setTimeout(finishFonts,1500);
  document.fonts.load('14px GHSCJK','仓储数字孪生').then(finishFonts,finishFonts);
}else finishFonts();
schedule();
})();
