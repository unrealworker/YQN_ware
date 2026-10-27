const fs=require('fs'),path=require('path'),M=require('../figma-import/src/model.cjs');
const pen=JSON.parse(fs.readFileSync(path.join(__dirname,'../migration.pen.json'))),ix=M.index(pen);
const payload=JSON.parse(fs.readFileSync(path.join(__dirname,'../figma-import/payload.json')));
const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
function render(n,parent={layout:'none'}){
 let css=['box-sizing:border-box'],flex=parent.layout&&parent.layout!=='none';
 css.push(flex?'position:relative':'position:absolute');if(!flex)css.push('left:'+(n.x||0)+'px','top:'+(n.y||0)+'px');
 if(typeof n.width==='number')css.push('width:'+n.width+'px');else if(n.width==='fill_container')css.push('flex:1','width:100%');
 if(typeof n.height==='number')css.push('height:'+n.height+'px');
 if(n.opacity!==undefined)css.push('opacity:'+n.opacity);
 if(n.cornerRadius)css.push('border-radius:'+n.cornerRadius+'px');
 if(n.type==='ellipse')css.push('border-radius:50%');
 if(n.clip)css.push('overflow:hidden');
 if(n.metadata?.scroll)css.push('overflow-y:auto');
 if(n.stroke)css.push('border:'+(n.strokeWidth||1)+'px solid '+n.stroke);
 if(n.rotation)css.push('transform:rotate('+n.rotation+'deg)','transform-origin:top left');
 if(n.enabled===false)css.push('display:none');
 if(n.effect){const es=Array.isArray(n.effect)?n.effect:[n.effect];css.push('box-shadow:'+es.map(e=>(e.shadowType==='inner'?'inset ':'')+(e.offset?.x||0)+'px '+(e.offset?.y||0)+'px '+(e.blur||0)+'px '+e.color).join(','));}
 let inside='';
 if(n.type==='text'){
   css.push('color:'+(n.fill||'#25364B'),'font-family:"'+(n.fontFamily||'Microsoft YaHei')+'",sans-serif','font-size:'+(n.fontSize||14)+'px','font-weight:'+(n.fontWeight||400),'line-height:'+(n.lineHeight||1.2),'text-align:'+(n.textAlign||'left'),'white-space:'+(n.textGrowth?'pre-wrap':'pre'),'letter-spacing:'+(n.letterSpacing||0)+'px');
   inside=esc(n.content);
 }else{
   if(typeof n.fill==='string')css.push('background:'+n.fill);
   if(n.fill?.type==='image'){let file=n.fill.url;if(!path.isAbsolute(file))file=path.join(__dirname,'../../GHS_Twin_SaaS_Concept',file);css.push('background-image:url(\''+'file:///'+file.replace(/\\/g,'/')+'\')','background-size:'+(n.fill.mode==='contain'?'contain':'cover'),'background-position:center','background-repeat:no-repeat');}
   if(n.type==='frame'&&n.layout!=='none'){css.push('display:flex','flex-direction:'+(n.layout==='vertical'?'column':'row'),'gap:'+(n.gap||0)+'px');if(n.padding)css.push('padding:'+(Array.isArray(n.padding)?n.padding.map(v=>v+'px').join(' '):n.padding+'px'));if(n.alignItems)css.push('align-items:'+n.alignItems);if(n.justifyContent)css.push('justify-content:'+n.justifyContent.replace('_','-'));}
   if(n.type==='svg')inside=n.svg.replace('<svg ','<svg style="display:block;width:100%;height:100%" ');
   if(n.type==='icon')inside='<svg width="100%" height="100%" viewBox="0 0 24 24" fill="none" stroke="'+(n.fill||'#25364B')+'" stroke-width="2">'+(payload.icons[n.icon]||'')+'</svg>';
   if(n.type==='path')inside='<svg width="100%" height="100%" viewBox="'+(n.viewBox||[0,0,n.width,n.height]).join(' ')+'"><path d="'+esc(n.geometry)+'" fill="'+(n.fill||'none')+'" stroke="'+(n.stroke||'none')+'" stroke-width="'+(n.strokeWidth||1)+'"/></svg>';
   inside+=(n.children||[]).map(c=>render(c,n)).join('');
 }
 return '<div data-node="'+esc(n.id)+'" title="'+esc(n.name)+'" style="'+esc(css.join(';'))+'">'+inside+'</div>';
}
for(const number of [31,11,47,50]){let board=M.expand(pen.children.find(b=>parseInt(b.name)===number),ix.components);board.x=0;board.y=0;const html='<!doctype html><html><head><meta charset="UTF-8"><title>SaasNew QA '+number+'</title><style>html,body{margin:0;width:1920px;height:1080px;background:#ccc}*{flex-shrink:0}::-webkit-scrollbar{width:5px}::-webkit-scrollbar-thumb{background:#d0d8e5;border-radius:4px}</style></head><body>'+render(board)+'</body></html>';fs.writeFileSync(path.join(__dirname,'board-'+number+'.html'),html);}
console.log('QA-only HTML 31,11,47,50 written');
