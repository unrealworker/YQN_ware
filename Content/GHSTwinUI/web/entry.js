(function(){
  'use strict';
  const $=id=>document.getElementById(id);
  const policy=window.EntryPolicy;
  const motionQuery=window.matchMedia('(prefers-reduced-motion: reduce)');
  let state={phase:'idle',stageVisible:true,selectedId:'',warehouses:[],pois:[],countries:[],transition:{opacity:0}};
  let loggedIn=false,page='login',pageGeneration=0,ready=false,catalogKey='',catalogReceived=false;
  let gate='idle',requestId='',localError='',lastPhase='idle',curtainFrame=0,curtainAck=null;
  let reduced=motionQuery.matches,returnPending=false;
  let helpGeneration=0;
  const animations=new Set();
  const icon=name=>'<svg aria-hidden="true"><use href="#'+name+'"/></svg>';
  const escape=value=>String(value==null?'':value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  function bridge(){return window.ue&&window.ue.twin;}
  function inputSource(event){return event&&event.isTrusted?(event.detail>0?'pointer':'keyboard'):'unknown';}
  function focus(element){if(element&&!element.hidden)element.focus({preventScroll:true});}
  function command(action,params,onFailure){
    const target=bridge();
    if(!target||typeof target.command!=='function'){if(onFailure)onFailure();return false;}
    try{
      Promise.resolve(target.command(JSON.stringify(Object.assign({action},params||{})))).catch(()=>{if(onFailure)onFailure();});
      return true;
    }catch(error){if(onFailure)onFailure();return false;}
  }
  function animate(element,keyframes,options){
    if(reduced||!element.animate)return Promise.resolve();
    const animation=element.animate(keyframes,options);animations.add(animation);
    return animation.finished.catch(()=>{}).then(()=>{animations.delete(animation);animation.cancel();});
  }
  function markInteractive(element,active){
    element.toggleAttribute('inert',!active);
    element.setAttribute('aria-hidden',String(!active));
  }
  async function showPage(next){
    if(next===page)return;
    const generation=++pageGeneration;
    const outgoing=$(page==='login'?'login-page':'warehouse-page');
    const incoming=$(next==='login'?'login-page':'warehouse-page');
    page=next;document.body.dataset.page=next;
    $('logout-button').hidden=next==='login';
    markInteractive(outgoing,false);
    await animate(outgoing,[{opacity:1,transform:'translateY(0)'},{opacity:0,transform:'translateY(-6px)'}],{duration:140,easing:'cubic-bezier(.4,0,1,1)',fill:'both'});
    if(generation!==pageGeneration)return;
    outgoing.hidden=true;incoming.hidden=false;markInteractive(incoming,true);
    const entrance=animate(incoming,[{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'translateY(0)'}],{duration:320,easing:'cubic-bezier(.22,1,.36,1)'});
    if(next==='warehouses')revealCards();
    focus($(next==='login'?'login-title':'warehouse-title'));
    await entrance;
  }
  function revealCards(){
    if(reduced||page!=='warehouses')return;
    $('warehouse-list').querySelectorAll('.card-reveal').forEach((element,index)=>{
      animate(element,[{opacity:0,transform:'translateY(12px)'},{opacity:1,transform:'translateY(0)'}],{duration:360,delay:index*45,easing:'cubic-bezier(.22,1,.36,1)',fill:'backwards'});
    });
  }
  function title(row){return row.id==='ghs-ca'?'GHS 仓库':'MPR 仓库';}
  function card(row){
    const image=policy.imagePath(row.thumbnail);
    return '<div class="card-reveal"><button class="warehouse-card" type="button" data-enter="'+escape(row.id)+'" aria-label="进入'+escape(title(row))+'">'+
      '<span class="card-photo">'+(image?'<img src="'+escape(image)+'" alt="'+escape(title(row))+'场景预览" decoding="async">':'')+'</span>'+
      '<span class="card-content"><span class="card-title">'+icon('warehouse-icon')+escape(title(row))+'</span>'+
      '<span class="card-city">'+escape(row.cityShort||row.city)+' · '+escape(row.country)+'</span>'+
      '<span class="card-address">'+escape(row.address)+'</span>'+
      '<span class="card-footer"><span class="card-status"><i class="status-dot" aria-hidden="true"></i><span class="card-status-label">场景已接入</span></span><svg class="card-arrow" aria-hidden="true"><use href="#arrow-icon"/></svg><i class="spinner card-spinner" aria-hidden="true"></i></span></span></button></div>';
  }
  function renderCards(){
    const previous=document.activeElement&&document.activeElement.dataset.enter;
    const rows=policy.filter(state.warehouses,$('warehouse-search').value,$('warehouse-region').value);
    $('warehouse-list').innerHTML=rows.map(card).join('');
    $('empty-state').hidden=rows.length>0||!catalogReceived;
    $('warehouse-count').textContent=policy.catalog(state.warehouses).length;
    $('catalog-status').hidden=catalogReceived&&policy.catalog(state.warehouses).length>0;
    $('catalog-status').textContent=catalogReceived?'暂无可进入的仓库。':'正在读取仓库目录…';
    if(previous){const button=[...$('warehouse-list').querySelectorAll('[data-enter]')].find(node=>node.dataset.enter===previous);focus(button||$('warehouse-search'));}
    renderStatus();revealCards();
  }
  function updateCatalog(){
    const key=JSON.stringify(policy.catalog(state.warehouses));
    if(key===catalogKey)return;
    catalogKey=key;
    const previous=$('warehouse-region').value;
    const regions=[...new Set(policy.catalog(state.warehouses).map(row=>row.region).filter(Boolean))];
    $('warehouse-region').innerHTML='<option value="">全部地区</option>'+regions.map(region=>'<option value="'+escape(region)+'">'+escape(region)+'</option>').join('');
    $('warehouse-region').value=regions.includes(previous)?previous:'';
    renderCards();
  }
  function renderStatus(){
    const busy=gate!=='idle'||!policy.browsing(state.phase);
    const selectedId=(gate==='pending'||localError?requestId:state.selectedId)||requestId;
    const row=policy.catalog(state.warehouses).find(value=>value.id===selectedId);
    const failed=localError||state.error||'';
    $('entry-notice').hidden=!failed;
    $('entry-notice').dataset.error=String(!!failed);
    $('entry-notice-text').textContent=failed;
    $('entry-retry').hidden=!failed||busy||!row;
    $('warehouse-search').disabled=busy;$('warehouse-region').disabled=busy;$('logout-button').disabled=busy;$('help-button').disabled=busy;
    for(const button of $('warehouse-list').querySelectorAll('[data-enter]')){
      const selected=policy.entering(state.phase,gate)&&button.dataset.enter===selectedId;
      button.disabled=busy;
      button.setAttribute('aria-disabled',String(busy));
      button.setAttribute('aria-busy',String(selected));
      button.querySelector('.card-status-label').textContent=selected?'正在进入仓库':'场景已接入';
    }
  }
  function enter(id,event){
    if(!loggedIn||!policy.canEnter(state.phase,gate,id,state.warehouses))return;
    requestId=id;localError='';gate=policy.advanceGate(gate,'request');renderStatus();
    command('enter',{id,inputSource:inputSource(event)},()=>{
      gate=policy.advanceGate(gate,'failed');localError='仓库连接尚未就绪，请稍后重试。';renderStatus();
    });
  }
  function cancel(){
    if(!['idle','selected','loading','error'].includes(state.phase)||gate==='cancelling')return;
    gate=policy.advanceGate(gate,'cancel-request');localError='';renderStatus();
    command('cancel',{},()=>{gate=policy.advanceGate(gate,'failed');localError='暂时无法取消，请稍后重试。';renderStatus();});
  }
  function viewport(){
    if(state.phase==='warehouse'||innerWidth<1||innerHeight<1)return;
    command('viewport',{width:innerWidth,height:innerHeight,sceneX:0,sceneY:0,sceneWidth:innerWidth,sceneHeight:innerHeight});
  }
  function catalogFrame(){
    const portal=$('portal'),content=$('warehouse-page'),header=portal.querySelector('.topbar');
    const visible=element=>{
      const style=getComputedStyle(element);
      return !element.closest('[hidden],[inert],[aria-hidden="true"]')&&style.display!=='none'&&style.visibility==='visible'&&Number(style.opacity)===1;
    };
    const background=getComputedStyle(portal).backgroundColor.match(/^rgba?\(([^)]+)\)$/);
    const channels=background?background[1].trim().split(/[,\s/]+/):[];
    return {page,stable:catalogReceived&&animations.size===0,
      visible:[portal,header,content,content.querySelector('.page-heading'),content.querySelector('.warehouse-toolbar'),$('warehouse-list')].every(visible),
      opaque:channels.length>=3&&(channels.length===3||Number(channels[3])===1),
      portal:portal.getBoundingClientRect(),header:header.getBoundingClientRect(),content:content.getBoundingClientRect()};
  }
  function queueCurtain(){
    if(curtainFrame||!policy.curtainReady(state.phase,state.transition,innerWidth,innerHeight,curtainAck))return;
    if(!policy.catalogFrameReady(catalogFrame(),innerWidth,innerHeight)){
      curtainFrame=requestAnimationFrame(()=>{curtainFrame=0;queueCurtain();});
      return;
    }
    const generation=state.transition.generation;
    // The opaque catalog itself covers the scene while loading. Acknowledge only
    // after it stays fully laid out and visible for two frames; native also checks paint.
    curtainFrame=requestAnimationFrame(()=>{
      if(!policy.catalogFrameReady(catalogFrame(),innerWidth,innerHeight)){curtainFrame=0;queueCurtain();return;}
      curtainFrame=requestAnimationFrame(()=>{
        curtainFrame=0;
        if(state.transition.generation!==generation||!policy.curtainReady(state.phase,state.transition,innerWidth,innerHeight,curtainAck))return;
        if(!policy.catalogFrameReady(catalogFrame(),innerWidth,innerHeight)){queueCurtain();return;}
        curtainAck=generation;
        command('curtainReady',{generation,width:innerWidth,height:innerHeight});
      });
    });
  }
  function receive(next){
    const candidate=window.GlobePolicy.nextState(state,next);
    if(!candidate)return;
    if(candidate.warehouses!==state.warehouses)catalogReceived=true;
    const previous=state.phase;
    state=candidate;gate=policy.advanceGate(gate,state.phase);
    if(!policy.browsing(state.phase))closeHelp(true);
    if(['loading','flying','revealing','warehouse','returning'].includes(state.phase)&&!loggedIn){loggedIn=true;showPage('warehouses');}
    if(typeof state.reducedMotion==='boolean'&&state.reducedMotion!==reduced){reduced=state.reducedMotion;applyMotion(false);}
    document.body.dataset.phase=state.phase;
    const sceneVisible=policy.sceneVisible(state.phase,state.transition);
    document.body.dataset.sceneVisible=String(sceneVisible);
    $('back-button').dataset.inHeader=String(state.returnInHeader===true);
    $('back-button').hidden=state.phase!=='warehouse';
    $('back-button').disabled=returnPending&&state.phase==='warehouse';
    $('back-button').title=state.error?'返回失败：'+state.error+'。点击重试':'返回仓库选择';
    if(state.phase!=='warehouse')returnPending=false;
    if(state.phase==='warehouse'&&state.error){returnPending=false;$('back-button').disabled=false;}
    markInteractive($('portal'),!sceneVisible);
    updateCatalog();renderStatus();queueCurtain();
    if(state.phase!==lastPhase){
      if(state.phase!=='warehouse')requestAnimationFrame(viewport);
      if(state.phase==='warehouse')requestAnimationFrame(()=>focus($('back-button')));
      if(state.phase==='returning')requestAnimationFrame(()=>focus($('warehouse-title')));
      if(policy.browsing(state.phase)&&['returning','loading','error'].includes(previous)){
        requestAnimationFrame(()=>{const selected=[...$('warehouse-list').querySelectorAll('[data-enter]')].find(node=>node.dataset.enter===(state.selectedId||requestId));focus(selected||$('warehouse-title'));});
      }
    }
    lastPhase=state.phase;
  }
  function applyMotion(send=true){
    document.body.dataset.reduced=String(reduced);
    if(reduced)for(const animation of animations)animation.cancel();
    if(send)command('reducedMotion',{enabled:reduced});
  }
  function setMotionPreference(value){reduced=value==='reduced'||motionQuery.matches;applyMotion();}
  async function closeHelp(immediate=false){
    const dialog=$('help-dialog');if(!dialog.open)return;
    if(dialog.dataset.closing==='true'&&!immediate)return;
    const generation=++helpGeneration;dialog.dataset.closing='true';
    if(!immediate)await animate(dialog,[{opacity:1,transform:'translateY(0) scale(1)'},{opacity:0,transform:'translateY(4px) scale(.98)'}],{duration:160,easing:'cubic-bezier(.4,0,1,1)',fill:'both'});
    if(generation===helpGeneration){dialog.close();delete dialog.dataset.closing;}
  }
  $('login-form').addEventListener('submit',event=>{
    event.preventDefault();
    if(loggedIn)return;
    loggedIn=true;
    // The entry is intentionally account-free: never read, store or transmit credentials.
    $('login-form').reset();$('company-password').type='password';$('password-toggle').setAttribute('aria-pressed','false');$('password-toggle').setAttribute('aria-label','显示密码');
    showPage('warehouses');
  });
  $('logout-button').addEventListener('click',()=>{
    if(!policy.browsing(state.phase)||gate!=='idle')return;
    loggedIn=false;$('login-form').reset();localError='';command('cancel');showPage('login');
  });
  $('password-toggle').addEventListener('click',()=>{
    const show=$('company-password').type==='password';$('company-password').type=show?'text':'password';
    $('password-toggle').setAttribute('aria-pressed',String(show));$('password-toggle').setAttribute('aria-label',show?'隐藏密码':'显示密码');
  });
  $('warehouse-list').addEventListener('click',event=>{const button=event.target.closest('[data-enter]');if(button)enter(button.dataset.enter,event);});
  $('warehouse-search').addEventListener('input',renderCards);$('warehouse-region').addEventListener('change',renderCards);
  $('entry-retry').addEventListener('click',event=>enter((localError?requestId:state.selectedId)||requestId,event));
  $('back-button').addEventListener('click',event=>{
    if(returnPending||state.phase!=='warehouse')return;
    returnPending=true;$('back-button').disabled=true;
    command('back',{inputSource:inputSource(event)},()=>{returnPending=false;$('back-button').disabled=false;$('back-button').title='暂时无法返回，请重试';});
  });
  $('help-button').addEventListener('click',()=>{if(gate==='idle'&&policy.browsing(state.phase)){$('help-dialog').showModal();}});
  $('help-dialog').addEventListener('submit',event=>{event.preventDefault();closeHelp();});
  $('help-dialog').addEventListener('cancel',event=>{event.preventDefault();closeHelp();});
  $('help-dialog').addEventListener('close',()=>{if(gate==='idle'&&policy.browsing(state.phase))focus($('help-button'));});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!$('help-dialog').open&&state.phase==='loading'){event.preventDefault();cancel();}});
  window.addEventListener('resize',()=>{curtainAck=null;viewport();queueCurtain();});
  if(motionQuery.addEventListener)motionQuery.addEventListener('change',()=>{reduced=motionQuery.matches;applyMotion();});
  else motionQuery.addListener(()=>{reduced=motionQuery.matches;applyMotion();});
  window.ghsGlobe={receive,setMotionPreference,showCluster:()=>{}};
  window.ghsEntry={getPage:()=>page};
  applyMotion(false);
  // A browser preview uses the same local catalog, but never simulates a successful
  // warehouse load. In UE the authoritative catalog is delivered by the bridge.
  if(!bridge()&&typeof fetch==='function')fetch('../data/warehouses.json').then(response=>response.ok?response.json():Promise.reject()).then(data=>{
    if(!ready&&Array.isArray(data.warehouses)){state.warehouses=data.warehouses;catalogReceived=true;updateCatalog();}
  }).catch(()=>{});
  const handshake=setInterval(()=>{
    const target=bridge();if(!target||typeof target.command!=='function')return;
    if(!ready){ready=true;command('ready');viewport();applyMotion();}
    if(target.getstate)Promise.resolve(target.getstate()).then(receive).catch(()=>{});
    clearInterval(handshake);
  },100);
})();
