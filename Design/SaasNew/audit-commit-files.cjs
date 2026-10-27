'use strict';
// Read-only dependency audit. Writes only manifests; never stages or commits.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),cp=require('child_process');
const root=__dirname,repo=path.resolve(root,'../..'),slash=s=>s.replace(/\\/g,'/');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const payload=JSON.parse(fs.readFileSync(path.join(root,'figma-import/payload.json')));
const sourceHash=hash(fs.readFileSync(path.join(root,'migration.pen.json')));
if(sourceHash!==payload.sourceHash)throw new Error('Build payload and migration source differ; rebuild after the active import finishes.');
const files=new Map();
function add(relative,reason){const full=path.join(repo,relative);if(!fs.existsSync(full))throw new Error('Missing commit dependency '+relative);files.set(slash(relative),reason);}
function addDir(relative,filter,reason){for(const d of fs.readdirSync(path.join(repo,relative),{withFileTypes:true})){const child=slash(path.join(relative,d.name));if(d.isDirectory())addDir(child,filter,reason);else if(filter(d.name))add(child,reason);}}
const base='Design/SaasNew/';
for(const f of fs.readdirSync(root).filter(f=>f.endsWith('.cjs')))add(base+f,'migration/build/audit source');
for(const f of ['HANDOFF.md','DEPENDENCIES.md','DESIGN_INVENTORY.md','inventory.json','migration.pen.json','runtime-overrides.json','migration-report.json','dom-to-pen-verification.json','asset-portability-audit.json'])add(base+f,'source snapshot or handoff');
for(const f of ['build.cjs','verify.cjs','verify-visual.cjs','README.md','manifest.json','prototype-links.json','resume-allowlist.json','revision-allowlist.json','build-report.json','verification.json','visual-verification.json'])add(base+'figma-import/'+f,'offline converter, ownership safety or checks');
addDir(base+'figma-import/src',()=>true,'plugin source');addDir(base+'figma-import/vendor',()=>true,'offline icon source and license');
for(const dir of ['dom','poi','search','context'])addDir(base+'runtime/'+dir,f=>f.endsWith('.json'),'actual UE editable capture');
addDir(base+'runtime/assets',()=>true,'raw DOM image inputs for repeatable conversion validation');
for(const f of ['README.md','manifest.json','board-state-mapping.json','scene-crop-manifest.json','validation.json','detail-alignment-validation.json'])add(base+'runtime/'+f,'capture provenance and validation');
for(const f of ['check-text-geometry.cjs','render-migration.cjs','REVIEW.md','text-geometry-verification.json'])add(base+'qa/'+f,'repeatable design QA');
for(const f of ['figma-render/SaasNew-acceptance.json','final/SaasNew-acceptance.json','final/visual-manifest.json','figma-error-02.json'])add(base+'acceptance/'+f,'actual Figma ownership or acceptance evidence');
for(const f of fs.readdirSync(path.join(root,'acceptance')).filter(f=>f.endsWith('.md')))add(base+'acceptance/'+f,'actual visual QA notes');
const assets=Object.values(payload.images).map(a=>{const p=slash(path.join('Design',a.source)),bytes=fs.readFileSync(path.join(repo,p));if(hash(bytes)!==a.sha256)throw new Error('Asset changed after build '+p);add(p,'required image input');return{path:p,sha256:a.sha256,width:a.width,height:a.height,bytes:bytes.length};});
// prepare-migration uses presence of this original to choose racks-detail rather than its fallback.
add(base+'runtime/scene/racks-detail.png','prepare-migration conditional source selection');
const upstream=['Design/GHS_Twin_SaaS_Concept/Saas.pen','Design/GHS_Twin_SaaS_Concept/current-design.json','Design/GHS_Twin_SaaS_Concept/order-replay-navigation.json','Design/GHS_SaaS_Interactive_20261026/src/pages.json'];
for(const p of upstream)add(p,'existing tracked upstream input');
const all=[...files.keys()].sort();const trackedResult=cp.spawnSync('git',['ls-files','--',...all],{cwd:repo,encoding:'utf8',maxBuffer:1024*1024});if(trackedResult.status!==0)throw new Error(trackedResult.stderr);
const tracked=new Set(trackedResult.stdout.split(/\r?\n/).filter(Boolean));
const dependencies=all.map(p=>({path:p,reason:files.get(p),tracked:tracked.has(p),bytes:fs.statSync(path.join(repo,p)).size}));
const newFiles=dependencies.filter(d=>!d.tracked).map(d=>d.path);
const outputs=['Design/SaasNew/DEPENDENCY_ASSETS.json','Design/SaasNew/COMMIT_MANIFEST.json','Design/SaasNew/COMMIT_FILES.txt'];
const commitFiles=[...new Set(newFiles.concat(outputs))].sort();
const result={schemaVersion:1,sourceHash,scope:'SaasNew design migration only; no production code, model/map edits, Git mutation or performance results',commitFiles,dependencies,existingUpstream:dependencies.filter(d=>d.tracked),requiredImageCount:assets.length,requiredImageBytes:assets.reduce((s,a)=>s+a.bytes,0),commitInputBytes:dependencies.filter(d=>!d.tracked).reduce((s,a)=>s+a.bytes,0),excluded:['figma-import/payload.json','figma-import/ui.html','figma-import/code.js','acceptance/**/boards/*.png','acceptance/*.png','acceptance/*.zip','runtime/screens/','runtime/sidebar/','qa/board-*.html','qa/board-*.png','qa/browser-*.mjs','node_modules/','WareProductData/'],gitMutated:false};
fs.writeFileSync(path.join(root,'DEPENDENCY_ASSETS.json'),JSON.stringify({sourceHash,requiredImages:assets,offlineIcons:'Design/SaasNew/figma-import/vendor/lucide-icons.json',imageBytes:result.requiredImageBytes},null,2));
fs.writeFileSync(path.join(root,'COMMIT_MANIFEST.json'),JSON.stringify(result,null,2));
fs.writeFileSync(path.join(root,'COMMIT_FILES.txt'),commitFiles.join('\n')+'\n');
console.log(JSON.stringify({sourceHash,commitFiles:commitFiles.length,existingUpstream:result.existingUpstream.length,requiredImages:assets.length,imageMiB:(result.requiredImageBytes/1048576).toFixed(2),commitMiB:(result.commitInputBytes/1048576).toFixed(2),gitMutated:false},null,2));
