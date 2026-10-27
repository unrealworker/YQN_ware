const fs = require('fs');
const path = require('path');
const Model = require('./figma-import/src/model.cjs');
const {convert} = require('./dom-to-pen.cjs');
const {convertPOIs} = require('./poi-to-pen.cjs');
const {updateChrome} = require('./native-chrome.cjs');
const {cleanup} = require('./current-state-cleanup.cjs');
const dir = __dirname;
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const pen = read(path.join(dir, '../GHS_Twin_SaaS_Concept/Saas.pen'));
delete pen.fileToken;
const original = Model.index(pen);
const clone = Model.clone;
pen.componentDefinitions = Object.values(original.components).map(clone);
pen.children.forEach(b => Model.walk(b, n => delete n.reusable));
const originalBoards = new Map(pen.children.map(b => [parseInt(b.name), clone(b)]));
const snapshots = {
  1:'page-overview',2:'detail-agv',3:'devices-scene',4:'detail-alert',5:'trace-playing',
  6:'detail-material',10:'devices-scene',11:'page-inventory',12:'page-orders',
  13:'page-devices',14:'page-alerts',15:'page-trace',16:'page-scene',17:'detail-material',
  18:'detail-order',19:'19-orders-inbound',20:'20-devices-chargers',23:'detail-agv',24:'page-overview',
  31:'page-overview',44:'44-overview-capacity-info',45:'trace-orders',
  46:'46-trace-invalid-range',47:'trace-follow-loaded',48:'trace-events',49:'49-trace-completed',
  50:'trace-exit-dialog',51:'51-trace-manual-end',53:'53-trace-1440-devices'
};
const runtimeComponents = [];
const allActions = [];
const changes = [];
const poiLinks=[];
const replayBoards = new Set([5,47,48,49,50,51,53]);
function effective(n) {return n.type === 'ref' ? {...original.components[n.ref],...n} : n;}
function hasImage(n) {return n.fill && n.fill.type === 'image';}
function sourceScene(b) {
  const number = parseInt(b.name);
  if([2,23].includes(number)) return 'detail-agv-current.png';
  if(number===4) return 'detail-alert-current.png';
  if(number === 47) return 'replay-forklift-trail-ring.png';
  if(number === 53) return 'replay-follow02-640-1440.png';
  if([49,51].includes(number))return 'replay-completed-3600.png';
  if(number===5)return 'replay-playing-current.png';
  if([48,50].includes(number))return 'replay-overview-230.png';
  if(replayBoards.has(number)) return 'replay-floor-overview.png';
  if([6,11,17,18].includes(number)) return fs.existsSync(path.join(dir,'runtime/scene/racks-detail.png')) ? 'racks-detail.png' : 'warehouse-interior-overview.png';
  if([15,16,24,31,32,44,45,46].includes(number)) return 'campus-roof-closed.png';
  return 'warehouse-interior-overview.png';
}
function imagePath(file) {return path.join(dir,'runtime/scene',file).replace(/\\/g,'/');}
function scenePath(file) {
  const cropped=path.join(dir,'runtime/scene-crop',file);
  return (fs.existsSync(cropped)?cropped:imagePath(file)).replace(/\\/g,'/');
}
// Replace every scene background and thumbnail. Product-only renders remain the current project assets.
for(const board of pen.children) {
  Model.walk(board,n => {
    if(!hasImage(n)) return;
    const u=n.fill.url;
    let file;
    if(u.includes('device-agv-clear')) {n.fill={type:'image',enabled:true,url:path.join(dir,'runtime/assets/agv.png').replace(/\\/g,'/'),mode:'contain'};return;}
    else if(u.includes('device-')) return;
    else if(u.includes('campus-closed')) file='campus-roof-closed.png';
    else if(u.includes('scene-followed')) file='replay-forklift-trail-ring.png';
    else if(u.includes('order-replay')) file='replay-floor-overview.png';
    else if(u.includes('racks-detail')) file=sourceScene({name:'11'});
    else if(u.includes('floor-storage')) file='replay-floor-overview.png';
    else file='warehouse-interior-overview.png';
    n.fill={type:'image',enabled:true,url:n.width>=960&&n.y===64?scenePath(file):imagePath(file),mode:'cover'};
  });
}
for(const board of pen.children) {
  const number = parseInt(board.name), snapName = snapshots[number];
  if(!snapName) continue;
  const snapPath = path.join(dir,'runtime/dom',snapName+'.json');
  if(!fs.existsSync(snapPath)) {changes.push({board:number,pending:snapName});continue;}
  const snap=read(snapPath), panelWidth=snap.nativePanel.width, x=snap.nativePanel.x, prefix='b'+number+'-actual';
  const result=convert(snap,prefix,{x,y:64,width:panelWidth,height:board.height-64});
  const shell=result.root.children.find(n=>n.metadata?.domId==='shell');
  if(!shell) throw new Error('No current shell: '+snapName);
  const nav=shell.children.find(n=>n.metadata?.tag==='nav');
  const main=shell.children.find(n=>n.metadata?.tag==='main');
  if(!nav||!main) throw new Error('Missing nav/main: '+snapName);
  const before=board.children.length;
  // Remove the old two-column panel and old replay controls; keep the global header and scene tools.
  board.children=board.children.filter(n=>{
    const e=effective(n);
    if(e.y===64 && e.x>=board.width-480 && (e.width===56||e.width===424||e.width===480||e.width===380)) return false;
    if(replayBoards.has(number)) {
      if(n.ref==='OsnX0'||n.ref==='f1klDQ') return false;
      if(/回放模式|回放标识|轨迹显示|显示全部轨迹|仅显示选中轨迹|关闭轨迹|底部时间轴|剩余路线|跟随状态|跟随图标|当前跟随设备|取消跟随按钮|回放全景按钮|跟随相机|确认遮罩|确认弹窗|停止追溯确认|回放完成浮层/.test(n.name||''))return false;
      if(n.ref==='UWu6c'||n.id==='UWu6c')return false;
    }
    return true;
  });
  nav.x=x;nav.y=64;nav.height=board.height-64;
  main.x=x+56;main.y=64;main.height=board.height-64;main.clip=true;
  board.children.push(nav,main);
  for(const n of shell.children.filter(n=>n!==nav&&n!==main)) {n.x+=x;n.y+=64;board.children.push(n);}
  for(const n of result.root.children.filter(n=>n!==shell)) {n.x+=x;n.y+=64;board.children.push(n);}
  allActions.push(...result.actions.map(a=>({...a,board:number})));
  if([1,11,12,13,14,15,16,5,45,47,48].includes(number)){
    const c=clone(main);c.id='current-component-'+number;c.x=0;c.y=0;
    runtimeComponents.push(c);
  }
  const scene=board.children.find(n=>hasImage(n)&&n.y===64);
  if(scene){scene.width=x;scene.fill={type:'image',enabled:true,url:scenePath(sourceScene(board)),mode:'cover'};}
  if(replayBoards.has(number)) {
    const transportNames={5:'trace-transport-playing',47:'trace-transport-loaded',48:'trace-transport-events',49:'49-trace-completed-transport',51:'trace-transport-manual-exit',53:'53-trace-1440-transport'};
    const desiredTransport=transportNames[number]||'trace-transport-paused';
    const transportFile=fs.existsSync(path.join(dir,'runtime/dom',desiredTransport+'.json'))?desiredTransport:'trace-transport-paused';
    const ts=read(path.join(dir,'runtime/dom',transportFile+'.json'));
    const timeline=convert(ts,'b'+number+'-transport',{x:ts.nativePanel.x,y:ts.nativePanel.y,width:ts.nativePanel.width,height:ts.nativePanel.height});
    // The transport browser texture can be wider than its visible card; use measured geometry.
    timeline.root.width=ts.nativePanel.width; timeline.root.clip=true;
    board.children.push(timeline.root);
    allActions.push(...timeline.actions.map(a=>({...a,board:number})));
  }
  if(scene){
    const poiCandidates=[2,23].includes(number)?['detail-agv-current']:
      number===4?['detail-alert-current']:
      number===47?['replay-follow02-loaded-640']:
      number===53?['replay-follow02-640-1440']:
      [49,51].includes(number)?['replay-completed-3600']:
      number===5?['replay-playing-current']:[48,50].includes(number)?['replay-overview-230']:
      [15,16,24,31,32,44,45,46].includes(number)?['campus-roof-closed']:
      [6,11,17,18].includes(number)?['racks-detail']:['warehouse-interior-overview'];
    const found=poiCandidates.map(n=>path.join(dir,'runtime/poi',n+'.json')).find(fs.existsSync);
    if(found){
      const current=convertPOIs(read(found),'b'+number+'-poi',scene.width,scene.height);
      scene.children=[current.root];
      const poiComponents=new Set(['AXhJs','AR4QQ','zZdjB','xO4VH','hyMUB','q2XioG','qmFIM','U071M','q1Fkpg','AE7wv','uLeSp','KtN6F','cwZ7S','Gjygy']);
      board.children=board.children.filter(n=>n===scene||!(poiComponents.has(n.ref)||/^(POI ·|库位 POI|唯一主仓库标签)/.test(n.name||'')));
      poiLinks.push(...current.actions.map(a=>({sourceBoard:number,sourceNodeId:a.id,targetBoard:a.warehouse?1:replayBoards.has(number)?47:a.deviceId.startsWith('AGV')?2:a.deviceId.startsWith('REGION:rack')?11:13,label:a.warehouse?'点击查看仓库':'选择 '+a.deviceId,event:'ON_CLICK'})).filter(l=>l.sourceBoard!==l.targetBoard));
    }
  }
  changes.push({board:number,snapshot:snapName,oldTopLevelNodes:before,newTopLevelNodes:board.children.length,actions:result.actions.length});
}
pen.runtimeComponentDefinitions=runtimeComponents;
// Latest snapshots use production thumbnails, whose image files can predate the model replacement.
const imageRefresh={
  'stacker.png':'agv-cart-shell-close.png',
  'warehouse-overview.png':'campus-roof-closed.png',
  'warehouse-top.png':'warehouse-interior-overview.png',
  'warehouse-racks.png':sourceScene({name:'11'}),
  'warehouse-storage.png':'replay-floor-overview.png'
};
const refreshImage=n=>{
  if(!hasImage(n))return;
  const file=imageRefresh[path.basename(n.fill.url)];
  if(file)n.fill={type:'image',enabled:true,url:imagePath(file),mode:'cover'};
};
pen.children.forEach(b=>Model.walk(b,refreshImage));
runtimeComponents.forEach(b=>Model.walk(b,refreshImage));
pen.children.forEach(b=>updateChrome(b,original.components));
// Keep the selected AGV location consistent with the verified current scene.
pen.children.filter(b=>[2,23].includes(parseInt(b.name))).forEach(b=>Model.walk(b,n=>{
  if(n.type==='text'&&n.content==='无效区')n.content='充电区';
}));
const stateCleanup=cleanup(pen,{snapshots});
for(const b of pen.children){
  const number=parseInt(b.name);
  if(number===3)b.name='03 · 设备监控 / 当前场景设备';
  if(number===6)b.name='06 · 库存 / 货架物料详情';
  if(number===10)b.name='10 · 设备监控 / 模型列表';
}
// Update narrative specifications without claiming the prototype runs the UE renderer.
pen.children.forEach(b=>Model.walk(b,n=>{
  if(n.type!=='text')return;
  if(n.content==='屋顶已闭合')n.content='点击查看';
  if(n.content==='手动溶解 · 0.5 秒')n.content='手动溶解 · 0.8 秒';
  n.content=n.content.replace(/GHS\s*[·・]\s*普通仓库/g,'GHS · 主仓库').replace(/Shift\s*\+\s*左键平移/g,'右键平移');
}));
// Keep approved links only where their original controls still exist exactly once.
const ix=Model.index(pen), byBoard={};
for(const b of pen.children){const count={};Model.walk(Model.expand(b,ix.components),n=>count[n.originalId||n.id]=(count[n.originalId||n.id]||0)+1);byBoard[parseInt(b.name)]=count;}
const oldLinks=read(path.join(dir,'figma-import/prototype-links.json'));
let links=oldLinks.filter(l=>byBoard[l.sourceBoard]?.[l.sourceNodeId]===1).concat(poiLinks,stateCleanup.actions);
const navTargets={overview:31,inventory:11,orders:12,devices:13,alerts:14,trace:15,scene:16};
const unmapped=[];
for(const a of allActions) {
  const d=a.dataset||{},active=replayBoards.has(a.board);let target;
  if(d.action==='nav')target=active&&d.page!=='trace'?50:navTargets[d.page];
  else if(d.action==='overview')target=active?50:31;
  else if(d.action==='open-warehouse')target=1;
  else if(d.action==='demo-bin'||d.action==='material')target=17;
  else if(d.action==='order')target=18;
  else if(d.action==='alert')target=4;
  else if(d.action==='device')target=/AGV/.test(d.id)?2:/CH-/.test(d.id)?20:7;
  else if(d.action==='back')target=/detail-order/.test(snapshots[a.board])?12:/detail-material/.test(snapshots[a.board])?11:13;
  else if(d.action==='preset')target=d.value==='overview'?31:d.value==='racks'?11:1;
  else if(d.action==='tab'&&d.key==='orders.direction')target=d.value==='inbound'?19:12;
  else if(d.action==='tab'&&d.key==='devices.facility')target=d.value==='true'?20:3;
  else if(d.action==='tab'&&d.key==='devices.view')target=d.value==='scene'?3:13;
  else if(d.replayAction==='query')target=45;
  else if(d.replayAction==='start')target=5;
  else if(d.replayAction==='end')target=51;
  else if(d.replayAction==='range')target=51;
  else if(d.replayAction==='follow')target=d.id?47:5;
  else if(d.replayAction==='tab')target=d.tab==='events'?48:47;
  else if(d.replayAction==='event'||d.marker!==undefined)target=48;
  else if(d.replayAction==='cancel-exit')target=47;
  else if(d.replayAction==='confirm-exit')target=a.board===50?31:15;
  else if(d.control==='play')target=a.board===5?47:5;
  else if(d.control==='overview')target=5;
  else if(d.info&&/库容|2,400|2400/.test(d.info))target=44;
  if(target!==undefined&&target!==a.board)links.push({sourceBoard:a.board,sourceNodeId:a.id,targetBoard:target,label:a.text||d.replayAction||d.action||'事件定位',event:'ON_CLICK'});
  else if(target===undefined)unmapped.push({board:a.board,id:a.id,dataset:d,text:a.text});
}
const unique=new Map();for(const l of links)if(l.sourceBoard!==l.targetBoard)unique.set(l.sourceBoard+':'+l.sourceNodeId,l);links=[...unique.values()];
const overrides={links,boardInteractions:{
  2:['当前详情设备为 AGV-01，场景相机和 POI 与该设备对应。','点击关闭返回设备列表；选择其他设备后详情与场景同步更新。','图中的设备状态是静态核验/演示快照，非实时接入声明。'],
  3:['模型监控页显示当前场景设备清单。','选择列表设备联动场景定位与详情；筛选只作用于相应设备类型。'],
  4:['当前告警详情对应 STACKER-04：货叉举升异常；相机、POI 与右栏保持同一设备。','返回告警列表保留已有筛选；定位设备时先展开屋顶，再平滑定位。','故障状态为演示快照，后续真实告警接入沿用相同交互。'],
  6:['右侧展示当前货架物料详情，示例数据保持未核验标记。','当前货架相机没有可见物料 POI，实际数据未映射时不附加虚假的场景定位标牌。'],
  10:['当前模型监控列表可按状态筛选和选择设备。','画板仅记录已捕获的实际列表状态，不把旧聚合弹层视为当前实现。'],
  23:['搜索结果浮层与当前搜索栏对齐，展示设备/货位/物料匹配项。','选择设备同步场景定位与设备详情；点击空白或 Esc 关闭结果浮层。','搜索可输入中文，空结果与加载状态参见搜索规范页。']
},boardStatus:Object.fromEntries(changes.filter(c=>c.snapshot).map(c=>[c.board,'已实现 · 2026-10-27 UE 实际界面；静态数据与演示数据仍按页面标记']))};
fs.writeFileSync(path.join(dir,'migration.pen.json'),JSON.stringify(pen));
fs.writeFileSync(path.join(dir,'runtime-overrides.json'),JSON.stringify(overrides,null,2));
fs.writeFileSync(path.join(dir,'migration-report.json'),JSON.stringify({changes,stateCleanup,sceneSource:'runtime/scene',sourceCommit:'73e7b58',links:links.length,unmappedControls:unmapped,counts:Model.audit(pen)},null,2));
console.log(JSON.stringify({updated:changes.filter(c=>c.snapshot).length,pending:changes.filter(c=>c.pending),links:links.length,unmappedControls:unmapped.length},null,2));
