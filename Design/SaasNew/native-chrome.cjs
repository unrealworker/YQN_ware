'use strict';

// Editable reconstruction of GHSTwinHUDWidget's native Slate chrome.
// Sources: NativePaint / RebuildWidget and GHSTwinHeaderLayout / GHSTwinLayout.
// This module mutates only the supplied scene board, never the component registry.
const SOURCE = 'Source/Test/GHSTwinHUDWidget.cpp::NativePaint';
const CAPTURE = 'runtime/screens/page-overview.png';
const STATIC_CLOCK = Object.freeze({ time: '06:57:03', date: '2026.10.27 · PDT (UTC-07:00)', zone: 'America/Los_Angeles', static: true, source: CAPTURE });
const REPLAY = new Set([5,47,48,49,50,51,53]);
const CLOSED = new Set([15,16,24,31,44,45,46]);
const round = n => Math.round(n * 10000) / 10000;
const fontPx = pt => round(pt * 4 / 3);
const metadata = role => ({ source: SOURCE, implementation: 'UE native Slate · current 2026-10-27', nativeChrome: role, capture: CAPTURE });
function frame(id, name, x, y, width, height, fill, children = []) {
  return { type: 'frame', id, name, x, y, width, height, layout: 'none', clip: false, ...(fill ? { fill } : {}), children };
}
function text(id, name, content, x, y, width, height, pt, fill, extra = {}) {
  return { type:'text', id, name, content, x:round(x), y:round(y), width:round(width), height:round(height),
    fontFamily:/[^\x00-\x7f]/.test(content)?'Microsoft YaHei':'Arial', fontSize:fontPx(pt), fontWeight:'400',
    lineHeight:1, fill, textAlign:'left', textAlignVertical:'top',
    metadata:{source:SOURCE,nativeSlatePoints:pt,pointToPixel:4/3,noWrap:true}, ...extra };
}
function centeredText(id, name, content, x, y, width, rowHeight, pt, fill, extra) {
  return text(id,name,content,x,y+(rowHeight-fontPx(pt))/2,width,fontPx(pt),pt,fill,extra);
}
function rect(id, name, x, y, width, height, fill, radius = 0) {
  return { type:'rectangle', id, name, x, y, width, height, fill, cornerRadius:radius };
}
function svg(id, name, x, y, width, height, body, stroke = '#8BAFFF', strokeWidth = 1.3) {
  return {type:'svg',id,name,x,y,width,height,svg:`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`};
}
function effective(node, components) {
  return node.type === 'ref' ? {...components[node.ref],...node} : node;
}
function materialize(node, next) {
  // Keep object identity, ID and nonvisual prototype metadata, not stale ref overrides.
  const oldMetadata = node.metadata || {};
  for(const key of Object.keys(node)) delete node[key];
  Object.assign(node,next,{metadata:{...oldMetadata,...next.metadata}});
  return node;
}
function childId(node, predicate, suffix) {
  return (node.children||[]).find(predicate)?.id || node.id+'-'+suffix;
}
function headerLayout(width) {
  let height=64,brandRowHeight=64,addressX=width>=1250?440:300,addressY=8,clockX=width-402,clockY=8;
  if(width<1000){brandRowHeight=52;addressX=24;addressY=56;height=width>=640?112:168;clockX=width>=640?width-290:24;clockY=width>=640?56:112;}
  const panelWidth=Math.max(380,Math.min(560,width*.25));
  return {height,brandRowHeight,addressX,addressY,clockX,clockY,panelButtonX:width-112,panelButtonY:(brandRowHeight-44)/2,
    showContext:width>=1250,compactBrand:width<440,panelWidth,sceneWidth:width-panelWidth};
}
function buildHeader(previous, width, state, layout) {
  const id=previous.id;
  const symbolId=childId(previous,n=>/项目图标|项目标志/.test(n.name||''),'brand-symbol');
  const titleId=childId(previous,n=>n.name==='项目名称','brand-title');
  const contextId=childId(previous,n=>n.name==='当前场景范围','context');
  const panelId=childId(previous,n=>/业务面板|面板开关/.test(n.name||'')||/^(收起|展开)面板$/.test(n.content||''),'panel-toggle');
  const addressId=childId(previous,n=>/仓库地址/.test(n.name||''),'address');
  const clockId=childId(previous,n=>/仓库当地时钟/.test(n.name||''),'clock');
  const children=[],logoY=(layout.brandRowHeight-21)/2;
  children.push(frame(symbolId,'项目标志 · UE 四方格',22,logoY,21,21,null,[
    rect(symbolId+'-1','主题蓝',0,0,9,9,'#356BFA',1),rect(symbolId+'-2','浅蓝',12,0,9,9,'#78A3FF',1),
    rect(symbolId+'-3','浅蓝',0,12,9,9,'#78A3FF',1),rect(symbolId+'-4','主题蓝',12,12,9,9,'#356BFA',1)
  ]));
  children.push(centeredText(titleId,'项目名称',layout.compactBrand?'GHS 数字孪生':'GHS 仓储数字孪生',57,0,234,layout.brandRowHeight,17,'#FFFFFF'));
  if(layout.showContext)children.push(centeredText(contextId,'当前场景范围','三维运营中心',300,0,112,layout.brandRowHeight,12,'#B3C1D1'));
  if(width>=1000)children.push(rect(id+'-address-divider','地址前分隔线',layout.addressX-20,18,1,28,'#354253'),rect(id+'-panel-divider','面板操作前分隔线',width-128,18,1,28,'#354253'));
  const address=frame(addressId,'仓库地址 · UE 当前实际',layout.addressX,layout.addressY,270,48,null,[
    svg(addressId+'-pin','地址图标',0,15,16,19,'<path d="M8 18L2 10 1 6 3 2 8 0 13 2 15 6 14 10 8 18Z"/><path d="M8 4L5 7 8 10 11 7Z"/>'),
    centeredText(addressId+'-street','街道地址','17335 Glen Helen Pkwy',28,0,242,23,13,'#FFFFFF'),
    centeredText(addressId+'-city','城市和国家','San Bernardino, CA 92407 美国',28,25,242,19,11,'#B3C1D1')
  ]);
  address.metadata={...metadata('address'),address:'17335 Glen Helen Pkwy, San Bernardino, CA 92407 美国'};
  children.push(address);
  const clock=frame(clockId,'仓库当地时钟 · 固定采集示意',layout.clockX,layout.clockY,266,48,null,[
    svg(clockId+'-icon','时钟图标',0,15,17,17,'<circle cx="8" cy="8" r="8"/><path d="M8 3V8L12 10"/>'),
    centeredText(clockId+'-label','当地时间标签','仓库当地时间',28,0,98,23,11,'#B3C1D1'),
    centeredText(clockId+'-date','当地日期与时区',state.clock.date,28,25,238,19,11,'#B3C1D1')
  ]);
  let digitX=130;
  for(const [i,glyph] of [...state.clock.time].entries()){
    const cell=glyph===':'?7:15;
    // Fixed advances reproduce the production clock's stable digit positions.
    clock.children.push(centeredText(clockId+'-digit-'+i,'时钟字符 '+(i+1),glyph,digitX,0,cell,23,19,'#FFFFFF',{
      textGrowth:'fixed-width-height',textAlign:'center',metadata:{...metadata('clock-digit'),nativeSlatePoints:19,pointToPixel:4/3,staticClock:true}
    }));digitX+=cell;
  }
  clock.metadata={...metadata('clock'),staticClock:true,clock:state.clock};children.push(clock);
  const panel=frame(panelId,'业务面板开关 · UE 当前实际',layout.panelButtonX,layout.panelButtonY,96,44,null,[
    centeredText(panelId+'-label','面板开关文案',state.panelCollapsed?'展开面板':'收起面板',10,0,86,44,12,'#FFFFFF')
  ]);
  panel.metadata={...metadata('panel-toggle'),action:'toggle-panel',collapsed:state.panelCollapsed,durationMs:420,easing:'smootherstep'};children.push(panel);
  const header=frame(id,'全局顶栏 · UE 当前实际',0,0,width,layout.height,'#172333',children);
  header.clip=true;header.metadata={...metadata('header'),sourceLayout:'Source/Test/GHSTwinHeaderLayout.h',staticClock:true};
  return {header,panelId};
}
function buildSelector(previous,state,layout) {
  const id=previous.id,selector=frame(id,'当前仓库选择器 · UE 当前实际',24,layout.height+16,256,84,'#FFFFFF',[
    text(id+'-title','仓库标识','GHS',24,12,180,35,22,'#25364B'),
    text(id+'-area','当前区域',state.area.slice(0,12),24,49,190,20,11,'#5B6C82'),
    svg(id+'-chevron','切换仓库',227,35,12,9,'<path d="M1 2L6 7 11 2"/>','#5B6C82',1.5)
  ]);
  selector.cornerRadius=12;selector.stroke='#DFE7F2';selector.strokeWidth=1;selector.strokeAlignment='inner';
  selector.metadata={...metadata('selector'),action:'toggle-warehouse-menu',area:state.area};return selector;
}
function buildSearch(previous,state,layout,width) {
  const id=previous.id,right=state.panelCollapsed?width:layout.sceneWidth,searchWidth=Math.max(0,Math.min(360,layout.sceneWidth-160));
  const query=state.searchQuery;
  const search=frame(id,'全局搜索 · UE 当前实际',Math.max(140,right-384),layout.height+16,searchWidth,48,'#FFFFFF',[
    centeredText(id+'-input',query?'搜索输入内容':'搜索提示',query||'搜索设备、货位或物料',16,0,searchWidth-82,48,13,query?'#25364B':'#A7B2C2'),
    centeredText(id+'-clear',query?'清除搜索':'仓库范围',query?'清除':'GHS',searchWidth-45,0,30,48,11,query?'#356BFA':'#8BA2FF')
  ]);
  search.cornerRadius=12;search.stroke='#D9E3F1';search.strokeWidth=1;search.strokeAlignment='inner';
  search.enabled=layout.sceneWidth>=720;
  search.metadata={...metadata('search'),source:'Source/Test/GHSTwinHUDWidget.cpp::UGHSTwinSearchInput::RebuildWidget',action:'open-search',query,
    geometry:'Source/Test/GHSTwinLayout.h::FGHSTwinPanelMotion::SceneSearchPosition',input:'Chinese IME supported; Enter selects; Esc closes'};
  return search;
}
function hintText(state) {
  if(state.replay)return state.following?'跟随中  ·  左键旋转  ·  滚轮缩放  ·  右键平移无效':'左键旋转  ·  右键平移  ·  滚轮缩放  ·  点击选择回放设备';
  return state.roofClosed?'左键旋转  ·  右键平移  ·  滚轮缩放  ·  点击仓库查看内部':'左键旋转  ·  右键平移  ·  滚轮缩放  ·  中键返回园区  ·  点击查看详情';
}
function buildHint(id,oldTextId,state,layout,height) {
  const content=hintText(state),px=fontPx(11);
  // Match the native font's measured hint sizes in captured frames. Differences
  // between native DroidSansFallback and editable YaHei are recorded, not hidden.
  const advance=[...content].reduce((sum,c)=>sum+(c===' '?px*.25:c==='·'?px*.28:c.charCodeAt(0)>255?px:px*.53),0);
  const hint=frame(id,'底部场景操作提示 · UE 当前实际',22,height-44,round(advance+28),32,'#FFFFFFF0',[
    centeredText(oldTextId||id+'-label','当前视角操作说明',content,14,0,round(advance),32,11,'#536478')
  ]);
  hint.cornerRadius=8;hint.stroke='#DFE7F2';hint.strokeWidth=1;hint.strokeAlignment='inner';hint.enabled=layout.sceneWidth>650;
  hint.metadata={...metadata('hint'),replay:state.replay,following:state.following,roofClosed:state.roofClosed,widthSource:'Native CJK advance approximation; text remains editable'};
  return hint;
}

