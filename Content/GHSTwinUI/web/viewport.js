/* Native Slate supplies design units. CEF supplies CSS pixels after Windows DPI.
   Keep typography, responsive breakpoints and fixed popups in one design space. */
(function(){
'use strict';
let logical=null,zoom=1;
function state(){return{width:logical?logical.width:window.innerWidth,height:logical?logical.height:window.innerHeight,zoom};}
function update(){
  if(!(window.innerWidth>0))return;
  const view=state(),width=view.width,height=view.height;
  zoom=logical?window.innerWidth/width:1;
  const root=document.documentElement;
  // UE 5.4's Chromium reports unscaled DOMRects for CSS zoom. A root transform
  // preserves measurable visual bounds and makes fixed children share this box.
  if(logical)Object.assign(root.style,{transform:'scale('+zoom+')',transformOrigin:'0 0',width:width+'px',height:height+'px'});
  // file:// stylesheets cannot be inspected through CSSOM in UE's CEF. Match
  // layout breakpoints from design dimensions explicitly; motion stays in CSS.
  const modes=[];
  if(width<=440)modes.push('compact');
  if(width<=359)modes.push('narrow');
  if(width>=640)modes.push('wide');
  if(width>=500&&height<=600)modes.push('short-wide');
  if(width>=450&&height<=600)modes.push('bottom-nav');
  if(width<=300)modes.push('tiny');
  if(width>=360&&height<=820)modes.push('short-rail');
  if(width<=359||width>=450&&height<=600)modes.push('horizontal-zoom');
  root.setAttribute('data-layout',modes.join(' '));
  if(window.TwinDropdown)window.TwinDropdown.close(false);
  document.dispatchEvent(new Event('twin-viewport-change'));
}
window.twinSetViewport=function(width,height){
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)return;
  if(logical&&logical.width===width&&logical.height===height&&zoom===window.innerWidth/width)return;
  logical={width,height};update();
};
window.TwinViewport={getState:state,toLayoutRect(rect){
  const result={};for(const key of ['left','top','right','bottom','width','height'])result[key]=rect[key]/zoom;
  return result;
}};
window.addEventListener('resize',update);
update();
})();
