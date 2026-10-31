const test=require('node:test'),assert=require('node:assert/strict');
const P=require('../../../Content/GHSTwinUI/web/globe-policy.js');
test('two thousand warehouses stay within moving DOM budget and preserve selected POI',()=>{
 const sites=Array.from({length:2000},(_,i)=>({id:'w'+i,x:10+i%1000,y:10+i%700,visible:true}));
 const result=P.markers(sites,'w1999',{left:0,top:0,right:1200,bottom:900});
 assert.ok(result.length<=48);assert.equal(result[0].id,'w1999');assert.equal(new Set(result.flatMap(x=>x.ids)).size,2000);assert.equal(result.flatMap(x=>x.ids).length,2000);
});
test('back hemisphere and invalid/outside projections cannot create clickable markers',()=>{
 assert.deepEqual(P.markers([{id:'a',x:5,y:5,visible:false},{id:'b',x:NaN,y:5,visible:true},{id:'c',x:-5,y:5,visible:true}],null,{left:0,top:0,right:100,bottom:100}),[]);
});
test('dense locations cluster, selected location remains separately addressable',()=>{
 const result=P.markers([{id:'a',x:10,y:10,visible:true},{id:'b',x:11,y:11,visible:true},{id:'c',x:12,y:12,visible:true}],'c',{left:0,top:0,right:100,bottom:100});
 assert.equal(result.length,2);assert.deepEqual(result[1].ids,['a','b']);
});
test('catalog search combines region and cluster filters with bounded pagination',()=>{
 const sites=Array.from({length:1000},(_,i)=>({id:'w'+i,name:'仓库'+i,city:'City',address:'Address',region:i%2?'亚洲':'北美'}));
 assert.equal(P.page(sites).rows.length,40);assert.equal(P.page(sites,{region:'北美'}).total,500);
 assert.equal(P.page(sites,{ids:['w1','w2'],region:'北美'}).rows[0].id,'w2');
 assert.equal(P.page(sites,{query:'不匹配'}).total,0);
});
test('invalid snapshots cannot replace a working catalog or poison later partial updates',()=>{
 const original={phase:'idle',stageVisible:true,selectedId:'',warehouses:[{id:'a',name:'仓库 A'}],pois:[],countries:[],transition:{opacity:0}};
 const saved=JSON.stringify(original);
 for(const message of ['{',null,[],{warehouses:null},{warehouses:[null]},{warehouses:[{id:'a',name:'A'},{id:'a',name:'B'}]},{pois:[null]},{countries:{}},{transition:{opacity:NaN}},{phase:'unknown'},{error:{message:'bad'}}]){
  assert.equal(P.nextState(original,message),null);assert.equal(JSON.stringify(original),saved);
 }
 const selected=P.nextState(original,JSON.stringify({phase:'selected',selectedId:'a'}));assert.equal(selected.phase,'selected');assert.equal(selected.warehouses,original.warehouses);
 const empty=P.nextState(selected,{selectedId:'',warehouses:[]});assert.deepEqual(empty.warehouses,[]);assert.equal(original.warehouses.length,1);
 const curtain=P.nextState(selected,{transition:{opacity:1,awaitingCurtain:true,generation:2,width:1672,height:941}});assert.ok(curtain);assert.equal(P.nextState(selected,{transition:{opacity:1,awaitingCurtain:true,width:0,height:0}}),null);
});
test('missing and blank regions use the same unassigned label in options and filtering',()=>{
 const sites=[{id:'missing',name:'Missing'},{id:'empty',name:'Empty',region:''},{id:'space',name:'Space',region:' '},{id:'north',name:'North',region:'北美'}];
 assert.deepEqual(Array.from(new Set(sites.map(P.warehouseRegion))),['未分区','北美']);
 assert.deepEqual(P.page(sites,{region:'未分区'}).rows.map(w=>w.id),['missing','empty','space']);
 assert.deepEqual(P.page(sites,{region:'北美'}).rows.map(w=>w.id),['north']);
});
test('partial snapshots reuse an accepted 2000-site catalog without reading its records',()=>{
 let reads=0;const sites=Array.from({length:2000},(_,i)=>({id:'w'+i,get name(){reads++;return 'Warehouse '+i;}}));
 const initial={phase:'idle',stageVisible:true,selectedId:'',warehouses:[],pois:[],countries:[],transition:{opacity:0}};
 const accepted=P.nextState(initial,{warehouses:sites});assert.ok(accepted);assert.equal(reads,2000);reads=0;
 const partial=P.nextState(accepted,{phase:'selected',selectedId:'w1999'});assert.ok(partial);assert.equal(partial.warehouses,sites);assert.equal(reads,0);
 assert.equal(P.nextState(partial,{warehouses:undefined}),null);assert.equal(P.nextState(partial,{warehouses:[{id:'bad',name:null}]}),null);
 assert.ok(P.nextState(partial,{phase:'idle',selectedId:''}));assert.equal(reads,0);
});
test('blank scene clicks cancel selection while drags, cancellations and controls preserve it',()=>{
 const finish={selectedId:'a',phase:'selected',blank:true};
 let gesture=P.beginSceneGesture(100,100,'a');gesture=P.moveSceneGesture(gesture,102,103);
 assert.equal(gesture.dragging,false);assert.equal(gesture.dx,0);assert.equal(gesture.dy,0);assert.equal(P.isBlankSceneClick(gesture,finish),true);
 assert.equal(P.isBlankSceneClick(gesture,{...finish,blank:false}),false);assert.equal(P.isBlankSceneClick(gesture,{...finish,cancelled:true}),false);
 assert.equal(P.isBlankSceneClick(gesture,{...finish,selectedId:'b'}),false);assert.equal(P.isBlankSceneClick(gesture,{...finish,phase:'flying'}),false);
 gesture=P.moveSceneGesture(gesture,106,100);assert.equal(gesture.dragging,true);assert.equal(gesture.dx,6);assert.equal(gesture.dy,0);
 gesture=P.moveSceneGesture(gesture,100,100);assert.equal(gesture.dx,-6);assert.equal(P.isBlankSceneClick(gesture,finish),false);
 const releaseOnly=P.moveSceneGesture(P.beginSceneGesture(0,0,'a'),0,8);assert.equal(P.isBlankSceneClick(releaseOnly,finish),false);
 assert.equal(P.isBlankSceneClick(P.beginSceneGesture(0,0,''),finish),false);
});
test('page motion defaults to normal and preserves an explicit reduced setting',()=>{
 assert.equal(P.motionPreference(null),'normal');assert.equal(P.motionPreference('normal'),'normal');assert.equal(P.motionPreference('reduced'),'reduced');assert.equal(P.motionPreference('unexpected'),'normal');
});
test('an old idle snapshot cannot unlock an unacknowledged entry request',()=>{
 let gate=P.entryRequestState('idle','request');
 for(const phase of ['selected','idle','selected']){gate=P.entryRequestState(gate,phase);assert.equal(gate,'pending');}
 gate=P.entryRequestState(gate,'loading');assert.equal(gate,'acknowledged');gate=P.entryRequestState(gate,'flying');assert.equal(gate,'acknowledged');
 assert.equal(P.entryRequestState(gate,'warehouse'),'idle');assert.equal(P.entryRequestState('pending','error'),'idle');assert.equal(P.entryRequestState('pending','cancel'),'idle');
 assert.equal(P.entryRequestState('acknowledged','selected'),'idle');
});
test('curtain copy appears only for actual covered waiting or an error',()=>{
 for(const phase of ['flying','revealing']){
  assert.equal(P.transitionNotice(phase,{opacity:1,waitingForDestination:false}).waiting,false);
  assert.equal(P.transitionNotice(phase,{opacity:.8,waitingForDestination:true}).waiting,false);
  const waiting=P.transitionNotice(phase,{opacity:1,waitingForDestination:true});assert.equal(waiting.waiting,true);assert.equal(waiting.text,'仓库正在初始化，请稍候');
  const failure=P.transitionNotice(phase,{opacity:1,waitingForDestination:true},'加载失败');assert.equal(failure.waiting,false);assert.equal(failure.error,true);assert.equal(failure.text,'加载失败');
 }
 assert.equal(P.transitionNotice('warehouse',{opacity:1,waitingForDestination:true}).active,false);
});

