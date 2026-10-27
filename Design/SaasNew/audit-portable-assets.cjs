'use strict';
// Audit only by default. --stage creates a NEW self-contained asset/source copy;
// it never rewrites migration.pen.json, payload.json, ui.html or the original .pen.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const root=__dirname,repo=path.resolve(root,'../..');
const source=path.join(root,'migration.pen.json');
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const slash=s=>s.replace(/\\/g,'/');
const sourceBytes=fs.readFileSync(source),sourceHash=sha(sourceBytes),pen=JSON.parse(sourceBytes);
const overridesPath=path.join(root,'runtime-overrides.json');
const overrides=fs.existsSync(overridesPath)?JSON.parse(fs.readFileSync(overridesPath,'utf8')):{};
const legacy=path.join(repo,'Design/GHS_Twin_SaaS_Concept');
function resolveImage(url){
  const replacement=overrides.imageReplacements?.[url]||url;
  const candidates=[replacement,path.resolve(root,replacement),path.resolve(legacy,replacement),path.resolve(repo,replacement)];
  const file=candidates.find(candidate=>fs.existsSync(candidate)&&fs.statSync(candidate).isFile());
  if(!file)throw new Error('Missing migration image: '+url);
  return path.resolve(file);
}
const refs=[];
function scan(value,scope,location){
  if(!value||typeof value!=='object')return;
  if(value.fill?.type==='image')refs.push({scope,location,id:value.id||null,url:value.fill.url});
  for(const [key,child] of Object.entries(value)){
    if(child&&typeof child==='object'){
      if(Array.isArray(child))child.forEach((item,i)=>scan(item,scope,location+'.'+key+'['+i+']'));
      else scan(child,scope,location+'.'+key);
    }
  }
}
for(const [i,b] of pen.children.entries())scan(b,'board '+b.name,'children['+i+']');
for(const [i,b] of (pen.componentDefinitions||[]).entries())scan(b,'legacy component '+b.id,'componentDefinitions['+i+']');
for(const [i,b] of (pen.runtimeComponentDefinitions||[]).entries())scan(b,'current component '+b.id,'runtimeComponentDefinitions['+i+']');
const imageMap=new Map();
for(const ref of refs){
  if(!imageMap.has(ref.url)){
    const file=resolveImage(ref.url),bytes=fs.readFileSync(file),hash=sha(bytes);
    const base=path.basename(file,path.extname(file)).replace(/[^a-zA-Z0-9_-]/g,'-');
    const relative=path.relative(root,file),inside=relative!==''&&!relative.startsWith('..'+path.sep)&&!path.isAbsolute(relative);
    imageMap.set(ref.url,{url:ref.url,source:slash(path.relative(repo,file)),resolvedFile:file,bytes:bytes.length,sha256:hash,
      portableUrl:'assets/'+base+'-'+hash.slice(0,12)+path.extname(file).toLowerCase(),insideSaasNew:inside,absoluteReference:path.isAbsolute(ref.url),uses:[]});
  }
  imageMap.get(ref.url).uses.push(ref);
}
const images=[...imageMap.values()];
const report={schema:'saasnew-portable-assets-v1',source:'migration.pen.json',sourceHash,
  scope:'All boards, all 47 legacy component definitions, current component definitions, and nested fill overrides',
  sourceBoards:pen.children.length,legacyComponents:(pen.componentDefinitions||[]).length,
  uniqueImages:images.length,totalImageBytes:images.reduce((s,a)=>s+a.bytes,0),imageReferences:refs.length,
  absoluteReferences:images.filter(a=>a.absoluteReference).length,externalLegacyImages:images.filter(a=>!a.insideSaasNew).length,
  originalPen:'Design/GHS_Twin_SaaS_Concept/Saas.pen',originalPreserved:true,
  additionalBuildDependency:'Design/SaasNew/figma-import/vendor/lucide-icons.json (offline first); prototype node_modules only for new icons absent from this snapshot',
  generatedFilesToExclude:['figma-import/payload.json','figma-import/ui.html','figma-import/code.js'],
  images};
fs.writeFileSync(path.join(root,'asset-portability-audit.json'),JSON.stringify(report,null,2));
if(process.argv.includes('--stage')){
  const payloadPath=path.join(root,'figma-import/payload.json');
  const payload=JSON.parse(fs.readFileSync(payloadPath,'utf8'));
  if(payload.sourceHash!==sourceHash)throw new Error('Current payload was built from a different migration. Rebuild after the ongoing import before staging icons.');
  const output=path.join(root,'portable-'+sourceHash.slice(0,12));
  fs.mkdirSync(path.join(output,'assets'),{recursive:true});
  function saveNew(file,bytes){
    if(fs.existsSync(file)){if(sha(fs.readFileSync(file))!==sha(bytes))throw new Error('Refusing to replace different archived content: '+file);return;}
    fs.writeFileSync(file,bytes,{flag:'wx'});
  }
  for(const asset of images){
    const bytes=fs.readFileSync(asset.resolvedFile);if(sha(bytes)!==asset.sha256)throw new Error('Asset changed since audit: '+asset.url);
    saveNew(path.join(output,asset.portableUrl),bytes);
  }
  function rewrite(value){
    if(!value||typeof value!=='object')return;
    if(value.fill?.type==='image')value.fill.url=imageMap.get(value.fill.url).portableUrl;
    for(const child of Object.values(value))if(child&&typeof child==='object')Array.isArray(child)?child.forEach(rewrite):rewrite(child);
  }
  rewrite(pen);
  saveNew(path.join(output,'migration.pen.json'),Buffer.from(JSON.stringify(pen,null,2)));
  // Preserve the already-built vector paths separately, without retaining a
  // 70 MB base64 payload or requiring the old prototype's node_modules later.
  saveNew(path.join(output,'icons.json'),Buffer.from(JSON.stringify(payload.icons,null,2)));
  saveNew(path.join(output,'asset-manifest.json'),Buffer.from(JSON.stringify({...report,icons:Object.keys(payload.icons).length,images:images.map(({resolvedFile,...a})=>a)},null,2)));
  if(sha(fs.readFileSync(source))!==sourceHash)throw new Error('Migration changed concurrently; archive is a source snapshot, not the current file.');
  console.log(JSON.stringify({staged:slash(path.relative(repo,output)),uniqueImages:images.length,imageBytes:report.totalImageBytes,icons:Object.keys(payload.icons).length,
    currentMigrationUnchanged:true,note:'To rebuild from this archive, point build.cjs to its migration.pen.json and prefer its icons.json. Current builder/payload were not changed.'},null,2));
}else{
  console.log(JSON.stringify({auditOnly:true,uniqueImages:report.uniqueImages,totalImageBytes:report.totalImageBytes,absoluteReferences:report.absoluteReferences,
    externalLegacyImages:report.externalLegacyImages,legacyComponents:report.legacyComponents,report:'Design/SaasNew/asset-portability-audit.json',
    stageCommand:'node Design/SaasNew/audit-portable-assets.cjs --stage',note:'Wait until the active Figma import finishes before staging/rebuilding source packages.'},null,2));
}
