// Run in globe.html without a native bridge. Returns rendered positions, not CSS declarations.
// Example: await page.evaluate(await fs.readFile(testPath, 'utf8')).
(async function(){
 const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 const frame=()=>new Promise(resolve=>requestAnimationFrame(resolve));
 const results=[];
 const check=(name,pass,details)=>results.push({name,pass,details});
 const receive=window.ghsGlobe.receive;
 const rect=document.getElementById('stage').getBoundingClientRect();
 const x=rect.left+rect.width*.4,y=rect.top+rect.height*.5;
 const point=(id,px,visible=true)=>({id,ids:[id],x:px,y,visible});
 const send=(pois,extra={})=>receive({phase:'idle',stageVisible:true,selectedId:'',pois,countries:[],transition:{opacity:0},...extra});
 const node=()=>document.getElementById('poi-a');
 const position=()=>node().getBoundingClientRect().left;
 window.ghsGlobe.setMotionPreference('normal');
 send([point('a',x)],{warehouses:[{id:'a',name:'A'},{id:'b',name:'B'}]});
 const initial=position();
 check('first visible marker is placed directly at its anchor',Math.abs(initial-x)<.2,{initial,x});
 await wait(300);
 await frame();
 send([point('a',x+48)]);
 const immediate=position();
 // Seek the real browser transition so GPU load / background rAF throttling cannot skip the sample.
 const tracking=node().getAnimations().find(animation=>animation.transitionProperty==='transform');
 let midpoint=position();
 if(tracking){tracking.pause();await tracking.ready;tracking.currentTime=Number(tracking.effect.getTiming().duration)/2;midpoint=position();tracking.play();await Promise.race([tracking.finished,wait(2000)]);}
 check('projection update moves through intermediate screen positions',Math.abs(immediate-initial)<1&&midpoint>initial+1&&midpoint<x+47,{initial,immediate,midpoint});
 await wait(150);
 check('marker settles at the latest geographic anchor',Math.abs(position()-(x+48))<.2,{actual:position(),expected:x+48});
 const retained=node();
 const focused=retained.querySelector('.poi-select');focused.focus();
 send([point('a',x+48),point('b',x+rect.width*.3)]);
 check('other markers entering the viewport preserve the existing anchor node',node()===retained,{});
 check('continuous marker retains keyboard focus when a neighbour appears',document.activeElement===focused,{});
 const retainedWithNeighbour=node();
 send([point('a',x+48)]);
 check('other markers leaving the viewport preserve the existing anchor node',node()===retainedWithNeighbour,{});
 send([]);await frame();send([point('a',x+90)]);
 check('reappearing marker starts at its current anchor without flying across the map',Math.abs(position()-(x+90))<.2,{actual:position(),expected:x+90});
 await wait(300);
 send([point('a',x+90)],{phase:'selected',selectedId:'a'});
 check('selection still updates the marker',node().dataset.selected==='true',{});
 window.ghsGlobe.setMotionPreference('reduced');
 await frame();send([point('a',x+120)]);
 await wait(90);
 check('reduced motion does not stretch geographic tracking to 120 milliseconds',Math.abs(position()-(x+120))<.5,{actual:position(),expected:x+120});
 window.ghsGlobe.setMotionPreference('normal');
 send([point('a',x+120)],{warehouses:[{id:'a',name:'Updated A'}]});
 check('catalog update refreshes marker text',node().textContent.includes('Updated A'),{});
 const stage=document.getElementById('stage'),oldWidth=stage.style.width;
 stage.style.width=(rect.width-10)+'px';
 send([point('a',x+135)]);
 check('viewport resize directly places the new anchor',Math.abs(position()-(x+135))<.2,{actual:position(),expected:x+135});
 stage.style.width=oldWidth;
 send([],{warehouses:[]});
 check('empty catalog removes the old clickable markers',document.querySelectorAll('#pois .poi').length===0,{});
 return {success:results.every(r=>r.pass),results};
})();
