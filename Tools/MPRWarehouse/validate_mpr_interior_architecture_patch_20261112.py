"""Independent FBX readback and door-opening ray checks; no UE/editor access."""
from pathlib import Path
import json
import math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/interior_cad_20261112/architecture'
manifest=json.loads((OUT/'mpr_interior_architecture_patch.json').read_text(encoding='utf8'))
old=json.loads((ROOT/'SourceAssets/MPR/reference_v4/architecture/reference_shell_manifest.json').read_text(encoding='utf8'))
checks=[]
openings_tested=0
large_openings_tested=0
for row in manifest['meshes']:
    for ob in list(bpy.data.objects):bpy.data.objects.remove(ob,do_unlink=True)
    for material in list(bpy.data.materials):bpy.data.materials.remove(material,do_unlink=True)
    bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']))
    objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
    assert len(objects)==1,(row['name'],len(objects))
    ob=objects[0];ob.data.calc_loop_triangles()
    assert len(ob.data.loop_triangles)==row['triangles']
    assert [m.name for m in ob.data.materials]==row['material_roles'],(row['name'],[m.name for m in ob.data.materials],row['material_roles'])
    points=[ob.matrix_world@Vector(p) for p in ob.bound_box]
    error=max(abs([min(v[i] for v in points),max(v[i] for v in points)][j]-row['bounds_m'][i][j]) for i in range(3) for j in range(2))
    assert error<.0001,(row['name'],error)
    assert len(ob.data.uv_layers)==1
    assert all(math.isfinite(v) for uv in ob.data.uv_layers[0].data for v in uv.uv)
    assert all(t.area>1e-12 for t in ob.data.loop_triangles)
    matching=[r for r in manifest['facade_replacements'] if r['new_mesh_name']==row['name']]
    door_rays=0
    if matching:
        replacement=matching[0]
        side=int(replacement['actor_label'][-2:])
        oldrow=next(r for r in old['meshes'] if r['name']==f'SM_MPR4_Facade_{side:02}')
        assert max(abs(a-b) for ax,bx in zip(row['bounds_m'],oldrow['bounds_m']) for a,b in zip(ax,bx))<.0001
        assert row['material_roles']==oldrow['material_roles']
        vertices=[ob.matrix_world@v.co for v in ob.data.vertices]
        tree=BVHTree.FromPolygons(vertices,[tuple(p.vertices) for p in ob.data.polygons])
        for door in replacement['exterior_door_groups']:
            axis=door['axis'];normal=1-axis
            for alpha in (.1,.5,.9):
                for z in (.10,1.0,2.10):
                    start=[0.,0.,z];start[axis]=door['lo']+(door['hi']-door['lo'])*alpha;start[normal]=door['fixed']-.5
                    direction=[0.,0.,0.];direction[normal]=1
                    hit=tree.ray_cast(Vector(start),Vector(direction),1.0)
                    assert hit[0] is None,(row['name'],door['jamb_source_handles'],start,hit)
                    door_rays+=1
            openings_tested+=1
        for opening in old['cad_apertures']:
            if opening['side']!=side:continue
            p=opening['wall_position_m'];axis=0 if side in (2,12) else 1;normal=1-axis
            for offset in (-.35,0,.35):
                start=list(p);start[axis]+=offset*opening['opening_width_m'];start[normal]-=.5;start[2]=1.
                direction=[0.,0.,0.];direction[normal]=1
                assert tree.ray_cast(Vector(start),Vector(direction),1.)[0] is None,(row['name'],opening['id'])
            large_openings_tested+=1
    checks.append(dict(name=row['name'],bounds_error_m=error,triangles=row['triangles'],
                       materials=row['material_roles'],uv_channels=1,pedestrian_opening_rays=door_rays))
assert openings_tested==32
assert large_openings_tested==74
result=dict(success=True,checks=checks,exterior_openings_verified=32,existing_large_openings_verified=74,
            partitions_added=6,measured_partition_total_length_m=manifest['measured_total_length_m'],
            door_leaves=80,scope='Offline FBX/source verification. UE import and fixed-view inspection remain required.')
(OUT/'fbx_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print('MPR_INTERIOR_ARCHITECTURE_VALID',json.dumps(result,ensure_ascii=False))
