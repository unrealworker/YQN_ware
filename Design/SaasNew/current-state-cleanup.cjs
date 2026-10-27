'use strict';
const fs=require('fs'),path=require('path');
const {fontPx,headerLayout}=require('./native-chrome.cjs');
const ROOT=__dirname,SOURCE='Source/Test/GHSTwinHUDWidget.cpp::NativePaint';
const round=n=>Math.round(n*10000)/10000;
const readIfExists=file=>fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):null;
function walk(n,fn){fn(n);for(const c of n.children||[])walk(c,fn);}
function frame(id,name,x,y,width,height,children=[],role,fill='#FFFFFF'){
  return {type:'frame',id,name,x,y,width,height,layout:'none',clip:false,fill,cornerRadius:12,stroke:'#DFE7F2',strokeWidth:1,strokeAlignment:'inner',children,
    metadata:{source:SOURCE,nativeChrome:role,implementation:'UE current captured state'}};
}
function text(id,name,content,x,y,pt,color='#25364B'){
  return {type:'text',id,name,content:String(content),x,y,width:Math.max(1,String(content).length*fontPx(pt)),height:round(fontPx(pt)*1.2),
    fontFamily:/[^\x00-\x7f]/.test(content)?'Microsoft YaHei':'Arial',fontSize:fontPx(pt),fontWeight:'400',lineHeight:1.2,fill:color,
    metadata:{source:SOURCE,nativeSlatePoints:pt,noWrap:true}};
}
function reportForScene(scene,number,options){
  if(options.poiReports?.[number])return options.poiReports[number];
  const exactName=[2,23].includes(number)?'detail-agv-current':number===4?'detail-alert-current':null;
  if(exactName){const report=readIfExists(path.join(ROOT,'runtime/poi',exactName+'.json'));if(report)return report;}
  let capture;
  walk(scene,n=>{if(!capture&&n.metadata?.source==='GetPOIReport')capture=n.metadata.capture;});
  if(capture){const found=readIfExists(path.join(ROOT,'runtime/poi',capture+'.json'));if(found)return found;}
  return null;
}
function buildFilters(board,state,report){
  const layout=headerLayout(board.width),id='b'+parseInt(board.name)+'-native-filters';
  if(state.replay||state.roofClosed||report?.interiorAvailable===false||layout.sceneWidth<=660||board.height-layout.height<195)return null;
  const filters=[['all','全部设备',1],['rack','货架区域',11],['truck','装卸车辆',13],['charger','充电设施',20]];
  const current=report?.pointFilter||'all';
  const root=frame(id,'按类型查看 · UE 当前实际',32,layout.height+116,408,71,[text(id+'-title','类型筛选标题','按类型查看',0,0,11,'#5B6C82')],'filters');
  delete root.fill;delete root.stroke;delete root.strokeWidth;
  const actions=[];
  for(const [i,[filter,label,targetBoard]]of filters.entries()){
    const control=frame(id+'-'+filter,label,i*104,31,96,40,[text(id+'-'+filter+'-label',label,label,15,12,11,filter===current?'#356BFA':'#25364B')],'filter-control');
    control.stroke=filter===current?'#356BFA':'#E5EAF2';control.strokeWidth=filter===current?3:1;
    control.metadata={...control.metadata,action:'point-filter',filter,selected:filter===current};root.children.push(control);
    actions.push({sourceBoard:parseInt(board.name),sourceNodeId:control.id,targetBoard,label:'按类型查看：'+label,event:'ON_CLICK'});
  }
  root.metadata.pointFilter=current;return {root,actions};
}
function buildWarehouseMenu(board,old){
  const id=old?.id||'b24-native-warehouse-menu',layout=headerLayout(board.width);
  const rowId=(old?.children||[]).find(n=>n.metadata?.nativeChrome==='warehouse-current'||/当前仓库选项/.test(n.name||''))?.id||id+'-current';
  const row=frame(rowId,'GHS · 当前仓库',16,46,288,48,[text(rowId+'-title','当前仓库','GHS · 当前仓库',16,14,14,'#356BFA')],'warehouse-current','#EDF3FF');
  delete row.stroke;delete row.strokeWidth;
  const root=frame(id,'仓库选择下拉 · UE 当前实际',24,layout.height+110,320,176,[
    text(id+'-title','仓库选择标题','切换仓库',16,14,11,'#5B6C82'),row,
    text(id+'-none','可选仓库','暂无其他仓库',16,116,11,'#5B6C82'),text(id+'-note','接入说明','接入后会显示在这里',16,142,11,'#5B6C82')
  ],'warehouse-menu');
  root.metadata.open=true;
  return {root,actions:[{sourceBoard:24,sourceNodeId:rowId,targetBoard:31,label:'返回当前 GHS 仓库',event:'ON_CLICK'}]};
}
function oldSearchResults(drop){
  if(drop?.metadata?.results)return drop.metadata.results;
  return (drop?.children||[]).filter(n=>/^结果 \/ /.test(n.name||'')).map(n=>{
    const fields={};walk(n,c=>{if(c.type==='text')fields[c.name]=c.content;});
    return {id:fields['设备编号']||n.name.slice(5),title:fields['设备编号']||n.name.slice(5),type:'搬运机器人',location:fields['设备位置']||'',status:fields['设备状态']||'',legacyNodeId:n.id};
  });
}
function searchLayout(input,sceneBottom,count){
  const y=input.y+input.height+8,available=Math.max(0,sceneBottom-y-8),visibleRows=Math.max(0,Math.min(8,count,Math.floor((available-72)/64)));
  return {x:input.x,y,width:input.width,height:Math.min(available,72+Math.max(1,visibleRows)*64),visibleRows};
}
function buildSearchMenu(board,old,input,report){
  const id=old?.id||'b23-native-search-menu';
  const results=report?.results||oldSearchResults(old),total=report?.total??results.length,selected=report?.selectedIndex??(results.length?0:-1),offset=report?.offset||0;
  const layout=searchLayout(input,board.height,total),first=Math.max(0,Math.min(results.length-layout.visibleRows,selected-offset-layout.visibleRows+1));
  const root=frame(id,'搜索匹配下拉 · UE 当前实际',layout.x,layout.y,layout.width,layout.height,[
    text(id+'-header','匹配结果总数','GHS · 匹配结果（'+total+'）',16,10,11,'#5B6C82')
  ],'search-menu');
  root.clip=true;
  const actions=[];
  for(let i=0;i<layout.visibleRows;i++){
    const r=results[first+i];if(!r)break;
    const rid=id+'-result-'+String(r.id).replace(/[^a-zA-Z0-9_-]/g,'-'),active=first+i+offset===selected;
    const row=frame(rid,'搜索结果 · '+r.id,8,36+i*64,layout.width-16,60,[
      text(rid+'-title','设备名称',String(r.title||r.id).slice(0,14),12,6,13),
      text(rid+'-location','设备类型与位置',((r.type||'')+' · '+(r.location||'')).slice(0,24),12,33,10,'#5B6C82'),
      text(rid+'-status','设备状态',r.status||'',layout.width-86,7,11,'#356BFA')
    ],'search-result',active?'#EDF3FF':'#FFFFFF');
    delete row.stroke;delete row.strokeWidth;row.metadata={...row.metadata,deviceId:r.id,action:'search-select',selected:active};root.children.push(row);
    actions.push({sourceBoard:23,sourceNodeId:row.id,targetBoard:String(r.id).startsWith('AGV')?2:String(r.id).startsWith('SKU')?17:13,label:'选择搜索结果 '+r.id,event:'ON_CLICK'});
  }
  if(!results.length)root.children.push(text(id+'-empty','搜索空态',report?.query?'GHS 中未找到匹配设备或物料':'输入设备名称、类型、编号或物料',16,52,12,'#5B6C82'));
  root.children.push(text(id+'-footer','搜索键盘与分页提示','↑ ↓ / 滚轮   '+(selected<0?0:selected+1)+' / '+total+'   Enter 定位   Esc 收起',16,layout.height-27,10,'#5B6C82'));
  root.metadata={...root.metadata,sourceLayout:'Source/Test/GHSTwinSearchLayout.h',query:report?.query||input.metadata?.query||'agv',total,selectedIndex:selected,visibleRows:layout.visibleRows,firstVisible:first,
    capture:report?.name||report?.capturedAt||(report?'GetSearchState':'Legacy content awaiting current capture'),verified:!!report,results,
    nativeDropdownDrawn:report?.nativeDropdownDrawn??null,nativeDropdownNote:report?.nativeDropdownNote||'Geometry follows NativePaint; this is an editable reconstruction.'};
  return {root,actions};
}