test('country names keep geographic anchors while overlap hides secondary labels',()=>{
 const rect={left:0,top:0,right:500,bottom:500};
 const rows=[{id:'a',x:100,y:100,width:60,height:20,visible:true},{id:'b',x:150,y:100,width:60,height:20,visible:true}];
 assert.deepEqual(P.countryLabels(rows,rect).map(c=>c.id),['a']);
 for(let y=100;y<180;y+=.5){
  rows[1].y=y;
  for(const label of P.countryLabels(rows,rect))assert.equal(label.y,rows.find(r=>r.id===label.id).y);
 }
 assert.deepEqual(P.countryLabels([{...rows[0],visible:false},{...rows[1],x:NaN}],rect),[]);
});

test('country label visibility has clearance hysteresis at a collision boundary',()=>{
 const rect={left:0,top:0,right:500,bottom:500},a={id:'a',x:100,y:100,width:60,height:20,visible:true};
 const b={...a,id:'b',x:168};
 assert.deepEqual(P.countryLabels([a,b],rect,new Set(['a','b'])).map(c=>c.id),['a','b']);
 assert.deepEqual(P.countryLabels([a,b],rect,new Set(['a'])).map(c=>c.id),['a']);
 assert.deepEqual(P.countryLabels([a,{...b,x:180}],rect,new Set(['a'])).map(c=>c.id),['a','b']);
});
