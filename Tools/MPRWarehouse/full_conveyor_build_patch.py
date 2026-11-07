"""Build only audited supply belts and floor markers; never save an Unreal map."""
from pathlib import Path
import sys,json,gzip,math,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent))
from mpr_blender_common import Geometry
from full_conveyor_geometry import add_meshes,MARKER_MESH
OUT=ROOT/'SourceAssets/MPR/conveyor_audit_20261107'
def read(p):return json.loads(p.read_text(encoding='utf8'))
evidence=read(OUT/'cad_source_evidence.json');g=Geometry();specs=add_meshes(g,evidence)
manifest=g.export(OUT,'MPR_CADConveyorAudit',{'owner':'mpr-conveyor-audit-20261107','source_sha256':evidence['source_sha256'],'scope':'3 CAD supply belts + 108 crossed ground markers only'})
ops=read(ROOT/'SourceAssets/MPR/operations/instances.json')['instances']
snapshot_path=ROOT/'SourceAssets/MPR/sorter_simulation/validation/scene_after.json.gz'
snapshot=json.loads(gzip.decompress(snapshot_path.read_bytes()));world=[]
for a in snapshot['actors']:
    for c in a['components']:
        for i,t in enumerate(c.get('instance_transforms',[])):
            world.append({'actor_guid':a['guid'],'actor_label':a['label'],'actor_path':a['path'],'component_name':c['name'],'instance_index':i,'expected_mesh_path':c['mesh'],'expected_transform':t})
mark_handles={p['source_handles'][0] for p in evidence['floor_placeholder_placements']}
replace=[]
for v in ops:
    h=v['source_handles'][0] if len(v['source_handles'])==1 else None
    if h not in specs and h not in mark_handles:continue
    target=[v['position_m'][0]*100,-v['position_m'][1]*100,v['position_m'][2]*100]
    matches=[w for w in world if w['expected_mesh_path'].split('.')[-1]==v['mesh'].split('/')[-1] and math.dist(w['expected_transform']['translation_cm'],target)<.05 and max(abs(a-b) for a,b in zip(w['expected_transform']['scale'],v['scale']))<1e-4]
    assert len(matches)==1,(h,len(matches))
    if h in specs:new=specs[h]
    else:new=dict(v,mesh=MARKER_MESH,kind='cad_floor_placeholder',height_basis='CAD rectangle and cross at floor level; operational meaning unconfirmed')
    replace.append({'source_handle':h,'remove':matches[0],'add':new})
assert len(replace)==111
patch={'schema_version':1,'owner':'mpr-conveyor-audit-20261107','map':snapshot['map'],'snapshot_source':snapshot_path.relative_to(ROOT).as_posix(),'snapshot_sha256':hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),'destination':'/Game/MPRWarehouse/ConveyorAudit20261107','geometry_manifest':(OUT/'MPR_CADConveyorAudit.json').relative_to(ROOT).as_posix(),'replacement_count':111,'source_counts':{'supply_belts':3,'floor_placeholders':108},'replace':replace,'apply_contract':['Check map and all 111 expected actor GUID/component/index/mesh/transform before mutation.','Within each HISM remove indexes in descending order, never delete the whole actor if other instances remain.','Import only the 4 listed private FBX assets; assign role materials without modifying shared material assets.','Add the 111 replacements, mirroring CAD Y and yaw exactly once; preserve all non-target actor properties, components and instances.','Do not regenerate scene, do not change camera, lighting, roof, sorters, line routes or shared GHS mesh.','No animation path is declared by this geometry patch.']}
(OUT/'patch_manifest.json').write_text(json.dumps(patch,ensure_ascii=False,indent=2),encoding='utf8')
print('FULL_CONVEYOR_PATCH',len(replace),'GEOMETRY',len(manifest['meshes']))
