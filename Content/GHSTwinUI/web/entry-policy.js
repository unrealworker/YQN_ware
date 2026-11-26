(function(root,factory){
  const policy=factory();
  if(typeof module==='object'&&module.exports)module.exports=policy;
  else root.EntryPolicy=policy;
})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const ids=['ghs-ca','mpr-nj'];
  const browsing=phase=>['idle','selected','error'].includes(phase);
  const entering=(phase,gate)=>!['warehouse','returning','error'].includes(phase)&&gate!=='cancelling'&&
    (gate==='pending'||['loading','flying','revealing'].includes(phase));
  function catalog(rows){
    if(!Array.isArray(rows))return [];
    return ids.map(id=>rows.find(row=>row&&row.id===id&&typeof row.name==='string')).filter(Boolean);
  }
  function filter(rows,query='',region=''){
    const term=String(query).trim().toLocaleLowerCase();
    return catalog(rows).filter(row=>(!region||row.region===region)&&(!term||
      [row.id,row.name,row.city,row.cityShort,row.country,row.address].some(value=>String(value||'').toLocaleLowerCase().includes(term))));
  }
  function canEnter(phase,gate,id,rows){return gate==='idle'&&browsing(phase)&&catalog(rows).some(row=>row.id===id);}
  function advanceGate(current,event){
    if(event==='request')return 'pending';
    if(event==='cancel-request')return 'cancelling';
    if(event==='failed')return 'idle';
    if(current==='cancelling')return browsing(event)?'idle':'cancelling';
    if(['error','warehouse'].includes(event))return 'idle';
    if(['loading','flying','revealing'].includes(event))return 'acknowledged';
    return current==='pending'?'pending':'idle';
  }
  function curtainReady(phase,transition,width,height,lastAck){
    return ['flying','returning'].includes(phase)&&transition&&transition.awaitingCurtain===true&&
      Number.isSafeInteger(transition.generation)&&transition.generation>0&&transition.generation!==lastAck&&
      Number.isFinite(transition.opacity)&&transition.opacity>=1&&
      Number.isFinite(width)&&Number.isFinite(height)&&width>0&&height>0&&
      Number.isFinite(transition.width)&&Number.isFinite(transition.height)&&transition.width>0&&transition.height>0&&
      Math.abs(width-transition.width)<=1&&Math.abs(height-transition.height)<=1;
  }
  function catalogFrameReady(frame,width,height){
    if(!frame||frame.page!=='warehouses'||!frame.visible||!frame.opaque||!frame.stable)return false;
    const matches=(rect,left,top,w,h)=>rect&&['left','top','width','height'].every(key=>Number.isFinite(rect[key]))&&
      Math.abs(rect.left-left)<=1&&Math.abs(rect.top-top)<=1&&Math.abs(rect.width-w)<=1&&Math.abs(rect.height-h)<=1;
    return Number.isFinite(width)&&Number.isFinite(height)&&width>0&&height>0&&
      frame.header&&Number.isFinite(frame.header.height)&&frame.header.height>0&&frame.header.height<height&&
      matches(frame.portal,0,0,width,height)&&matches(frame.header,0,0,width,frame.header.height)&&
      matches(frame.content,0,frame.header.height,width,height-frame.header.height);
  }
  function imagePath(value){return typeof value==='string'&&/^assets\/[a-zA-Z0-9_./-]+\.(png|webp|jpe?g)$/.test(value)&&!value.includes('..')?value:'';}
  return {catalog,filter,canEnter,advanceGate,curtainReady,catalogFrameReady,imagePath,browsing,entering};
});