/**
 * Mutates one actual UE scene board, returning the updated IDs and layout.
 * Non-scene/specification/backend/launcher boards are unchanged.
 * Optional board.metadata.nativeChromeState values: area, searchQuery,
 * replay, following, roofClosed, panelCollapsed, clock {time,date,zone}.
 * Call after replacing the runtime sidebar, before resolving prototype links.
 */
function updateChrome(board,originalComponents={}) {
  if(!board||!Array.isArray(board.children))throw new TypeError('updateChrome requires a board with children');
  const components=originalComponents.components||originalComponents;
  const children=board.children;
  const header=children.find(n=>n.metadata?.nativeChrome==='header'||(/^全局导航$|项目深蓝顶栏|全局顶栏/.test(n.name||'')&&(n.y||0)===0));
  const selector=children.find(n=>n.metadata?.nativeChrome==='selector'||n.ref==='Dta3T'||/当前仓库选择器|当前仓库 \/ GHS/.test(n.name||''));
  const search=children.find(n=>n.metadata?.nativeChrome==='search'||n.ref==='q7JLn'||/仓库内搜索|搜索 \/ 当前仓库范围/.test(n.name||''));
  const scene=children.find(n=>{const e=effective(n,components);return e.fill?.type==='image'&&e.y===64&&e.width>=720;});
  if(!header||!selector||!search||!scene)return {updated:false,board:board.id,reason:'Not a complete actual UE scene board'};
  const number=parseInt(board.name),layout=headerLayout(board.width);
  const previousSearch=search.descendants?.UiwzM?.content;
  const override=board.metadata?.nativeChromeState||{};
  const state={area:'全部区域',searchQuery:previousSearch&&previousSearch!=='搜索设备、货位或物料'?previousSearch:'',
    replay:REPLAY.has(number),following:number===47,roofClosed:CLOSED.has(number),panelCollapsed:false,...override,
    clock:{...STATIC_CLOCK,...override.clock,static:true}};
  // Preserve previously materialized state when the utility runs a second time.
  if(search.metadata?.nativeChrome==='search'&&!('searchQuery' in override))state.searchQuery=search.metadata.query||'';
  const next=buildHeader(header,board.width,state,layout);
  materialize(header,next.header);materialize(selector,buildSelector(selector,state,layout));materialize(search,buildSearch(search,state,layout,board.width));
  const oldHint=children.find(n=>n.metadata?.nativeChrome==='hint'||/^底部场景说明$|^底部操作提示/.test(n.name||''));
  const oldHintText=children.find(n=>n.type==='text'&&/左键旋转/.test(n.content||'')&&n.y>=board.height-100);
  const hintId=oldHint?.id||board.id+'-native-hint';
  const preservedHintTextId=oldHintText?.id||(oldHint?.children||[]).find(n=>n.type==='text')?.id;
  const hint=buildHint(hintId,preservedHintTextId,state,layout,board.height);
  // The old footer was a full-width strip plus loose label and data note.
  // Replace only those footer nodes; do not alter any scene/POI layer.
  const obsolete=new Set([oldHintText?.id]);
  board.children=children.filter(n=>!obsolete.has(n.id)&&!(n.name==='场景示例与数据未核验标记'&&n.y>=board.height-100));
  if(oldHint)materialize(oldHint,hint);else board.children.push(hint);
  board.metadata={...board.metadata,nativeChromeUpdated:{implementation:'UE current 2026-10-27',source:SOURCE,staticClock:true,viewport:[board.width,board.height]}};
  return {updated:true,board:board.id,number,headerId:header.id,selectorId:selector.id,searchId:search.id,hintId,panelButtonId:next.panelId,layout,state};
}
module.exports={updateChrome,headerLayout,fontPx,STATIC_CLOCK};