/** After updateChrome(), before prototype links resolve. Does not mutate masters. */
function cleanup(pen,options={}){
  const snapshots=options.snapshots||{},allowed=new Set(Object.keys(snapshots).map(Number));
  const summary={boards:[],removed:[],actions:[],warnings:[]};
  const searchReport=options.searchReport||readIfExists(path.join(ROOT,'runtime/search/detail-agv-search.json'))||readIfExists(path.join(ROOT,'runtime/search/current-search.json'));
  for(const board of pen.children||[]){
    const number=parseInt(board.name),prefix='b'+number+'-';
    if(number===32||!allowed.has(number))continue;
    const scene=board.children.find(n=>n.fill?.type==='image'&&n.y===64&&n.width>=720);
    const header=board.children.find(n=>n.metadata?.nativeChrome==='header');
    const input=board.children.find(n=>n.metadata?.nativeChrome==='search');
    const main=board.children.find(n=>n.id.startsWith(prefix+'actual-')&&n.metadata?.tag==='main');
    if(!scene||!header||!input||!main){summary.warnings.push({board:number,message:'Skipped cleanup: missing current scene/chrome/main; do not strip a specification board.'});continue;}
    const oldSearch=board.children.find(n=>n.metadata?.nativeChrome==='search-menu'||/搜索匹配下拉/.test(n.name||''));
    const oldWarehouse=board.children.find(n=>n.metadata?.nativeChrome==='warehouse-menu'||n.name==='仓库选择下拉');
    const hint=board.children.find(n=>n.metadata?.nativeChrome==='hint'),report=reportForScene(scene,number,options);
    const state={roofClosed:report?.roofClosed??hint?.metadata?.roofClosed??false,replay:report?.replay??hint?.metadata?.replay??false};
    const selector=board.children.find(n=>n.metadata?.nativeChrome==='selector');
    const capturedArea=report?.nativeChrome?.area||report?.selectedLocation||report?.locationLabel;
    if(selector&&capturedArea){
      const label=selector.children.find(n=>n.name==='当前区域');if(label){label.content=String(capturedArea).slice(0,12);label.name='当前区域';}
      selector.metadata={...selector.metadata,area:capturedArea,areaSource:report.name||'Current runtime capture'};
    }
    if(number===23&&searchReport?.query!==undefined){
      input.metadata.query=searchReport.query;
      const label=input.children.find(n=>n.id.endsWith('-input'));if(label){label.content=searchReport.query||'搜索设备、货位或物料';label.fill=searchReport.query?'#25364B':'#A7B2C2';}
      const clear=input.children.find(n=>n.id.endsWith('-clear'));if(clear)clear.content=searchReport.query?'清除':'GHS';
    }
    const keep=new Set(['header','selector','search','hint']);
    const removed=[];
    board.children=board.children.filter(n=>{
      if(n===scene||keep.has(n.metadata?.nativeChrome)||n.id.startsWith(prefix+'actual-')||n.id.startsWith(prefix+'transport-'))return true;
      if(!['filters','search-menu','warehouse-menu'].includes(n.metadata?.nativeChrome))removed.push({id:n.id,name:n.name,type:n.type});
      return false;
    });
    const filter=buildFilters(board,state,report);
    if(filter){board.children.push(filter.root);summary.actions.push(...filter.actions);}
    if(number===23){
      const menu=buildSearchMenu(board,oldSearch,input,searchReport);board.children.push(menu.root);summary.actions.push(...menu.actions);
      if(!searchReport)summary.warnings.push({board:number,message:'Search menu geometry current; result contents await current-search.json capture.'});
    }
    if(number===24){const menu=buildWarehouseMenu(board,oldWarehouse);board.children.push(menu.root);summary.actions.push(...menu.actions);}
    if(number===4)board.name='04 · 告警定位 / STACKER-04 故障详情';
    summary.removed.push(...removed.map(r=>({board:number,...r})));
    const hasSelectedPOI=[];walk(scene,n=>{if(n.metadata?.selected)hasSelectedPOI.push(n.metadata.deviceId);});
    if([2,4,23].includes(number)&&!hasSelectedPOI.length)summary.warnings.push({board:number,message:'Current camera/POI capture has no selected device yet; await exact capture from runtime QA.'});
    if([3,10].includes(number))summary.warnings.push({board:number,message:'Legacy aggregation popover removed. Current snapshot displays device model monitoring; aggregation-expanded state is not captured.'});
    board.metadata={...board.metadata,currentStateCleanup:{source:'Actual CEF/native chrome and captured scene POIs only',legacyRootOverlaysRemoved:true}};
    summary.boards.push({board:number,removed:removed.length,rootNodes:board.children.length,filters:!!filter,searchMenu:number===23,warehouseMenu:number===24,selectedPOIs:hasSelectedPOI});
  }
  return summary;
}
module.exports={cleanup,searchLayout};
