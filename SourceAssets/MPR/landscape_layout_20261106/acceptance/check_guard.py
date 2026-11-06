from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys

ROOT=Path('D:/UEPro/Test')
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
import mpr_landscape_layout as m

v=m.g.read(m.SOURCE/'vegetation_plan.json')
g=m.g.read(m.SOURCE/'ground/manifest.json')
b=m.g.read(m.OUT/'before.json.gz')
# Construct a prospective engine snapshot using a separate implementation.
a=deepcopy(b)
lookup={r['guid']:r for r in a['actors']}
for item in v['groups']:
    c=next(c for c in lookup[item['actor_guid']]['components'] if c['name']==item['component_name'])
    c['instance_count']=len(item['instance_transforms'])
    c['instance_transforms']=deepcopy(item['instance_transforms'])
    c['num_custom_data_floats']=1
    c['custom_data']=list(item['custom_data'])
    c['materials'][1:]=[m.g.obj(p) for p in m.LEAVES]
for spec in g['mesh_mappings']:
    c=next(c for row in a['actors'] for c in row['components'] if c.get('mesh','').split('.')[0]==spec['old_mesh'])
    c['mesh']=m.g.obj(spec['new_mesh'])

results=[]
def record(name,call,reject=False,match=None):
    try:
        value=call()
        if reject:raise AssertionError('bad input accepted')
        results.append(dict(name=name,passed=True,result=value))
    except Exception as exc:
        passed=reject and not isinstance(exc,AssertionError) and (match is None or match in str(exc))
        results.append(dict(name=name,passed=passed,error=str(exc)[:600]))

treeid=next(r['actor_guid'] for r in v['groups'] if r['instance_transforms'])
treeids={r['actor_guid'] for r in v['groups']}
groundids={r['guid']for r in g['mesh_mappings']}
otherid=next(r['guid']for r in a['actors']if r['guid']not in treeids|groundids and r['class']=='/Script/Engine.StaticMeshActor')
def actor(s,guid):return next(r for r in s['actors']if r['guid']==guid)
def tree(s):return next(c for c in actor(s,treeid)['components']if c.get('mesh')==m.g.obj(m.TREE))
def invalid(name,change):
    bad=deepcopy(a);change(bad)
    record(name,lambda:m.validate(b,bad,v,g),True,'Unreviewed scene change')

record('expected_scene_passes',lambda:m.validate(b,a,v,g))
invalid('unrelated_actor_move',lambda s:actor(s,otherid)['transform']['translation_cm'].__setitem__(0,12345.))
invalid('unrelated_actor_hidden',lambda s:actor(s,otherid).__setitem__('hidden',True))
invalid('tree_actor_hidden',lambda s:actor(s,treeid).__setitem__('hidden',True))
invalid('tree_component_hidden',lambda s:tree(s).__setitem__('hidden_in_game',True))
invalid('tree_component_scaled',lambda s:tree(s)['transform']['scale'].__setitem__(0,2.))
invalid('tree_instance_scaled',lambda s:tree(s)['instance_transforms'][0]['scale'].__setitem__(0,.99))
invalid('tree_instance_moved',lambda s:tree(s)['instance_transforms'][0]['translation_cm'].__setitem__(0,99999.))
invalid('tree_mask_changed',lambda s:tree(s)['custom_data'].__setitem__(0,1-tree(s)['custom_data'][0]))
invalid('tree_material_changed',lambda s:tree(s)['materials'].__setitem__(2,'/Game/Bad.Bad'))
invalid('tree_mesh_changed',lambda s:tree(s).__setitem__('mesh','/Game/Bad.Bad'))
invalid('world_settings_changed',lambda s:s['world_settings'].__setitem__('world_to_meters',99.))
invalid('world_coverage_actor_removed',lambda s:s['world_actor_coverage'].pop())
invalid('actor_removed',lambda s:s['actors'].pop())
invalid('actor_added',lambda s:s['actors'].append(dict(deepcopy(s['actors'][0]),guid='BAD_GUID')))

equivalent=deepcopy(a)
for t in tree(equivalent)['instance_transforms']:
    t['rotation_xyzw']=[-x for x in t['rotation_xyzw']]
record('quaternion_sign_equivalence',lambda:m.validate(b,equivalent,v,g))

report=dict(success=all(r['passed'] for r in results),tests=results,
            script_sha256=m.g.guard.sha(ROOT/'Tools/MPRWarehouse/mpr_landscape_layout.py'),
            vegetation_sha256=m.g.guard.sha(m.SOURCE/'vegetation_plan.json'),
            ground_sha256=m.g.guard.sha(m.SOURCE/'ground/manifest.json'))
(m.OUT/'review/guard_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
assert report['success']
