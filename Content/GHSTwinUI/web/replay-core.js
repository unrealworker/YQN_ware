(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.TwinReplayCore=factory();})(typeof window!=='undefined'?window:this,function(){
'use strict';
const zone='America/Los_Angeles';
const formatter=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
const pad=n=>String(n).padStart(2,'0');
function parts(ms){const p={};formatter.formatToParts(new Date(ms)).forEach(x=>{if(x.type!=='literal')p[x.type]=x.value});if(p.hour==='24')p.hour='00';return p;}
function localText(ms){const p=parts(ms);return p.year+'-'+p.month+'-'+p.day+'T'+p.hour+':'+p.minute+':'+p.second;}
function localCandidates(value){
 const m=String(value||'').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/);if(!m)return[];
 const values=m.slice(1).map(Number);values[5]=values[5]||0;
 const [year,month,day,hour,minute,second]=values;
 const date=new Date(0);date.setUTCFullYear(year,month-1,day);date.setUTCHours(hour,minute,second,0);
 if(year<1||year>9999||date.getUTCFullYear()!==year||date.getUTCMonth()!==month-1||date.getUTCDate()!==day||date.getUTCHours()!==hour||date.getUTCMinutes()!==minute||date.getUTCSeconds()!==second)return[];
 const key=year+'-'+pad(month)+'-'+pad(day)+'T'+pad(hour)+':'+pad(minute)+':'+pad(second);
 return [{name:'PDT',minutes:-420},{name:'PST',minutes:-480}].map(o=>{const ms=date.getTime()-o.minutes*60000;return{...o,ms,utc:new Date(ms).toISOString(),label:o.name+' (UTC'+(o.minutes===-420?'-07:00':'-08:00')+')'}}).filter(o=>localText(o.ms)===key).sort((a,b)=>a.ms-b.ms);
}
function resolve(value,offset){const choices=localCandidates(value);if(!choices.length)return{error:'时间无效，或处于夏令时跳过的时段。',choices};if(choices.length>1&&!choices.some(x=>x.name===offset))return{error:'这个时间出现两次，请选择 PDT 或 PST。',choices};return{choice:choices.find(x=>x.name===offset)||choices[0],choices};}
function validateRange(start,end,startOffset,endOffset){
 const a=resolve(start,startOffset),b=resolve(end,endOffset);const errors={};if(a.error)errors.start=a.error;if(b.error)errors.end=b.error;
 if(a.error||b.error)return{ok:false,errors,startChoices:a.choices,endChoices:b.choices};
 const duration=(b.choice.ms-a.choice.ms)/1000;
 if(duration<3600)errors.end=duration<=0?'结束时间必须晚于开始时间。':'请选择至少 1 小时（3600 秒）的时间段。';
 return{ok:!Object.keys(errors).length,errors,duration,startUtc:a.choice.utc,endUtc:b.choice.utc,startOffset:a.choice.name,endOffset:b.choice.name,startChoices:a.choices,endChoices:b.choices};
}
function defaultRange(now=Date.now()){const end=Math.floor(now/60000)*60000;return{start:localText(end-3600000),end:localText(end),startOffset:localCandidates(localText(end-3600000)).find(c=>c.ms===end-3600000).name,endOffset:localCandidates(localText(end)).find(c=>c.ms===end).name};}
function orders(){return[1,2,3,4].map(i=>({id:'TEST-OUT-00'+i,isTest:true}));}
function durationText(seconds){const s=Math.max(0,Math.floor(Number(seconds)||0)),h=Math.floor(s/3600);return pad(h)+':'+pad(Math.floor(s%3600/60))+':'+pad(s%60);}
function dateText(utc,time=0,full=true){const ms=Date.parse(utc)+time*1000;if(!Number.isFinite(ms))return'—';const p=parts(ms);return(full?p.year+'-'+p.month+'-'+p.day+' ':'')+p.hour+':'+p.minute+':'+p.second;}
function offsetLabel(utc){const ms=Date.parse(utc);if(!Number.isFinite(ms))return'';const match=localCandidates(localText(ms)).find(c=>Math.abs(c.ms-ms)<1000);return match?match.label:zone;}
function createLeaveGuard(send,isActive){
 let serial=0,pending=null,exitPending=false;
 return{request(title,run){if(!isActive()){run();return false}if(pending)return true;const token='replay-leave-'+Date.now()+'-'+(++serial);pending={token,run};send({action:'replayLeave',token,title});return true;},continue(token){if(!pending||pending.token!==token)return false;const run=pending.run;pending=null;run();return true;},cancel(){pending=null;exitPending=false;},receive(s){if(exitPending&&!s.exitPending&&s.active)pending=null;exitPending=!!s.exitPending;},hasPending(){return!!pending}};
}
function createTimeline(send,getState){
 let drag=null;
 const limit=t=>Math.max(0,Math.min(Number(getState().duration)||0,Number(t)||0));
 return{begin(){if(drag||!getState().active||getState().preparing||getState().exitPending)return;drag={time:getState().time||0,resume:!!getState().playing};if(drag.resume)send({action:'replayPause'});},preview(t){if(!drag)this.begin();if(drag)drag.time=limit(t);return drag?drag.time:limit(t);},finish(){if(!drag)return false;const d=drag;drag=null;send({action:'replaySeek',time:d.time});if(d.resume&&d.time<getState().duration)send({action:'replayPlay'});return true;},cancel(){drag=null;},isDragging(){return!!drag},time(){return drag?drag.time:getState().time||0;},event(e){send({action:'replayPause'});send({action:'replaySeek',time:limit(e.time)});if(e.deviceId)send({action:'replaySelect',id:e.deviceId});if(e.count>1&&Number.isFinite(e.rangeStart)&&Number.isFinite(e.rangeEnd))send({action:'replayEvents',start:limit(e.rangeStart),end:limit(e.rangeEnd)});},step(seconds){send({action:'replaySeek',time:limit((getState().time||0)+seconds)});}};
}
function aggregateMarkers(events,duration,width=1000,max=80){
 const groups=new Map(),buckets=Math.max(1,Math.min(max,Math.floor(width/12))),priority={fault:4,failure:4,warning:3,wait:3,recovered:2,recovery:2};
 for(const e of events||[]){if(!Number.isFinite(e.time)||e.time<0||e.time>duration)continue;const slot=Math.min(buckets-1,Math.floor(e.time/Math.max(1,duration)*buckets)),count=Number.isFinite(e.count)&&e.count>0?e.count:1,start=Number.isFinite(e.rangeStart)?e.rangeStart:e.time,end=Number.isFinite(e.rangeEnd)?e.rangeEnd:e.time;let g=groups.get(slot);if(!g){g={...e,count,rangeStart:start,rangeEnd:end};groups.set(slot,g);continue;}const merged={count:g.count+count,rangeStart:Math.min(g.rangeStart,start),rangeEnd:Math.max(g.rangeEnd,end)};if((priority[e.type]||1)>(priority[g.type]||1))Object.assign(g,e);Object.assign(g,merged);}
 return Array.from(groups.values()).sort((a,b)=>a.time-b.time);
}
function normalizeState(input){let s=input;if(typeof s==='string'){try{s=JSON.parse(s)}catch(e){return null}}if(!s||typeof s!=='object')return null;return{...s,active:!!s.active,preparing:!!s.preparing,playing:!!s.playing,completed:!!s.completed,duration:Math.max(0,Number(s.duration)||0),time:Math.max(0,Math.min(Number(s.duration)||0,Number(s.time)||0)),rate:[1,2,4,8,16,32,64].includes(s.rate)?s.rate:1,devices:Array.isArray(s.devices)?s.devices.slice(0,16):[],events:Array.isArray(s.events)?s.events.slice(0,100):[],markers:Array.isArray(s.markers)?s.markers.slice(0,240):[],trailMode:['all','selected','off'].includes(s.trailMode)?s.trailMode:'all',followId:s.followId||'',selectedId:s.selectedId||'',isTest:true};}
return{zone,parts,localText,localCandidates,resolve,validateRange,defaultRange,orders,durationText,dateText,offsetLabel,createLeaveGuard,createTimeline,aggregateMarkers,normalizeState};
});
