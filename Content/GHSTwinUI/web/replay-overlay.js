(function(){
'use strict';
const C=window.TwinReplayCore,$=id=>document.getElementById(id);
let state=C.normalizeState({active:false}),markers=[],markerKey='',controlKeys={};
let nativeWidth=null,layoutMoving=false,markerWidth=0,visibleWidth=0;
function dropdown(id,key,value,options,label){const signature=JSON.stringify([value,options]);if(controlKeys[id]===signature||window.TwinDropdown.isOpen())return;controlKeys[id]=signature;$(id).innerHTML=window.TwinDropdown.render(key,value,options);const b=$(id).querySelector('button');b.setAttribute('aria-label',label);}
function controls(){dropdown('replay-rate','replayRate',String(state.rate),[1,2,4,8,16,32,64].map(x=>[String(x),x+'×']),'播放倍率');dropdown('replay-trails','replayTrails',state.trailMode,[['all','全部叉车'],['selected','仅选中叉车'],['off','关闭路线']],'叉车剩余路线显示');dropdown('replay-follow','replayFollow',state.followId,[['','自由视角'],...state.devices.filter(d=>d.visible!==false||state.followId===d.id).map(d=>[d.id,d.id])],'跟随设备');}
function send(payload){const bridge=window.ue&&window.ue.twin;if(!bridge||typeof bridge.command!=='function')return false;try{const pending=bridge.command(JSON.stringify(payload));if(pending&&pending.catch)pending.catch(()=>{});return true;}catch(e){return false}}
const timeline=C.createTimeline(send,()=>state);
function current(){const time=timeline.time();$('replay-current').textContent=C.dateText(state.startUtc,time);$('replay-elapsed').textContent=C.durationText(time)+' / '+C.durationText(state.duration);const range=$('replay-seek');range.style.setProperty('--replay-progress',(state.duration?time/state.duration*100:0)+'%');range.setAttribute('aria-valuetext',C.dateText(state.startUtc,time));if(!timeline.isDragging())range.value=String(time);}
function renderMarkers(){
 // Percentage positions stretch with the card. Preserve event nodes and their
 // grouping while the drawer moves; recluster once at its final width.
 const width=layoutMoving&&markerWidth>0?markerWidth:($('replay-markers').clientWidth||1000);
 const key=JSON.stringify([state.duration,state.startUtc,state.markers,width]);if(key===markerKey)return;
 markerKey=key;markerWidth=width;markers=C.aggregateMarkers(state.markers,state.duration,width,80);
 const root=$('replay-markers');root.replaceChildren();markers.forEach((e,i)=>{const b=document.createElement('button');b.className='replay-marker '+e.type;b.dataset.marker=String(i);b.style.left=(state.duration?e.time/state.duration*100:0)+'%';b.title=C.dateText(state.startUtc,e.time)+' · '+e.title+(e.count>1?'（附近 '+e.count+' 个事件）':'');b.setAttribute('aria-label',b.title);root.appendChild(b);});
}
function layout(width,moving){
 if(!Number.isFinite(width)||width<=0)return;
 if(visibleWidth!==width&&window.TwinDropdown.isOpen())window.TwinDropdown.close(false);
 visibleWidth=width;
 layoutMoving=!!moving;
 // Native supplies its already-eased drawer edge. Do not resize the CEF root,
 // scale the text, or start a second CSS transition that would lag the panel.
 $('replay-transport').style.width=Math.max(0,width-8)+'px';
 document.documentElement.setAttribute('data-replay-condensed',width<=850?'true':'false');
 document.documentElement.setAttribute('data-replay-compact',width<=650?'true':'false');
 if(state.active||state.preparing)renderMarkers();
}
function viewportLayout(){
 if(nativeWidth===null)layout(window.TwinViewport?window.TwinViewport.getState().width:window.innerWidth,false);
 else if(state.active||state.preparing)renderMarkers();
}
window.twinReplayLayout=function(width,moving){
 if(!Number.isFinite(width)||width<=0)return;
 nativeWidth=width;layout(width,moving);
};
function receive(value){const next=C.normalizeState(value);if(!next)return;state=next;$('replay-transport').hidden=!state.active&&!state.preparing;if(!state.active&&!state.preparing){timeline.cancel();return;}
 $('replay-status').textContent=state.preparing?'准备中':state.completed?'回放完成':state.playing?'播放中':'已暂停';$('replay-play').textContent=state.completed?'从头回放':state.playing?'暂停':'播放';
 $('replay-seek').max=String(state.duration||1);$('replay-seek').disabled=!!state.preparing;$('replay-play').disabled=!!state.preparing;
 $('replay-start-label').textContent=C.dateText(state.startUtc)+' '+C.offsetLabel(state.startUtc).split(' ')[0];$('replay-end-label').textContent=C.dateText(state.endUtc)+' '+C.offsetLabel(state.endUtc).split(' ')[0];
 controls();current();renderMarkers();const blocked=state.preparing||state.exitPending;if(blocked){timeline.cancel();window.TwinDropdown.close(false);}document.querySelectorAll('#replay-transport button,#replay-transport input').forEach(el=>{el.disabled=!!blocked;});
}
document.addEventListener('click',e=>{const mark=e.target.closest('[data-marker]');if(mark){const item=markers[Number(mark.dataset.marker)];if(item)timeline.event(item);return;}const b=e.target.closest('[data-control]');if(!b||b.disabled)return;switch(b.dataset.control){case'play':if(state.completed){send({action:'replaySeek',time:0});send({action:'replayPlay'});}else send({action:state.playing?'replayPause':'replayPlay'});break;case'back':timeline.step(-30);break;case'forward':timeline.step(30);break;case'overview':send({action:'replayOverview'});break;}});
const slider=$('replay-seek');slider.addEventListener('pointerdown',()=>timeline.begin());slider.addEventListener('mousedown',()=>timeline.begin());slider.addEventListener('touchstart',()=>timeline.begin(),{passive:true});slider.addEventListener('input',()=>{timeline.preview(Number(slider.value));current()});slider.addEventListener('change',()=>{timeline.finish();current()});slider.addEventListener('blur',()=>timeline.finish());document.addEventListener('pointerup',()=>timeline.finish());document.addEventListener('mouseup',()=>timeline.finish());document.addEventListener('touchend',()=>timeline.finish());window.addEventListener('blur',()=>timeline.finish());
document.addEventListener('change',e=>{const action=e.target.dataset&&e.target.dataset.filter,key={replayRate:'rate',replayFollow:'id',replayTrails:'mode'}[action];if(key)send({action,[key]:key==='rate'?Number(e.target.value):e.target.value});});
document.addEventListener('twin-dropdown-close',()=>setTimeout(controls,0));
document.addEventListener('twin-viewport-change',viewportLayout);
window.TwinDropdown.setBoundsProvider(()=>({width:visibleWidth}));
viewportLayout();
window.twinReplayReceive=receive;window.twinReplayOverlay={getState:()=>state,markerCount:()=>markers.length};send({action:'replayReady'});
})();
