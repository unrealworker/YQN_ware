(function(){
'use strict';
const M=window.TwinModel,D=M.demo,S=M.createState(),Dropdown=window.TwinDropdown;
let snapshot=null,selectionKey='',toastTimer,renderToken=0,previousFocus=null;
let prepared=M.prepareSnapshot(null),panelVisible=true,snapshotDirty=false,hiddenRestore=false,pendingFocusRefresh=false;
let diagnosticsEnabled=!/(?:^|[?&])diagnostics=(?:0|false)(?:&|$)/i.test(window.location&&window.location.search||'');
const performanceCounts={receivedSnapshots:0,normalizedSnapshots:0,htmlBuilds:0,domWrites:0,skippedRenders:0,hiddenSnapshots:0};
const main=document.getElementById('main'),page=document.getElementById('page'),nav=document.getElementById('navigation');
const colors={running:'#6e91ee',idle:'#bcc6d4',warning:'#da963f',fault:'#cb5663',offline:'#8997aa',unknown:'#d0d7e2',charging:'#356bfa',completed:'#356bfa',executing:'#8daafc',waiting:'#dbe4f2',exception:'#da963f'};
const names={overview:'总览',inventory:'库存',orders:'订单',devices:'设备',alerts:'告警',trace:'追溯',scene:'场景'};
const paths={overview:'M3 3h6v6H3z M15 3h6v6h-6z M3 15h6v6H3z M15 15h6v6h-6z',inventory:'m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3z M4 7.5l8 4.5 8-4.5 M12 12v9 M8 5.2l8 4.5',orders:'M8 5H5v16h14V5h-3 M8 3h8v4H8z M8 11h8 M8 15h8 M8 18h5',devices:'m12 2 5 3v6l-5 3-5-3V5l5-3z M3 13l5-3 5 3v6l-5 3-5-3v-6z M13 13l5-3 5 3v6l-5 3-5-3 M12 2v6 M7 5l5 3 5-3 M8 16v6 M3 13l5 3 5-3 M18 16v6 M13 13l5 3 5-3',alerts:'m12 3 10 18H2L12 3z M12 9v5 M12 17v.1',trace:'M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v6l4 2',scene:'M4 5h7 M15 5h5 M4 12h3 M11 12h9 M4 19h11 M19 19h1 M11 3v4 M7 10v4 M15 17v4',search:'m20 20-5-5 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',close:'M5 5l14 14 M19 5 5 19',back:'m14 5-7 7 7 7',focus:'M9 3H3v6 M15 3h6v6 M3 15v6h6 M21 15v6h-6 M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8',collapse:'M4 4h16v16H4z M9 4v16 M13 8l4 4-4 4',check:'m5 12 4 4L19 6'};
const icon=n=>'<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="'+(paths[n]||paths.devices)+'"/></svg>';
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>Number(v).toLocaleString('en-US');
const pct=(a,b)=>b?(100*a/b).toFixed(1):'0.0';
const attr=(k,v)=>' data-'+k+'="'+esc(v)+'"';
const link=(label,action,attrs='')=>'<button class="link" data-action="'+action+'" '+attrs+'>'+label+'</button>';
function button(label,action,attrs='',primary=false,ic=''){return '<button class="btn '+(primary?'primary':'')+'" data-action="'+action+'" '+attrs+'>'+(ic?icon(ic):'')+label+'</button>';}
function source(scene=false){return '<span class="source '+(scene===true?'scene':'')+'">'+(scene==='unconnected'?'遥测未接入':scene?'场景数据':'演示数据')+'</span>';}
function header(title,subtitle,scene=false,detail=false){return (detail?'<button class="back" data-action="back">'+icon('back')+'返回'+esc(names[S.page]||'列表')+'</button>':'')+'<header class="page-head"><div class="title-row"><h1>'+title+'</h1>'+source(scene)+'</div><p>'+subtitle+'</p></header>';}
function section(title,body,action=''){return '<section class="section"><div class="section-head"><h2>'+title+'</h2>'+action+'</div>'+body+'</section>';}
function kv(label,value){return '<div class="kv"><dt>'+label+'</dt><dd>'+esc(value==null?'—':value)+'</dd></div>';}
function status(s){return '<span class="status '+esc(s)+'">'+esc(M.stateNames[s]||s)+'</span>';}
function ring(parts,center,label){let offset=0;const sum=parts.reduce((s,p)=>s+p.value,0)||1;const arcs=parts.map(p=>{const n=p.value/sum*100;const a='<circle cx="75" cy="75" r="64" fill="none" stroke="'+p.color+'" stroke-width="9" pathLength="100" stroke-dasharray="'+n+' '+(100-n)+'" stroke-dashoffset="'+(-offset)+'"/>';offset+=n;return a}).join('');return '<div class="ring" role="img" aria-label="'+esc(label+' '+center)+'"><svg viewBox="0 0 150 150">'+arcs+'</svg><div class="ring-center"><strong class="num">'+center+'</strong><small>'+label+'</small></div></div>';}
function stack(parts,total){return '<div class="stacked" role="img" aria-label="'+esc(parts.map(p=>p.label+' '+p.value).join('，'))+'">'+parts.map(p=>'<span title="'+esc(p.label+' '+p.value)+'" style="width:'+(total?p.value/total*100:0)+'%;background:'+p.color+'"></span>').join('')+'</div>';}
function legend(parts,inline=false){return '<div class="'+(inline?'legend-inline':'legend')+'">'+parts.map(p=>inline?'<span><i class="swatch" style="background:'+p.color+'"></i>'+p.label+'</span>':'<div class="legend-item"><i class="dot" style="background:'+p.color+'"></i><span>'+p.label+'</span><strong class="num">'+p.value+'</strong></div>').join('')+'</div>';}
function stateBars(rows,facility=false){const counts=M.countStates(rows),keys=facility?['charging','idle','offline']:['running','idle','warning','fault','offline'];if(counts.unknown)keys.push('unknown');const max=Math.max(1,...keys.map(k=>counts[k]||0));return keys.map(k=>'<div class="bar-row"><span>'+M.stateNames[k]+'</span><div class="bar-track"><div class="bar-fill" style="width:'+((counts[k]||0)/max*100)+'%;background:'+colors[k]+'"></div></div><span class="num">'+(counts[k]||0)+'</span></div>').join('');}
function facilityChart(rows){const counts=M.countStates(rows),parts=['charging','idle','offline','unknown'].filter(k=>counts[k]).map(k=>({label:M.stateNames[k],value:counts[k],color:colors[k]}));return '<div class="chart-split">'+ring(parts.length?parts:[{value:1,color:'#e5eaf2'}],String(rows.length),'充电设施 / 个')+legend(parts)+'</div>';}
function search(key,value,placeholder){return '<label class="search" style="display:block">'+icon('search')+'<input type="search" data-search="'+key+'" value="'+esc(value)+'" placeholder="'+placeholder+'" aria-label="'+placeholder+'" autocomplete="off"></label>';}
function select(key,value,items){return Dropdown.render(key,value,items);}
function tabs(key,value,items){return '<div class="tabs" role="tablist">'+items.map(([v,t])=>'<button role="tab" aria-selected="'+(v===value)+'" class="'+(v===value?'active':'')+'" data-action="tab" data-key="'+key+'" data-value="'+v+'">'+t+'</button>').join('')+'</div>';}
function empty(title,copy,reset=''){return '<div class="empty"><strong>'+title+'</strong>'+copy+(reset?'<br>'+link('清除筛选','reset',attr('scope',reset)):'')+'</div>';}
function pager(p,scope,unit){return '<div class="pager"><span class="num">'+p.start+'–'+p.end+' / '+p.total+' '+unit+'</span><div class="pager-controls"><button aria-label="上一页" data-action="page" data-scope="'+scope+'" data-value="'+(p.page-1)+'" '+(p.page===1?'disabled':'')+'>‹</button><span>'+p.page+' / '+p.pages+'</span><button aria-label="下一页" data-action="page" data-scope="'+scope+'" data-value="'+(p.page+1)+'" '+(p.page===p.pages?'disabled':'')+'>›</button></div></div>';}
function equipment(){return S.filters.devices.facility?prepared.facilities:prepared.equipment;}
function findDevice(id){return prepared.byId.get(id);}
function photo(type){return 'assets/'+(M.typeNames[type]?type:'truck')+'.png';}
function equipRow(e){return '<button class="list-row media-row" data-action="device" data-id="'+esc(e.id)+'"><img class="thumb" src="'+photo(e.type)+'" alt="'+M.typeNames[e.type]+'模型"><span><span class="row-title"><span>'+esc(e.id)+'</span><span class="link">详情 →</span></span><span class="row-sub" style="display:block">'+M.typeNames[e.type]+' · '+esc(e.location)+'</span><span class="row-sub '+(e.status==='fault'?'red':e.status==='warning'?'amber':e.status==='running'?'green':'')+'" style="display:block">'+M.stateNames[e.status]+' · '+esc(e.value||e.taskId||'—')+'</span></span></button>';}
function orderParts(direction){return ['completed','executing','waiting','exception'].map(k=>({label:M.stateNames[k],value:D.orders[direction][k],color:colors[k]}));}
function overview(){const c=D.capacity,rows=prepared.equipment;return header('仓库运营总览','今日 · 2026-10-20 / 业务演示快照 14:20:08')+'<div class="kpis"><button class="kpi" data-action="nav" data-page="orders" data-direction="inbound"><span>今日入库 / 单</span><strong class="num">128</strong><small>已完成 96 · 完成率 75.0%</small></button><button class="kpi" data-action="nav" data-page="orders" data-direction="outbound"><span>今日出库 / 单</span><strong class="num">156</strong><small>已完成 118 · 完成率 75.6%</small></button><button class="kpi" data-action="nav" data-page="inventory"><span>已用托位</span><strong class="num">'+fmt(c.occupied)+'</strong><small>总容量 '+fmt(c.total)+' 托位</small></button><button class="kpi" data-action="nav" data-page="inventory"><span>可用托位</span><strong class="num">'+fmt(c.available)+'</strong><small>另有 '+fmt(c.lockedEmpty)+' 个空位锁定</small></button></div>'+section('库容占用','<div class="chart-split">'+ring([{value:c.occupied,color:'#356bfa'},{value:c.available,color:'#dce6ff'},{value:c.lockedEmpty,color:'#aebccc'}],pct(c.occupied,c.total)+'%','占用率')+legend([{label:'已占用',value:pct(c.occupied,c.total)+'%',color:'#356bfa'},{label:'可用',value:pct(c.available,c.total)+'%',color:'#dce6ff'},{label:'空位锁定',value:pct(c.lockedEmpty,c.total)+'%',color:'#aebccc'}])+'</div>',link('查看库存 →','nav',attr('page','inventory')))+section('今日订单进度 · 284 单',['inbound','outbound'].map(d=>'<div class="progress-label"><span>'+(d==='inbound'?'入库':'出库')+'</span><span>'+D.orders[d].completed+' / '+D.orders[d].total+' 已完成</span></div>'+stack(orderParts(d),D.orders[d].total)).join('')+legend(orderParts('inbound').map(p=>({...p,label:p.label.replace('已','').replace('中','')})),true)+'<p class="caption">每条对应各自订单总量（100%）</p>',link('查看订单 →','nav',attr('page','orders')))+section('设备状态 · '+rows.length+' 台',stateBars(rows)+'<p class="caption">'+(snapshot?'设备状态来自当前场景；业务统计为演示。':'浏览器预览 · 设备为演示数据。')+'</p>',link('查看设备 →','nav',attr('page','devices')))+'<div class="notice-row"><span class="amber">7 项设备告警 · 6 单异常订单</span>'+link('查看 →','nav',attr('page','alerts'))+'</div>';}
function inventory(){const f=S.filters.inventory,c=D.capacity,bins=M.rackBins(),binCounts=M.countStates(bins),chosen=bins.find(b=>b.id===f.bin),match=!f.query||['SKU2038','B20261018','电机安装支架','A-03','A-03-12'].some(x=>x.toLowerCase().includes(f.query.toLowerCase()));let detail='';if(chosen){if(chosen.status==='available')detail='<h3>'+chosen.label+' · 空货位</h3><p class="small">可用托位 1 · 当前没有库存物料</p>';else if(chosen.status==='locked')detail='<h3>'+chosen.label+' · 空位锁定</h3><p class="small">维护锁定 · 不计入可用库容</p>';else if(chosen.sku)detail='<h3>A-03-12 · 电机安装支架</h3><p class="small">SKU2038 · 批次 B20261018</p><div class="flex-between"><strong class="num">480 件</strong>'+link('查看物料 →','material')+'</div>';else detail='<h3>'+chosen.label+' · 已占用</h3><p class="small">演示格位未配置物料明细</p>';}
return header('库存与货位','全仓容量 · 业务演示快照 14:20:08')+section('','<div class="big-stat"><strong class="num">'+fmt(c.occupied)+'</strong><span>/ '+fmt(c.total)+' 托位已用</span></div>'+stack([{label:'占用',value:c.occupied,color:'#356bfa'},{label:'可用',value:c.available,color:'#dce6ff'},{label:'锁定',value:c.lockedEmpty,color:'#aebccc'}],c.total)+'<div class="progress-label"><span class="blue">占用 '+pct(c.occupied,c.total)+'%</span><span>可用 '+fmt(c.available)+'</span><span>锁定 '+fmt(c.lockedEmpty)+'</span></div>'+c.regions.map(r=>'<div class="region"><div class="progress-label"><span>'+r.name+'</span><span>'+r.occupied+' / '+r.total+'</span></div>'+stack([{label:'占用',value:r.occupied,color:'#7b9af1'},{label:'可用',value:r.available,color:'#dce6ff'},{label:'锁定',value:r.lockedEmpty,color:'#aebccc'}],r.total)+'</div>').join(''))+section('货架 A-03 · 48 个托位',search('inventory',f.query,'搜索物料 / 批次 / 货位')+'<div class="filters">'+select('inventory.state',f.state,[['all','全部货位'],['occupied','占用'],['available','可用'],['locked','锁定']])+'<span class="badge">演示分布</span></div>'+(match?'<div class="bin-grid">'+bins.map(b=>'<button title="'+b.label+'" aria-label="'+b.label+' '+({occupied:'占用',available:'可用',locked:'锁定'}[b.status])+'" class="bin '+b.status+(f.bin===b.id?' selected':'')+(f.state!=='all'&&f.state!==b.status?' filtered':'')+'" '+(f.state!=='all'&&f.state!==b.status?'disabled ':'')+'data-action="bin" data-id="'+b.id+'">'+String(b.id).padStart(2,'0')+'</button>').join('')+'</div>'+legend([{label:'占用 '+binCounts.occupied,color:'#dce6ff'},{label:'可用 '+binCounts.available,color:'#fff'},{label:'锁定 '+binCounts.locked,color:'#f6e9d4'}],true)+'<div class="selection-card">'+detail+'</div>':empty('未找到匹配物料','检查 SKU、批次或货位编号。','inventory'))+'<p class="caption">示例物料可用 360 件 · 已分配 120 件<br>格位分布为演示；点击场景货架查看实际 CAD 实例。</p>');}
function trend(){const pts=M.trendPoints(),x=p=>30+p.x*282,y=v=>122-v/150*110;let out='<svg class="trend" viewBox="0 0 330 154" role="img" aria-label="累计完成订单趋势：入库96单，出库118单">';[0,75,150].forEach(v=>{out+='<line x1="30" y1="'+y(v)+'" x2="312" y2="'+y(v)+'" stroke="#e5eaf2"/><text x="23" y="'+(y(v)+4)+'" text-anchor="end">'+v+'</text>';});['inbound','outbound'].forEach((key,i)=>out+='<polyline points="'+pts.map(p=>x(p)+','+y(p[key])).join(' ')+'" fill="none" stroke="'+(i?'#356bfa':'#879bb8')+'" stroke-width="2"/>');pts.slice(0,5).forEach((p,i)=>out+='<text x="'+x(p)+'" y="145" text-anchor="'+(i===0?'start':i===4?'end':'middle')+'">'+p.time.slice(0,5)+'</text>');return out+'</svg>';}
function orders(){const f=S.filters.orders,rows=M.filterOrders(M.makeOrders(f.direction),f.query,f.status),p=M.paginate(rows,f.page,5),summary=D.orders[f.direction];f.page=p.page;return header('今日出入库订单','2026-10-20 · 00:00–14:20 / 共 284 单')+tabs('orders.direction',f.direction,[['inbound','入库 128'],['outbound','出库 156']])+'<div class="stats-four">'+['completed','executing','waiting','exception'].map(k=>'<div><strong class="num '+(k==='executing'?'blue':k==='exception'?'amber':'')+'">'+summary[k]+'</strong><span>'+M.stateNames[k]+'</span></div>').join('')+'</div>'+stack(orderParts(f.direction),summary.total)+'<div class="section" style="padding-top:24px"><div class="section-head"><h2>累计完成 / 单</h2><span class="badge">演示趋势</span></div>'+legend([{label:'入库',color:'#879bb8'},{label:'出库',color:'#356bfa'}],true)+trend()+'</div>'+search('orders',f.query,'搜索订单号 / 物料')+'<div class="filters">'+select('orders.status',f.status,[['all','全部状态'],...['completed','executing','waiting','exception'].map(k=>[k,M.stateNames[k]])])+'<span class="filter-tag">今日</span>'+link('只看异常','filter-exception')+'</div><div class="row-list">'+(p.rows.length?p.rows.map(o=>'<button class="list-row '+(o.id===D.material.outbound?'selected':'')+'" data-action="order" data-id="'+o.id+'"><span class="row-title"><span>'+o.id+'</span><span class="link">详情 →</span></span><span class="row-sub" style="display:block">'+o.sku+' · '+o.name+'</span><span class="row-foot"><span>'+o.completed+' / '+o.quantity+' 件</span><span class="'+(o.status==='exception'?'amber':o.status==='executing'?'blue':'')+'">'+o.step+'</span></span></button>').join(''):empty('没有符合条件的订单','换一个订单号或状态继续查找。','orders'))+'</div>'+pager(p,'orders','单');}
function devices(){const f=S.filters.devices,all=equipment(),rows=M.filterEquipment(all,f.query,f.status,f.type),p=M.paginate(rows,f.page,5);f.page=p.page;return header('设备监控',snapshot?'普通仓库 · 场景设备':'浏览器预览 · 演示快照 14:20:08',!!snapshot)+tabs('devices.facility',String(f.facility),[['false','作业设备 '+prepared.equipment.length],['true','充电设施 '+prepared.facilities.length]])+section('',f.facility?facilityChart(all):stateBars(all))+search('devices',f.query,'搜索设备编号 / 任务')+'<div class="filters">'+(f.facility?'':select('devices.type',f.type,[['all','全部类型'],...Object.keys(M.typeNames).filter(k=>k!=='charger').map(k=>[k,M.typeNames[k]])]))+select('devices.status',f.status,[['all','全部状态'],...(f.facility?['charging','idle','offline','unknown']:['running','idle','warning','fault','offline','unknown']).map(k=>[k,M.stateNames[k]])])+'<span class="small muted">异常优先</span></div><div class="row-list">'+(p.rows.length?p.rows.map(equipRow).join(''):empty('没有匹配的设备','调整编号、类型或运行状态。','devices'))+'</div>'+pager(p,'devices',f.facility?'个':'台')+'<p class="caption">图片为设备模型预览。'+(snapshot?'状态来自场景数据；具体来源见详情。':'当前设备列表使用演示数据。')+'</p>';}
function alerts(){const f=S.filters.alerts,all=M.alerts.filter(a=>a.recovered===f.history),rows=all.filter(a=>f.severity==='all'||a.severity===f.severity),pending=all.filter(a=>!a.acknowledged).length;return header('设备告警中心','当前未恢复 7 项 · 业务演示快照 14:20:08')+'<div class="alert-summary"><div><strong class="num">'+all.length+'</strong> <small>'+(f.history?'条恢复记录':'项未恢复告警')+'</small></div><small>待确认 '+pending+' · 已确认 '+(all.length-pending)+'</small></div>'+stack([{label:'故障',value:all.filter(a=>a.severity==='fault').length,color:colors.fault},{label:'预警',value:all.filter(a=>a.severity==='warning').length,color:colors.warning}],all.length)+legend([{label:'故障 '+all.filter(a=>a.severity==='fault').length,color:colors.fault},{label:'预警 '+all.filter(a=>a.severity==='warning').length,color:colors.warning}],true)+tabs('alerts.history',String(f.history),[['false','当前 7'],['true','已恢复记录']])+'<div class="filters">'+select('alerts.severity',f.severity,[['all','全部级别'],['fault','故障'],['warning','预警']])+'<span class="small muted">按严重程度排序</span></div>'+rows.map(a=>{const e=findDevice(a.device);return '<button class="list-row media-row" data-action="alert" data-id="'+a.id+'"><img class="thumb" src="'+photo(e?e.type:'truck')+'" alt="设备模型"><span><span class="row-title"><span>'+a.device+'</span><span class="link">查看 →</span></span><span class="row-sub '+(a.severity==='fault'?'red':'amber')+'" style="display:block">'+a.title+'</span><span class="row-sub" style="display:block">'+a.time+' · '+(a.acknowledged?'已确认':'待确认')+'</span></span></button>'}).join('')+(rows.length?'':empty('暂无恢复记录','确认告警后仍保留，直到异常真正恢复。'))+'<p class="caption">告警确认仅记录处理进度，不代表设备恢复。<br>本页为演示队列，不下发真实设备控制指令。</p>';}
function trace(){const f=S.filters.trace,material=f.mode==='material',found=material&&['sku2038','b20261018','plt202610200038','电机安装支架','a-03-12'].some(v=>v.includes(f.query.toLowerCase().trim()))&&f.date==='2026-10-20';return header('追溯查询',material?'串联批次、货位和关联订单':'查看选定设备的历史运行记录')+tabs('trace.mode',f.mode,[['material','物料追溯'],['device','设备轨迹']])+search('trace',f.query,material?'SKU / 批次 / 托盘编号':'设备编号，如 AGV-07')+'<div class="query-row"><input class="date-input" type="date" value="'+f.date+'" data-filter="trace.date" aria-label="查询日期">'+button('查询','trace-query','',true,'search')+'</div>'+(f.queried?(material?(found?'<div class="section" style="margin-top:28px"><h2>'+D.material.name+'</h2><p class="caption">'+D.material.pallet+' · 当前 A-03-12</p></div><div class="section-head"><h2>5 条流转事件</h2><span class="small muted">最新在下</span></div><ol class="timeline">'+M.trace.map(t=>'<li><time>'+t.time+'</time><div><h3>'+t.title+'</h3><p>'+t.location+'</p><p>'+t.detail+'</p>'+(t.device?link('定位设备 →','device',attr('id',t.device)):t.order?link('查看订单 →','order',attr('id',t.order)):'')+'</div></li>').join('')+'</ol><p class="caption">数量单位为件；事件时间为本地时间。业务演示数据。</p>':empty('没有匹配的流转记录','示例批次 B20261018 的记录日期为 2026-10-20。')):deviceHistory()):'<div class="notice" style="margin-top:24px">设置编号和日期后查询。</div>');}
function deviceHistory(){const e=findDevice(S.filters.trace.query.trim());if(!e)return empty('未找到该设备','输入完整设备编号，例如 AGV-07。');return '<div class="selection-card"><div class="flex-between"><h3>'+esc(e.id)+'</h3>'+status(e.status)+'</div><p class="small">'+M.typeNames[e.type]+' · '+esc(e.location)+'</p>'+link('查看设备 →','device',attr('id',e.id))+'</div><div class="notice">当前场景未接入历史轨迹服务。可定位设备当前坐标；不会将演示路线显示为真实历史。</div><div class="actions">'+button('定位当前设备','focus',attr('id',e.id),true,'focus')+'</div>';}
function settings(){const t=S.settings,presets=[['overview','全仓','warehouse-overview'],['top','俯视','warehouse-overview'],['racks','货架区域','warehouse-racks'],['floor','地堆区域','warehouse-storage']];return header('场景设置','普通仓库 · 场景视图',!!snapshot)+section('常用视角','<div class="preset-grid">'+presets.map(([id,label,img])=>'<button class="preset '+(t.preset===id?'active':'')+'" data-action="preset" data-value="'+id+'"><div class="preset-illustration '+id+'"><img src="assets/'+img+'.png" alt="'+label+'场景参考"></div><span>'+label+'</span>'+(t.preset===id?'<span class="preset-check">'+icon('check')+'</span>':'')+'</button>').join('')+'</div>')+section('图层显示',[['racks','货架与建筑','显示仓库空间结构'],['equipment','作业设备','车辆、叉车与 AGV'],['pois','POI 标签','显示编号与运行状态']].map(([key,label,copy])=>'<div class="setting-row"><div><h3>'+label+'</h3><p>'+copy+'</p></div><button role="switch" aria-label="'+label+'" aria-checked="'+t[key]+'" class="switch" data-action="toggle" data-key="'+key+'"></button></div>').join(''))+section('标签密度',tabs('settings.density',t.density,[['minimal','精简'],['auto','标准'],['all','全部']])+'<p class="caption">远景自动聚合；选中与异常设备优先显示。</p>')+'<div class="actions">'+button('恢复默认','settings-reset')+button('应用到当前视图','settings-apply','',true)+'</div><p class="caption">视角切换平滑移动。图层与标签设置仅改变当前观察方式。</p>';}
function deviceDetail(detail){const e=findDevice(detail.id);if(!e)return header('设备详情','所选设备未在当前快照中',!!snapshot,true)+empty('当前设备已不可用','返回设备列表刷新选择。');const live=!!snapshot&&e.live&&!e.demo;const progress=e.progress==null?null:(e.progress<=1&&e.progress>0?e.progress*100:e.progress);const progressLabel=e.type==='agv'||e.type==='stacker'?'剩余电量':e.type==='charger'?'充电进度':'任务进度';let body='';if(S.deviceTab==='status'){body='<div class="device-metrics">'+(progress==null?ring([{value:1,color:'#e5eaf2'}],'—',progressLabel):ring([{value:progress,color:e.status==='warning'?'#da963f':'#356bfa'},{value:Math.max(0,100-progress),color:'#e5ebf6'}],Math.round(progress)+'%',progressLabel))+'<div><p class="small muted">'+esc(e.available===false?'数据状态':e.metric||'当前状态')+'</p><div class="metric-value num" style="'+(e.available===false?'font-size:16px':'')+'">'+esc(e.available===false?(e.status==='offline'?'设备离线':'遥测未接入'):e.value||'—')+'</div><p class="small muted">'+esc(e.available===false?'场景位置仍可定位':e.title||M.typeNames[e.type])+'</p></div></div>'+section('当前任务','<div class="flex-between"><span class="small muted">任务编号</span><span class="small">'+esc(e.taskId||(e.available===false?'未接入':'暂无任务'))+'</span></div>'+(e.taskId?'<div class="steps"><div class="step">任务下发<small>已接收</small></div><div class="step">前往目标点<small>已就绪</small></div><div class="step current">'+(e.status==='running'?'运输中':M.stateNames[e.status])+'<small>当前状态</small></div></div>':'')+kv('当前位置',e.location));}else if(S.deviceTab==='task')body=section('作业信息',kv('任务编号',e.taskId||'—')+kv('设备类型',M.typeNames[e.type])+kv('当前状态',M.stateNames[e.status])+kv('所在位置',e.location)+'<p class="caption">'+(live?'任务字段由场景组件提供。':e.demo?'设备遥测为场景演示数据。':'尚未接入设备遥测，未知字段保留为空。')+'</p>');else body=section('关联事件',M.alerts.filter(a=>a.device===e.id).map(a=>'<div class="list-row"><div class="flex-between"><span>'+a.title+'</span>'+link('查看 →','alert',attr('id',a.id))+'</div><p class="caption">'+a.time+' · 演示告警</p></div>').join('')||'<div class="notice">演示队列中没有该设备的当前告警。</div>');return header('设备详情',(live?'场景组件数据':e.demo?'设备演示数据':'已定位场景对象 · 遥测未接入')+' · '+esc(e.id),live?true:e.demo?false:'unconnected',true)+'<button class="device-photo" data-action="photo" data-type="'+e.type+'" data-id="'+esc(e.id)+'"><img src="'+photo(e.type)+'" alt="'+M.typeNames[e.type]+'模型预览"></button><div class="image-caption"><span>设备模型预览</span>'+link('放大查看 ↗','photo',attr('type',e.type)+attr('id',e.id))+'</div><div class="flex-between"><h2 class="device-id">'+esc(e.id)+'</h2>'+status(e.status)+'</div><p class="caption">'+M.typeNames[e.type]+' · '+esc(e.location)+'</p>'+tabs('deviceTab',S.deviceTab,[['status','运行状态'],['task','任务信息'],['events','事件']])+body+'<div class="actions device-actions">'+button('定位设备','focus',attr('id',e.id),true,'focus')+button('历史追溯','device-trace',attr('id',e.id),false,'trace')+'</div>';}
function materialDetail(){const d=D.material;return header('货架物料详情','演示物料 · A-03-12',false,true)+'<div class="selection-card"><h2>'+d.name+'</h2><p class="small">'+d.sku+' · '+d.model+'</p><div class="flex-between"><strong>'+d.quantity+' <small>件</small></strong><span class="small">'+d.boxes+' 箱 × '+d.perBox+' 件</span></div></div>'+section('库存分配','<div class="chart-split">'+ring([{value:d.available,color:'#356bfa'},{value:d.allocated,color:'#c4d5ff'}],d.available+'','可用 / 件')+legend([{label:'可用',value:d.available+' 件',color:'#356bfa'},{label:'已分配',value:d.allocated+' 件',color:'#c4d5ff'}])+'</div>')+section('物料信息',kv('SKU',d.sku)+kv('规格',d.model)+kv('批次',d.batch)+kv('托盘',d.pallet)+kv('货位',d.bin)+kv('入库时间','2026-10-20 10:12')+kv('包装','24 箱 / 1 托'))+section('关联订单','<div class="list-row"><div class="row-title"><span>'+d.inbound+'</span>'+link('查看 →','order',attr('id',d.inbound))+'</div><p class="row-sub">入库 480 件 · 已完成</p></div><div class="list-row"><div class="row-title"><span>'+d.outbound+'</span>'+link('查看 →','order',attr('id',d.outbound))+'</div><p class="row-sub">已分配 120 件 · 待拣货</p></div>')+'<div class="actions">'+button('物料追溯','material-trace','',true,'trace')+'</div><p class="caption">该物料为批准设计的业务示例，尚未绑定 WMS。</p>';}
function rackDetail(detail){return header(detail.kind==='material'?'场景物料详情':'场景货架详情','当前选中的 CAD 实例',true,true)+'<div class="cad-preview"><img src="assets/warehouse-racks.png" alt="货架区域模型参考"><span>货架区域模型参考</span></div><h2 style="font-size:20px">'+esc(detail.title||detail.id||'货架实例')+'</h2><p class="caption">'+esc(detail.location||'当前场景')+'</p><div class="divider"></div>'+kv('CAD 标识',detail.cadId||detail.id)+kv('实例序号',detail.instanceIndex==null?'—':detail.instanceIndex)+(detail.level?kv('货架层',detail.level):'')+(detail.column?kv('货架列',detail.column):'')+kv('场景类型',detail.kind==='material'?'托盘 / 物料实例':'货架实例')+(detail.actor?kv('场景对象',detail.actor):'')+'<div class="notice" style="margin-top:20px">该空间对象已定位。库存数量、SKU 和批次尚未接入业务系统，因此保留为空。</div><div class="actions">'+button('查看演示物料','material','',true)+'</div><p class="caption">演示物料 SKU2038 独立展示，不代表此 CAD 实例的实际库存。</p>';}
function orderDetail(detail){const dir=detail.id.startsWith('IN')?'inbound':'outbound',o=M.makeOrders(dir).find(r=>r.id===detail.id);if(!o)return header('订单详情','业务演示数据',false,true)+empty('未找到订单','请返回订单列表。');return header(dir==='inbound'?'入库订单详情':'出库订单详情','业务演示 · 2026-10-20',false,true)+'<div class="flex-between"><h2>'+o.id+'</h2>'+status(o.status)+'</div><p class="caption">'+o.step+' · 计划 '+o.dueAt+' 前完成</p>'+section('作业进度','<div class="big-stat"><strong class="num">'+o.completed+'</strong><span>/ '+o.quantity+' 件'+(dir==='inbound'?'入库':'出库')+'</span></div>'+stack([{label:'完成',value:o.completed,color:'#356bfa'},{label:'剩余',value:o.quantity-o.completed,color:'#e5ebf6'}],o.quantity)+'<p class="caption">完成率 '+pct(o.completed,o.quantity)+'% · 剩余 '+(o.quantity-o.completed)+' 件</p>')+section('物料','<div class="flex-between"><h3>'+o.name+'</h3>'+(o.sku==='SKU2038'?link('物料详情 →','material'):'')+'</div>'+kv('SKU',o.sku)+kv('计划数量',o.quantity+' 件')+kv('源位置',o.from)+kv('目标位置',o.to))+section('执行信息',kv('关联任务',o.task)+kv('执行设备',o.device)+kv('任务步骤',o.step)+'<div class="steps"><div class="step">订单创建<small>已下发</small></div><div class="step current">'+o.step+'<small>当前</small></div><div class="step">作业完成<small>'+(o.status==='completed'?'已完成':'待完成')+'</small></div></div>')+'<div class="actions">'+button('定位执行设备','device',attr('id',o.device),true,'focus')+'</div>';}
function alertDetail(detail){const a=M.alerts.find(a=>a.id===detail.id);if(!a)return alerts();const e=findDevice(a.device);return header('告警详情','演示告警 · '+a.time,false,true)+'<button class="device-photo" data-action="device" data-id="'+a.device+'"><img src="'+photo(e?e.type:'truck')+'" alt="告警设备模型"></button><div class="image-caption"><span>关联设备模型预览</span><span>'+a.device+'</span></div><div class="flex-between"><h2 style="font-size:20px">'+a.title+'</h2>'+status(a.severity)+'</div><p class="caption">'+a.device+' · 尚未恢复</p>'+(a.device==='AGV-12'?'<div class="device-metrics">'+ring([{value:18,color:colors.warning},{value:82,color:'#e5ebf6'}],'18%','当前电量')+'<div><p class="small muted">预警阈值</p><div class="metric-value">20<small>%</small></div><p class="small amber">低于阈值 2%</p></div></div>':'<div class="divider"></div>')+section('处理状态',kv('发生时间','2026-10-20 '+a.time)+kv('确认状态',a.acknowledged?'已确认':'待确认')+kv('恢复状态','未恢复')+'<div class="notice">确认表示已接手处理，不会解除告警或恢复设备。</div>')+(a.device==='AGV-12'?section('建议关联设施','<div class="media-row"><img class="thumb" src="assets/charger.png" alt="充电设施模型"><div><h3>CH-12 · 充电区 C</h3><p class="caption">演示设施 · 空闲</p>'+link('查看设施 →','device',attr('id','CH-12'))+'</div></div>'):'')+'<div class="actions">'+button(a.acknowledged?'已确认':'确认告警','ack',attr('id',a.id)+(a.acknowledged?' disabled':''),true)+button('定位设备','device',attr('id',a.device),false,'focus')+'</div>';}
const renderers={overview,inventory,orders,devices,alerts,trace,scene:settings};
function content(){if(S.detail){switch(S.detail.kind){case'device':return deviceDetail(S.detail);case'material-demo':return materialDetail();case'order':return orderDetail(S.detail);case'alert':return alertDetail(S.detail);default:return rackDetail(S.detail);}}return renderers[S.page]();}
const fields=(row,keys)=>row?keys.map(key=>row[key]??null):null;
const stateCounts=counts=>Object.keys(M.stateNames).map(key=>counts[key]||0);
// This key describes the visible business view, not the entire native scene.
// Comparing it before content() avoids HTML/SVG generation for irrelevant updates.
function contentDependency(){
  let data=null;const detail=S.detail,f=S.filters[S.page];
  if(detail){
    if(detail.kind==='device'){
      const e=findDevice(detail.id),base=['id','type','status','location','live','demo'];
      if(S.deviceTab==='status')base.push('progress','available','metric','value','title','taskId');
      else if(S.deviceTab==='task')base.push('taskId');
      data=[!!snapshot,S.deviceTab,fields(e,base),S.deviceTab==='events'?M.alerts.filter(a=>a.device===detail.id):null];
    }else if(detail.kind==='alert'){
      const alert=M.alerts.find(a=>a.id===detail.id),e=alert&&findDevice(alert.device);
      data=[alert,e&&e.type];
    }else if(detail.kind!=='material-demo'&&detail.kind!=='order')data=fields(detail,['kind','id','title','location','cadId','instanceIndex','level','column','actor']);
  }else if(S.page==='overview')data=[!!snapshot,prepared.equipment.length,stateCounts(prepared.equipmentStates)];
  else if(S.page==='devices'){
    const rows=equipment(),filtered=M.filterEquipment(rows,f.query,f.status,f.type),p=M.paginate(filtered,f.page,5);
    data=[!!snapshot,prepared.equipment.length,prepared.facilities.length,stateCounts(f.facility?prepared.facilityStates:prepared.equipmentStates),f,p.page,p.total,p.rows.map(e=>fields(e,['id','type','location','status','value','taskId']))];
  }else if(S.page==='alerts')data=[f,M.alerts.map(a=>[a,(findDevice(a.device)||{}).type])];
  else if(S.page==='trace')data=[f,f.mode==='device'&&f.queried?fields(findDevice(f.query.trim()),['id','type','status','location']):null];
  else if(S.page==='scene')data=[!!snapshot,S.settings];
  else data=f;
  return JSON.stringify([viewKey(),data]);
}
// DOM identity belongs to the visible view, while S may already target the next one.
// Refreshes only update the snapshot during a transition; they cannot replace or restart it.
const motionPreference=window.matchMedia?window.matchMedia('(prefers-reduced-motion: reduce)'):null;
const viewFocus={};
let displayedKey='',renderedHtml='',renderedDependency='',transitionPhase='idle',transitionTimer=0,transitionSerial=0,deferredRender=false,restoreNext=false,reportTimer=0;
const recentPhases=[];
function recordTransitionPhase(){
  if(!diagnosticsEnabled||!panelVisible)return;
  const opacity=window.getComputedStyle?Number(window.getComputedStyle(page).opacity):null;
  recentPhases.push({phase:transitionPhase,atMs:window.performance?window.performance.now():Date.now(),opacity,displayedView:displayedKey,targetView:viewKey(),serial:transitionSerial});
  if(recentPhases.length>8)recentPhases.shift();
}
function viewKey(){return S.page+(S.detail?':'+S.detail.kind+':'+S.detail.id:'');}
function captureFocus(){
  const active=Dropdown.getAnchor()||document.activeElement;
  if(!active||!page.contains(active)||!active.dataset)return null;
  const keys=['search','filter','action','id','key','value','scope','page'].filter(key=>active.dataset[key]!=null);
  if(!keys.length)return null;
  const quote=value=>String(value).replace(/\\/g,'\\\\').replace(/"/g,'\\"');
  return{selector:keys.map(key=>'[data-'+key+'="'+quote(active.dataset[key])+'"]').join(''),start:active.selectionStart,end:active.selectionEnd};
}
function restoreFocus(bookmark){
  if(!bookmark)return false;const target=page.querySelector(bookmark.selector);if(!target)return false;
  target.focus({preventScroll:true});
  if(typeof bookmark.start==='number'&&target.setSelectionRange){try{target.setSelectionRange(bookmark.start,bookmark.end);}catch(e){}}
  return true;
}
function saveScroll(){
  if(!displayedKey||transitionPhase==='out')return;
  S.scroll[displayedKey]=main.scrollTop;
  const bookmark=captureFocus();if(bookmark)viewFocus[displayedKey]=bookmark;
}
function renderNavigation(){
  // Keep the navigation nodes so a keyboard user does not lose their focused destination.
  if(!nav.innerHTML)nav.innerHTML=Object.keys(names).map(k=>'<button aria-label="'+names[k]+'" title="'+names[k]+'" data-action="nav" data-page="'+k+'">'+icon(k)+'<span>'+names[k]+'</span></button>').join('')+'<div class="nav-camera" role="group" aria-label="场景视角"><button class="nav-zoom" aria-label="放大场景" title="放大场景" data-action="zoomIn">+</button><button class="nav-zoom" aria-label="缩小场景" title="缩小场景" data-action="zoomOut">−</button><button class="nav-utility" aria-label="返回全仓并取消选中" title="返回全仓并取消选中" data-action="overview">'+icon('focus')+'<span>全仓</span></button></div>';
  nav.querySelectorAll('[data-page]').forEach(button=>{const active=button.dataset.page===S.page;button.classList.toggle('active',active);if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
}
function scheduleReport(){
  clearTimeout(reportTimer);if(!diagnosticsEnabled||!panelVisible)return;
  const token=renderToken;reportTimer=setTimeout(()=>{if(token===renderToken&&transitionPhase==='idle')report();},40);
}
function paint(restore,enter=false){
  const bookmark=captureFocus(),key=viewKey(),scroll=restore?(S.scroll[key]||0):main.scrollTop;
  const dependency=contentDependency();
  if(dependency!==renderedDependency){
    ++performanceCounts.htmlBuilds;const html=content();
    if(renderedHtml!==html){Dropdown.close(false);page.innerHTML=html;renderedHtml=html;++performanceCounts.domWrites;}
    // Pagination may clamp a stale page number while rendering.
    renderedDependency=contentDependency();
  }else ++performanceCounts.skippedRenders;
  ++renderToken;displayedKey=key;
  page.className='view-'+S.page+(S.detail&&S.detail.kind==='device'?' detail-device':'')+(enter?' page-enter-start':'');
  main.scrollTop=scroll;
  if(!restoreFocus(restore?viewFocus[key]:bookmark)&&bookmark)main.focus({preventScroll:true});
  renderNavigation();
}
function finishTransition(){
  transitionPhase='idle';page.classList.remove('page-leave','page-enter-start','page-enter');main.removeAttribute('aria-busy');
  if(deferredRender){deferredRender=false;paint(false);}
  recordTransitionPhase();
  scheduleReport();
}
function completeWithoutMotion(){
  const restore=transitionPhase==='in'?false:restoreNext;
  if(transitionPhase==='idle')recentPhases.length=0;
  clearTimeout(transitionTimer);++transitionSerial;transitionPhase='idle';deferredRender=false;
  paint(restore);main.removeAttribute('aria-busy');recordTransitionPhase();scheduleReport();
}
function render(animate=false,restore=false){
  if(!panelVisible){hiddenRestore=hiddenRestore||restore;return;}
  if(animate)Dropdown.close(false);
  renderNavigation();
  if(!animate){if(transitionPhase!=='idle'){deferredRender=true;return;}paint(restore);scheduleReport();return;}
  restoreNext=restore||transitionPhase==='out'&&restoreNext;
  if(!displayedKey||motionPreference&&motionPreference.matches){completeWithoutMotion();return;}
  // Another request during fade-out changes its destination, not its starting time.
  if(transitionPhase==='out')return;
  clearTimeout(transitionTimer);const serial=++transitionSerial;
  if(transitionPhase==='idle')recentPhases.length=0;
  transitionPhase='out';main.setAttribute('aria-busy','true');
  page.classList.remove('page-enter-start','page-enter');page.classList.add('page-leave');
  recordTransitionPhase();
  transitionTimer=setTimeout(()=>{
    if(serial!==transitionSerial)return;
    transitionPhase='in';deferredRender=false;paint(restoreNext,true);
    recordTransitionPhase();
    void page.offsetWidth;
    requestAnimationFrame(()=>{
      if(serial!==transitionSerial)return;
      page.classList.remove('page-enter-start');page.classList.add('page-enter');
      transitionTimer=setTimeout(()=>{if(serial===transitionSerial)finishTransition();},200);
    });
  },120);
}
if(motionPreference){const changed=()=>{if(motionPreference.matches&&transitionPhase!=='idle')completeWithoutMotion();};if(motionPreference.addEventListener)motionPreference.addEventListener('change',changed);else if(motionPreference.addListener)motionPreference.addListener(changed);}
function navigate(p){if(p==='settings')p='scene';if(!names[p])return;saveScroll();M.navigate(S,p);render(true,true);}
function open(detail){saveScroll();M.openDetail(S,detail);S.deviceTab='status';render(true,true);}
function back(){saveScroll();M.back(S);render(true,true);}
function toast(message){const el=document.getElementById('toast');clearTimeout(toastTimer);el.textContent=message;el.classList.add('show');toastTimer=setTimeout(()=>el.classList.remove('show'),3000);}
function command(payload,quiet=false){if(window.ue&&window.ue.twin&&typeof window.ue.twin.command==='function'){try{const result=window.ue.twin.command(JSON.stringify(payload));if(result&&result.catch)result.catch(()=>toast('场景连接暂不可用，请稍后重试。'));}catch(e){toast('场景连接暂不可用。');}}else if(!quiet)toast('浏览器预览：'+({select:'已选择示例对象',focus:'场景定位需在 Unreal 中运行',preset:'视角切换需在 Unreal 中运行',layers:'图层设置已保存',poiDensity:'标签密度已保存',overview:'全仓视角需在 Unreal 中运行'}[payload.action]||'设置已保存'));}
function setNested(key,value){const parts=key.split('.');if(parts[0]==='deviceTab'){S.deviceTab=value;return;}if(parts[0]==='settings'){S.settings[parts[1]]=value;return;}const f=S.filters[parts[0]];if(!f)return;f[parts[1]]=value==='true'?true:value==='false'?false:value;if('page'in f)f.page=1;}
function selectDevice(id){open({kind:'device',id});command({action:'select',id},true);}
document.addEventListener('click',event=>{const el=event.target.closest('[data-action]');if(!el||el.disabled||transitionPhase!=='idle'&&page.contains(el))return;const a=el.dataset.action;switch(a){case'nav':command({action:'navigate',page:el.dataset.page},true);if(el.dataset.direction)S.filters.orders.direction=el.dataset.direction;navigate(el.dataset.page);break;case'back':back();break;case'overview':command({action:'overview'});break;case'zoomIn':case'zoomOut':command({action:a});break;case'device':selectDevice(el.dataset.id);break;case'focus':command({action:'focus',id:el.dataset.id});break;case'material':open({kind:'material-demo',id:'SKU2038'});break;case'order':open({kind:'order',id:el.dataset.id});break;case'alert':open({kind:'alert',id:el.dataset.id});break;case'bin':S.filters.inventory.bin=Number(el.dataset.id);render();break;case'page':saveScroll();S.filters[el.dataset.scope].page=Number(el.dataset.value);S.scroll[viewKey()]=0;render(true,true);break;case'tab':setNested(el.dataset.key,el.dataset.value);if(el.dataset.key==='devices.facility'){S.filters.devices.status='all';S.filters.devices.type='all';}if(el.dataset.key==='trace.mode'){S.filters.trace.query=el.dataset.value==='material'?'SKU2038':'AGV-07';S.filters.trace.queried=false;}render(true);break;case'filter-exception':S.filters.orders.status='exception';S.filters.orders.page=1;render();break;case'reset':{const scope=el.dataset.scope,defaults=M.createState().filters[scope];Object.assign(S.filters[scope],defaults);render();break;}case'ack':{const alert=M.alerts.find(a=>a.id===el.dataset.id);if(alert)alert.acknowledged=true;render();toast('演示告警已确认，恢复状态仍为“未恢复”。');break;}case'trace-query':S.filters.trace.queried=true;render(true);break;case'material-trace':navigate('trace');S.filters.trace.mode='material';S.filters.trace.query='SKU2038';S.filters.trace.queried=true;render();break;case'device-trace':navigate('trace');S.filters.trace.mode='device';S.filters.trace.query=el.dataset.id;S.filters.trace.queried=true;render();break;case'preset':S.settings.preset=el.dataset.value;command({action:'preset',value:el.dataset.value});render();break;case'toggle':S.settings[el.dataset.key]=!S.settings[el.dataset.key];el.setAttribute('aria-checked',String(S.settings[el.dataset.key]));break;case'settings-apply':command({action:'layers',equipment:S.settings.equipment,racks:S.settings.racks,pois:S.settings.pois},true);command({action:'poiDensity',value:S.settings.density},true);toast('当前视图设置已应用。');break;case'settings-reset':Object.assign(S.settings,M.createState().settings);command({action:'layers',equipment:true,racks:true,pois:true},true);command({action:'poiDensity',value:'auto'},true);render();toast('已恢复默认图层和标签密度。');break;case'photo':openPhoto(el.dataset.type,el.dataset.id);break;case'close-photo':closePhoto();break;}});
let composingSearch=null;
function applySearchInput(input){
  const scope=input.dataset.search;if(!scope)return;
  if(S.filters[scope].query===input.value)return;
  S.filters[scope].query=input.value;
  if(scope==='trace'){S.filters.trace.queried=false;return;}
  S.filters[scope].page=1;
  const pos=input.selectionStart,scroll=main.scrollTop;render();
  const restored=document.querySelector('[data-search="'+scope+'"]');
  if(restored){restored.focus();try{restored.setSelectionRange(pos,pos);}catch(e){}}
  main.scrollTop=scroll;
}
// Keep the same editable element throughout IME composition. Rebuilding the
// page for each provisional syllable cancels the operating system candidate UI.
document.addEventListener('compositionstart',event=>{if(event.target.dataset.search)composingSearch=event.target;});
document.addEventListener('compositionend',event=>{if(event.target===composingSearch){composingSearch=null;applySearchInput(event.target);}});
document.addEventListener('input',event=>{if(event.isComposing||event.target===composingSearch)return;applySearchInput(event.target);});
document.addEventListener('change',event=>{if(!event.target.dataset.filter)return;setNested(event.target.dataset.filter,event.target.value);if(event.target.dataset.filter.startsWith('trace'))S.filters.trace.queried=false;render();});
function openPhoto(type,id){const modal=document.getElementById('modal');previousFocus=document.activeElement;modal.innerHTML='<button class="close" data-action="close-photo" aria-label="关闭图片">'+icon('close')+'</button><h2>'+esc(id)+'</h2><img src="'+photo(type)+'" alt="'+M.typeNames[type]+'模型大图"><p class="small muted">设备模型预览 · '+M.typeNames[type]+'</p>';modal.hidden=false;modal.querySelector('button').focus();}
function closePhoto(){document.getElementById('modal').hidden=true;if(previousFocus&&previousFocus.isConnected)previousFocus.focus();}
document.addEventListener('keydown',e=>{if(e.defaultPrevented)return;const modal=document.getElementById('modal');if(e.key==='Escape'){if(!modal.hidden){closePhoto();e.stopPropagation();}else if(S.detail){if(window.ue&&window.ue.twin)command({action:'clear'},true);else back();e.stopPropagation();}}if(e.key==='Tab'&&!modal.hidden){e.preventDefault();modal.querySelector('button').focus();}});
function normalizePendingSnapshot(){
  if(!snapshotDirty)return;
  prepared=M.prepareSnapshot(snapshot);snapshotDirty=false;++performanceCounts.normalizedSnapshots;
}
function updateSceneDetailRecords(selection){
  if(!selection||!selection.id||selection.kind==='device')return;
  const matches=detail=>detail&&detail.kind===selection.kind&&detail.id===selection.id&&(detail.instanceIndex??null)===(selection.instanceIndex??null);
  // Native messages carry a full record. Replacing it removes optional fields
  // absent from the new snapshot, including details temporarily in the Back stack.
  if(matches(S.detail))S.detail=Object.assign({},selection);
  S.stack.forEach(frame=>{if(matches(frame.detail))frame.detail=Object.assign({},selection);});
}
function receiveSnapshot(value){
  let next=value;if(typeof next==='string'){try{next=JSON.parse(next);}catch(e){return;}}
  if(!next||typeof next!=='object')return;
  ++performanceCounts.receivedSnapshots;snapshot=next;snapshotDirty=true;
  if(panelVisible)normalizePendingSnapshot();else ++performanceCounts.hiddenSnapshots;
  const selection=next.selection;
  updateSceneDetailRecords(selection);
  const key=selection&&selection.id?selection.kind+':'+selection.id+':'+(selection.instanceIndex??''):'';
  if(key&&key!==selectionKey){
    selectionKey=key;
    if(!(S.detail&&S.detail.kind==='device'&&selection.kind==='device'&&S.detail.id===selection.id)){
      open(selection.kind==='device'?{kind:'device',id:selection.id}:Object.assign({},selection));return;
    }
  }else if(!key)selectionKey='';
  if(!panelVisible)return;
  if(transitionPhase!=='idle'){deferredRender=true;return;}
  const active=document.activeElement;
  if(Dropdown.isOpen()||active&&(active.tagName==='INPUT'||active.tagName==='SELECT'||active.dataset&&active.dataset.filter)){pendingFocusRefresh=true;return;}
  if(contentDependency()===renderedDependency){++performanceCounts.skippedRenders;return;}
  render();
}
window.twinReceive=receiveSnapshot;
// A focused control owns its DOM until focus leaves. The latest normalized snapshot
// is retained, and a later user action or focus-out consumes it without resetting scroll.
function refreshAfterControlBlur(){if(!pendingFocusRefresh)return;setTimeout(()=>{
  const active=document.activeElement;if(Dropdown.isOpen()||active&&(active.tagName==='INPUT'||active.tagName==='SELECT'||active.dataset&&active.dataset.filter))return;
  pendingFocusRefresh=false;if(panelVisible)render();
},0);}
document.addEventListener('focusout',refreshAfterControlBlur);
document.addEventListener('twin-dropdown-close',refreshAfterControlBlur);
window.twinSetVisibility=function(value){
  const visible=!!value;if(visible===panelVisible)return;
  if(!visible){
    saveScroll();Dropdown.close(false);hiddenRestore=transitionPhase==='out'?restoreNext:false;panelVisible=false;
    clearTimeout(transitionTimer);clearTimeout(reportTimer);++transitionSerial;
    transitionPhase='idle';deferredRender=false;main.removeAttribute('aria-busy');
    page.classList.remove('page-leave','page-enter-start','page-enter');return;
  }
  panelVisible=true;normalizePendingSnapshot();pendingFocusRefresh=false;
  const restore=hiddenRestore||displayedKey!==viewKey();hiddenRestore=false;
  render(false,restore);recordTransitionPhase();
};
window.twinSetDiagnostics=function(value){
  const enabled=!!value;if(enabled===diagnosticsEnabled)return;
  diagnosticsEnabled=enabled;clearTimeout(reportTimer);
  if(enabled){recordTransitionPhase();scheduleReport();}else recentPhases.length=0;
};
window.twinGetPerformance=function(){return Object.assign({},performanceCounts,{visible:panelVisible,diagnostics:diagnosticsEnabled});};

function report(){
  if(!diagnosticsEnabled||!panelVisible)return;
  const actions=document.querySelector('.device-actions'),bounds=actions?actions.getBoundingClientRect():null;
  const tolerance=1,visual=window.visualViewport;
  const actionBounds=bounds?{left:bounds.left,top:bounds.top,right:bounds.right,bottom:bounds.bottom,width:bounds.width,height:bounds.height}:null;
  const designViewport=window.TwinViewport?window.TwinViewport.getState():{width:innerWidth,height:innerHeight,zoom:1};
  const viewport={design:designViewport,width:innerWidth,height:innerHeight,clientWidth:document.documentElement.clientWidth,clientHeight:document.documentElement.clientHeight,devicePixelRatio:window.devicePixelRatio||1,visual:visual?{width:visual.width,height:visual.height,scale:visual.scale,offsetLeft:visual.offsetLeft,offsetTop:visual.offsetTop}:null};
  // Chromium rounds innerWidth/Height to integers while DOMRects retain fractional
  // CSS pixels at Windows 150% scaling. Only the visibility predicate tolerates 1px;
  // raw rectangles, strict visibility and each scroll extent remain in the report.
  command({action:'report',page:S.page==='scene'?'settings':S.page,detail:S.detail?{kind:S.detail.kind,id:S.detail.id}:null,equipmentCount:prepared.equipment.length,facilityCount:prepared.facilities.length,width:innerWidth,height:innerHeight,viewport,transition:{phase:transitionPhase,durationMs:motionPreference&&motionPreference.matches?0:320,displayedView:displayedKey,recentPhases:recentPhases.slice()},detailActionBounds:actionBounds,visibilityToleranceCssPx:tolerance,detailActionsStrictlyVisible:bounds?bounds.left>=0&&bounds.top>=0&&bounds.right<=innerWidth&&bounds.bottom<=innerHeight:null,detailActionsVisible:bounds?bounds.left>=-tolerance&&bounds.top>=-tolerance&&bounds.right<=innerWidth+tolerance&&bounds.bottom<=innerHeight+tolerance:null,overflow:document.documentElement.scrollWidth>designViewport.width+1||main.scrollWidth>main.clientWidth||nav.scrollWidth>nav.clientWidth,scrollExtents:{document:document.documentElement.scrollWidth,main:main.scrollWidth,mainClient:main.clientWidth,navigation:nav.scrollWidth,navigationClient:nav.clientWidth},imageFailures:Array.from(document.images).filter(i=>i.complete&&!i.naturalWidth).map(i=>i.getAttribute('src')),charts:document.querySelectorAll('.ring svg,.trend').length,performance:window.twinGetPerformance()},true);
}
window.twinNavigate=navigate;window.twinBack=back;window.twinState=S;
// Clearing a scene pick closes the entire detail stack; ordinary Back still
// walks that stack. This is a native notification and must not echo a clear command.
window.twinClearSelection=function(){if(!S.detail&&!S.stack.length)return;saveScroll();M.navigate(S,S.page);render(true,true);};
// Explicit scene picks differ from periodic telemetry refreshes: re-picking an
// object must reopen it even when its identity did not change since the last snapshot.
window.twinSelect=function(value){selectionKey='';window.twinReceive(value);};
window.twinFilterType=function(type){S.filters.devices.facility=type==='charger';S.filters.devices.type=type==='charger'?'all':type;S.filters.devices.query='';S.filters.devices.status='all';S.filters.devices.page=1;navigate('devices');};
window.twinSearch=function(text){
  const query=String(text||'').trim(),key=query.toLowerCase();
  if(['sku2038','电机安装支架','bh-m8','b20261018',D.material.pallet.toLowerCase()].includes(key)){
    S.filters.inventory.query='';S.filters.inventory.bin=12;S.filters.inventory.state='all';
    navigate('inventory');open({kind:'material-demo',id:'SKU2038'});return;
  }
  if(key==='a-03'||key==='a-03-12'){
    S.filters.inventory.query='';S.filters.inventory.bin=12;S.filters.inventory.state='all';navigate('inventory');return;
  }
  S.filters.devices.query=query;S.filters.devices.type='all';S.filters.devices.status='all';S.filters.devices.facility=/^CH-/i.test(query);S.filters.devices.page=1;navigate('devices');
};
render();command({action:'ready'},true);let attempts=0;const readyTimer=setInterval(()=>{if(snapshot||++attempts>20){clearInterval(readyTimer);return;}command({action:'ready'},true);},500);
})();

