"""CPU-only source/import contract check; never loads Blender or Unreal."""
import json,math,re,traceback
from pathlib import Path
import rebuild_preservation as guard

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'SourceAssets/MPR/rebuild_b50b57'
REPORT=ROOT/'Saved/MPR/rebuild_20261104/cpu_import_preflight.json'
require=guard.require
sha=guard.sha

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def contained(root,name):
    path=(root/name).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(),'Missing/outside source: '+name)
    return path

def finite(value):
    if isinstance(value,bool):return True
    if isinstance(value,(int,float)):return math.isfinite(value)
    if isinstance(value,(list,tuple)):return all(finite(v) for v in value)
    if isinstance(value,dict):return all(isinstance(k,str) and finite(v) for k,v in value.items())
    return False

def valid_lighting(value,key=None):
    if value is None:return key=='color_grading_lut'
    if isinstance(value,dict):
        if set(value)=={'enum'}:
            return value['enum'] in {'AutoExposureMethod.AEM_HISTOGRAM',
                'DynamicGlobalIlluminationMethod.LUMEN','ReflectionMethod.LUMEN'}
        return all(isinstance(k,str)and valid_lighting(v,k)for k,v in value.items())
    return finite(value)

def run():
    manifest_path=SRC/'manifest.json';manifest_hash=sha(manifest_path)
    manifest=read(manifest_path);plan=read(SRC/'protection_plan.json')
    require(manifest.get('rebuild_namespace')==guard.DEST and manifest.get('map')==guard.MAP,'Incorrect new map/namespace')
    for field in ('namespace','extension_namespace'):
        require(field not in manifest or manifest[field]==guard.DEST,'Conflicting namespace field: '+field)
    require(not manifest.get('allowed_replacements'),'Independent map cannot replace original-map assets')
    guard.retained_material_spec_map(manifest.get('retained_material_overrides',[]),manifest['materials'])
    solar_rows,solar_files=guard.solar_source_contract(ROOT,manifest)
    require(plan['source_map']==guard.SOURCE_MAP and plan['new_map']==guard.MAP and plan['namespace']==guard.DEST,
            'Retention plan targets a different map')
    source_map=ROOT/'Content/Maps/MPR_CAD_Warehouse.umap'
    require(sha(source_map)==plan['source_map_sha256'],'Original map changed after retention review')
    mesh_specs=guard.retained_mesh_spec_map(manifest.get('retained_mesh_overrides',[]))
    for guid in mesh_specs:
        matches=[r for r in plan['actors'] if r['guid']==guid]
        require(len(matches)==1 and matches[0]['name']==guard.SOLAR_IDENTITIES[guid][0] and
                matches[0]['action']=='keep_main_shell','Solar exception is not a retained reviewed shell actor')
    rows=manifest['meshes'];names=[r['name'] for r in rows]
    require(rows and len(set(n.lower() for n in names))==len(names),'Empty/duplicate mesh names')
    for row in rows:
        require(re.fullmatch(r'SM_[A-Za-z0-9_-]+',row['name']) is not None,'Invalid mesh name')
        require(re.fullmatch(r'[A-Za-z0-9_]+',row['category']) is not None,'Invalid mesh category')
        fbx=contained(ROOT,row['fbx'])
        require(fbx.is_relative_to(SRC.resolve()) and fbx.suffix.lower()=='.fbx','FBX outside rebuild source')
        require(sha(fbx)==row['sha256'],'FBX hash mismatch: '+row['name'])
        require(row['material_roles'] and set(row['material_roles'])<=set(manifest['materials']),
                'Missing material role: '+row['name'])
    inputs=manifest['input_hashes'];require(bool(inputs),'Missing source input hashes')
    for name,expected in inputs.items():
        require(sha(contained(SRC/'inputs',name))==expected,'Input hash mismatch: '+name)
    require(inputs.get('topoexport-B50B57.blend')==manifest['source_sha256'],'Original Blender input identity mismatch')
    reused={}
    for name,asset in manifest.get('reused_meshes',{}).items():
        require(asset.startswith('/Game/') and '..' not in Path(asset).parts,'Invalid reused asset path')
        package=asset.split('.')[0]
        path=contained(ROOT/'Content',package.removeprefix('/Game/')+'.uasset')
        reused[name]=dict(asset=asset,sha256=sha(path))
    for name,instances in manifest.get('instances',{}).items():
        require(name in names or name in reused,'Unknown instance mesh: '+name)
        for row in instances:
            require(len(row['position_m'])==3 and len(row.get('scale',[1,1,1]))==3 and
                finite([row['position_m'],row.get('scale',[1,1,1]),row.get('rotation_deg',0),row.get('pitch_deg',0)]),
                'Nonfinite/invalid instance transform: '+name)
            if 'tile' in row:require(len(row['tile'])==2 and finite(row['tile']),'Invalid instance tile')
    for name,roles in manifest.get('instance_material_roles',{}).items():
        require(name in manifest['instances'] and roles and set(roles)<=set(manifest['materials']),
                'Missing instance material role: '+name)
    lighting=manifest.get('lighting_overrides',[])
    profile=manifest.get('render_profile',{})
    require(set(profile)=={'lumen_clipmap_extent'} and finite(profile['lumen_clipmap_extent']) and
            2500<=profile['lumen_clipmap_extent']<=8000,'Invalid scene render profile')
    require(isinstance(lighting,list),'Lighting overrides must be a list')
    keys=set()
    for item in lighting:
        require(item['actor_label'] in guard.LIGHT_LABELS and valid_lighting(item['value'],item['property']),'Invalid/nonfinite lighting override')
        key=(item['actor_label'],item.get('component_name'),item['property'])
        require(key not in keys,'Duplicate lighting override');keys.add(key)
    require(sha(manifest_path)==manifest_hash,'Manifest changed during preflight; wait for the build to finish')
    return dict(success=True,map=guard.MAP,namespace=guard.DEST,manifest_sha256=manifest_hash,
        meshes=len(rows),triangles=sum(r['triangles'] for r in rows),fbx_hashes_verified=len(rows)+len(solar_rows)*3,
        solar_meshes=len(solar_rows),solar_source_files=solar_files,retained_mesh_overrides=manifest.get('retained_mesh_overrides',[]),
        input_hashes_verified=inputs,reused_assets_verified=reused,protection_plan_sha256=sha(SRC/'protection_plan.json'),
        source_map=guard.SOURCE_MAP,source_map_sha256=plan['source_map_sha256'],
        source_actor_count=len(plan['actors']),plan_counts=plan['counts'],
        instances={k:len(v) for k,v in manifest.get('instances',{}).items()},
        pitched_instances=sum(bool(r.get('pitch_deg')) for rows in manifest.get('instances',{}).values() for r in rows),
        lighting_overrides=lighting,scope='CPU source/hash preflight only; native import/reload validated separately')

def main():
    try:result=run()
    except Exception:result=dict(success=False,error=traceback.format_exc())
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    temp=REPORT.with_suffix('.json.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(REPORT)
    print(json.dumps({k:result[k] for k in ['success','manifest_sha256','meshes','triangles','error'] if k in result},ensure_ascii=False))
    return 0 if result['success'] else 1

if __name__=='__main__':raise SystemExit(main())
