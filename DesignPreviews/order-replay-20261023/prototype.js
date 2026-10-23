(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const TZ = 'America/Los_Angeles';
  const WAVE = 720;
  const forkOffsets = [0, 105, 35, 70, 175];
  const forkLanes = [650, 700, 750, 800, 850];
  const sourceY = [176, 266, 356, 446, 536];
  const dockY = [208, 383, 558];
  const destinations = [0, 0, 1, 2, 2];
  const capacities = [2, 1, 2];
  const orders = [1, 2, 3, 4].map(n => ({id: `TEST-OUT-${String(n).padStart(3, '0')}`, label: `出库测试订单 ${String(n).padStart(2, '0')}`}));
  const navItems = [['overview','总览','grid'],['inventory','库存','box'],['orders','订单','order'],['devices','设备','device'],['alerts','告警','bell'],['trace','追溯','history'],['scene','场景','layers']];
  const pageNames = {overview:'仓库运营总览', inventory:'库存查询', orders:'订单管理', devices:'设备台账', alerts:'告警中心', trace:'作业追溯', scene:'场景设置'};
  const state = {active:false, playing:false, completed:false, speed:1, time:0, duration:3600, start:0, end:0, queried:false, order:null, follow:null, tab:'devices', view:'real', page:'trace', eventWave:0, pinEventWave:false, selectedEvent:null, exit:null, camera:{x:0,y:0,w:1200,h:760}};
  let previousFrame = 0;
  let previousUiSecond = -1;
  let toastTimer;
  let lastFocus;
  let totalEventCount = 0;
  let timelineEvents = [];
  let mapBuilt = false;
  let scrubPlayback = null;
  const formatClock = new Intl.DateTimeFormat('en-GB', {timeZone:TZ, hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23'});
  const formatDate = new Intl.DateTimeFormat('en-CA', {timeZone:TZ, year:'numeric', month:'2-digit', day:'2-digit'});
  const formatZone = new Intl.DateTimeFormat('en-US', {timeZone:TZ, timeZoneName:'short'});
  const formatParts = new Intl.DateTimeFormat('en-CA', {timeZone:TZ, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hourCycle:'h23'});
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const clockAt = seconds => formatClock.format(new Date(state.start + seconds * 1000));
  const zoneAt = epoch => formatZone.formatToParts(new Date(epoch)).find(x => x.type === 'timeZoneName').value;
  const dateAt = epoch => formatDate.format(new Date(epoch));
  const pad = n => String(n).padStart(2,'0');
  const durationLabel = seconds => {
    const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60);
    return hours ? `${hours} 小时${minutes ? ` ${minutes} 分钟` : ''}` : `${minutes} 分钟`;
  };
  const elapsedLabel = seconds => `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor(seconds % 3600 / 60))}:${pad(Math.floor(seconds % 60))}`;
  function warehouseDateTime(value) {
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
    const [year,month,day,hour,minute] = value.split(/[-T:]/).map(Number);
    const wall = Date.UTC(year, month - 1, day, hour, minute);
    const matches = [7,8].map(offset => wall + offset * 3600000).filter(epoch => {
      const p = Object.fromEntries(formatParts.formatToParts(new Date(epoch)).map(x => [x.type,x.value]));
      return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}` === value;
    });
    return matches.length ? {epoch:Math.min(...matches), ambiguous:matches.length > 1} : null;
  }
  function readRange() {
    const start = warehouseDateTime($('start-time').value), end = warehouseDateTime($('end-time').value);
    const endInput=$('end-time'), explicitEpoch=Number(endInput.dataset?.resolvedEpoch);
    if(end&&end.ambiguous&&endInput.dataset?.resolvedValue===endInput.value&&Number.isFinite(explicitEpoch)){end.epoch=explicitEpoch;end.usedExplicitFold=true;}
    if (!start || !end) return {error:'请选择有效的开始与结束时间。夏令时跳变中不存在的当地时刻不可使用。'};
    if (end.epoch <= start.epoch) return {error:'结束时间必须晚于开始时间。'};
    const duration = (end.epoch - start.epoch) / 1000;
    if (duration < 3600) return {error:'回放区间至少需要 1 小时，请延长结束时间。'};
    return {start:start.epoch, end:end.epoch, duration, ambiguous:start.ambiguous || end.ambiguous, explicitFold:!!end.usedExplicitFold};
  }
  function updateRangeSummary() {
    const r = readRange();
    $('range-summary').textContent = r.error ? '最短查询区间：1 小时' : `已选 ${durationLabel(r.duration)} · ${zoneAt(r.start)}${r.explicitFold ? ' · 按快捷时长跨越重复时刻' : r.ambiguous ? ' · 重复时刻采用较早一次' : ''}`;
    document.querySelectorAll('[data-hours]').forEach(button=>{const active=!r.error&&r.duration===Number(button.dataset.hours)*3600;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
  }
  function toast(message) {
    clearTimeout(toastTimer);
    $('toast').textContent = message;
    $('toast').classList.remove('hidden');
    toastTimer = setTimeout(() => $('toast').classList.add('hidden'), 3200);
  }
  function setHidden(id, hidden) { $(id).classList.toggle('hidden', hidden); }
  function updateHeaderClock() {
    const now = new Date();
    $('warehouse-clock').textContent = formatClock.format(now);
    $('warehouse-date').textContent = `${formatDate.format(now)} · ${zoneAt(now.getTime())}`;
  }
  function renderNav() {
    $('nav-rail').innerHTML = navItems.map(([id,label,glyph]) => `<button class="nav-item ${id === state.page ? 'active' : ''}" data-page="${id}" title="${label}" ${id === state.page ? 'aria-current="page"' : ''}>${icon(glyph)}<span>${label}</span></button>`).join('') + `<div class="nav-bottom"><button class="nav-item" id="zoom-in" aria-label="放大作业示意"><span style="font-size:22px">+</span></button><button class="nav-item" id="zoom-out" aria-label="缩小作业示意"><span style="font-size:22px">−</span></button><div class="nav-separator"></div><button class="nav-item" id="whole-scene">${icon('focus')}<span>全仓</span></button></div>`;
    document.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => navigate(button.dataset.page)));
    $('whole-scene').addEventListener('click', () => {if(state.active){requestExit('overview');return;}cancelFollow();state.camera={x:0,y:0,w:1200,h:760};$('scene-photo').classList.remove('open');setHidden('warehouse-poi',state.view==='diagram');$('area-label').textContent='园区总览';});
    $('zoom-in').addEventListener('click', () => adjustZoom(.8));
    $('zoom-out').addEventListener('click', () => adjustZoom(1.25));
  }
  function adjustZoom(factor) {
    if(state.view !== 'diagram') {toast('此处为实际场景底图，切换作业示意可调整视野');return;}
    state.follow = null;
    const c=state.camera, w=clamp(c.w*factor,480,1200), h=w*760/1200;
    state.camera={x:clamp(c.x+c.w/2-w/2,0,1200-w),y:clamp(c.y+c.h/2-h/2,0,760-h),w,h};
    updateFollow();
  }
  function navigate(page) {
    if(state.active) {requestExit(page);return;}
    state.page = page;
    showNormal(page);
  }
  function showNormal(page) {
    state.view='real';state.camera={x:0,y:0,w:1200,h:760};
    renderNav();
    const query = page === 'trace';
    setHidden('query-view',!query);setHidden('normal-view',query);setHidden('replay-view',true);
    if(!query) $('normal-page-title').textContent=pageNames[page];
    $('area-label').textContent='园区总览';$('scene-photo').classList.remove('open');
    syncSceneMode();
  }
  function queryOrders(event) {
    event?.preventDefault();
    const range = readRange();
    if(range.error) {
      $('query-error').textContent = range.error;setHidden('query-error',false);
      state.queried=false;setHidden('query-result-note',true);$('order-count').textContent='请调整区间';
      $('order-list').innerHTML='<div class="empty-state">'+icon('clock')+'<strong>区间尚未满足查询条件</strong><p>开始与结束至少相隔 1 小时</p></div>';
      return false;
    }
    Object.assign(state,range,{queried:true});
    setHidden('query-error',true);$('order-count').textContent='4 个测试订单';
    $('query-result-note').textContent=`${dateAt(state.start)} · ${clockAt(0).slice(0,5)} — ${clockAt(state.duration).slice(0,5)} · ${durationLabel(state.duration)}`;
    setHidden('query-result-note',false);
    $('order-list').innerHTML = orders.map(order => `<button class="order-card" data-order="${order.id}"><div class="order-card-top"><strong>${order.id}</strong><span class="order-type">测试订单</span></div><div class="order-card-bottom"><span>测试场景 · 全区间设备</span><span class="enter-order">进入回放 ${icon('arrow')}</span></div></button>`).join('');
    document.querySelectorAll('[data-order]').forEach(button => button.addEventListener('click',()=>startReplay(button.dataset.order)));
    return true;
  }
  function startReplay(orderId) {
    if(!state.queried) return;
    Object.assign(state,{active:true,playing:true,completed:false,time:0,speed:1,order:orderId,follow:null,tab:'devices',view:'diagram',page:'trace',eventWave:0,pinEventWave:false,selectedEvent:null,exit:null,camera:{x:0,y:0,w:1200,h:760}});
    previousUiSecond=-1;
    $('business-panel').scrollTop=0;
    setHidden('query-view',true);setHidden('replay-view',false);setHidden('normal-view',true);
    $('replay-order-id').textContent=orderId;$('entry-order').textContent=`入口订单 ${orderId}`;
    $('replay-range').innerHTML=`<strong>${dateAt(state.start)} ${clockAt(0).slice(0,5)} — ${dateAt(state.end)} ${clockAt(state.duration).slice(0,5)}</strong>仓库当地时间 · America/Los_Angeles · ${durationLabel(state.duration)}`;
    $('timeline-range').max=state.duration;
    $('timeline-zone').textContent=`${zoneAt(state.start)} · 仓库当地时间`;
    renderDeviceRows();buildTimeline();setTab('devices');renderSpeed();renderNav();syncSceneMode();renderPlayback(true);
  }
  function finishReplay(target='trace') {
    Object.assign(state,{active:false,playing:false,completed:false,follow:null,exit:null,page:target,time:0,selectedEvent:null});
    setHidden('exit-modal',true);setHidden('completion-card',true);
    showNormal(target);
    $('business-panel').scrollTop=0;
    toast(target==='trace'?'已结束回放，查询区间与订单列表已保留':`已结束回放并进入${navItems.find(n=>n[0]===target)?.[1]||'普通场景'}`);
  }
  function requestExit(target=null) {
    if(!state.active || state.exit) return;
    state.exit={target,wasPlaying:state.playing};state.playing=false;
    lastFocus=document.activeElement;
    $('exit-title').textContent=target?`结束回放并前往${navItems.find(n=>n[0]===target)[1]}？`:'结束当前回放？';
    $('exit-description').textContent=target?'离开前先结束当前回放并恢复普通场景，然后打开所选页面。取消后回到刚才的回放状态。':'结束后恢复普通场景，并返回订单列表。已选时间区间和查询结果会保留。';
    $('cancel-exit').textContent=target?'取消，留在回放':'继续查看';
    $('confirm-exit').textContent=target?'结束并前往':'结束回放';
    $('exit-time').textContent=clockAt(state.time);
    setHidden('exit-modal',false);renderPlayback(true);$('cancel-exit').focus();
  }
  function cancelExit() {
    if(!state.exit) return;
    state.playing=state.exit.wasPlaying && !state.completed;state.exit=null;
    setHidden('exit-modal',true);renderPlayback(true);lastFocus?.focus();
  }
  function seek(time, selectedEvent=null, preservePlaying=false) {
    if(!state.active || state.exit) return;
    const wasPlaying=state.playing;
    state.time=clamp(Number(time),0,state.duration);state.completed=state.time>=state.duration;
    state.playing=preservePlaying&&wasPlaying&&!state.completed;
    state.selectedEvent=selectedEvent;
    if(!state.pinEventWave)state.eventWave=waveIndex(state.time);
    renderPlayback(true);renderEvents();
  }
  function finishScrub() {
    if(scrubPlayback===null)return;
    const wasPlaying=scrubPlayback;scrubPlayback=null;
    if(!state.active||state.exit)return;
    state.playing=wasPlaying&&!state.completed;renderPlayback(true);
  }
  function restartReplay() {
    if(!state.active||state.exit)return;
    Object.assign(state,{time:0,playing:true,completed:false,eventWave:0,pinEventWave:false,selectedEvent:null});
    renderPlayback(true);renderEvents();
  }
  function togglePlayback() {
    if(!state.active||state.exit||state.time>=state.duration)return;
    state.playing=!state.playing;state.completed=false;state.pinEventWave=false;
    renderPlayback(true);
  }
  function waveIndex(time) {return Math.min(Math.floor(time/WAVE),Math.max(0,Math.ceil(state.duration/WAVE)-1));}
  function waveTime(time) {const w=waveIndex(time);return {index:w,t:time-w*WAVE};}
  function forkState(i,time=state.time) {
    const {index,t}=waveTime(time), delay=i===2?clamp(t-310,0,45):0;
    const phase=t-forkOffsets[i]-delay;
    const isFault=i===2&&t>=310&&t<355;
    let stage,loaded=false,progress;
    if(phase<0) {stage='等待作业';progress=0;}
    else if(phase<75) {stage='取货准备';progress=phase/75*.14;}
    else if(phase<105) {stage='取货中';progress=.14;}
    else if(phase<315) {stage='载货运输';loaded=true;progress=.14+(phase-105)/210*.68;}
    else if(phase<350) {stage='卸货中';loaded=true;progress=.82;}
    else if(phase<510) {stage='空载返回';progress=.82-(phase-350)/160*.68;}
    else {stage='等待下一波';progress=.14;}
    if(isFault)stage='故障 · 暂停';
    const pickTime=105+forkOffsets[i],dropTime=350+forkOffsets[i]+(i===2?45:0);
    const sy=sourceY[i],dy=dockY[destinations[i]];
    const lane=forkLanes[i];
    const route=[[573,sy],[lane,sy],[lane,dy],[920,dy]];
    const returnRoute=[[920,dy],[870,dy+76],[640,dy+76],[640,sy],[573,sy]];
    let position;
    if(phase<75) position={x:573,y:sy,angle:180};
    else if(phase<105)position={x:573,y:sy,angle:180};
    else if(phase<315)position=pointOnRoute(route,clamp((phase-105)/210,0,1));
    else if(phase<350)position={x:920,y:dy,angle:0};
    else if(phase<510){position=pointOnRoute(returnRoute,(phase-350)/160);}
    else position={x:573,y:sy,angle:180};
    return {i,index,t,phase,stage,loaded,isFault,progress,position,upperAtSource:t<pickTime,delivered:t>=dropTime,pickTime,dropTime};
  }
  function pointOnRoute(points,progress) {
    const smooth=[points[0]];
    for(let i=1;i<points.length-1;i++){
      const a=points[i-1],b=points[i],c=points[i+1],la=Math.hypot(b[0]-a[0],b[1]-a[1]),lb=Math.hypot(c[0]-b[0],c[1]-b[1]),r=Math.min(24,la/2,lb/2);
      if(!r){smooth.push(b);continue;}
      const before=[b[0]-(b[0]-a[0])/la*r,b[1]-(b[1]-a[1])/la*r],after=[b[0]+(c[0]-b[0])/lb*r,b[1]+(c[1]-b[1])/lb*r];
      smooth.push(before);
      for(let j=1;j<=12;j++){const t=j/12,u=1-t;smooth.push([u*u*before[0]+2*u*t*b[0]+t*t*after[0],u*u*before[1]+2*u*t*b[1]+t*t*after[1]]);}
    }
    smooth.push(points[points.length-1]);points=smooth;
    const lengths=points.slice(1).map((p,i)=>Math.hypot(p[0]-points[i][0],p[1]-points[i][1]));
    let distance=lengths.reduce((a,b)=>a+b,0)*clamp(progress,0,1);
    for(let i=0;i<lengths.length;i++){if(distance<=lengths[i]||i===lengths.length-1){const q=lengths[i]?distance/lengths[i]:0,a=points[i],b=points[i+1];return{x:a[0]+(b[0]-a[0])*q,y:a[1]+(b[1]-a[1])*q,angle:Math.atan2(b[1]-a[1],b[0]-a[0])*180/Math.PI};}distance-=lengths[i];}
    return{x:points[0][0],y:points[0][1],angle:0};
  }
  function truckState(i,time=state.time) {
    const {index,t}=waveTime(time),forks=forkOffsets.map((_,n)=>forkState(n,time));
    const assigned=forks.filter(f=>destinations[f.i]===i), load=assigned.filter(f=>f.delivered).length;
    const fullAt=Math.max(...assigned.map(f=>f.dropTime)),departAt=fullAt+25;
    let stage='等待装货',position={x:1000,y:dockY[i],angle:0},visible=true,pallets=load;
    if(load>0&&load<capacities[i])stage='装货中';
    if(t>=fullAt&&t<departAt)stage='已装满 · 待驶离';
    if(t>=departAt&&t<departAt+65){stage='装满驶离';position=pointOnRoute([[1000,dockY[i]],[1095,dockY[i]],[1095,660],[1195,660]],(t-departAt)/65);}
    if(t>=departAt+65&&t<620){stage='等待下一空车';visible=false;pallets=0;}
    if(t>=620&&t<695){stage='下一空车驶入';pallets=0;position=pointOnRoute([[1185,91],[1095,91],[1095,dockY[i]],[1000,dockY[i]]],(t-620)/75);}
    if(t>=695){stage='空车就位';pallets=0;}
    return {i,index,t,stage,position,visible,load:pallets,capacity:capacities[i],departAt};
  }
  function waveEvents(wave) {
    const base=wave*WAVE,events=[];
    forkOffsets.forEach((offset,i)=>{
      events.push({time:base+offset+105,type:'pickup',device:`FORK-${pad(i+1)}`,title:'取货完成',detail:'上层单托已转移到货叉，下层蓝托保留',wave});
      events.push({time:base+offset+350+(i===2?45:0),type:'drop',device:`FORK-${pad(i+1)}`,title:'放货完成',detail:`单托已放入装卸车 ${pad(destinations[i]+1)}，货叉清空`,wave});
    });
    events.push({time:base+310,type:'fault',device:'FORK-03',title:'设备故障',detail:'人工叉车 03 停在当前路径，保持载货',wave});
    events.push({time:base+355,type:'recover',device:'FORK-03',title:'故障恢复',detail:'暂停 45 秒后，从原位置继续作业',wave});
    [0,1,2].forEach(i=>{const dropTimes=forkOffsets.map((offset,f)=>({f,time:offset+350+(f===2?45:0)})).filter(x=>destinations[x.f]===i);events.push({time:base+Math.max(...dropTimes.map(x=>x.time))+25,type:'depart',device:`TRUCK-${pad(i+1)}`,title:'卡车装满驶离',detail:'沿出口驶离；下一空车随后从入口进入',wave});});
    return events.filter(e=>e.time<=state.duration).sort((a,b)=>a.time-b.time).map(e=>({...e,id:`${e.wave}-${e.device}-${e.type}`}));
  }
  function buildTimeline() {
    const waves=Math.ceil(state.duration/WAVE);
    totalEventCount=Math.max(0,waves-1)*15+waveEvents(waves-1).length;
    $('events-count').textContent=totalEventCount.toLocaleString();
    const stride=Math.max(1,Math.ceil(waves/16));
    timelineEvents=[];
    for(let w=0;w<waves;w+=stride)timelineEvents.push(...waveEvents(w));
    $('event-markers').innerHTML=timelineEvents.map(e=>`<button class="event-marker ${e.type}" style="left:${e.time/state.duration*100}%" data-event="${e.id}" title="${clockAt(e.time)} · ${e.device} · ${e.title}" aria-label="跳转至 ${clockAt(e.time)} ${e.device} ${e.title}"></button>`).join('');
    document.querySelectorAll('.event-marker').forEach(button=>button.addEventListener('click',()=>selectEvent(timelineEvents.find(e=>e.id===button.dataset.event))));
    $('time-ticks').innerHTML=Array.from({length:7},(_,i)=>`<span>${clockAt(state.duration*i/6).slice(0,5)}</span>`).join('');
    $('timeline-tip').innerHTML=icon('info')+(stride>1?'长区间已聚合标记；全部事件可按波次查看':'点击事件或拖动时间轴，暂停到对应时刻');
  }
  function selectEvent(event) {
    if(!event)return;
    state.eventWave=event.wave;state.pinEventWave=true;
    seek(event.time,event.id);setTab('events');
  }
  function renderEvents() {
    const waves=Math.ceil(state.duration/WAVE), w=clamp(state.eventWave,0,waves-1),events=waveEvents(w);
    $('event-list').innerHTML=`<div class="event-wave-heading"><span>第 ${w+1} / ${waves} 波 · ${clockAt(w*WAVE).slice(0,5)} — ${clockAt(Math.min((w+1)*WAVE,state.duration)).slice(0,5)}</span><div><button id="previous-wave" ${w===0?'disabled':''} aria-label="上一波事件">‹</button><button id="next-wave" ${w===waves-1?'disabled':''} aria-label="下一波事件">›</button></div></div>`+events.map(e=>`<button class="event-row ${e.id===state.selectedEvent?'active':''} ${e.time>state.time?'future':''}" data-list-event="${e.id}"><span class="event-row-icon ${e.type}"></span><span class="event-row-main"><span class="event-row-title">${e.title}<time>${clockAt(e.time)}</time></span><small>${e.device} · ${e.detail}</small></span></button>`).join('');
    $('previous-wave').addEventListener('click',()=>{state.eventWave=w-1;state.pinEventWave=true;renderEvents();});
    $('next-wave').addEventListener('click',()=>{state.eventWave=w+1;state.pinEventWave=true;renderEvents();});
    document.querySelectorAll('[data-list-event]').forEach(button=>button.addEventListener('click',()=>selectEvent(events.find(e=>e.id===button.dataset.listEvent))));
  }
  function renderDeviceRows() {
    $('forklift-list').innerHTML=Array.from({length:5},(_,i)=>`<div class="device-row" id="fork-row-${i}"><span class="device-row-icon">${icon('device')}</span><div class="device-row-main"><div class="device-name">人工叉车 ${pad(i+1)}<span class="device-id">FORK-${pad(i+1)}</span></div><div class="device-status"><i class="status-dot"></i><span id="fork-status-${i}"></span></div></div><button class="follow-button" data-follow="fork-${i}" aria-label="跟随人工叉车 ${pad(i+1)}">跟随</button></div>`).join('');
    $('truck-list').innerHTML=Array.from({length:3},(_,i)=>`<div class="device-row waiting" id="truck-row-${i}"><span class="device-row-icon">${icon('truck')}</span><div class="device-row-main"><div class="device-name">装卸车 ${pad(i+1)}<span class="device-id">TRUCK-${pad(i+1)}</span></div><div class="device-status"><i class="status-dot"></i><span id="truck-status-${i}"></span></div><div class="truck-progress"><i id="truck-progress-${i}"></i></div></div><button class="follow-button" data-follow="truck-${i}" aria-label="跟随装卸车 ${pad(i+1)}">跟随</button></div>`).join('');
    document.querySelectorAll('[data-follow]').forEach(button=>button.addEventListener('click',()=>followDevice(button.dataset.follow)));
  }
  function followDevice(id) {
    if(!state.active)return;
    if(state.follow===id){cancelFollow();return;}
    state.follow=id;
    if(state.view!=='diagram'){state.view='diagram';syncSceneMode();toast('已切换至作业演示示意，查看设备动作');}
    updateFollow();
  }
  function cancelFollow() {state.follow=null;state.camera={x:0,y:0,w:1200,h:760};updateFollow();}
  function updateFollow() {
    setHidden('follow-banner',!state.follow);
    $('scene').classList.toggle('is-following',!!state.follow);
    if(state.follow){const [type,index]=state.follow.split('-');$('follow-copy').textContent=`正在跟随 · ${type==='fork'?'人工叉车':'装卸车'} ${pad(Number(index)+1)}`;}
    document.querySelectorAll('[data-follow]').forEach(button=>{const active=button.dataset.follow===state.follow;button.textContent=active?'取消':'跟随';button.closest('.device-row').classList.toggle('followed',active);button.setAttribute('aria-pressed',String(active));});
    document.querySelectorAll('.device-unit').forEach(unit=>unit.classList.toggle('followed',unit.dataset.device===state.follow));
  }
  function setTab(tab) {
    state.tab=tab;setHidden('device-content',tab!=='devices');setHidden('event-content',tab!=='events');
    document.querySelectorAll('[data-tab]').forEach(button=>{button.classList.toggle('active',button.dataset.tab===tab);button.setAttribute('aria-selected',String(button.dataset.tab===tab));});
    if(tab==='events')renderEvents();
  }
  function renderSpeed() {
    $('speed-group').innerHTML=[1,2,4,8,16,32,64].map(speed=>`<button data-speed="${speed}" class="${state.speed===speed?'active':''}" aria-label="${speed}倍速度" aria-pressed="${state.speed===speed}">${speed}×</button>`).join('');
    document.querySelectorAll('[data-speed]').forEach(button=>button.addEventListener('click',()=>{state.speed=Number(button.dataset.speed);renderSpeed();}));
  }
  function syncSceneMode() {
    $('scene').classList.toggle('is-replaying',state.active);
    setHidden('timeline-panel',!state.active);setHidden('replay-scene-bar',!state.active);
    setHidden('diagram-wrap',state.view!=='diagram');setHidden('scene-legend',state.view!=='diagram');
    setHidden('real-scene-note',!state.active||state.view!=='real');
    setHidden('warehouse-poi',state.active||state.view==='diagram');
    $('scene-photo').style.opacity=state.view==='diagram'?'.22':'1';
    if(state.active)$('scene-photo').classList.add('open');
    $('area-label').textContent=state.active?'测试回放 · 全部设备':state.view==='diagram'?'作业演示示意':'园区总览';
    document.querySelectorAll('[data-view]').forEach(button=>{button.classList.toggle('active',button.dataset.view===state.view);button.setAttribute('aria-pressed',String(button.dataset.view===state.view));});
    if(state.view==='diagram'&&!mapBuilt)buildMap();
    updateFollow();
  }
  function pallet(x,y,opacity=1) {return `<g transform="translate(${x} ${y})" opacity="${opacity}"><rect x="-11" y="-8" width="22" height="17" rx="2" fill="#356BFA"/><path d="M-9-3H9 M-9 2H9" stroke="#8DABFF" stroke-width="2"/><path d="M-8 9v3 M0 9v3 M8 9v3" stroke="#2559D6" stroke-width="3"/></g>`;}
  function roundedRoute(points) {
    let d='M'+points[0].join(' ');
    for(let i=1;i<points.length-1;i++){
      const a=points[i-1],b=points[i],c=points[i+1],la=Math.hypot(b[0]-a[0],b[1]-a[1]),lb=Math.hypot(c[0]-b[0],c[1]-b[1]),r=Math.min(24,la/2,lb/2);
      if(!r){d+=' L'+b.join(' ');continue;}
      const before=[b[0]-(b[0]-a[0])/la*r,b[1]-(b[1]-a[1])/la*r],after=[b[0]+(c[0]-b[0])/lb*r,b[1]+(c[1]-b[1])/lb*r];
      d+=' L'+before.join(' ')+' Q'+b.join(' ')+' '+after.join(' ');
    }
    return d+' L'+points[points.length-1].join(' ');
  }

  function buildMap() {
    mapBuilt=true;
    let racks='';
    for(let r=0;r<5;r++)for(let c=0;c<4;c++){const x=159+c*89,y=145+r*90;racks+=`<g><rect x="${x}" y="${y}" width="70" height="55" rx="3" fill="#E3EAF2" stroke="#BCCBDC"/><path d="M${x+8} ${y+7}v41 M${x+62} ${y+7}v41" stroke="#A5B8D0" stroke-width="3"/><rect x="${x+14}" y="${y+10}" width="42" height="13" rx="1.5" fill="#D0DEEF"/><rect x="${x+14}" y="${y+29}" width="42" height="13" rx="1.5" fill="#D0DEEF"/></g>`;}
    const pallets=sourceY.map((y,i)=>`<g transform="translate(541 ${y})"><rect x="-16" y="-17" width="32" height="33" rx="3" fill="#E5EEFF" stroke="#B8CDFC"/>${pallet(0,4,.7)}<g id="source-upper-${i}">${pallet(0,-5)}<rect x="-8" y="-11" width="16" height="10" rx="1" fill="#C9D4E2" stroke="#A5B5CA" stroke-width=".8"/></g></g>`).join('');
    const routes=sourceY.map((sy,i)=>{const dy=dockY[destinations[i]],lane=forkLanes[i],out=roundedRoute([[573,sy],[lane,sy],[lane,dy],[920,dy]]),back=roundedRoute([[920,dy],[870,dy+76],[640,dy+76],[640,sy],[573,sy]]);return `<path d="${back}" fill="none" stroke="#6D88AD" stroke-width="1.5" stroke-dasharray="4 7" opacity=".24"/><path class="route-line" d="${out}"/><path class="route-flow" d="${out}"/>`;}).join('');
    const forklifts=sourceY.map((y,i)=>`<g class="device-unit" id="fork-map-${i}" data-device="fork-${i}" role="button" tabindex="0" aria-label="跟随人工叉车 ${pad(i+1)}"><ellipse class="focus-ring" cx="0" cy="0" rx="37" ry="31"/><g id="fork-body-${i}"><rect x="-15" y="-13" width="29" height="26" rx="6" fill="#FFFFFF" stroke="#8CA3C7" stroke-width="1.5"/><rect x="-14" y="-11" width="10" height="22" rx="3" fill="#356BFA"/><rect x="-10" y="-18" width="8" height="5" rx="2" fill="#3F5067"/><rect x="-10" y="13" width="8" height="5" rx="2" fill="#3F5067"/><rect x="8" y="-18" width="7" height="5" rx="2" fill="#3F5067"/><rect x="8" y="13" width="7" height="5" rx="2" fill="#3F5067"/><rect x="-3" y="-10" width="14" height="20" rx="2" fill="#E5EDF7" stroke="#8DA2BC"/><circle cx="3" cy="0" r="4" fill="#647B9A"/><path d="M17-11v22 M17-8h21 M17 8h21" fill="none" stroke="#647B9A" stroke-width="3" stroke-linecap="round"/><g id="fork-pallet-${i}" style="display:none">${pallet(29,0)}<rect x="21" y="-7" width="16" height="13" rx="1" fill="#C9D4E2" stroke="#A5B5CA" stroke-width=".8"/></g></g><g id="fork-fault-${i}" style="display:none"><circle cx="-19" cy="-25" r="8" fill="#C85852"/><text x="-19" y="-21" text-anchor="middle" fill="white" font-size="12" font-weight="700">!</text></g><rect x="-25" y="24" width="50" height="17" rx="4" fill="#FFFFFFEE" stroke="#DEE6F0"/><text class="forklift-label" x="0" y="36" text-anchor="middle">FORK-${pad(i+1)}</text></g>`).join('');
    const trucks=dockY.map((y,i)=>`<g class="device-unit" id="truck-map-${i}" data-device="truck-${i}" role="button" tabindex="0" aria-label="跟随装卸车 ${pad(i+1)}"><rect class="focus-ring" x="-75" y="-40" width="160" height="80" rx="12"/><g id="truck-body-${i}"><rect x="-64" y="-29" width="105" height="58" rx="4" fill="#FFFFFF" stroke="#9AACBF" stroke-width="2"/><path d="M-57-22h88 M-57 22h88" stroke="#E3E9F1" stroke-width="2"/><rect x="42" y="-25" width="34" height="50" rx="7" fill="#356BFA" stroke="#2459D6" stroke-width="1.5"/><rect x="62" y="-20" width="9" height="40" rx="3" fill="#B7CEFF"/><path d="M44-24v48" stroke="#D8E5FF" stroke-width="2"/><g fill="#405167"><rect x="-50" y="-34" width="14" height="7" rx="2"/><rect x="-50" y="27" width="14" height="7" rx="2"/><rect x="13" y="-34" width="14" height="7" rx="2"/><rect x="13" y="27" width="14" height="7" rx="2"/><rect x="53" y="-31" width="13" height="7" rx="2"/><rect x="53" y="24" width="13" height="7" rx="2"/></g><g id="truck-pallets-${i}"></g></g><rect x="-33" y="41" width="76" height="18" rx="4" fill="#FFFFFFEE" stroke="#DEE6F0"/><text class="forklift-label" x="5" y="54" text-anchor="middle">TRUCK-${pad(i+1)}</text></g>`).join('');
    $('operation-map').innerHTML=`<defs><pattern id="floor-grid" width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0H0V30" fill="none" stroke="#E7EDF3" stroke-width=".7"/></pattern><marker id="lane-arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 2 8 5 2 8" fill="none" stroke="#AAB9CC" stroke-width="1.4"/></marker></defs><rect width="1200" height="760" fill="#F8FAFC"/><rect x="100" y="93" width="970" height="565" rx="9" fill="#F0F4F8" stroke="#C9D5E3" stroke-width="2"/><rect x="119" y="116" width="930" height="519" rx="5" fill="url(#floor-grid)"/><path d="M103 95H1067 M103 657H1067" stroke="#AABBD0" stroke-width="7"/><path d="M103 98V654" stroke="#AABBD0" stroke-width="7"/><text x="154" y="84" class="map-zone-title">货架与地堆作业区</text><text x="651" y="84" class="map-zone-title">主作业通道</text><text x="916" y="84" class="map-zone-title">装卸月台</text>${racks}<path d="M620 127V640 M874 127V640" stroke="#CCD8E6" stroke-width="1.5" stroke-dasharray="10 8"/><path d="M1104 103V622" stroke="#D8E1EB" stroke-width="2" stroke-dasharray="10 8"/><path d="M1160 91H1095V145 M1095 610V660H1160" stroke="#AAB9CC" stroke-width="2" fill="none" marker-end="url(#lane-arrow)"/><text x="1130" y="77" class="map-small">空车入口</text><text x="1130" y="684" class="map-small">装满出口</text>${dockY.map((y,i)=>`<rect x="875" y="${y-56}" width="182" height="112" rx="4" fill="#EAF0F7" stroke="#C5D4E6"/><path d="M887 ${y-50}v100" stroke="#AFC3DF" stroke-width="4"/><text x="912" y="${y-65}" class="map-small">装卸位 ${pad(i+1)}</text>`).join('')}<text x="158" y="690" class="map-small">地堆两层蓝托 · 仅搬运上层单托</text><text x="615" y="690" class="map-small">5 台人工叉车错峰作业 · 每波 12 分钟</text>${routes}${pallets}<g id="truck-units">${trucks}</g><g id="fork-units">${forklifts}</g>`;
    document.querySelectorAll('.device-unit').forEach(unit=>{unit.addEventListener('click',()=>followDevice(unit.dataset.device));unit.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();followDevice(unit.dataset.device);}});});
  }
  function renderMap() {
    if(!mapBuilt||state.view!=='diagram')return;
    const phase=waveTime(state.active?state.time:0);
    const replenishing=state.active&&phase.t>=600&&phase.t<720;
    setHidden('replenishment-placeholder',!replenishing);
    if(replenishing){$('replenishment-progress').style.width=(phase.t-600)/120*100+'%';$('replenishment-countdown').textContent=`固定时刻进入下一测试波次 · ${Math.ceil(720-phase.t)} 秒`;}
    const forks=Array.from({length:5},(_,i)=>forkState(i,state.active?state.time:0));
    const trucks=Array.from({length:3},(_,i)=>truckState(i,state.active?state.time:0));
    forks.forEach(f=>{const p=f.position;$(`fork-map-${f.i}`).setAttribute('transform',`translate(${p.x.toFixed(2)} ${p.y.toFixed(2)})`);$(`fork-body-${f.i}`).setAttribute('transform',`rotate(${p.angle})`);$(`fork-pallet-${f.i}`).style.display=f.loaded?'':'none';$(`fork-fault-${f.i}`).style.display=f.isFault?'':'none';$(`source-upper-${f.i}`).style.display=f.upperAtSource?'':'none';});
    trucks.forEach(t=>{const p=t.position;$(`truck-map-${t.i}`).setAttribute('transform',`translate(${p.x.toFixed(2)} ${p.y.toFixed(2)})`);$(`truck-map-${t.i}`).style.opacity=t.visible?'1':'0';$(`truck-map-${t.i}`).style.pointerEvents=t.visible?'auto':'none';$(`truck-body-${t.i}`).setAttribute('transform',`rotate(${p.angle})`);const load=$(`truck-pallets-${t.i}`);if(load.dataset.load!==String(t.load)){load.innerHTML=Array.from({length:t.load},(_,n)=>pallet(-39+n*30,0)).join('');load.dataset.load=t.load;}});
    $('operation-map').classList.toggle('animating',state.active&&state.playing);
    if(state.follow){const [type,n]=state.follow.split('-');const target=type==='fork'?forks[Number(n)]:trucks[Number(n)];const p=target.position;const desired={x:clamp(p.x-330,0,540),y:clamp(p.y-210,0,340),w:660,h:420};for(const key of ['x','y','w','h'])state.camera[key]+=(desired[key]-state.camera[key])*.09;}
    const c=state.camera;$('operation-map').setAttribute('viewBox',`${c.x.toFixed(2)} ${c.y.toFixed(2)} ${c.w.toFixed(2)} ${c.h.toFixed(2)}`);
  }
  function renderPlayback(force=false) {
    if(!state.active)return;
    $('scene-state-label').textContent=state.completed?'区间播放完成':state.playing?'场景回放中':'回放已暂停';
    document.querySelector('.live-dot').classList.toggle('running',state.playing);
    $('play-state').textContent=state.completed?'已完成':state.playing?'播放中':'已暂停';
    $('play-state').className=`state-pill ${state.completed?'complete':state.playing?'':'paused'}`;
    $('current-time').textContent=clockAt(state.time);$('timeline-range').value=Math.floor(state.time);
    const percent=state.time/state.duration*100;$('timeline-progress').style.width=percent+'%';$('timeline-thumb-label').style.left=percent+'%';$('timeline-thumb-label').textContent=clockAt(state.time);
    $('toggle-play').innerHTML=icon(state.playing?'pause':'play');$('toggle-play').setAttribute('aria-label',state.playing?'暂停回放':'继续播放');$('toggle-play').disabled=state.completed;$('toggle-play').title=state.completed?'已到终点，向前拖动后可继续播放':'';
    $('elapsed-copy').textContent=`${elapsedLabel(state.time)} / ${elapsedLabel(state.duration)}`;
    setHidden('completion-card',!state.completed);
    const second=Math.floor(state.time);if(!force&&second===previousUiSecond)return;previousUiSecond=second;
    let faults=0;
    for(let i=0;i<5;i++){const f=forkState(i);$(`fork-status-${i}`).textContent=f.stage+(f.loaded?' · 载 1 托':'');$(`fork-row-${i}`).classList.toggle('fault',f.isFault);$(`fork-row-${i}`).classList.toggle('waiting',f.stage.startsWith('等待'));if(f.isFault)faults++;}
    for(let i=0;i<3;i++){const t=truckState(i);$(`truck-status-${i}`).textContent=`${t.stage} · ${t.load}/${t.capacity} 托`;$(`truck-progress-${i}`).style.width=t.load/t.capacity*100+'%';}
    $('fault-count').textContent=faults;$('fault-count').style.color=faults?'#A84540':'#356BFA';
    document.querySelectorAll('.event-marker').forEach(marker=>marker.classList.toggle('active',marker.dataset.event===state.selectedEvent));
    const currentWave=waveIndex(state.time);if(!state.pinEventWave&&state.eventWave!==currentWave){state.eventWave=currentWave;if(state.tab==='events')renderEvents();}
    if(state.tab==='events')document.querySelectorAll('[data-list-event]').forEach(button=>{const ev=waveEvents(state.eventWave).find(e=>e.id===button.dataset.listEvent);button.classList.toggle('future',ev.time>state.time);});
  }
  function frame(now) {
    const delta=previousFrame?Math.min((now-previousFrame)/1000,.15):0;previousFrame=now;
    if(state.active&&state.playing&&!state.exit){state.time=Math.min(state.duration,state.time+delta*state.speed);if(state.time>=state.duration){state.playing=false;state.completed=true;state.follow=null;updateFollow();}renderPlayback();}
    renderMap();requestAnimationFrame(frame);
  }
  $('query-form').addEventListener('submit',queryOrders);
  const editedRange=()=>{delete $('end-time').dataset.resolvedEpoch;delete $('end-time').dataset.resolvedValue;updateRangeSummary();};
  $('start-time').addEventListener('input',editedRange);$('end-time').addEventListener('input',editedRange);
  document.querySelectorAll('[data-hours]').forEach(button=>button.addEventListener('click',()=>{const start=warehouseDateTime($('start-time').value);if(!start){toast('请先选择有效的开始时间');return;}const parts=Object.fromEntries(formatParts.formatToParts(new Date(start.epoch+Number(button.dataset.hours)*3600000)).map(p=>[p.type,p.value]));$('end-time').value=`${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;$('end-time').dataset.resolvedEpoch=String(start.epoch+Number(button.dataset.hours)*3600000);$('end-time').dataset.resolvedValue=$('end-time').value;setHidden('query-error',true);updateRangeSummary();}));
  $('toggle-play').addEventListener('click',togglePlayback);
  $('back-30').addEventListener('click',()=>seek(state.time-30,null,true));$('forward-30').addEventListener('click',()=>seek(state.time+30,null,true));
  $('timeline-range').addEventListener('pointerdown',()=>{scrubPlayback=state.playing;state.playing=false;state.pinEventWave=false;renderPlayback(true);});
  $('timeline-range').addEventListener('input',event=>{state.pinEventWave=false;seek(event.target.value,null,scrubPlayback===null);});
  document.addEventListener('pointerup',finishScrub);document.addEventListener('pointercancel',finishScrub);
  $('end-replay').addEventListener('click',()=>requestExit());
  $('cancel-exit').addEventListener('click',cancelExit);$('confirm-exit').addEventListener('click',()=>finishReplay(state.exit?.target||'trace'));
  $('cancel-follow').addEventListener('click',cancelFollow);
  $('review-events').addEventListener('click',()=>{setTab('events');setHidden('completion-card',true);});
  $('complete-return').addEventListener('click',()=>finishReplay());
  $('restart-replay').addEventListener('click',restartReplay);
  $('return-query').addEventListener('click',()=>{state.page='trace';showNormal('trace');});
  $('warehouse-poi').addEventListener('click',()=>{$('scene-photo').classList.add('open');setHidden('warehouse-poi',true);$('area-label').textContent='全部区域';toast('已切换最新开顶场景底图');});
  $('warehouse-button').addEventListener('click',()=>toast('当前仓库：GHS · San Bernardino'));
  document.querySelector('.scene-search').setAttribute('role','button');document.querySelector('.scene-search').tabIndex=0;
  document.querySelector('.scene-search').addEventListener('click',()=>state.active?requestExit('devices'):toast('此预览聚焦订单回放；全局搜索使用现有产品入口'));
  document.querySelector('.scene-search').addEventListener('keydown',event=>{if(event.key==='Enter')document.querySelector('.scene-search').click();});
  $('scene').addEventListener('auxclick',event=>{if(event.button===1){event.preventDefault();if(state.active)requestExit('overview');}});
  document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>setTab(button.dataset.tab)));
  document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{state.view=button.dataset.view;if(state.view==='real')cancelFollow();syncSceneMode();}));
  document.addEventListener('keydown',event=>{
    if(state.exit){if(event.key==='Escape'){event.preventDefault();cancelExit();}if(event.key==='Tab'){const first=$('cancel-exit'),last=$('confirm-exit');if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}return;}
    if(event.key==='Home'&&state.active&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){event.preventDefault();requestExit('overview');return;}
    if(event.code==='Space'&&state.active&&!['INPUT','BUTTON'].includes(document.activeElement.tagName)){event.preventDefault();togglePlayback();}
  });
  document.addEventListener('visibilitychange',()=>{previousFrame=0;});
  renderNav();updateHeaderClock();setInterval(updateHeaderClock,1000);updateRangeSummary();syncSceneMode();
  const params=new URLSearchParams(location.search),previewState=params.get('state');
  if(previewState){queryOrders();if(previewState!=='orders'){startReplay(orders[0].id);if(params.has('speed')){state.speed=[1,2,4,8,16,32,64].includes(Number(params.get('speed')))?Number(params.get('speed')):1;renderSpeed();}if(previewState==='paused')seek(Number(params.get('time')||310));if(previewState==='running'&&params.has('time'))state.time=clamp(Number(params.get('time')),0,state.duration);if(previewState==='complete')seek(state.duration);if(previewState==='confirm'){state.time=310;requestExit('overview');}if(previewState==='follow'){state.time=230;followDevice('fork-2');}renderPlayback(true);}}
  window.orderReplayPreview=Object.freeze({snapshot:()=>({...state,camera:{...state.camera}}),forkState,truckState,waveEvents,warehouseDateTime,readRange,seek,startReplay,queryOrders,requestExit,cancelExit,finishReplay,followDevice,setTab});
  requestAnimationFrame(frame);
})();
