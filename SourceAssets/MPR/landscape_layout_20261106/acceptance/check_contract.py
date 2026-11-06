from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys

ROOT=Path('D:/UEPro/Test')
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
import mpr_landscape_layout as m
vpath=m.SOURCE/'vegetation_plan.json'
gpath=m.SOURCE/'ground/manifest.json'
apath=m.SOURCE/'ground/geometry_validation.json'
read=m.g.read
v,g,b=m.source_contract()
results=[dict(name='real_source_contract',passed=True,trees=sum(len(r['instance_transforms'])for r in v['groups']))]

def reject(name,path,mutate,match):
    wrong=deepcopy(read(path));mutate(wrong)
    def fake(p):return deepcopy(wrong)if Path(p).resolve()==path.resolve()else read(p)
    try:
        with patch.object(m.g,'read',fake):m.source_contract()
        results.append(dict(name=name,passed=False,error='bad source accepted'))
    except Exception as exc:
        results.append(dict(name=name,passed=match in str(exc),error=str(exc)))

reject('wrong_map',vpath,lambda x:x.update(map='/Game/Maps/Wrong'),'Wrong landscape map')
reject('stale_baseline',vpath,lambda x:x.update(baseline_sha256='wrong'),'Stale vegetation baseline')
reject('wrong_tree_mesh',vpath,lambda x:x.update(tree_mesh='/Game/Bad'),'Unreviewed tree mesh')
reject('failed_vegetation_validation',vpath,lambda x:x['validation'].update(success=False),'Vegetation geometry validation failed')
reject('vegetation_protected_overlap',vpath,lambda x:x['validation'].update(protected_overlap_m2=1.),'Vegetation geometry validation failed')
reject('vegetation_crown_collision',vpath,lambda x:x['validation'].update(min_canopy_gap_m=.2),'Vegetation geometry validation failed')
reject('stale_source_hash',vpath,lambda x:x['source_hashes'].update({next(iter(x['source_hashes'])):'wrong'}),'Source changed')
reject('source_path_escape',vpath,lambda x:x['source_hashes'].update({'../escape.bin':'wrong'}),'Source changed')
reject('omitted_tree_group',vpath,lambda x:x['groups'].pop(),'Tree component scope changed')
reject('duplicate_tree_group',vpath,lambda x:x['groups'].__setitem__(0,deepcopy(x['groups'][1])),'Tree component scope changed')
reject('invalid_colour_mask',vpath,lambda x:next(r for r in x['groups']if r['custom_data'])['custom_data'].__setitem__(0,.5),'Invalid tree colour mask')
reject('invalid_tree_scale',vpath,lambda x:next(r for r in x['groups']if r['instance_transforms'])['instance_transforms'][0]['scale'].__setitem__(0,2.),'Invalid tree scale')
reject('invalid_tree_pitch',vpath,lambda x:next(r for r in x['groups']if r['instance_transforms'])['instance_transforms'][0]['rotation_xyzw'].__setitem__(0,.5),'Only normalized yaw')
reject('wrong_asset_namespace',gpath,lambda x:x.update(namespace='/Game/Bad'),'Unexpected landscape asset namespace')
reject('bad_fbx_hash',gpath,lambda x:x['meshes'][0].update(sha256='wrong'),'FBX source changed')
reject('bad_ground_source',gpath,lambda x:x['mesh_mappings'][0].update(old_mesh='/Game/Bad'),'Ground scope must be exactly')
reject('stale_ground_report',apath,lambda x:x.update(manifest_sha256='wrong'),'Ground geometry validation is missing or stale')
reject('failed_ground_report',apath,lambda x:x.update(success=False),'Ground geometry validation is missing or stale')

report=dict(success=all(r['passed']for r in results),tests=results,
            script_sha256=m.g.guard.sha(ROOT/'Tools/MPRWarehouse/mpr_landscape_layout.py'),
            vegetation_sha256=m.g.guard.sha(vpath),ground_sha256=m.g.guard.sha(gpath))
(m.OUT/'review/contract_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
assert report['success']
