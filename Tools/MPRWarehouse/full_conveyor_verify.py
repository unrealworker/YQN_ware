"""Verify the source-derived patch without opening or modifying Unreal."""
from pathlib import Path
import json,hashlib,math,sys
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/conveyor_audit_20261107'
def read(p):return json.loads(p.read_text(encoding='utf8'))
evidence=read(OUT/'cad_source_evidence.json');patch=read(OUT/'patch_manifest.json');geometry=read(OUT/'MPR_CADConveyorAudit.json')
assert hashlib.sha256(Path(evidence['source']).read_bytes()).hexdigest()==evidence['source_sha256']
assert len(evidence['floor_placeholder_symbol'])==3
assert patch['replacement_count']==len(patch['replace'])==111
keys=[(r['remove']['actor_guid'],r['remove']['component_name'],r['remove']['instance_index']) for r in patch['replace']]
assert len(keys)==len(set(keys))
marks=[];belts=[]
for r in patch['replace']:
    old=r['remove']['expected_transform'];new=r['add'];p=new['position_m']
    assert math.dist(old['translation_cm'][:2],[100*p[0],-100*p[1]])<.001
    if new['kind']=='cad_floor_placeholder':
        marks.append(r);assert new['mesh']=='SM_MPR_CADFloorPlaceholder'
        assert new['scale']==[round(v,6) for v in old['scale']]
    else:
        belts.append(r);a,b=new['belt_endpoints_cad_m']
        assert abs(a[1]-b[1])<1e-7 and b[0]>a[0]
        assert 'display-only' in new['height_basis'] and 'unconfirmed' in new['flow_basis']
        assert new['rotation_deg']==0 and new['scale']==[1,1,1]
assert len(marks)==108 and len(belts)==3
assert len(geometry['meshes'])==4
regen=ROOT/'Saved/MPR/full_workflow_20261107/regenerated_operations/instances.json'
result={'source_sha256_verified':True,'unique_removals':111,'floor_placeholders':108,'cad_supply_belts':3,'all_source_xy_positions_preserved':True,'three_belt_travel_axes_x_verified':True,'no_operational_links_invented':True,'geometry_triangles':sum(r['triangles'] for r in geometry['meshes'])}
if regen.exists():
    old=read(ROOT/'SourceAssets/MPR/operations/instances.json')['instances'];new=read(regen)['instances']
    assert len(old)==len(new)==886
    changes=[i for i,(a,b) in enumerate(zip(old,new)) if a!=b]
    assert len(changes)==111
    target_handles={r['source_handle'] for r in patch['replace']}
    assert all(len(old[i]['source_handles'])==1 and old[i]['source_handles'][0] in target_handles for i in changes)
    result['isolated_generator_regression']={'total_instances':886,'only_intended_changed':111,'non_target_exact_equal':775}
OUT.joinpath('verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False))
