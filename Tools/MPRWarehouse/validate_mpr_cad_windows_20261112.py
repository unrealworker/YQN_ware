"""Independent readback checks for CAD windows; no editor access or modification."""
from pathlib import Path
import gzip
import json
import math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/interior_cad_20261112/windows'
m=json.loads((OUT/'cad_windows_manifest.json').read_text(encoding='utf8'))
first=json.loads((ROOT/'SourceAssets/MPR/interior_cad_20261112/architecture/mpr_interior_architecture_patch.json').read_text(encoding='utf8'))
original=json.loads((ROOT/'SourceAssets/MPR/reference_v4/architecture/reference_shell_manifest.json').read_text(encoding='utf8'))
source=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_extracted.json').read_text(encoding='utf8'))
baseline=json.load(gzip.open(ROOT/m['baseline'],'rt',encoding='utf8'))
checks=[];window_count=0;door_count=0;pane_count=0

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
    assert all(math.isfinite(v) for uv in ob.data.uv_layers[0].data for v in uv.uv)
    vertices=[ob.matrix_world@v.co for v in ob.data.vertices]
    tree=BVHTree.FromPolygons(vertices,[tuple(p.vertices) for p in ob.data.polygons])
    window_rays=0;door_rays=0;glass_rays=0
    replacements=[r for r in m['replacements'] if r['new_mesh_name']==row['name']]
    if replacements:
        replacement=replacements[0];side=replacement['side']
        if side is not None:
            oldrow=next(r for r in original['meshes'] if r['name']==f'SM_MPR4_Facade_{side:02}')
            assert max(abs(a-b) for ax,bx in zip(row['bounds_m'],oldrow['bounds_m']) for a,b in zip(ax,bx))<.0001
            assert row['material_roles']==oldrow['material_roles']
            for pane in replacement['windows']:
                axis=pane['axis'];normal=1-axis
                # Verify each aperture using three horizontal and three vertical
                # samples independently against the triangulated FBX wall.
                for alpha in (.1,.5,.9):
                    for beta in (.1,.5,.9):
                        start=[0.,0.,pane['z0']+beta*(pane['z1']-pane['z0'])]
                        start[axis]=pane['lo']+alpha*(pane['hi']-pane['lo']);start[normal]=pane['wall_fixed']-.5
                        direction=[0.,0.,0.];direction[normal]=1
                        assert tree.ray_cast(Vector(start),Vector(direction),1.)[0] is None,(row['name'],pane['source_handles'],start)
                        window_rays+=1
                window_count+=1
            first_side=[r for r in first['facade_replacements'] if r['actor_label']==replacement['actor_label']]
            if first_side:
                for door in first_side[0]['exterior_door_groups']:
                    axis=door['axis'];normal=1-axis
                    for alpha in (.1,.5,.9):
                        for z in (.10,1.,2.1):
                            start=[0.,0.,z];start[axis]=door['lo']+alpha*(door['hi']-door['lo']);start[normal]=door['fixed']-.5
                            direction=[0.,0.,0.];direction[normal]=1
                            assert tree.ray_cast(Vector(start),Vector(direction),1.)[0] is None,(row['name'],door['jamb_source_handles'])
                            door_rays+=1
                    door_count+=1
        actor=next(a for a in baseline['actors'] if a['guid']==replacement['actor_guid'])
        assert actor['label']==replacement['actor_label']
        component=next(c for c in actor['components'] if c.get('mesh'))
        assert component['mesh']==replacement['old_mesh']
        assert component['materials']==replacement['preserve_material_overrides']
    else:
        assert row['name']=='SM_MPR_CAD_WindowSystem_20261112'
        glass_index=row['material_roles'].index('MPR4_GlassBlue')
        for pane in m['panes']:
            axis=pane['axis'];normal=1-axis
            start=[0.,0.,(pane['z0']+pane['z1'])/2];start[axis]=(pane['lo']+pane['hi'])/2;start[normal]=pane['fixed']-.05
            direction=[0.,0.,0.];direction[normal]=1
            hit=tree.ray_cast(Vector(start),Vector(direction),.1)
            assert hit[0] is not None,(pane['source_handles'],'missing glass')
            assert ob.data.polygons[hit[2]].material_index==glass_index,(pane['source_handles'],'centre hits frame')
            assert abs(hit[0][normal]-(pane['fixed']-.011))<.0001,(pane['source_handles'],hit[0])
            pane_count+=1;glass_rays+=1
    checks.append(dict(name=row['name'],bounds_error_m=error,triangles=row['triangles'],
        materials=row['material_roles'],window_rays=window_rays,pedestrian_door_rays=door_rays,glass_rays=glass_rays))

assert window_count==41 and pane_count==102
assert door_count==8
for remove in m['removals']:
    actor=next(a for a in baseline['actors'] if a['guid']==remove['actor_guid'])
    assert actor['label']==remove['actor_label']
    assert [c['mesh'] for c in actor['components'] if c.get('mesh')]==remove['expected_meshes']

# Verify the plan opening ends from actual wall cross-section entities, not
# repetition or an assumed nominal window width.
source_by_handle={tuple(r['source_handles']):r for r in source['architecture']}
jamb_count=0
for pane in m['panes']:
    if pane['exterior_edge'] is None:continue
    for end,handles in zip((pane['frame_lo'],pane['frame_hi']),pane['measured_jamb_source_handles']):
        assert handles
        for handle in handles:
            row=source_by_handle[tuple(handle)]
            assert row['layer']=='A-WALL-EXT' and row['type']=='LINE'
            assert all(abs(p[pane['axis']]-end)<.001 for p in row['points_m'])
        jamb_count+=1
assert jamb_count==82
untouched_sides=[r['actor_label'] for r in first['facade_replacements'] if r['actor_label'] not in {x['actor_label'] for x in m['replacements']}]
assert {'MPR4_Facade_02','MPR4_Facade_12'}<=set(untouched_sides)
result=dict(success=True,checks=checks,cad_glass_panes_verified=102,external_window_apertures_verified=41,
    measured_cad_jambs_verified=82,retained_pedestrian_doors_on_changed_facades=8,
    first_patch_door_facades_untouched=untouched_sides,
    unchanged_large_doors=74,large_door_preservation_basis='Facade02/12 asset references are outside this replacement set; first-patch validation already ray-checked all74.',
    exact_actor_replacements=5,exact_old_glazing_removals=3,
    limitations='Offline FBX verification only. Window and sill heights are explicitly inherited display estimates. UE import and fixed-view inspection remain required.')
(OUT/'fbx_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print('MPR_CAD_WINDOWS_VALID',json.dumps(result,ensure_ascii=False))
