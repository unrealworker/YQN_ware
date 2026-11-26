// CI/build prerequisite. JSON strings do not create Unreal cook dependencies.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'../..');
const catalog=JSON.parse(fs.readFileSync(path.join(root,'Content/GHSTwinUI/data/warehouses.json'),'utf8'));
const ini=fs.readFileSync(path.join(root,'Config/DefaultGame.ini'),'utf8');
const maps=new Set(['/Game/Maps/GHS_WarehousePortal','/Game/Maps/GHS_GlobalWarehouse',...catalog.warehouses.map(w=>w.map)]);
const failures=[];
for(const map of maps){
 if(!/^\/Game\/Maps\/[A-Za-z0-9_/]+$/.test(map)){failures.push('Invalid map path: '+map);continue;}
 if(!fs.existsSync(path.join(root,'Content',map.slice(6)+'.umap')))failures.push('Missing map asset: '+map);
 if(!ini.includes('+MapsToCook=(FilePath="'+map+'")'))failures.push('Missing MapsToCook: '+map);
}
if(catalog.schemaVersion!==2)failures.push('Expected catalog schemaVersion 2');
if(catalog.coordinateSystem!=='WGS84')failures.push('Expected WGS84 coordinates');
if(catalog.warehouses.length>2000)failures.push('Catalog exceeds supported 2000 warehouse budget');
const ids=new Set();for(const w of catalog.warehouses){if(ids.has(w.id))failures.push('Duplicate id: '+w.id);ids.add(w.id);
 if(typeof w.id!=='string'||!w.id.length||w.id.length>80||typeof w.name!=='string'||!w.name.length)failures.push('Invalid warehouse identity: '+w.id);
 if(typeof w.id==='string'&&/^cluster[-:]/.test(w.id))failures.push('Reserved warehouse id prefix (case-sensitive cluster- or cluster:): '+w.id);
 if(!Number.isFinite(w.latitude)||Math.abs(w.latitude)>90||!Number.isFinite(w.longitude)||Math.abs(w.longitude)>180)failures.push('Invalid coordinates: '+w.id);
 if(!['ghs','generic'].includes(w.runtimeProfile))failures.push('Unknown profile: '+w.id);
 if(!Array.isArray(w.features)||new Set(w.features).size!==w.features.length||w.features.some(f=>!(w.runtimeProfile==='generic'?['roof-inspection']:['warehouse-ui','traffic']).includes(f)))failures.push('Invalid features: '+w.id);
 if(w.runtimeProfile==='ghs'&&!w.features?.includes('warehouse-ui'))failures.push('GHS requires warehouse-ui: '+w.id);
 if(w.runtimeProfile==='generic'&&(!w.entryCamera))failures.push('Generic requires entryCamera: '+w.id);
 if(w.entryCamera){const c=w.entryCamera;if(!['x','y','z','distance','pitch','yaw'].every(k=>Number.isFinite(c[k]))||['x','y','z'].some(k=>Math.abs(c[k])>1e8)||c.distance<900||c.distance>95000||c.pitch< -80||c.pitch> -15)failures.push('Invalid entryCamera: '+w.id);}
 if(w.thumbnail&&(!w.thumbnail.startsWith('assets/')||w.thumbnail.includes('..')||!fs.existsSync(path.join(root,'Content/GHSTwinUI/web',w.thumbnail))))failures.push('Missing/invalid thumbnail: '+w.id);
}
if(failures.length){console.error(failures.join('\n'));process.exitCode=1;}else console.log(JSON.stringify({success:true,warehouses:ids.size,cookedMaps:[...maps],note:'Source and cook configuration validation, not a completed packaged build'}));
