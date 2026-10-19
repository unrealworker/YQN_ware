"""Finalize separate editable low-poly source and a triangulated FBX; no UE operations."""
import bpy,bmesh,math,json
from pathlib import Path
from mathutils import Matrix,Vector
OUT=Path(r'D:/UEPro/Test/SourceAssets/GHS_Normal/MannedForklift')
scene=bpy.context.scene;asset=bpy.data.collections['MannedForklift_Editable'];root=bpy.data.objects['MF_Root']
original=json.loads((OUT/'worker_v3_validation.json').read_text(encoding='utf-8'))
for c in asset.children:c.hide_render=False
cam=scene.camera
v=scene['qa_original_camera_matrix'];cam.matrix_world=Matrix([v[i*4:i*4+4] for i in range(4)])
cam.data.ortho_scale=scene['qa_original_ortho']
del scene['qa_original_camera_matrix'];del scene['qa_original_ortho']
scene.render.resolution_x=1440;scene.render.resolution_y=1260;scene.render.resolution_percentage=100
scene.render.filepath=str(OUT/'manned_forklift_50k_preview.png')
bpy.context.view_layer.update()
parts=[o for o in asset.all_objects if o and o.type=='MESH'];rows=[];coords=[];groups={}
dg=bpy.context.evaluated_depsgraph_get()
for c in asset.children:
    for o in c.all_objects:
        if not o or o.type!='MESH':continue
        e=o.evaluated_get(dg);m=e.to_mesh();m.calc_loop_triangles();nt=len(m.loop_triangles)
        assert all(math.isfinite(x) for v in m.vertices for x in v.co),o.name
        assert all(len(p.vertices)>=3 for p in m.polygons),o.name
        coords.extend(o.matrix_world@v.co for v in m.vertices)
        groups[c.name]=groups.get(c.name,0)+nt
        rows.append({'name':o.name,'triangles':nt,'vertices':len(m.vertices),'materials':[s.name for s in m.materials]})
        e.to_mesh_clear()
total=sum(groups.values());assert 49000<=total<=50000,total
assert not any(o.name.startswith(('MF_LiftChainLink','MF_ChainPin')) for o in parts)
bounds=[[min(p[i] for p in coords),max(p[i] for p in coords)] for i in range(3)]
delta=max(abs(bounds[i][j]-original['bounds_m'][i][j]) for i in range(3) for j in range(2))
assert delta<.001,(bounds,delta)
closed={}
for name in ['DRV_Head','DRV_WorkJacket','DRV_Trousers']:
    o=bpy.data.objects[name];bm=bmesh.new();bm.from_mesh(o.data)
    bad=sum(not e.is_manifold for e in bm.edges);closed[name]=bad;bm.free();assert bad==0,(name,bad)
root['revision']='50k_appearance_preserving_optimization'
root['triangles_including_driver']=total
root['triangle_budget']=50000
root['UnrealImport']='Not imported. Blender review only per user request.'
root['optimized_original_file']='manned_forklift_worker_v3.blend'
report={'original_triangles':original['total_triangles'],'triangles':total,'reduction_percent':round((1-total/original['total_triangles'])*100,3),
        'groups':groups,'mesh_objects':len(parts),'bounds_m':bounds,'dimensions_m':[b[1]-b[0] for b in bounds],
        'maximum_bounds_change_m':delta,'primary_worker_non_manifold_edges':closed,'removed_chain_parts':136,
        'duplicate_axles_removed':2,'original_preserved':True,'unreal_imported':False,
        'blend':str(OUT/'manned_forklift_50k.blend'),'fbx':str(OUT/'manned_forklift_50k.fbx'),
        'preview':scene.render.filepath,'objects':rows}
for o in bpy.context.selected_objects:o.select_set(False)
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0]
bpy.ops.export_scene.fbx(filepath=report['fbx'],use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',
    apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',use_mesh_modifiers=True,use_triangles=True,add_leaf_bones=False)
for o in parts:o.select_set(False)
root.select_set(True);bpy.context.view_layer.objects.active=root
(OUT/'manned_forklift_50k_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
# Open the source at the same presentation angle, with the complete asset visible.
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
bpy.ops.wm.save_as_mainfile(filepath=report['blend'],compress=True)
bpy.ops.render.render(write_still=True)
print('FINAL_SAVED',json.dumps({k:report[k] for k in ['triangles','reduction_percent','groups','mesh_objects','bounds_m','maximum_bounds_change_m','primary_worker_non_manifold_edges','blend','fbx']}))
