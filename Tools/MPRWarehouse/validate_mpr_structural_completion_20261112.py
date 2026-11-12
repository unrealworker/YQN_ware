"""Independent structural FBX round-trip, column bounds and stair contact checks."""
from pathlib import Path
import gzip
import json
import math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/interior_cad_20261112/structure'
m=json.loads((OUT/'structural_completion_manifest.json').read_text(encoding='utf8'))
baseline=json.load(gzip.open(ROOT/'Saved/MPR/interior_cad_20261112/preservation/baseline.json.gz','rt',encoding='utf8'))
checks=[]
for row in m['meshes']:
    for ob in list(bpy.data.objects):bpy.data.objects.remove(ob,do_unlink=True)
    for mat in list(bpy.data.materials):bpy.data.materials.remove(mat,do_unlink=True)
    bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']))
    objects=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(objects)==1
    ob=objects[0];ob.data.calc_loop_triangles()
    assert len(ob.data.loop_triangles)==row['triangles']
    assert [mat.name for mat in ob.data.materials]==row['material_roles']
    points=[ob.matrix_world@Vector(p) for p in ob.bound_box]
    error=max(abs([min(v[i] for v in points),max(v[i] for v in points)][j]-row['bounds_m'][i][j]) for i in range(3) for j in range(2))
    assert error<.0001
    assert all(t.area>1e-12 for t in ob.data.loop_triangles)
    assert len(ob.data.uv_layers)==1
    vertices=[ob.matrix_world@v.co for v in ob.data.vertices]
    tree=BVHTree.FromPolygons(vertices,[tuple(p.vertices) for p in ob.data.polygons])
    contacts=[]
    if 'NestedColumns' in row['name']:
        for column in m['column_sections']:
            x,y=column['center_m']
            hit=tree.ray_cast(Vector((x,y,13.)),Vector((0,0,-1)),14.)
            assert hit[0] is not None and abs(hit[0].z-12.2)<.0001
            contacts.append(dict(source=column['source_handles'],top_z=hit[0].z))
        assert len(contacts)==142
    else:
        for stair in m['stairs']:
            x=sum(stair['tread_x_m'])/2;ys=stair['tread_edge_y_m']
            for i,(a,b) in enumerate(zip(ys,ys[1:])):
                hit=tree.ray_cast(Vector((x,(a+b)/2,2.)),Vector((0,0,-1)),4.)
                target=-(i+1)*.15
                assert hit[0] is not None and abs(hit[0].z-target)<.0001,(stair['source_index'],i,hit,target)
                contacts.append(dict(stair=stair['source_index'],tread=i,z=hit[0].z))
            landing_x=sum(stair['platform_x_m'])/2
            hit=tree.ray_cast(Vector((landing_x,(stair['wall_y_m']+ys[0])/2,2.)),Vector((0,0,-1)),4.)
            assert hit[0] is not None and abs(hit[0].z)<.0001
            contacts.append(dict(stair=stair['source_index'],landing_z=hit[0].z))
        assert len(contacts)==144
    checks.append(dict(mesh=row['name'],triangles=row['triangles'],bounds_error_m=error,contact_checks=len(contacts)))
for remove in m['removals']:
    actor=next(a for a in baseline['actors'] if a['guid']==remove['actor_guid'])
    component=next(c for c in actor['components'] if c['name']==remove['component_name'])
    assert component['instance_transforms'][remove['instance_index']]==remove['expected_transform']
assert len(m['removals'])==6 and sum(r['actor_label'].startswith('MPR_Columns_') for r in m['removals'])==3
result=dict(success=True,checks=checks,exact_removal_targets_verified=6,column_profiles=142,stair_groups=18,
            column_top_contacts=142,stair_tread_and_landing_contacts=144,
            limitations='Offline FBX verification. All heights follow declared existing-scene estimates, not source measured elevations.')
(OUT/'fbx_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print('MPR_STRUCTURAL_COMPLETION_VALID',json.dumps(result,ensure_ascii=False))
