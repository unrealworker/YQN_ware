'use strict';
// Reconstruct saved production CEF geometry as editable, absolutely positioned Pen nodes.
// No production state, original .pen, or Figma document is changed by this module.
const fs = require('fs');
const path = require('path');
const num = (value, fallback = 0) => Number.isFinite(parseFloat(value)) ? parseFloat(value) : fallback;
const round = value => Math.round(value * 10000) / 10000;
const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value));
const esc = value => String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
const unesc = value => String(value).replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&#(\d+);/g, (_,n)=>String.fromCodePoint(+n));
function color(value, fallback = '#00000000') {
  if (!value || value === 'none' || value === 'transparent') return fallback;
  if (/^#[\da-f]{3,8}$/i.test(value)) return value;
  const match = String(value).match(/^rgba?\(([^)]+)\)$/);
  if (!match) throw new Error('Unsupported CSS color: ' + value);
  const parts = match[1].split(/\s*,\s*/).map(Number);
  return '#' + parts.slice(0,3).map(n=>clamp(Math.round(n),0,255).toString(16).padStart(2,'0')).join('') + (parts.length>3 ? clamp(Math.round(parts[3]*255),0,255).toString(16).padStart(2,'0') : '');
}
function splitComma(text) {
  let depth=0,start=0,out=[];
  for (let i=0;i<text.length;i++) { if(text[i]==='(')depth++; if(text[i]===')')depth--; if(text[i]===','&&!depth){out.push(text.slice(start,i).trim());start=i+1;} }
  out.push(text.slice(start).trim());return out;
}
function gradientSvg(value, width, height, radius, id) {
  const match = value.match(/^linear-gradient\((.*)\)$/); if(!match)throw new Error('Unsupported background: '+value);
  const parts=splitComma(match[1]); let angle=180;
  if(/^(to |[-\d.]+deg)/.test(parts[0])) {
    const direction=parts.shift();angle=direction==='to right'?90:direction==='to left'?270:direction==='to top'?0:direction==='to bottom'?180:num(direction,180);
  }
  const rad=angle*Math.PI/180,dx=Math.sin(rad),dy=-Math.cos(rad);
  const stops=parts.map((part,i)=>{const m=part.match(/^(rgba?\([^)]+\)|#[\da-f]+|[a-z]+)(?:\s+([\d.]+)(%|px))?$/i);if(!m)throw new Error('Unsupported gradient stop '+part);let offset=m[2]===undefined?i/(parts.length-1):m[3]==='%'?+m[2]/100:+m[2]/Math.max(width,height);return '<stop offset="'+round(offset*100)+'%" stop-color="'+color(m[1])+'"/>';});
  return '<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'" viewBox="0 0 '+width+' '+height+'"><defs><linearGradient id="'+id+'" x1="'+round((1-dx)*50)+'%" y1="'+round((1-dy)*50)+'%" x2="'+round((1+dx)*50)+'%" y2="'+round((1+dy)*50)+'%">'+stops.join('')+'</linearGradient></defs><rect width="'+width+'" height="'+height+'" rx="'+radius+'" fill="url(#'+id+')"/></svg>';
}
function attr(tag, key, fallback='') {const m=tag.match(new RegExp('(?:^|\\s)'+key+'="([^"]*)"'));return m?unesc(m[1]):fallback;}
function textNode(id, content, x, y, width, height, style, extra={}) {
  const fontSize=num(style.fontSize,14),lineHeight=num(style.lineHeight,fontSize*1.4);
  return {type:'text',id,name:content.slice(0,70),content,x:round(x),y:round(y),width:round(Math.max(.1,width)),height:round(Math.max(fontSize,height)),fontFamily:/[^\x00-\x7f]/.test(content)?'Microsoft YaHei':'Arial',fontSize,fontWeight:String(style.fontWeight||'400'),lineHeight:round(lineHeight/fontSize),fill:color(style.color,'#25364B'),textGrowth:'fixed-width-height',textAlign:'left',textAlignVertical:'top',...extra};
}
function boxPaint(node, style, id, warnings) {
  const bg=color(style.backgroundColor);if(bg!=='#00000000')node.fill=bg;
  node.opacity=clamp(num(style.opacity,1),0,1);
  node.cornerRadius=style.borderRadius?.includes('%')?Math.min(node.width,node.height)*num(style.borderRadius)/100:num(style.borderRadius);
  const borders=['Top','Right','Bottom','Left'].map(side=>({side,width:num(style['border'+side+'Width']),color:color(style['border'+side+'Color'])}));
  if(borders.every(b=>b.width===borders[0].width&&b.color===borders[0].color)&&borders[0].width>0){node.stroke=borders[0].color;node.strokeWidth=borders[0].width;node.strokeAlignment='inner';}
  else for(const b of borders.filter(b=>b.width>0)){
    const horizontal=b.side==='Top'||b.side==='Bottom';node.children.push({type:'rectangle',id:id+'-border-'+b.side,name:b.side+' border',x:b.side==='Right'?node.width-b.width:0,y:b.side==='Bottom'?node.height-b.width:0,width:horizontal?node.width:b.width,height:horizontal?b.width:node.height,fill:b.color});
  }
  if(style.backgroundImage&&style.backgroundImage!=='none')node.children.unshift({type:'svg',id:id+'-gradient',name:'原生渐变背景',x:0,y:0,width:node.width,height:node.height,svg:gradientSvg(style.backgroundImage,node.width,node.height,node.cornerRadius,id.replace(/[^a-z\d]/gi,''))});
  if(style.boxShadow&&style.boxShadow!=='none') {
    const shadows=splitComma(style.boxShadow);node.effect=[];
    for(const shadow of shadows){const c=shadow.match(/rgba?\([^)]+\)|#[\da-f]+/i),v=shadow.replace(c?.[0]||'','').match(/-?[\d.]+px/g)||[];if(c&&v.length>=3)node.effect.push({type:'shadow',shadowType:shadow.includes('inset')?'inner':'outer',color:color(c[0]),offset:{x:num(v[0]),y:num(v[1])},blur:num(v[2])});else warnings.push(id+': unparsed shadow '+shadow);}
    if(!node.effect.length)delete node.effect;
  }
}
function addPseudo(node, source, key, warnings) {
  const pseudo=source[key];if(!pseudo)return;
  const s=pseudo.style||{},width=num(pseudo.width),height=num(pseudo.height);if(width<=0||height<=0)return;
  const base=source.style||{},id=node.id+'-'+key.replace(/:/g,''),matrix=s.transform?.match(/^matrix\(([^)]+)\)/)?.[1].split(',').map(Number);
  let x=pseudo.left!=='auto'?num(pseudo.left):pseudo.right!=='auto'?node.width-num(pseudo.right)-width:num(base.paddingLeft);
  let y=pseudo.top!=='auto'?num(pseudo.top):pseudo.bottom!=='auto'?node.height-num(pseudo.bottom)-height:num(base.paddingTop);
  // Inline ::before markers are vertically centered in their flex row.
  if(s.position!=='absolute'&&base.display?.includes('flex')&&base.alignItems==='center')y=(node.height-height)/2;
  if(source.attributes?.role==='switch'){x=num(base.paddingLeft);y=(node.height-height)/2;}
  if(matrix){x+=matrix[4]||0;y+=matrix[5]||0;}
  const p={type:s.borderRadius==='50%'?'ellipse':'rectangle',id,name:key+' · '+source.className,x:round(x),y:round(y),width,height,fill:color(s.backgroundColor),cornerRadius:num(s.borderRadius)};
  if(matrix&&Math.abs(matrix[1])>.001){p.rotation=round(Math.atan2(matrix[1],matrix[0])*180/Math.PI);const a=p.rotation*Math.PI/180;p.x=round(x+width/2-Math.cos(a)*width/2+Math.sin(a)*height/2);p.y=round(y+height/2-Math.sin(a)*width/2-Math.cos(a)*height/2);}
  node.children.push(p);
  if(pseudo.content&&!['""',"''",'none','normal'].includes(pseudo.content)){
    const text=pseudo.content.replace(/^['"]|['"]$/g,'');node.children.push(textNode(id+'-text',text,x,y,width,height,s));
  }
}
function svgChildren(source,id,warnings) {
  const s=source.style||{},b=source.bounds,children=[];
  let svg=source.svg.replace(/currentColor/g,s.color||'#25364B');
  // Imported SVG does not inherit browser CSS. Place computed icon properties on root.
  svg=svg.replace(/<svg\b([^>]*)>/,(_,attrs)=>{
    let a=attrs.replace(/\sstyle="[^"]*"/g,'');
    const add=(key,value)=>{if(!new RegExp('(?:^|\\s)'+key+'=').test(a))a+=' '+key+'="'+esc(value)+'"';};
    add('xmlns','http://www.w3.org/2000/svg');add('width',b.width);add('height',b.height);add('fill',s.fill||'none');add('stroke',s.stroke||'none');add('stroke-width',s.strokeWidth||'1.6');add('stroke-linecap','round');add('stroke-linejoin','round');return '<svg'+a+'>';
  });
  let textIndex=0;
  svg=svg.replace(/<text\b([^>]*)>([\s\S]*?)<\/text>/g,(full,attrs,body)=>{
    const transform=attr(attrs,'transform'),match=transform.match(/^translate\(\s*([-\d.]+)[, ]+([-\d.]+)\s*\)$/);
    if(transform&&!match){warnings.push(id+': retained complex SVG text transform '+transform);return full;}
    const content=unesc(body.replace(/<[^>]+>/g,'')),sty=attr(attrs,'style'),fontSize=num(sty.match(/font-size:\s*([\d.]+)/)?.[1],12),fontWeight=sty.match(/font-weight:\s*([^;]+)/)?.[1]||'400';
    const tx=match?+match[1]:num(attr(attrs,'x')),ty=match?+match[2]:num(attr(attrs,'y')),anchor=attr(attrs,'text-anchor','start');
    const width=anchor==='end'?Math.max(1,tx):anchor==='middle'?Math.min(b.width,Math.max(tx,b.width-tx)*2):Math.max(1,b.width-tx);
    const x=anchor==='end'?tx-width:anchor==='middle'?tx-width/2:tx,y=ty-fontSize*(attr(attrs,'dominant-baseline')==='central'?.5:.85);
    children.push(textNode(id+'-chart-text-'+(++textIndex),content,x,y,width,fontSize*1.2,{fontSize,fontWeight,lineHeight:fontSize*1.2,color:attr(attrs,'fill',s.color||'#25364B')},{textAlign:anchor==='end'?'right':anchor==='middle'?'center':'left',metadata:{source:'ECharts SVG text'}}));return '';
  });
  children.unshift({type:'svg',id:id+'-vector',name:textIndex?'ECharts 可编辑图表矢量':'图标矢量',x:0,y:0,width:b.width,height:b.height,svg});
  return children;
}
function inputChildren(source,node,warnings){
  const input=source.input;if(!input)return;const s=source.style||{},id=node.id;
  if(input.type==='range'){
    const min=num(input.min),max=num(input.max,100),pct=clamp((num(input.value)-min)/Math.max(1,max-min),0,1),isTimeline=source.domId==='replay-seek',thumb=isTimeline?12:16;
    if(isTimeline){node.children.push({type:'rectangle',id:id+'-track',name:'时间轴剩余',x:0,y:(node.height-4)/2,width:node.width,height:4,cornerRadius:2,fill:'#E0E7F2'});if(pct>0)node.children.push({type:'rectangle',id:id+'-progress',name:'已播放进度',x:0,y:(node.height-4)/2,width:Math.max(.01,node.width*pct),height:4,cornerRadius:2,fill:'#356BFA'});}
    node.children.push({type:'ellipse',id:id+'-thumb',name:'拖动手柄',x:round((node.width-thumb)*pct),y:(node.height-thumb)/2,width:thumb,height:thumb,fill:isTimeline?'#356BFA':'#FFFFFF',stroke:isTimeline?'#FFFFFF':'#356BFA',strokeWidth:2});return;
  }
  let text=String(input.value||source.attributes?.placeholder||'');if(input.type==='datetime-local')text=text.replace('T',' ').replace(/-/g,'/');
  if(!text)return;const fontSize=num(s.fontSize,14),paddingX=num(s.paddingLeft,10)+num(s.borderLeftWidth),available=node.width-paddingX-num(s.paddingRight,10);
  const inputText=textNode(id+'-input-value',text,paddingX,(node.height-fontSize*1.4)/2,available,fontSize*1.4,{...s,lineHeight:fontSize*1.4,color:input.value?s.color:'#697B92'},{metadata:{inputType:input.type,value:input.value,placeholder:source.attributes?.placeholder||'',noWrap:true}});
  delete inputText.textGrowth;node.children.push(inputText);
  if(input.type==='datetime-local')node.children.push({type:'svg',id:id+'-calendar',name:'日期选择',x:node.width-27,y:(node.height-16)/2,width:16,height:16,svg:'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#536478" stroke-width="1.7"><rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/></svg>'});
}
function convert(snapshot,prefix,options={}) {
  if(!snapshot||!Array.isArray(snapshot.nodes))throw new Error('Expected saved ghs-runtime-dom snapshot');
  prefix=String(prefix||snapshot.name||snapshot.page||'runtime').replace(/[^\w-]/g,'-');
  const warnings=[],actions=[],nodes=snapshot.nodes,sourceById=new Map(nodes.map(n=>[n.id,n])),map=new Map();
  const width=options.width??snapshot.viewport?.width??480,height=options.height??snapshot.viewport?.height??1016;
  const root={type:'frame',id:prefix+'-root',name:'UE 当前页面 · '+(snapshot.note||snapshot.name||snapshot.page||''),x:options.x||0,y:options.y||0,width,height,layout:'none',clip:true,children:[],metadata:{source:'UE actual CEF DOM',capture:snapshot.capturedAt,sourceCommit:snapshot.sourceCommit,mapSha256:snapshot.mapSha256,viewport:snapshot.viewport}};
  for(const n of nodes){
    const b=n.bounds||{},s=n.style||{};if(!(b.width>0&&b.height>0)){warnings.push(prefix+': skipped empty DOM box '+n.id);continue;}
    const parent=sourceById.get(n.parentId),pb=parent?.bounds||{x:0,y:0},id=prefix+'-'+n.id;
    const frame={type:'frame',id,name:n.attributes?.['aria-label']||n.domId||n.className||n.tag,x:round(b.x-pb.x),y:round(b.y-pb.y),width:b.width,height:b.height,layout:'none',clip:/^(hidden|auto|scroll)$/.test(s.overflow)||/^(hidden|auto|scroll)$/.test(s.overflowY),children:[],metadata:{domId:n.domId,tag:n.tag,className:n.className,dataset:n.dataset||{},attributes:n.attributes||{}}};
    if(/^(auto|scroll)$/.test(s.overflowY))frame.metadata.scroll={direction:'VERTICAL',contentHeight:Math.max(b.height,...nodes.filter(c=>c.parentId===n.id).map(c=>c.bounds.y+c.bounds.height-b.y)),source:'CSS overflow'};
    boxPaint(frame,s,id,warnings);addPseudo(frame,n,'::before',warnings);
    if(n.svg){frame.children.push(...svgChildren(n,id,warnings));frame.clip=false;}
    else if(n.image){const imagePath=n.image.copiedAsset?path.resolve(__dirname,'runtime',n.image.copiedAsset):decodeURIComponent((n.image.currentSrc||n.image.src).replace(/^file:\/\//,''));frame.fill={type:'image',enabled:true,url:imagePath.replace(/\\/g,'/'),mode:n.image.objectFit==='contain'?'contain':'cover'};}
    else {
      (n.textRuns||[]).forEach((run,i)=>{if(!run.text)return;const r=run.bounds,rects=run.rects||[r],lh=num(s.lineHeight,num(s.fontSize,14)*1.4),rows=new Set(rects.map(v=>round(v.y))).size||1,actualLineHeight=rects[0]?.height||num(s.fontSize,14),multi=rows>1;
        const text=textNode(id+'-text-'+i,run.text,r.x-b.x,r.y-b.y-(lh-actualLineHeight)/2,multi?Math.max(r.width,b.width-num(s.paddingLeft)-num(s.paddingRight)):r.width+1,Math.max(lh*rows,r.height),s,{metadata:{source:'DOM text run',sourceIndex:i,sourceRects:rects,noWrap:!multi}});
        // Figma's measured font advance can differ from Chromium by a pixel. A
        // one-line DOM run must remain WIDTH_AND_HEIGHT rather than wrap within
        // its old measured width (dates and order totals were particularly prone).
        if(!multi)delete text.textGrowth;
        frame.children.push(text);
      });inputChildren(n,frame,warnings);
    }
    map.set(n.id,frame);
    const dataset=n.dataset||{};if(Object.keys(dataset).some(k=>['action','control','replayAction','marker','capacity','replayField'].includes(k))||n.tag==='button'||n.input)actions.push({id,sourceId:n.id,dataset,attributes:n.attributes||{},input:n.input||null,text:((n.textRuns||[]).map(r=>r.text).join(' ')||n.attributes?.['aria-label']||n.attributes?.title||n.domId||''),bounds:{...b}});
  }
  for(const n of nodes){const frame=map.get(n.id);if(!frame)continue;let parent=map.get(n.parentId);if(!parent&&n.parentId){warnings.push(prefix+': missing parent '+n.parentId+' for '+n.id);frame.x=n.bounds.x;frame.y=n.bounds.y;} (parent||root).children.push(frame);}
  // ::after is painted after the element's descendants. Reordering here preserves this.
  for(const n of nodes){const frame=map.get(n.id);if(frame)addPseudo(frame,n,'::after',warnings);}
  // CSS sibling z-index is meaningful for active navigation highlight and modal layers.
  for(const n of nodes){const frame=map.get(n.id);if(!frame)continue;const domChildren=frame.children.filter(c=>c.metadata?.tag),other=frame.children.filter(c=>!c.metadata?.tag);if(domChildren.some(c=>num(sourceById.get(c.id.slice(prefix.length+1))?.style?.zIndex)!==0)){
      const sorted=domChildren.map((c,i)=>({c,i,z:num(sourceById.get(c.id.slice(prefix.length+1))?.style?.zIndex)})).sort((a,b)=>a.z-b.z||a.i-b.i).map(v=>v.c);frame.children=[...other.filter(c=>!c.id.endsWith('-after')),...sorted,...other.filter(c=>c.id.endsWith('-after'))];
    }}
  function content(n){return (n.textRuns||[]).map(r=>r.text).join(' ')+(nodes.filter(c=>c.parentId===n.id).map(content).join(' '));}
  actions.forEach(a=>{if(!a.text)a.text=content(sourceById.get(a.sourceId)).trim();});
  return {root,actions,warnings};
}
function walk(n,fn){fn(n);for(const child of n.children||[])walk(child,fn);}
function verifyDirectory(directory=path.join(__dirname,'runtime/dom')){
  const records=[],errors=[];
  const importer=fs.readFileSync(path.join(__dirname,'figma-import/src/plugin.js'),'utf8');
  const propertyText=importer.match(/const exactProps=new Set\(\[([^\]]+)\]\)/)?.[1];
  const allowed=new Set((propertyText?.match(/'([^']+)'/g)||[]).map(s=>s.slice(1,-1)));
  for(const file of fs.readdirSync(directory).filter(f=>f.endsWith('.json'))){
    const snapshot=JSON.parse(fs.readFileSync(path.join(directory,file),'utf8')),converted=convert(snapshot,file.replace('.json','')),all=[];walk(converted.root,n=>all.push(n));
    const ids=new Set(),duplicates=[];for(const n of all){if(ids.has(n.id))duplicates.push(n.id);ids.add(n.id);if(!Number.isFinite(n.x)||!Number.isFinite(n.y)||!(n.width>0&&n.height>0))errors.push(file+': invalid box '+n.id);for(const key of Object.keys(n))if(allowed.size&&!allowed.has(key))errors.push(file+': unsupported importer property '+n.id+'.'+key);}
    const originalText=snapshot.nodes.flatMap(n=>(n.textRuns||[]).map(r=>r.text)),actualText=all.filter(n=>n.metadata?.source==='DOM text run').map(n=>n.content);
    const sortedText=arr=>arr.slice().sort().join('\u0000');if(sortedText(originalText)!==sortedText(actualText))errors.push(file+': lost or duplicated text');
    if(duplicates.length)errors.push(file+': duplicate IDs '+duplicates);
    for(const n of all.filter(n=>n.fill?.type==='image'))if(!fs.existsSync(n.fill.url))errors.push(file+': missing image '+n.fill.url);
    const svgCount=all.filter(n=>n.type==='svg').length;
    const expectedSvg=snapshot.nodes.filter(n=>n.svg&&n.bounds.width>0&&n.bounds.height>0).length,actualSvg=all.filter(n=>n.metadata?.tag==='svg').length;
    if(expectedSvg!==actualSvg)errors.push(file+': SVG dropped');
    for(const action of converted.actions)if(!ids.has(action.id))errors.push(file+': missing action target '+action.id);
    records.push({file,sourceNodes:snapshot.nodes.length,editableNodes:all.length,texts:all.filter(n=>n.type==='text').length,domTextRuns:originalText.length,textPreserved:sortedText(originalText)===sortedText(actualText),svgs:svgCount,chartsText:all.filter(n=>n.metadata?.source==='ECharts SVG text').length,actions:converted.actions.length,scrollFrames:all.filter(n=>n.metadata?.scroll).length,warnings:converted.warnings});
  }
  const report={scope:'Offline geometry/content validation; Figma visual validation remains required',createdAt:new Date().toISOString(),files:records.length,passed:errors.length===0,errors,records};
  fs.writeFileSync(path.join(__dirname,'dom-to-pen-verification.json'),JSON.stringify(report,null,2));return report;
}
module.exports={convert,color,verifyDirectory};
if(require.main===module){const report=verifyDirectory();console.log(JSON.stringify({passed:report.passed,files:report.files,errors:report.errors,editableNodes:report.records.reduce((a,r)=>a+r.editableNodes,0),texts:report.records.reduce((a,r)=>a+r.texts,0),warnings:report.records.flatMap(r=>r.warnings)},null,2));if(!report.passed)process.exitCode=1;}
