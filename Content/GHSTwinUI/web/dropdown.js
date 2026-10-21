(function(){
'use strict';
// Keep filters in the browser's DOM. UE 5.4's native select popup crosses CEF
// and Slate coordinate spaces, which can disagree when the HUD has a DPI scaler.
const esc=value=>String(value==null?'':value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={'inventory.state':'货位状态','orders.status':'订单状态','devices.type':'设备类型','devices.status':'设备状态','alerts.severity':'告警级别'};
const menuId='twin-filter-listbox';
let anchor=null,menu=null,items=[],activeIndex=0,placement='below';

function render(key,value,options){
  const selected=options.find(item=>item[0]===value)||options[0],label=selected?selected[1]:'';
  return '<button type="button" class="filter-select" id="filter-'+esc(key.replace(/\./g,'-'))+'" data-filter="'+esc(key)+'" data-dropdown-options="'+esc(JSON.stringify(options))+'" value="'+esc(value)+'" aria-haspopup="listbox" aria-expanded="false" aria-label="'+esc((names[key]||'筛选')+'：'+label)+'"><span>'+esc(label)+'</span><svg class="filter-chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg></button>';
}

function position(rect,desired,viewport){
  const margin=8,gap=6,width=Math.min(Math.max(rect.width,desired.width),Math.max(1,viewport.width-margin*2));
  const below=Math.max(0,viewport.height-margin-rect.bottom-gap),above=Math.max(0,rect.top-margin-gap);
  const side=below>=desired.height||below>=above?'below':'above',available=side==='below'?below:above;
  const height=Math.min(desired.height,available);
  const left=Math.max(margin,Math.min(rect.left,viewport.width-margin-width));
  const top=side==='below'?rect.bottom+gap:rect.top-gap-height;
  return{left,top,width,height,maxHeight:available,side};
}

function close(restoreFocus=true){
  if(!menu)return;
  const previous=anchor,popup=menu;anchor=null;menu=null;items=[];
  previous.setAttribute('aria-expanded','false');previous.removeAttribute('aria-controls');
  popup.remove();
  if(restoreFocus&&previous.isConnected)previous.focus({preventScroll:true});
  // Chromium may remove a focused element without a focusout event. Let the
  // page consume any telemetry it deferred while this listbox owned focus.
  document.dispatchEvent(new Event('twin-dropdown-close'));
}

function highlight(index){
  if(!menu)return;
  activeIndex=Math.max(0,Math.min(items.length-1,index));
  menu.querySelectorAll('[data-dropdown-index]').forEach((option,i)=>option.classList.toggle('is-active',i===activeIndex));
  const active=menu.querySelector('[data-dropdown-index="'+activeIndex+'"]');
  menu.setAttribute('aria-activedescendant',active.id);active.scrollIntoView({block:'nearest'});
}

function open(button,index){
  if(button.disabled||button.closest('[aria-busy="true"]'))return;
  close(false);
  let options;try{options=JSON.parse(button.dataset.dropdownOptions);}catch(e){return;}
  if(!Array.isArray(options)||!options.length)return;
  const rect=button.getBoundingClientRect(),viewport={width:window.innerWidth,height:window.innerHeight};
  if(rect.bottom<=0||rect.top>=viewport.height||rect.right<=0||rect.left>=viewport.width)return;
  anchor=button;items=options;
  menu=document.createElement('div');menu.id=menuId;menu.className='filter-listbox';menu.tabIndex=-1;
  menu.setAttribute('role','listbox');menu.setAttribute('aria-label',names[button.dataset.filter]||'筛选选项');
  menu.innerHTML=options.map(([value,label],i)=>'<div id="'+menuId+'-'+i+'" class="filter-option" role="option" aria-selected="'+(String(value)===button.value)+'" data-dropdown-index="'+i+'"><span>'+esc(label)+'</span><svg class="filter-check" viewBox="0 0 16 16" aria-hidden="true"><path d="m3 8 3 3 7-7"/></svg></div>').join('');
  menu.style.visibility='hidden';menu.style.maxWidth=Math.max(1,viewport.width-16)+'px';
  document.body.appendChild(menu);
  const bounds=position(rect,{width:menu.offsetWidth,height:menu.scrollHeight+2},viewport);
  // No physical-pixel or devicePixelRatio conversion: both rect and fixed CSS
  // positions use the same viewport, including while the native drawer moves.
  Object.assign(menu.style,{left:bounds.left+'px',top:bounds.top+'px',width:bounds.width+'px',maxHeight:bounds.maxHeight+'px',visibility:'visible'});
  placement=bounds.side;menu.dataset.placement=placement;
  button.setAttribute('aria-expanded','true');button.setAttribute('aria-controls',menuId);
  menu.focus({preventScroll:true});
  highlight(index==null?Math.max(0,options.findIndex(item=>String(item[0])===button.value)):index);
}

function choose(index){
  if(!menu||!items[index])return;
  const trigger=anchor,value=String(items[index][0]),changed=trigger.value!==value;
  trigger.value=value;close(true);
  // Preserve the page controller's existing data-filter/change contract.
  if(changed)trigger.dispatchEvent(new Event('change',{bubbles:true}));
}

function triggerFor(target){
  const button=target&&target.closest?target.closest('[data-dropdown-options]'):null;
  return button&&button.dataset&&button.dataset.dropdownOptions?button:null;
}

document.addEventListener('click',event=>{
  const button=triggerFor(event.target);
  if(button){if(anchor===button)close();else open(button);return;}
  const option=event.target&&event.target.closest?event.target.closest('[data-dropdown-index]'):null;
  if(menu&&option&&menu.contains(option)){choose(Number(option.dataset.dropdownIndex));return;}
  close(false);
});
document.addEventListener('pointerdown',event=>{if(menu&&!menu.contains(event.target)&&!anchor.contains(event.target))close(false);});
document.addEventListener('focusin',event=>{if(menu&&!menu.contains(event.target)&&event.target!==anchor)close(false);});
document.addEventListener('keydown',event=>{
  const button=triggerFor(event.target);
  if(!menu){
    if(button&&['ArrowDown','ArrowUp','Enter',' '].includes(event.key)){
      event.preventDefault();open(button,event.key==='ArrowUp'?JSON.parse(button.dataset.dropdownOptions).length-1:undefined);
    }
    return;
  }
  if(event.key==='Tab'){close(true);return;}
  if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();close(true);return;}
  if(['ArrowDown','ArrowUp','Home','End','Enter',' '].includes(event.key)){
    event.preventDefault();event.stopPropagation();
    if(event.key==='Enter'||event.key===' ')choose(activeIndex);
    else highlight(event.key==='Home'?0:event.key==='End'?items.length-1:activeIndex+(event.key==='ArrowDown'?1:-1));
  }
});
// A scroll or resize invalidates the anchor geometry. Close on that event only;
// no per-frame measurements, polling, or background layout work is needed.
document.addEventListener('scroll',event=>{if(menu&&!menu.contains(event.target))close(false);},true);
window.addEventListener('resize',()=>close(false));
window.addEventListener('blur',()=>close(false));

window.TwinDropdown={render,close,isOpen:()=>!!menu,getAnchor:()=>anchor,
  getState(){return menu?{open:true,filter:anchor.dataset.filter,value:anchor.value,activeValue:items[activeIndex][0],placement,anchor:rectOf(anchor),menu:rectOf(menu)}:{open:false};}
};
function rectOf(element){const r=element.getBoundingClientRect();return{left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};}
})();
