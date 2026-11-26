(function(){
'use strict';
const $=id=>document.getElementById(id),stage=$('stage');
let motionMode='normal';try{motionMode=GlobePolicy.motionPreference(localStorage.getItem('ghs-globe-motion'));}catch(e){}
let state={phase:'idle',stageVisible:true,selectedId:'',warehouses:[],pois:[],countries:[],transition:{opacity:0}},catalogKey='',selectedKey='',lastPhase='',pointer=null,dx=0,dy=0,dragFrame=0,ready=false;
let warehouseById=new Map();
let clusterIds=null,pageOffset=0,markerKey=null,markerGroups=new Map();
const markerNodes=new Map();
let markerViewport='';
let selectionSource=null,pendingFocus=null,focusFrame=0,interactionActive=false,windowFocused=true;
let curtainFrame=0,curtainAck=null;
let bootFrame=0,entryGate='idle';
const motionTracks=new WeakMap(),activeMotion=new Set();
const detailTracks=new Map();let thumbnailGeneration=0,thumbnailOutgoing=null,thumbnailLoadTimer=0,detailNeedsRefresh=false;
const countryPriority=new Map(['美国','加拿大','墨西哥','巴西','智利','阿根廷','秘鲁','哥伦比亚','委内瑞拉','中国','澳大利亚','印度','俄罗斯','南非'].map((id,index)=>[id,index]));
let countryVisible=new Set();
let recent=[];try{recent=JSON.parse(localStorage.getItem('ghs-globe-recent')||'[]');if(!Array.isArray(recent))recent=[];}catch(e){}
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon=name=>'<svg aria-hidden="true"><use href="#'+name+'"/></svg>';
function bridge(){return window.ue&&window.ue.twin;}
function command(action,params){const target=bridge();if(target&&target.command)target.command(JSON.stringify(Object.assign({action},params||{})));}
function reducedMotion(){return motionMode==='reduced';}
function inputSource(event){return event&&event.isTrusted===true?(event.detail>0?'pointer':'keyboard'):'unknown';}
function stopDetailFade(el){const animation=detailTracks.get(el);if(animation){detailTracks.delete(el);animation.cancel();}}
function detailFade(el,from,to,duration,finish){
 stopDetailFade(el);el.style.opacity=String(to);
 if(!el.animate){if(finish)finish();return;}
 const easing=getComputedStyle(document.body).getPropertyValue('--ease-standard').trim();
 const animation=el.animate([{opacity:from},{opacity:to}],{duration,easing,fill:'both'});detailTracks.set(el,animation);
 animation.onfinish=()=>{if(detailTracks.get(el)!==animation)return;detailTracks.delete(el);animation.cancel();if(finish)finish();};
}
function clearDetailFades(){
 for(const [el,animation] of detailTracks){animation.cancel();el.style.opacity='1';}detailTracks.clear();
 if(thumbnailOutgoing){thumbnailOutgoing.remove();thumbnailOutgoing=null;}
}
function cancelDetail(){++thumbnailGeneration;clearTimeout(thumbnailLoadTimer);thumbnailLoadTimer=0;clearDetailFades();}
function thumbnailSnapshot(){
 const thumbnail=$('thumbnail'),width=thumbnail.clientWidth,height=thumbnail.clientHeight;
 if(!width||!height||(!thumbnail.naturalWidth&&!thumbnailOutgoing))return null;
 // Flatten the current two-layer picture before retargeting. No pixel readback:
 // a rapid A→B→A change keeps its actual blend, with at most one outgoing layer.
 const canvas=document.createElement('canvas'),ratio=devicePixelRatio||1;canvas.width=Math.ceil(width*ratio);canvas.height=Math.ceil(height*ratio);
 const context=canvas.getContext('2d');if(!context)return null;context.scale(ratio,ratio);
 context.fillStyle=getComputedStyle(thumbnail.parentElement).backgroundColor;context.fillRect(0,0,width,height);
 if(thumbnail.complete&&thumbnail.naturalWidth){const scale=Math.max(width/thumbnail.naturalWidth,height/thumbnail.naturalHeight),w=thumbnail.naturalWidth*scale,h=thumbnail.naturalHeight*scale;context.globalAlpha=Number(getComputedStyle(thumbnail).opacity);context.drawImage(thumbnail,(width-w)/2,(height-h)/2,w,h);}
 if(thumbnailOutgoing){context.globalAlpha=Number(getComputedStyle(thumbnailOutgoing).opacity);context.drawImage(thumbnailOutgoing,0,0,width,height);}
 canvas.className='thumbnail-outgoing';canvas.setAttribute('aria-hidden','true');canvas.style.transform=getComputedStyle(thumbnail).transform;return canvas;
}
function updateDetail(w,animate){
 const thumbnail=$('thumbnail'),duration=reducedMotion()?120:180,oldPicture=animate?thumbnailSnapshot():null;
 const textStarts=['city','address'].map(id=>detailTracks.has($(id))?Number(getComputedStyle($(id)).opacity):0);
 cancelDetail();detailNeedsRefresh=false;const generation=thumbnailGeneration;
 $('name').textContent=w.name;$('city').textContent=w.city;$('address').textContent=w.address;
 $('breadcrumb').textContent='全球 / '+GlobePolicy.warehouseRegion(w)+' / '+(w.country||'未标注国家');
 thumbnail.alt=w.name+'三维场景预览';thumbnail.style.opacity=oldPicture?'0':'1';
 if(oldPicture){thumbnailOutgoing=oldPicture;thumbnail.parentElement.appendChild(oldPicture);}
 const source=w.thumbnail||'assets/warehouse-overview.png';
 const load=(url,fallback=false)=>{
  const image=new Image();
  let settled=false;
  const failed=()=>{if(settled||generation!==thumbnailGeneration)return;settled=true;clearTimeout(thumbnailLoadTimer);if(!fallback)load('assets/warehouse-overview.png',true);else{clearDetailFades();thumbnail.style.opacity='0';}};
  image.onload=()=>{if(settled||generation!==thumbnailGeneration)return;settled=true;clearTimeout(thumbnailLoadTimer);thumbnailLoadTimer=0;thumbnail.src=url;thumbnail.style.opacity='1';if(oldPicture&&thumbnailOutgoing===oldPicture)detailFade(oldPicture,1,0,duration,()=>{oldPicture.remove();if(thumbnailOutgoing===oldPicture)thumbnailOutgoing=null;});else if(animate)detailFade(thumbnail,0,1,duration);};
  image.onerror=failed;
  thumbnailLoadTimer=setTimeout(failed,5000);
  image.src=url;
 };
 // Keep the currently visible picture until the replacement is ready. A late
 // request cannot replace a newer warehouse, and image loading never gates entry.
 load(source);
 if(animate)['city','address'].forEach((id,index)=>detailFade($(id),textStarts[index],1,duration));
}
function playMotion(el,frames,options={}){if(!el||!el.animate||reducedMotion())return;const old=motionTracks.get(el);if(old)old.cancel();const animation=el.animate(frames,{duration:280,easing:'cubic-bezier(.22,1,.36,1)',fill:'backwards',...options});motionTracks.set(el,animation);activeMotion.add(animation);const done=()=>{activeMotion.delete(animation);if(motionTracks.get(el)===animation)motionTracks.delete(el);};animation.onfinish=done;animation.oncancel=done;}
function revealChildren(root,selector,delay=35){Array.from(root.querySelectorAll(selector)).forEach((el,index)=>playMotion(el,[{opacity:0,transform:'translateY(8px)'},{opacity:1,transform:'translateY(0)'}],{duration:320,delay:Math.min(index,6)*delay}));}
function bootMotion(){if(document.body.dataset.ready==='true'||bootFrame)return;bootFrame=requestAnimationFrame(()=>{bootFrame=requestAnimationFrame(()=>{bootFrame=0;document.body.dataset.ready='true';});});}
function renderEntryLabel(value){const label=$('enter').querySelector('.button-label');if(label.dataset.value===value)return;label.dataset.value=value;label.textContent='';Array.from(value).forEach((letter,index)=>{const glyph=document.createElement('span');glyph.textContent=letter;label.appendChild(glyph);playMotion(glyph,[{opacity:0,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:200,delay:index*18});});$('enter').setAttribute('aria-label',value);}
function focusToken(node){if(!node)return null;const scope=['pois','warehouse-list','recent-list'].find(id=>$(id).contains(node));return {node,scope,id:node.id,select:node.dataset.select,enter:node.dataset.enter,cluster:node.dataset.cluster,members:node.dataset.cluster?(markerGroups.get(node.dataset.cluster)||[]).slice():[]};}
function canFocus(node){return node&&node.isConnected&&!node.disabled&&!node.closest('[inert]')&&node.getClientRects().length>0;}
function findFocus(token){if(!token)return null;if(canFocus(token.node))return token.node;const root=$(token.scope)||document;let node=Array.from(root.querySelectorAll('button')).find(el=>(token.select&&el.dataset.select===token.select)||(token.enter&&el.dataset.enter===token.enter)||(token.cluster&&el.dataset.cluster===token.cluster)||(token.id&&el.id===token.id));if(canFocus(node))return node;if(token.scope==='pois'){const ids=new Set(token.members.length?token.members:[token.select||token.enter]);for(const [id,members] of markerGroups){if(!members.some(member=>ids.has(member)))continue;const marker=$('poi-'+id);node=marker&&marker.querySelector('button');if(canFocus(node))return node;}}const id=token.select||token.enter;return id?Array.from($('warehouse-list').querySelectorAll('[data-select]')).find(el=>el.dataset.select===id&&canFocus(el)):null;}
function focusElement(node){if(!canFocus(node))return false;node.focus({preventScroll:true});return document.activeElement===node;}
function syncInteraction(force=false){const active=!!pointer||(windowFocused&&$('pois').contains(document.activeElement));if(force||active!==interactionActive){interactionActive=active;command('interaction',{active});}}
function restoreFocus(token,fallback){if(!focusElement(findFocus(token)))focusElement(fallback||stage);syncInteraction();}
function queueFocus(){if(!pendingFocus||focusFrame)return;focusFrame=requestAnimationFrame(()=>{focusFrame=0;if(!pendingFocus)return;const intent=pendingFocus,phase=state.phase,settled=['idle','selected','error'].includes(phase);if(intent.type==='back'){if(phase!=='warehouse')return;pendingFocus=null;focusElement($('back'));}else if(intent.type==='detail'){if(!settled||state.selectedId!==intent.id)return;pendingFocus=null;focusElement($('name'));}else{if(!settled||state.selectedId)return;pendingFocus=null;if(intent.type==='list')focusElement($('warehouse-list').querySelector('[data-select]')||$('search'));else if(intent.type==='stage')focusElement(stage);else restoreFocus(selectionSource,stage);}syncInteraction();});}
function select(id,source,event){entryGate=GlobePolicy.entryRequestState(entryGate,'cancel');selectionSource=focusToken(source||document.activeElement);pendingFocus={type:'detail',id};command('select',{id,inputSource:inputSource(event)});}
function enter(id,source,event){if(!id||entryGate!=='idle'||!['idle','selected','error'].includes(state.phase))return;entryGate=GlobePolicy.entryRequestState(entryGate,'request');if(source&&source.closest('#pois'))selectionSource=focusToken(source);pendingFocus={type:'back'};command('enter',{id,inputSource:inputSource(event)});}
function clearSelection(returnToStage=false){if(state.phase==='warehouse'||['flying','revealing','returning'].includes(state.phase))return;entryGate=GlobePolicy.entryRequestState(entryGate,'cancel');pendingFocus={type:returnToStage===true?'stage':'source'};command('clear');queueFocus();}
function queueCurtain(){const t=state.transition;if(curtainFrame||!t||!t.awaitingCurtain||!(Number(t.opacity)>=1)||curtainAck===t.generation)return;const generation=t.generation;curtainFrame=requestAnimationFrame(()=>{curtainFrame=requestAnimationFrame(()=>{curtainFrame=0;const latest=state.transition;if(!latest||!latest.awaitingCurtain||latest.generation!==generation||!(Number(latest.opacity)>=1)||!Number.isFinite(latest.width)||!Number.isFinite(latest.height)||latest.width<=0||latest.height<=0||Math.abs(innerWidth-latest.width)>1||Math.abs(innerHeight-latest.height)>1)return;curtainAck=generation;command('curtainReady',{generation,width:innerWidth,height:innerHeight});});});}
function row(w){return '<button class="warehouse-row" data-select="'+esc(w.id)+'"><span class="warehouse-icon">'+icon('warehouse')+'</span><span class="row-copy"><strong>'+esc(w.name)+'</strong><small>'+esc(w.cityShort||w.city)+'</small></span>'+icon('chevron')+'</button>';}
function list(){const active=$('warehouse-list').contains(document.activeElement)?focusToken(document.activeElement):null,result=GlobePolicy.page(state.warehouses,{query:$('search').value,region:$('region').value,ids:clusterIds,offset:pageOffset,limit:40});$('warehouse-list').innerHTML=(clusterIds?'<button class="clear-cluster" id="clear-cluster">显示全部仓库</button>':'')+(result.rows.map(row).join('')||'<p class="list-hint">没有找到匹配的仓库</p>')+(pageOffset>0?'<button class="warehouse-row" id="previous-results">上一页</button>':'')+(result.total>pageOffset+40?'<button class="warehouse-row" id="more-results">下一页 · 还有'+(result.total-pageOffset-40)+'座</button>':'');$('count').textContent=state.warehouses.length;revealChildren($('warehouse-list'),'.warehouse-row,.list-hint',24);if(active)restoreFocus(active,$('warehouse-list').querySelector('[data-select]')||$('search'));}

function updateRecent(){const active=$('recent-list').contains(document.activeElement)?focusToken(document.activeElement):null,rows=recent.map(id=>warehouseById.get(id)).filter(Boolean);$('recent-list').innerHTML=rows.map(row).join('');$('recent-empty').hidden=rows.length>0;if(active)restoreFocus(active,$('name'));}
function panel(active){for(const [id,on] of [['initial',!active],['detail',active]]){const el=$(id),opening=on&&el.dataset.active!=='true';el.dataset.active=String(on);el.setAttribute('aria-hidden',String(!on));if(on)el.removeAttribute('inert');else el.setAttribute('inert','');for(const node of el.querySelectorAll('button,input,select'))node.tabIndex=on?0:-1;if(opening)revealChildren(el,id==='detail'?'.breadcrumb,.photo-wrap,.card-title,.metrics,.primary,.recent':'.list-section',35);}}
function layoutCountries(labels,origin){
 const measured=labels.map(({c,el})=>({...c,width:el.offsetWidth,height:el.offsetHeight}));
 measured.sort((a,b)=>(countryPriority.get(a.id)??100)-(countryPriority.get(b.id)??100)||String(a.id).localeCompare(String(b.id)));
 const nextVisible=new Set(GlobePolicy.countryLabels(measured,origin,countryVisible).map(c=>c.id));
 for(const {c,el} of labels){
  const visible=nextVisible.has(c.id),continuous=visible&&countryVisible.has(c.id);
  el.style.transition=continuous&&!reducedMotion()?'transform 60ms linear':'none';
  el.style.transform='translate3d('+(c.x-origin.left)+'px,'+(c.y-origin.top)+'px,0) translate(-50%,-50%)';
  el.style.visibility=visible?'visible':'hidden';
 }
 countryVisible=nextVisible;
}
function markerContent(p){
 if(p.ids.length>1)return '<button class="cluster-dot" data-cluster="'+esc(p.id)+'" aria-label="查看此区域'+p.ids.length+'座仓库">'+p.ids.length+'</button>';
 // Browser preview fallback; the live globe renders the complete POI in native Slate.
 const w=warehouseById.get(p.id);return w?'<div class="poi-card"><button class="poi-select" data-select="'+esc(w.id)+'" aria-label="选择'+esc(w.name)+'"><span class="warehouse-icon">'+icon('warehouse')+'</span><span class="row-copy"><strong>'+esc(w.name)+'</strong></span></button><button class="poi-enter" data-enter="'+esc(w.id)+'" aria-label="进入'+esc(w.name)+'">'+icon('chevron')+'</button></div>':'';
}
function positionLabels(){if(state.phase==='warehouse'){markerViewport='';return;}const origin=stage.getBoundingClientRect();const markers=state.nativeWarehouseAnnotations?[]:GlobePolicy.markers(state.pois||[],state.selectedId,origin,64,48),key=markers.map(p=>p.id+':'+p.ids.join(',')).join('|');
 const viewportKey=[origin.left,origin.top,origin.width,origin.height].join(','),sameViewport=viewportKey===markerViewport;
 markerViewport=viewportKey;
 if(key!==markerKey){
  const active=$('pois').contains(document.activeElement)?focusToken(document.activeElement):null;markerKey=key;markerGroups=new Map(markers.map(p=>[p.id,p.ids]));
  // Keep surviving anchors (and their in-flight transforms/focus) when another POI is culled or clustered.
  for(const [id,entry] of markerNodes)if(!markerGroups.has(id)){entry.node.remove();markerNodes.delete(id);}
  for(const p of markers){
   let entry=markerNodes.get(p.id);const fresh=!entry,content=markerContent(p);
   if(fresh){const node=document.createElement('div');node.className='poi';node.id='poi-'+p.id;entry={node,content:null};markerNodes.set(p.id,entry);$('pois').appendChild(node);}
   if(entry.content!==content){entry.node.innerHTML=content;entry.content=content;}
   if(fresh)playMotion(entry.node.querySelector('.poi-card,.cluster-dot'),[{opacity:0,transform:'translateY(6px) scale(.98)'},{opacity:1,transform:'translateY(0) scale(1)'}],{duration:220});
  }
  if(active)restoreFocus(active,stage);
 }
 for(const p of markers){const node=markerNodes.get(p.id)?.node;if(node){
  // Native projection arrives at 20 Hz. Interpolate only continuous visible anchors,
  // on their own layer; never let the reduced-motion wildcard extend tracking to 120 ms.
  const continuous=sameViewport&&!!node.style.transform&&state.stageVisible&&!reducedMotion();
  node.style.setProperty('transition',continuous?'transform 60ms linear':'none','important');
  node.style.transform='translate3d('+(p.x-origin.left)+'px,'+(p.y-origin.top)+'px,0)';node.dataset.selected=String(state.selectedId===p.id);
 }}

 const countryRoot=$('countries'),labels=[],seen=new Set();for(const c of state.nativeCountryLabels?[]:(state.countries||[])){const id='country-'+c.id;seen.add(id);let el=document.getElementById(id);if(!el){el=document.createElement('span');el.id=id;el.className='country';el.style.left='0';el.style.top='0';countryRoot.appendChild(el);}if(el.textContent!==c.label)el.textContent=c.label;labels.push({c,el});}
 for(const el of Array.from(countryRoot.children))if(!seen.has(el.id))el.remove();layoutCountries(labels,origin);
}
function receive(next){const candidate=GlobePolicy.nextState(state,next);if(!candidate)return;const catalogUpdated=candidate.warehouses!==state.warehouses;state=candidate;
 const key=catalogUpdated?JSON.stringify(state.warehouses):catalogKey,catalogChanged=key!==catalogKey;if(catalogChanged){const previousRegion=$('region').value;pageOffset=0;catalogKey=key;warehouseById=new Map(state.warehouses.map(w=>[w.id,w]));$('region').innerHTML='<option value="">全部区域</option>'+Array.from(new Set(state.warehouses.map(GlobePolicy.warehouseRegion))).map(r=>'<option>'+esc(r)+'</option>').join('');if(Array.from($('region').options).some(o=>o.value===previousRegion))$('region').value=previousRegion;markerKey=null;list();updateRecent();}
 const w=warehouseById.get(state.selectedId);if((state.selectedId||'')!==selectedKey||catalogChanged){const losingFocus=$(w?'initial':'detail').contains(document.activeElement),switching=!!w&&!!warehouseById.get(selectedKey)&&selectedKey!==w.id&&$('detail').dataset.active==='true'&&state.stageVisible&&['selected','idle','error'].includes(state.phase)&&state.selectionInputSource==='pointer';selectedKey=state.selectedId||'';panel(!!w);if(w)updateDetail(w,switching);else cancelDetail();if(losingFocus&&!pendingFocus)pendingFocus=w?{type:'detail',id:w.id}:{type:'source'};}
 if(w){$('inventory').textContent=typeof w.inventory==='number'?w.inventory.toLocaleString('en-US'):'—';$('occupancy').textContent=typeof w.occupancy==='number'?(w.occupancy*100).toFixed(1)+'%':'—';}
 const phase=state.phase||'idle',busy=['loading','flying','revealing'].includes(phase);entryGate=GlobePolicy.entryRequestState(entryGate,phase);document.body.dataset.phase=phase;document.body.dataset.world=state.stageVisible===false?'warehouse':'globe';document.body.dataset.exiting=String(['flying','revealing','warehouse'].includes(phase));$('enter').disabled=false;$('enter').setAttribute('aria-disabled',String(busy));$('enter').setAttribute('aria-busy',String(busy));if(phase==='error'&&pendingFocus&&pendingFocus.type==='back')pendingFocus=w?{type:'detail',id:w.id}:{type:'source'};if(phase==='warehouse'&&state.error&&pendingFocus)pendingFocus={type:'back'};renderEntryLabel(busy?'正在进入':'进入仓库');
 const sceneHidden=state.stageVisible===false||['flying','revealing','returning','warehouse'].includes(phase);for(const el of [stage,document.querySelector('.sidebar')]){if(sceneHidden)el.setAttribute('inert','');else el.removeAttribute('inert');el.setAttribute('aria-hidden',String(sceneHidden));}
 if(sceneHidden&&!detailNeedsRefresh){cancelDetail();detailNeedsRefresh=true;}else if(!sceneHidden&&detailNeedsRefresh&&w)updateDetail(w,false);
 const transition=$('transition'),notice=GlobePolicy.transitionNotice(phase,state.transition,state.error),transitionActive=notice.active,transitionError=notice.error,transitionText=notice.text;transition.dataset.waiting=String(notice.waiting);transition.setAttribute('aria-hidden',String(!transitionActive));transition.dataset.error=String(!!transitionError);transition.setAttribute('role',transitionError?'alert':'status');transition.setAttribute('aria-live',transitionError?'assertive':'polite');transition.setAttribute('aria-atomic','true');if(transition.querySelector('span').textContent!==transitionText)transition.querySelector('span').textContent=transitionText;if(phase!==lastPhase&&['flying','returning'].includes(phase))focusElement(transition);
 $('error').textContent=state.error||'';$('back').textContent='← 返回运营中心';$('back').title=state.error?'返回运营中心失败：'+state.error+'。点击重试':'返回运营中心';$('back').setAttribute('aria-label',state.error?'返回运营中心失败：'+state.error+'。点击重试':'返回运营中心');const opacity=state.transition?Number(state.transition.opacity)||0:0;$('transition').style.opacity=Math.max(0,Math.min(1,opacity));$('transition').style.pointerEvents=opacity>.05?'auto':'none';queueCurtain();
 if(phase==='warehouse'&&lastPhase!=='warehouse'&&state.selectedId){recent=[state.selectedId,...recent.filter(id=>id!==state.selectedId)].slice(0,5);try{localStorage.setItem('ghs-globe-recent',JSON.stringify(recent));}catch(e){}updateRecent();}
 if(phase!==lastPhase){if(phase!=='warehouse')requestAnimationFrame(viewport);if(['idle','selected','error'].includes(phase))syncInteraction(true);}lastPhase=phase;positionLabels();queueFocus();bootMotion();
}
function viewport(){if(state.phase==='warehouse')return;const width=innerWidth,height=innerHeight,u=Math.max(.65,Math.min(width/1672,height/941));document.body.style.setProperty('--u',u);document.body.style.setProperty('--header',(54*u)+'px');document.body.style.setProperty('--sidebar',(width<700?Math.max(245,width*.42):440*u)+'px');const r=stage.getBoundingClientRect();command('viewport',{width,height,sceneX:r.left,sceneY:r.top,sceneWidth:r.width,sceneHeight:r.height});positionLabels();}
document.addEventListener('click',e=>{if(e.target.closest('#previous-results')){pageOffset=Math.max(0,pageOffset-40);list();return;}if(e.target.closest('#more-results')){pageOffset+=40;list();return;}if(e.target.closest('#clear-cluster')){clusterIds=null;pageOffset=0;list();return;}const cluster=e.target.closest('[data-cluster]');if(cluster){clusterIds=markerGroups.get(cluster.dataset.cluster)||null;pageOffset=0;entryGate=GlobePolicy.entryRequestState(entryGate,'cancel');pendingFocus={type:'list'};command('clear');panel(false);list();queueFocus();return;}const entry=e.target.closest('[data-enter]');if(entry){enter(entry.dataset.enter,entry,e);return;}const choice=e.target.closest('[data-select]');if(choice){if(choice.classList.contains('poi-select')&&state.selectedId===choice.dataset.select)enter(choice.dataset.select,choice,e);else select(choice.dataset.select,choice,e);return;}const control=e.target.closest('[data-command]');if(control){const action=control.dataset.command;if(action==='fullscreen'){if(['idle','selected','error'].includes(state.phase))command('fullscreen');}else{if(action==='home'){entryGate=GlobePolicy.entryRequestState(entryGate,'cancel');playMotion(control.querySelector('svg,span'),[{transform:'rotate(-50deg)',opacity:.5},{transform:'rotate(0)',opacity:1}],{duration:380});}command(action,action==='zoom'?{steps:Number(control.dataset.steps)}:{});}}});
$('search').addEventListener('input',()=>{$('search').closest('.search').dataset.filled=String(!!$('search').value);pageOffset=0;list();});$('region').addEventListener('change',()=>{pageOffset=0;list();});$('clear').addEventListener('click',clearSelection);$('enter').addEventListener('click',e=>enter(state.selectedId,null,e));$('back').addEventListener('click',e=>{pendingFocus={type:'detail',id:state.selectedId};command('back',{inputSource:inputSource(e)});});
document.addEventListener('focusin',()=>syncInteraction());document.addEventListener('focusout',()=>Promise.resolve().then(()=>syncInteraction()));
function flushDrag(){dragFrame=0;if(dx||dy){command('orbit',{dx,dy});dx=dy=0;}}
function blankSceneTarget(target){return !!target&&stage.contains(target)&&!target.closest('.poi,.map-controls,button,input,select,a');}
function trackDrag(e){if(!pointer||pointer.id!==e.pointerId)return;pointer.gesture=GlobePolicy.moveSceneGesture(pointer.gesture,e.clientX,e.clientY);dx+=pointer.gesture.dx;dy+=pointer.gesture.dy;stage.classList.toggle('dragging',pointer.gesture.dragging);if((dx||dy)&&!dragFrame)dragFrame=requestAnimationFrame(flushDrag);}
function endDrag(e){if(!pointer)return;if(e&&e.pointerId!==undefined&&e.pointerId!==pointer.id)return;const released=!!e&&e.type==='pointerup';if(released)trackDrag(e);const finished=pointer;pointer=null;if(dragFrame)cancelAnimationFrame(dragFrame);dragFrame=0;flushDrag();try{stage.releasePointerCapture(finished.id);}catch(error){}stage.classList.remove('dragging');syncInteraction();if(GlobePolicy.isBlankSceneClick(finished.gesture,{cancelled:!released,blank:released&&blankSceneTarget(document.elementFromPoint(e.clientX,e.clientY)),selectedId:state.selectedId,phase:state.phase}))clearSelection(true);}
stage.addEventListener('pointerdown',e=>{if(e.button!==0||pointer||!blankSceneTarget(e.target)||!['idle','selected','error'].includes(state.phase))return;pointer={id:e.pointerId,gesture:GlobePolicy.beginSceneGesture(e.clientX,e.clientY,state.selectedId)};stage.setPointerCapture(e.pointerId);focusElement(stage);syncInteraction();e.preventDefault();});
stage.addEventListener('pointermove',trackDrag);stage.addEventListener('pointerup',endDrag);stage.addEventListener('pointercancel',endDrag);stage.addEventListener('lostpointercapture',endDrag);window.addEventListener('blur',()=>{windowFocused=false;endDrag();syncInteraction();});window.addEventListener('focus',()=>{windowFocused=true;syncInteraction();});stage.addEventListener('contextmenu',e=>e.preventDefault());
stage.addEventListener('wheel',e=>{if(e.target.closest('button')||!['idle','selected','error'].includes(state.phase))return;e.preventDefault();command('zoom',{steps:Math.max(-3,Math.min(3,-e.deltaY/(e.deltaMode===1?3:120)))});},{passive:false});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&state.selectedId){clearSelection();e.preventDefault();return;}if(e.target.matches('input,select'))return;if(e.target===stage){const delta={ArrowLeft:[-30,0],ArrowRight:[30,0],ArrowUp:[0,-30],ArrowDown:[0,30]}[e.key];if(delta){command('orbit',{dx:delta[0],dy:delta[1]});e.preventDefault();}if(e.key==='+'||e.key==='=')command('zoom',{steps:1});if(e.key==='-')command('zoom',{steps:-1});}});
function motionChanged(){const limited=reducedMotion();document.body.dataset.reduced=String(limited);if(limited)for(const animation of activeMotion)animation.cancel();command('reducedMotion',{enabled:limited});}
function setMotionPreference(value){motionMode=GlobePolicy.motionPreference(value);try{localStorage.setItem('ghs-globe-motion',motionMode);}catch(e){}motionChanged();}
const beijingClock=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',weekday:'long',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
function clock(){const parts=Object.fromEntries(beijingClock.formatToParts(new Date()).map(part=>[part.type,part.value]));$('clock').textContent='北京时间 '+parts.hour+':'+parts.minute;$('date').textContent=parts.year+'.'+parts.month+'.'+parts.day+' · '+parts.weekday;}clock();setInterval(clock,1000);
function showCluster(payload){const ids=payload&&payload.ids;if(!Array.isArray(ids))return;clusterIds=ids.filter(id=>warehouseById.has(id));if(!clusterIds.length){clusterIds=null;return;}pageOffset=0;entryGate=GlobePolicy.entryRequestState(entryGate,'cancel');pendingFocus={type:'list'};panel(false);list();queueFocus();}
window.ghsGlobe={receive,setMotionPreference,showCluster};window.addEventListener('resize',()=>{curtainAck=null;viewport();queueCurtain();});viewport();panel(false);motionChanged();
const handshake=setInterval(()=>{if(!bridge())return;if(!ready){ready=true;command('ready');viewport();motionChanged();syncInteraction(true);}if(bridge().getstate)Promise.resolve(bridge().getstate()).then(receive).catch(()=>{});clearInterval(handshake);},100);
})();
