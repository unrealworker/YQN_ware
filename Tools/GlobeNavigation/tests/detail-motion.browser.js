// Run against the rendered globe.html. The caller may isolate its native receive
// hook while this suite supplies snapshots, then restore the native catalog.
(async function(){
 const receive=window.ghsGlobe.receive;
 const results=[],check=(name,pass,details={})=>results.push({name,pass,details});
 const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 const until=async predicate=>{for(let i=0;i<100;i++){if(predicate())return true;await wait(20);}return false;};
 const $=id=>document.getElementById(id),opacity=el=>Number(getComputedStyle(el).opacity);
 const imageUrl=color=>'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="230"><rect width="400" height="230" fill="'+color+'"/></svg>');
 const a=imageUrl('#ff0000'),b=imageUrl('#0000ff');
 const warehouses=[{id:'motion-a',name:'仓库 A',city:'城市 A',address:'地址 A',thumbnail:a},{id:'motion-b',name:'仓库 B',city:'城市 B',address:'地址 B',thumbnail:b}];
 const send=(selectedId,selectionInputSource='pointer',extra={})=>receive({phase:selectedId?'selected':'idle',selectedId,selectionInputSource,stageVisible:true,warehouses,pois:[],countries:[],nativeWarehouseAnnotations:true,nativeCountryLabels:true,transition:{opacity:0},...extra});
 const photo=()=>document.querySelector('.thumbnail-outgoing');
 const photoAnimation=()=>photo()?.getAnimations().find(animation=>animation.effect.getKeyframes().some(frame=>'opacity' in frame));
 const commandsFrom=action=>{const native=window.ue,commands=[];try{window.ue={twin:{command:json=>commands.push(JSON.parse(json))}};action();}finally{window.ue=native;}return commands;};
 const originalMotion=document.body.dataset.reduced==='true'?'reduced':'normal',NativeImage=window.Image;
 try{
  commandsFrom(()=>window.ghsGlobe.setMotionPreference('normal'));
  send('');send('motion-a','unknown');await until(()=>$('thumbnail').src===a&&$('thumbnail').complete);await wait(700);
  check('initial detail opening does not add a selection crossfade',!photo());
  const card=$('enter').getBoundingClientRect(),width=document.querySelector('.warehouse-card').getBoundingClientRect().width;
  send('motion-b');
  check('warehouse identity and city change immediately',$('name').textContent==='仓库 B'&&$('city').textContent==='城市 B');
  const commands=commandsFrom(()=>$('enter').click());
  check('entry immediately targets the new selection without waiting for motion',commands.some(c=>c.action==='enter'&&c.id==='motion-b'&&c.inputSource==='unknown'),{commands});
  await until(()=>!!photoAnimation());const fade=photoAnimation();
  check('pointer switch starts a 180ms standard opacity transition',!!fade&&fade.effect.getTiming().duration===180&&fade.effect.getTiming().easing==='cubic-bezier(0.4, 0, 0.2, 1)',{timing:fade?.effect.getTiming()});
  if(fade){fade.pause();await fade.ready;fade.currentTime=90;}
  await until(()=>$('thumbnail').src===b&&$('thumbnail').complete);
  const half=photo()?opacity(photo()):NaN;
  check('outgoing photograph has a real intermediate alpha',half>0&&half<1,{opacity:half});
  const same=photo();receive({phase:'selected',selectedId:'motion-b',pois:[],transition:{opacity:0}});
  check('ordinary native state refresh does not restart the crossfade',photo()===same&&photoAnimation()===fade);
  const position=$('enter').getBoundingClientRect();
  check('button position and card width do not animate',Math.abs(position.x-card.x)<.1&&Math.abs(position.y-card.y)<.1&&Math.abs(document.querySelector('.warehouse-card').getBoundingClientRect().width-width)<.1);
  send('motion-a');const reversed=photo(),reverseFade=photoAnimation();
  // The canvas is a snapshot of the rendered red/blue blend, not a restart
  // from the old full-opacity photograph. These fixtures permit pixel reads.
  const pixel=reversed?.getContext('2d').getImageData(0,0,1,1).data;
  check('rapid reversal starts from the current visible blend',!!pixel&&Math.abs(pixel[0]/255-half)<.025&&Math.abs(pixel[2]/255-(1-half))<.025,{pixel:pixel?Array.from(pixel):null,previousAlpha:half});
  check('rapid switching keeps exactly one outgoing noninteractive layer',document.querySelectorAll('.thumbnail-outgoing').length===1&&reversed.getAttribute('aria-hidden')==='true'&&getComputedStyle(reversed).pointerEvents==='none'&&!reversed.id);
  if(reverseFade){reverseFade.finish();}await wait(250);
  check('completed transition removes outgoing layers',!photo()&&$('thumbnail').src===a&&opacity($('thumbnail'))===1);
  send('motion-b','keyboard');
  check('keyboard selection changes content without new detail animations',!photo()&&$('city').getAnimations().length===0&&$('address').getAnimations().length===0&&$('name').textContent==='仓库 B');
  await until(()=>$('thumbnail').src===b);send('motion-a','unknown');
  check('programmatic or legacy unknown selection has no detail animation',!photo()&&$('city').getAnimations().length===0);
  await until(()=>$('thumbnail').src===a);
  commandsFrom(()=>window.ghsGlobe.setMotionPreference('reduced'));send('motion-b');await until(()=>!!photoAnimation());
  const reduced=photoAnimation();check('reduced motion retains a 120ms opacity-only transition',!!reduced&&reduced.effect.getTiming().duration===120&&reduced.effect.getKeyframes().every(frame=>!('transform' in frame)),{timing:reduced?.effect.getTiming()});
  if(reduced)reduced.finish();await wait(150);
  let delayed;
  window.Image=function(){const image=new NativeImage(),descriptor=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');Object.defineProperty(image,'src',{get(){return descriptor.get.call(image);},set(value){if(value===a)delayed=()=>descriptor.set.call(image,value);else descriptor.set.call(image,value);}});return image;};
  send('motion-a');send('motion-b');await wait(180);if(delayed)delayed();await wait(200);
  check('late image completion cannot overwrite a newer selection',$('thumbnail').src===b&&$('name').textContent==='仓库 B');window.Image=NativeImage;
  send('motion-a');receive({phase:'flying'});
  check('entering the scene immediately removes temporary detail layers',!photo()&&$('city').getAnimations().length===0&&$('address').getAnimations().length===0);
  receive({phase:'selected'});await until(()=>$('thumbnail').src===a);
  check('returning restores the current photograph without replaying selection motion',$('thumbnail').src===a&&!photo());
  send('motion-a','unknown',{warehouses:[{...warehouses[0],thumbnail:'assets/__missing_motion_fixture__.png'},warehouses[1]]});
  await until(()=>$('thumbnail').src.endsWith('/assets/warehouse-overview.png'));
  check('failed thumbnail resolves to the existing fallback',$('thumbnail').src.endsWith('/assets/warehouse-overview.png'));
  send('');check('clearing selection cleans all temporary detail layers',!photo()&&$('city').getAnimations().length===0&&$('address').getAnimations().length===0);
  return {success:results.every(result=>result.pass),results};
 }finally{window.Image=NativeImage;send('');commandsFrom(()=>window.ghsGlobe.setMotionPreference(originalMotion));}
})();
