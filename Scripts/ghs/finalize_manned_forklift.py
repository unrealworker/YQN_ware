"""Save editable forklift, bake a UE mesh/FBX and record measured geometry."""
import bpy,json,math,bmesh
from pathlib import Path
from mathutils import Vector
ROOT=Path(r'D:/UEPro/Test');OUT=ROOT/'SourceAssets/GHS_Normal/MannedForklift'
scene=bpy.context.scene
asset=bpy.data.collections['MannedForklift_Editable']
originals=[o for o in asset.all_objects if o.type in {'MESH','FONT','CURVE'}]
deps=bpy.context.evaluated_depsgraph_get()
# Confirm operator enums against this installed Blender before using them.
for op,prop,expected in [(bpy.ops.object.select_all,'action','DESELECT'),(bpy.ops.object.mode_set,'mode','EDIT'),(bpy.ops.mesh.select_all,'action','SELECT')]:
    assert expected in {e.identifier for e in op.get_rna_type().properties[prop].enum_items}
for o in bpy.context.selected_objects:o.select_set(False)
export_collection=bpy.data.collections.new('TEMP_Export');scene.collection.children.link(export_collection)
copies=[]
for o in originals:
    d=bpy.data.meshes.new_from_object(o.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
    ob=bpy.data.objects.new('EXPORT_'+o.name,d);export_collection.objects.link(ob);ob.matrix_world=o.matrix_world.copy();ob.select_set(True);copies.append(ob)
bpy.context.view_layer.objects.active=copies[0];bpy.ops.object.join();obj=bpy.context.object;obj.name='SM_GHN_MannedForklift'
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
# Recalculate winding consistently; preserve bevelled geometry and smooth groups.
bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(obj.data);bm.free();obj.data.update()
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(island_margin=.01);bpy.ops.object.mode_set(mode='OBJECT')
obj.data.calc_loop_triangles()
bounds=[[min(v.co[i] for v in obj.data.vertices),max(v.co[i] for v in obj.data.vertices)] for i in range(3)]
assert all(math.isfinite(c) for v in obj.data.vertices for c in v.co)
assert 3.0<bounds[0][1]-bounds[0][0]<3.7
assert 1.0<bounds[1][1]-bounds[1][0]<1.45
assert 2.1<bounds[2][1]-bounds[2][0]<2.5
assert -.03<bounds[2][0]<.01
used=[m.name for m in obj.data.materials]
materials=json.loads((OUT/'material_manifest.json').read_text(encoding='utf8'))
assert set(used)<=set(m['name'] for m in materials)
report={'name':'SM_GHN_MannedForklift','blend':str(OUT/'manned_forklift.blend'),'fbx':str(OUT/'manned_forklift.fbx'),'units':'metres','dimensions_estimated_from_reference':True,'bounds_m':bounds,'dimensions_m':[b[1]-b[0] for b in bounds],'source_parts':len(originals),'driver_parts':len(list(bpy.data.collections['05_Driver'].objects)),'vertices':len(obj.data.vertices),'triangles':len(obj.data.loop_triangles),'slots':used,'materials':[m for m in materials if m['name'] in used]}
bpy.ops.export_scene.fbx(filepath=report['fbx'],use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False)
# Remove only the temporary export mesh; the 583 source parts stay editable.
bpy.data.objects.remove(obj,do_unlink=True);bpy.data.collections.remove(export_collection)
(OUT/'manned_forklift.json').write_text(json.dumps(report,indent=2),encoding='utf8')
bpy.ops.wm.save_as_mainfile(filepath=report['blend'])
scene.render.filepath=str(OUT/'manned_forklift_preview.png')
bpy.ops.render.render(write_still=True)
print('MANNED_FORKLIFT_EXPORTED',json.dumps({k:report[k] for k in ['dimensions_m','source_parts','driver_parts','vertices','triangles','bounds_m']}))
