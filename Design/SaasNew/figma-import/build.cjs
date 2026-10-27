const fs=require('fs'),path=require('path'),crypto=require('crypto'),vm=require('vm');
const Model=require('./src/model.cjs');
const here=__dirname,design=path.resolve(here,'..');
// Prefer the migration prepared from the latest actual UE UI.
const designRoot=path.resolve(here,'../..');
const penSource=fs.existsSync(path.join(design,'migration.pen.json'))?path.join(design,'migration.pen.json'):path.join(designRoot,'GHS_Twin_SaaS_Concept/Saas.pen');
const pen=JSON.parse(fs.readFileSync(penSource,'utf8'));delete pen.fileToken;
const inventory=JSON.parse(fs.readFileSync(path.join(design,'inventory.json'),'utf8'));
const overridesPath=path.join(design,'runtime-overrides.json');
const overrides=fs.existsSync(overridesPath)?JSON.parse(fs.readFileSync(overridesPath,'utf8')):{};
const linksPath=path.join(here,'prototype-links.json');
let links=fs.existsSync(linksPath)?JSON.parse(fs.readFileSync(linksPath,'utf8')):[];
if(overrides.links)links=overrides.links;
if(overrides.nodeIdMap)links=links.map(link=>({...link,sourceNodeId:overrides.nodeIdMap[link.sourceBoard+':'+link.sourceNodeId]||link.sourceNodeId}));
const corrections=[];
const roofTextCorrections={
 gG7Ey:'POI 或屋顶 → 立即开始 0.8 秒溶解',
 JrDCr:'0.8 秒后屋顶消失，按图层偏好解锁标签与拾取；设备定位使用 0.5 秒快速展开',
 eE7Cl:'手动浅蓝溶解 · 0.8 秒；设备定位 · 0.5 秒',
 r4NMPS:'手动展开 · 0.8 秒浅蓝溶解 · 设备定位 0.5 秒 · 完成后解锁标签与拾取',
 dscNS:'0.40 s',lV77Z:'0.80 s',
 yTtj7:'关闭外壳先展开屋顶，再隐藏外墙。手动展开 0.8 秒，设备定位 0.5 秒。闭顶和开顶期间均锁定内部标签与拾取；拖动库容不自动开顶。'
};
pen.children.forEach(board=>Model.walk(board,n=>{if(roofTextCorrections[n.id]){corrections.push({id:n.id,from:n.content,to:roofTextCorrections[n.id]});n.content=roofTextCorrections[n.id];}if(n.id==='q2RKW8')n.name=n.name.replace('0.5 秒','0.8 秒');}));
const ix=Model.index(pen),images={},icons={},warnings=[];
function dimensions(bytes){
 if(bytes.subarray(1,4).toString()==='PNG')return{width:bytes.readUInt32BE(16),height:bytes.readUInt32BE(20),mime:'image/png'};
 if(bytes[0]===255&&bytes[1]===216){let p=2;while(p<bytes.length){if(bytes[p]!==255){p++;continue;}const marker=bytes[p+1];p+=2;if(marker===216||marker===217)continue;const len=bytes.readUInt16BE(p);if([192,193,194,195,197,198,199,201,202,203,205,206,207].includes(marker))return{height:bytes.readUInt16BE(p+3),width:bytes.readUInt16BE(p+5),mime:'image/jpeg'};p+=len;}}
 throw new Error('Unsupported image encoding; use PNG/JPEG');
}
function resolveImage(url){
 const replacement=(overrides.imageReplacements||{})[url]||url;
 const candidates=[replacement,path.resolve(path.dirname(penSource),replacement),path.resolve(designRoot,'GHS_Twin_SaaS_Concept',replacement),path.resolve(design,replacement),path.resolve(designRoot,'..',replacement)];
 const found=candidates.find(p=>fs.existsSync(p)&&fs.statSync(p).isFile());if(!found)throw new Error('Missing image: '+url);return found;
}
const escape=s=>String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
const iconSnapshotPath=path.join(here,'vendor/lucide-icons.json');
const iconSnapshot=fs.existsSync(iconSnapshotPath)?JSON.parse(fs.readFileSync(iconSnapshotPath,'utf8')).icons:{};
function iconSvg(name){
 if(iconSnapshot[name])return iconSnapshot[name];
 const dir=path.join(designRoot,'GHS_SaaS_Interactive_20261026/node_modules/lucide-react/dist/esm/icons');
 const fn=path.join(dir,name+'.js');if(!fs.existsSync(fn))throw new Error('Missing Lucide icon: '+name);
 let src=fs.readFileSync(fn,'utf8').replace(/^import .*;?\r?\n/gm,'').replace(/^export .*;?\r?\n/gm,'');
 let shape;vm.runInNewContext(src,{createLucideIcon:(_name,nodes)=>{shape=nodes;return nodes;}});
 if(!shape)throw new Error('Unsupported Lucide icon module: '+name);
 return shape.map(([tag,attrs])=>'<'+tag+' '+Object.entries(attrs).filter(([k])=>k!=='key').map(([k,v])=>k+'="'+escape(v)+'"').join(' ')+'/>').join('');
}
const assetNodes=[];pen.children.concat(Object.values(ix.components),ix.runtimeComponents).forEach(board=>Model.walk(Model.expand(board,ix.components),node=>assetNodes.push(node)));
for(const node of assetNodes){
 if(node.fill&&node.fill.type==='image'){
  const url=node.fill.url;if(!images[url]){const file=resolveImage(url),bytes=fs.readFileSync(file),dim=dimensions(bytes);if(Math.max(dim.width,dim.height)>4096)throw new Error('Image exceeds 4096; resize explicitly first: '+file);images[url]={...dim,base64:bytes.toString('base64'),sha256:crypto.createHash('sha256').update(bytes).digest('hex'),source:path.relative(designRoot,file).replace(/\\/g,'/')};}
 }
 if(node.type==='icon'&&!icons[node.icon])icons[node.icon]=iconSvg(node.icon);
 for(const override of Object.values(node.descendants||{}))if(override.icon&&!icons[override.icon])icons[override.icon]=iconSvg(override.icon);
}
// The expanded traversal includes image/icon overrides inside references.
const expected=Model.audit(pen);
if(expected.boards!==54||expected.components!==47)throw new Error('Expected all 54 artboards / 47 components, got '+expected.boards+'/'+expected.components);
const resumePath=path.join(here,'resume-allowlist.json');
const resumeFrom=fs.existsSync(resumePath)?JSON.parse(fs.readFileSync(resumePath,'utf8')):null;
const revisionPath=path.join(here,'revision-allowlist.json');
const revisionFrom=fs.existsSync(revisionPath)?JSON.parse(fs.readFileSync(revisionPath,'utf8')):null;
const payload={schemaVersion:1,name:'SaasNew',builtAt:new Date().toISOString(),source:path.relative(designRoot,penSource).replace(/\\/g,'/'),sourceHash:crypto.createHash('sha256').update(fs.readFileSync(penSource)).digest('hex'),pen,inventory,overrides,images,icons,links,expected,warnings,corrections,resumeFrom,revisionFrom};
fs.writeFileSync(path.join(here,'payload.json'),JSON.stringify(payload));
const model=fs.readFileSync(path.join(here,'src/model.cjs'),'utf8').replace(/if \(typeof module[^\n]+/,'');
fs.writeFileSync(path.join(here,'code.js'),model+'\n'+fs.readFileSync(path.join(here,'src/plugin.js'),'utf8'));
const html=fs.readFileSync(path.join(here,'src/ui.template.html'),'utf8');
fs.writeFileSync(path.join(here,'ui.html'),html.replace('/*__ZIP__*/',fs.readFileSync(path.join(here,'src/store-zip.js'),'utf8')).replace('/*__PAYLOAD__*/',JSON.stringify(payload).replace(/</g,'\\u003c')));
const idIndex=process.argv.indexOf('--plugin-id');const manifest={name:'SaasNew · 完整设计迁移',api:'1.0.0',editorType:['figma'],main:'code.js',ui:'ui.html',documentAccess:'dynamic-page',networkAccess:{allowedDomains:['none']}};
if(idIndex>=0){const id=process.argv[idIndex+1];if(!/^\d+$/.test(id||''))throw new Error('--plugin-id must be an actual numeric ID assigned by Figma');manifest.id=id;}
else if(fs.existsSync(path.join(here,'manifest.json'))){const existing=JSON.parse(fs.readFileSync(path.join(here,'manifest.json')));if(existing.id)manifest.id=existing.id;}
fs.writeFileSync(path.join(here,'manifest.json'),JSON.stringify(manifest,null,2));
const summary={...expected,uniqueImages:Object.keys(images).length,uniqueIcons:Object.keys(icons).length,links:links.length,payloadBytes:fs.statSync(path.join(here,'payload.json')).size,source:payload.source,sourceHash:payload.sourceHash,pluginId:manifest.id?'Figma-assigned ID preserved':'omitted for local development import; use a Figma-assigned ID only if requested',warnings};delete summary.textByBoard;
fs.writeFileSync(path.join(here,'build-report.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify(summary,null,2));
