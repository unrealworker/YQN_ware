(function(root){
'use strict';
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('en-US');
const labels={occupied:'有货',empty:'空货位',unknown:'待核验'};
const stateText=s=>labels[s]||labels.unknown;
const kv=(k,v)=>'<div class="inventory-field"><span>'+esc(k)+'</span><strong>'+esc(v==null||v===''?'—':v)+'</strong></div>';
const section=(title,body)=>'<section class="section"><div class="section-head"><h2>'+esc(title)+'</h2></div>'+body+'</section>';
const badge=s=>'<span class="inventory-state '+(labels[s]?s:'unknown')+'">'+stateText(s)+'</span>';
function filterPage(rows,f={},size=20){
 const q=String(f.query||'').trim().toLowerCase(),state=f.state||'all';
 const matches=rows.filter(r=>(state==='all'||state===r.state)&&(!q||r.code.toLowerCase().includes(q)||r.id===q));
 const pages=Math.max(1,Math.ceil(matches.length/size)),page=Math.max(1,Math.min(pages,Number(f.page)||1));
 return {rows:matches.slice((page-1)*size,page*size),total:matches.length,page,pages};
}
function renderDetail(envelope){
 if(envelope&&envelope.mappingStatus==='unknown')return '<div class="notice-row">库存明细暂不可用，未推断为空货位。</div>';
 if(!envelope||envelope.mappingStatus!=='mapped'||!envelope.location)
  return '<div class="notice-row">库位编码未匹配，暂不能判断真实库存状态。</div>';
 const l=envelope.location,f=l.fields||{},t=l.totals||{},items=l.items||[],source=envelope.source||{};
 const reason=l.state==='empty'?(l.emptyReason==='no_inventory_record'?'本次快照未关联库存记录。':'本次快照库存总量为 0。'):l.state==='unknown'?'库存数据存在缺失或异常，暂不判断为空位。':'按库存总量判断；冻结和已分配库存仍计入有货。';
 let html='<header class="page-head"><div class="title-row"><h1>库位详情</h1><span class="source scene">真实库存快照</span></div><p>'+esc(source.exportedAt||'2026-11-25 静态导出')+'</p></header>';
 html+='<div class="selection-card inventory-location"><div class="flex-between"><h2>'+esc(l.code)+'</h2>'+badge(l.state)+'</div><p class="small">'+esc(reason)+'</p></div>';
 if(envelope.sceneBinding)html+='<p class="inventory-binding-note">按编码规则匹配 · 物理对应待复核</p>';
 html+='<div class="kpis verified-kpis"><div class="kpi"><span>库存总量 / 件</span><strong class="num">'+num(t.quantity)+'</strong></div><div class="kpi"><span>可用数量 / 件</span><strong class="num">'+num(t.availableQuantity)+'</strong></div></div>';
 html+=section('库存构成',kv('已分配 / 件',num(t.allocationQuantity))+kv('冻结 / 件',num(t.freezeQuantity))+kv('待移入 / 件',num(t.waitMoveInQuantity))+kv('待移出 / 件',num(t.waitMoveOutQuantity)));
 html+=section('库位信息',kv('库位 ID',l.id)+kv('仓库',l.warehouseCode||'GHS_CA_US')+kv('库区 ID',f.warehouse_area_id)+kv('排 / 列 / 层（WMS 原值）',[f.location_row,f.location_col,f.location_layer].map(v=>v==null?'—':v).join(' / '))+kv('横向序号',f.horizontal_num)+kv('库位状态（源编码）',f.location_status)+kv('库位类型（源编码）',f.location_type)+kv('长 × 宽 × 高 / 米',[f.location_length_m,f.location_width_m,f.location_height_m].map(v=>v==null?'—':v).join(' × ')));
 html+=section('库存明细 · '+num(l.recordCount)+' 条 / '+num(l.skuCount)+' 个 SKU',items.length?'<div class="inventory-items">'+items.map(item=>'<article class="list-row"><div class="row-title"><strong>'+esc(item.sku)+'</strong><span class="num">'+num(item.quantity)+' 件</span></div><div class="row-sub">记录 '+esc(item.id)+'</div><div class="row-foot"><span>可用 '+num(item.availableQuantity)+'</span><span>已分配 '+num(item.allocationQuantity)+' · 冻结 '+num(item.freezeQuantity)+'</span></div><p class="small muted">'+esc(item.updatedAt||'更新时间未知')+' (UTC+8)</p></article>').join('')+'</div>':'<p class="small">本次快照无库存明细。</p>');
 html+=section('数据时间',kv('库存最近更新（UTC+8）',l.updatedAtMax)+kv('库位档案更新（源值）',f.location_updated_at)+'<p class="small muted">本次为静态导出，跨表同步完整水位待核实。空货位不等于可用库位，库位状态源编码暂不作业务解释。</p>');
 return html;
}
let index=null,revision=0;
const byId=new Map(),shards=new Map(),pending=new Map(),errors=new Map(),listeners=new Set();
const changed=()=>{revision++;listeners.forEach(fn=>fn());};
const shardName=name=>typeof name==='string'&&/^\d{3}\.json$/.test(name)&&Number(name.slice(0,3))<128;
function script(key,url){
 if(pending.has(key)||errors.has(key))return;
 const el=root.document.createElement('script');pending.set(key,el);el.src=url;el.async=true;
 const fail=message=>{pending.delete(key);el.remove();errors.set(key,message);changed();};
 el.onerror=()=>fail('库存文件读取失败，请重试。');
 el.onload=()=>{pending.delete(key);el.remove();if(key==='index'?!index:!shards.has(key))fail(errors.get(key)||'库存文件缺少有效数据，请重试。');};
 root.document.head.appendChild(el);
}
function loadIndex(retry=false){if(index)return;if(retry)errors.delete('index');script('index','../data/inventory/index.js');}
function loadLocation(id,retry=false){
 if(!index){loadIndex(retry);return;}
 const row=byId.get(String(id));if(!row||shards.has(row.shard))return;
 if(retry)errors.delete(row.shard);
 if(!shardName(row.shard))return;
 script(row.shard,'../data/inventory/'+row.shard.replace('.json','.js'));
}
function receive(data){
 const key=data&&data.kind==='shard'?data.shard:'index';
 try{
  if(!data||data.schemaVersion!==1||typeof data.snapshotId!=='string')throw Error('schema');
  if(data.kind==='index'){
   if(data.warehouseId!=='108'||data.warehouseCode!=='GHS_CA_US'||!Array.isArray(data.locations)||!data.source||!data.summary)throw Error('warehouse');
   if(root.GHSInventorySummary&&root.GHSInventorySummary.snapshotId!==data.snapshotId)throw Error('summary snapshot');
   const ids=new Set(),codes=new Set();for(const r of data.locations){if(typeof r.id!=='string'||!r.id||typeof r.code!=='string'||!r.code||ids.has(r.id)||codes.has(r.code)||!labels[r.state]||!shardName(r.shard))throw Error('location');ids.add(r.id);codes.add(r.code);}
   index=data;byId.clear();shards.clear();data.locations.forEach(r=>byId.set(r.id,r));
  }else if(data.kind==='shard'){
   if(!index||data.snapshotId!==index.snapshotId||!shardName(data.shard)||!data.locations)throw Error('snapshot');
   for(const [id,l] of Object.entries(data.locations)){
    const row=byId.get(id);
    if(!row||row.shard!==data.shard||l.id!==id||l.code!==row.code||l.warehouseId!=='108'||l.state!==row.state||!l.totals||l.totals.quantity!==row.quantity||!Array.isArray(l.items))throw Error('identity');
   }
   shards.set(data.shard,data.locations);
   // Bound browser memory while letting cached native scene details stay independent.
   if(shards.size>8)shards.delete(shards.keys().next().value);
  }else throw Error('kind');
  errors.delete(key);changed();
 }catch(e){errors.set(key,'库存文件校验失败，未显示未经核验的数据。');changed();}
}
function renderList(f){
 if(!index){loadIndex();const error=errors.get('index');return '<header class="page-head"><h1>库存与货位</h1><p>真实库存快照</p></header><p role="status">'+esc(error||'正在读取库位索引…')+'</p>'+(error?'<button class="btn" data-action="inventory-retry">重新读取</button>':'');}
 const s=index.summary,p=filterPage(index.locations,f);f.page=p.page;
 let html='<header class="page-head"><div class="title-row"><h1>库存与货位</h1><span class="source scene">真实库存快照</span></div><p>'+esc(index.source.exportedAt)+'</p></header>';
 html+='<div class="kpis verified-kpis">'+[['库存总量 / 件',s.quantity],['可用数量 / 件',s.availableQuantity],['有货库位',s.occupiedCount],['无库存库位',s.emptyCount]].map(([k,v])=>'<div class="kpi"><span>'+k+'</span><strong class="num">'+num(v)+'</strong></div>').join('')+'</div>';
 html+='<p class="small muted">共 '+num(s.locationCount)+' 个库位档案，含临时及非场景库位，不作为三维仓库的物理容量。数据非实时刷新。</p>';
 html+='<label class="search inventory-search"><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m20 20-5-5 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0"/></svg><input type="search" aria-label="搜索真实库位编码或 ID" data-search="inventory" value="'+esc(f.query||'')+'" placeholder="搜索真实库位编码 / ID" autocomplete="off"></label><div class="inventory-filters">'+[['all','全部'],['occupied','有货'],['empty','空货位'],['unknown','待核验']].map(([v,t])=>'<button class="btn '+((f.state||'all')===v?'primary':'')+'" data-action="inventory-state" data-value="'+v+'">'+t+'</button>').join('')+'</div>';
 html+='<div class="row-list">'+p.rows.map(l=>'<button class="list-row inventory-result" data-action="inventory-location" data-id="'+esc(l.id)+'"><span class="row-title"><strong>'+esc(l.code)+'</strong>'+badge(l.state)+'</span><span class="row-foot"><span>'+num(l.quantity)+' 件 · '+num(l.skuCount)+' 个 SKU</span><span class="link">查看详情 →</span></span></button>').join('')+(p.rows.length?'':'<p class="small">没有符合条件的库位。</p>')+'</div>';
 html+='<div class="inventory-pager"><button class="btn" data-action="page" data-scope="inventory" data-value="'+(p.page-1)+'"'+(p.page===1?' disabled':'')+'>上一页</button><span>'+p.page+' / '+p.pages+' · '+num(p.total)+' 个</span><button class="btn" data-action="page" data-scope="inventory" data-value="'+(p.page+1)+'"'+(p.page===p.pages?' disabled':'')+'>下一页</button></div>';
 return html;
}
function renderLocation(id){
 if(!index)return renderList({});
 const row=byId.get(String(id));if(!row)return '<p>未找到该库位，未推断为空位。</p>';
 const shard=shards.get(row.shard);if(!shard){loadLocation(id);const error=errors.get(row.shard);return '<p role="status">'+esc(error||'正在读取库存明细…')+'</p>'+(error?'<button class="btn" data-action="inventory-retry-location" data-id="'+esc(id)+'">重新读取</button>':'');}
 const l=shard[id];return l?renderDetail({mappingStatus:'mapped',source:index.source,location:l}):'<p>未找到该库位，未推断为空位。</p>';
}
const hasLocation=query=>!!index&&(byId.has(query)||index.locations.some(l=>l.code.toLowerCase()===query.toLowerCase()));
const api={filterPage,renderDetail,renderList,renderLocation,loadIndex,loadLocation,receive,hasLocation,subscribe:fn=>listeners.add(fn),revision:()=>revision};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
else{root.TwinInventory=api;root.GHSInventoryPayload=receive;}
})(typeof window!=='undefined'?window:globalThis);
