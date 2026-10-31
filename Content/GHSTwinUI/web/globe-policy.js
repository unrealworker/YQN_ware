(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.GlobePolicy=api;})(typeof globalThis==='object'?globalThis:this,function(){
'use strict';
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const optional=(value,key,check)=>!Object.prototype.hasOwnProperty.call(value,key)||check(value[key]);
const string=value=>typeof value==='string';
const finite=value=>typeof value==='number'&&Number.isFinite(value);
const identity=value=>string(value)&&value.length>0;
const boolean=value=>typeof value==='boolean';
function catalogValid(rows){
 if(!Array.isArray(rows)||rows.length>2000)return false;const ids=new Set();
 for(const w of rows){if(!object(w)||!identity(w.id)||!identity(w.name)||ids.has(w.id))return false;ids.add(w.id);
  for(const field of ['city','cityShort','address','thumbnail','region','country','map','runtimeProfile'])if(!optional(w,field,string))return false;
  for(const field of ['inventory','occupancy'])if(!optional(w,field,value=>value===null||finite(value)))return false;
 }return true;
}
function projectionsValid(rows,countries=false){
 if(!Array.isArray(rows)||rows.length>2000)return false;const ids=new Set();
 return rows.every(p=>{if(!object(p)||!identity(p.id)||ids.has(p.id)||!finite(p.x)||!finite(p.y)||!boolean(p.visible))return false;ids.add(p.id);return countries?string(p.label):optional(p,'ids',members=>Array.isArray(members)&&members.length>0&&members.length<=2000&&members.every(identity));});
}
function nextState(previous,message){
 if(typeof message==='string'){try{message=JSON.parse(message);}catch(e){return null;}}
 if(!object(message))return null;const candidate={...previous,...message};
 // Previous is an accepted state (or the trusted local initial state). Revalidate only a transmitted catalog.
 if(!['idle','selected','loading','flying','revealing','warehouse','returning','error'].includes(candidate.phase)||!string(candidate.selectedId)||!boolean(candidate.stageVisible)
  ||!optional(message,'warehouses',catalogValid)||!projectionsValid(candidate.pois)||!projectionsValid(candidate.countries,true)||!optional(candidate,'error',string)||!optional(candidate,'reducedMotion',boolean))return null;
 const transition=candidate.transition;
 if(!object(transition)||!finite(transition.opacity)||transition.opacity<0||transition.opacity>1||!optional(transition,'progress',finite)||!optional(transition,'generation',value=>Number.isSafeInteger(value)&&value>=0)||!optional(transition,'awaitingCurtain',boolean))return null;
 for(const key of ['width','height'])if(!optional(transition,key,value=>finite(value)&&value>=0))return null;
 if(transition.awaitingCurtain&&(!Number.isSafeInteger(transition.generation)||!(transition.width>0)||!(transition.height>0)))return null;
 if(!optional(candidate,'viewport',value=>object(value)&&finite(value.width)&&value.width>0&&finite(value.height)&&value.height>0))return null;
 return candidate;
}
function warehouseRegion(w){return typeof w.region==='string'&&w.region.trim()?w.region.trim():'未分区';}
// Budgets are independent of catalog size: thousands of sites never become thousands of moving DOM nodes.
function markers(pois,selectedId,rect,cellSize=64,maxMarkers=48){
 const buckets=new Map(),selected=[];
 for(const p of pois){if(!p.visible||!Number.isFinite(p.x)||!Number.isFinite(p.y)||p.x<rect.left||p.x>rect.right||p.y<rect.top||p.y>rect.bottom)continue;
  if(p.id===selectedId){selected.push({...p,ids:[p.id]});continue;}
  const key=Math.floor((p.x-rect.left)/cellSize)+':'+Math.floor((p.y-rect.top)/cellSize);let b=buckets.get(key);if(!b){b={id:'cluster-'+key,x:0,y:0,ids:[],visible:true,n:0};buckets.set(key,b);}const members=p.ids||[p.id];b.x+=p.x*members.length;b.y+=p.y*members.length;b.n+=members.length;b.ids.push(...members);
 }
 const result=Array.from(buckets.values()).map(b=>({...b,id:b.ids.length===1?b.ids[0]:b.id,x:b.x/b.n,y:b.y/b.n}));
 if(result.length+selected.length>maxMarkers&&cellSize<Math.max(rect.right-rect.left,rect.bottom-rect.top)*2)return markers(pois,selectedId,rect,cellSize*1.5,maxMarkers);
 result.sort((a,b)=>b.ids.length-a.ids.length||a.id.localeCompare(b.id));
 return selected.concat(result);
}
function page(warehouses,{query='',region='',ids=null,offset=0,limit=40}={}){const q=query.trim().toLocaleLowerCase(),allowed=ids?new Set(ids):null;const matches=warehouses.filter(w=>(!allowed||allowed.has(w.id))&&(!region||warehouseRegion(w)===region)&&(!q||(w.name+' '+(w.city||'')+' '+(w.address||'')).toLocaleLowerCase().includes(q)));return {total:matches.length,rows:matches.slice(offset,offset+Math.min(80,Math.max(1,limit)))};}
return {markers,page,nextState,warehouseRegion};
});
