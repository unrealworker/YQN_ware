'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const repo = path.resolve(__dirname, '../..');
const args = process.argv.slice(2);
function argument(name, fallback) { const i=args.indexOf(name); if(i<0)return fallback; if(!args[i+1])throw Error('Missing '+name); return path.resolve(args[i+1]); }
const output = argument('--output', path.join(repo, 'Package_PublicStreaming_20261028'));
const launcher = argument('--launcher', path.join(repo, 'Saved/PixelStreaming/PublicLauncherReview'));
const runtime = argument('--runtime', path.join(repo, 'Deployment/GHSPixelStreaming/runtime'));
if(output===repo || !output.startsWith(repo+path.sep)) throw Error('交付输出必须为项目工作目录内的独立子目录');
const required = [
 'App/Windows/TestGame.exe', 'App/Windows/Test/Binaries/Win64/TestGame-Win64-Shipping.exe',
 'App/Windows/Engine/Binaries/Win64/EpicWebHelper.exe',
 'App/Windows/Engine/Extras/Redist/en-us/UEPrereqSetup_x64.exe',
 'App/Windows/Test/Content/GHSTwinUI/web/index.html',
 'App/Windows/Test/Content/GHSTwinUI/data/order-replay.json',
 'App/Windows/Test/Content/GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf'
];
for(const file of required) if(!fs.statSync(path.join(output,file),{throwIfNoEntry:false})?.isFile()) throw Error('缺少最新 Shipping 文件：'+file);
execFileSync(process.execPath,[path.join(__dirname,'build.js'),'--output',output],{stdio:'inherit'});
fs.cpSync(runtime,path.join(output,'runtime'),{recursive:true});
fs.copyFileSync(path.join(launcher,'像素流服务启动器.exe'),path.join(output,'像素流服务启动器.exe'));
for(const entry of fs.readdirSync(path.join(__dirname,'deployment'))){
 const source=path.join(__dirname,'deployment',entry);
 if(!fs.statSync(source).isFile())continue;
 if(entry.endsWith('.ps1'))fs.writeFileSync(path.join(output,entry),'\ufeff'+fs.readFileSync(source,'utf8').replace(/^\ufeff/,''),'utf8');
 else fs.copyFileSync(source,path.join(output,entry));
}
const configuration={executablePath:'App/Windows/Test/Binaries/Win64/TestGame-Win64-Shipping.exe',httpPort:8080,streamerPort:8888,showWindow:false,width:1920,height:1080,mode:'independent',fps:30,minBitrateMbps:5,startBitrateMbps:12,maxBitrateMbps:24,qualityProfile:'custom',adaptiveResourceBudget:false,maxViewers:10,networkMode:'lan',publicUrl:'',accessCode:'',tlsCertPath:'',tlsKeyPath:'',trustProxy:false,stunUrl:'',turnUrl:'',turnUsername:'',turnPassword:''};
const cfgPath=path.join(output,'launcher.config.json');
if(!fs.existsSync(cfgPath))fs.writeFileSync(cfgPath,JSON.stringify(configuration,null,2)+'\n');
function sha(file){return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');}
// Prove non-UFS UI/data equal current saved source, not merely present in an older package.
function files(dir,prefix=''){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(dir,e.name),prefix+e.name+'/'):[prefix+e.name]);}
const assets=[];
for(const category of ['web','data'])for(const relative of files(path.join(repo,'Content/GHSTwinUI',category))){
 const source=path.join(repo,'Content/GHSTwinUI',category,relative), target=path.join(output,'App/Windows/Test/Content/GHSTwinUI',category,relative);
 if(!fs.existsSync(target)||sha(source)!==sha(target))throw Error('运行时资源不是最新版本：'+category+'/'+relative);
 assets.push({path:category+'/'+relative,sha256:sha(source)});
}
const manifest={version:1,createdAt:new Date().toISOString(),sourceCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim(),mapSha256:sha(path.join(repo,'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap')),defaultMaxViewers:10,runtimeAssets:assets,files:[]};
for(const relative of files(output)){
 if(relative==='delivery-manifest.json'||relative==='launcher.config.json'||/^(logs|sessions|certificates)\//.test(relative)||relative.includes('/Saved/'))continue;
 const file=path.join(output,relative);
 manifest.files.push({path:relative,bytes:fs.statSync(file).size,sha256:sha(file)});
}
fs.writeFileSync(path.join(output,'delivery-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(JSON.stringify({output,fileCount:manifest.files.length,bytes:manifest.files.reduce((n,f)=>n+f.bytes,0),runtimeAssetsVerified:assets.length,mapSha256:manifest.mapSha256},null,2));
