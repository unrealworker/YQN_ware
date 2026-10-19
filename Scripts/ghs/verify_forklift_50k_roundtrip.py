"""Read-only Blender/FBX verification in an independent Blender process."""
import bpy,json,math
from pathlib import Path
OUT=Path(r'D:/UEPro/Test/SourceAssets/GHS_Normal/MannedForklift')
report=json.loads((OUT/'manned_forklift_50k_validation.json').read_text(encoding='utf-8'))
bpy.ops.wm.open_mainfile(filepath=str(OUT/'manned_forklift_50k.blend'))
asset=bpy.data.collections['MannedForklift_Editable'];objects=[o for o in asset.all_objects if o and o.type=='MESH']
dg=bpy.context.evaluated_depsgraph_get();count=0
for o in objects:
    e=o.evaluated_get(dg);m=e.to_mesh();m.calc_loop_triangles();count+=len(m.loop_triangles);e.to_mesh_clear()
assert count==report['triangles'] and count<=50000,(count,report['triangles'])
assert len(objects)==report['mesh_objects']
assert all(not c.hide_render for c in asset.children)
assert not any(o.name.startswith(('MF_LiftChainLink','MF_ChainPin')) for o in objects)
saved_count=count
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(OUT/'manned_forklift_50k.fbx'))
objects=[o for o in bpy.context.scene.objects if o.type=='MESH'];coords=[];count=0;nontri=0
for o in objects:
    o.data.calc_loop_triangles();count+=len(o.data.loop_triangles)
    nontri+=sum(len(p.vertices)!=3 for p in o.data.polygons)
    coords.extend(o.matrix_world@v.co for v in o.data.vertices)
assert count==saved_count,(count,saved_count)
assert nontri==0,nontri
assert len(objects)==report['mesh_objects'],len(objects)
bounds=[[min(p[i] for p in coords),max(p[i] for p in coords)] for i in range(3)]
delta=max(abs(bounds[i][j]-report['bounds_m'][i][j]) for i in range(3) for j in range(2))
assert delta<.0001,(bounds,delta)
result={'blend_reopened_triangles':saved_count,'fbx_reimported_triangles':count,'fbx_mesh_objects':len(objects),
        'non_triangular_fbx_faces':nontri,'bounds_m':bounds,'maximum_roundtrip_bounds_error_m':delta,'passed':True}
(OUT/'manned_forklift_50k_roundtrip.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('ROUNDTRIP_VERIFIED',json.dumps(result))
