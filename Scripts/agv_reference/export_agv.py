"""Export evaluated copies; preserve the editable source .blend components."""
import bpy
import bmesh
import json
from pathlib import Path
from mathutils import Vector
ROOT=Path(r"D:\UEPro\Test")
OUT=ROOT/'SourceAssets/AGV_Reference'
scene=bpy.data.scenes['AGV_Reference_Model']
bpy.context.window.scene=scene
parts=[o for o in scene.objects if o.get('agv_part')]
source_names=[o.name for o in parts]
deps=bpy.context.evaluated_depsgraph_get()
copies=[]
export_collection=bpy.data.collections.new('Export_Evaluated_Copy');scene.collection.children.link(export_collection)
for o in parts:
    assert all(m is not None for m in o.data.materials), 'Unassigned material on '+o.name
    evaluated=o.evaluated_get(deps)
    data=bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=deps)
    dup=bpy.data.objects.new(o.name+'_export',data);export_collection.objects.link(dup)
    dup.matrix_world=o.matrix_world.copy();copies.append(dup)
bpy.ops.object.select_all(action='DESELECT')
for o in copies:o.select_set(True)
bpy.context.view_layer.objects.active=copies[0]
bpy.ops.object.join()
obj=bpy.context.object;obj.name='SM_AGV_Reference'
scene.cursor.location=(0,0,0)
bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
bm=bmesh.new();bm.from_mesh(obj.data)
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
bmesh.ops.triangulate(bm,faces=list(bm.faces))
bm.to_mesh(obj.data);bm.free()
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.151917,island_margin=.004)
bpy.ops.object.mode_set(mode='OBJECT')
# Ground-aligned asset pivot and meaningful dimensions in metres.
minz=min(v.co.z for v in obj.data.vertices)
for v in obj.data.vertices:v.co.z-=minz
bounds=[[min(v.co[i] for v in obj.data.vertices),max(v.co[i] for v in obj.data.vertices)] for i in range(3)]
materials=[]
for m in obj.data.materials:
    assert m is not None, 'Unassigned export material'
    bs=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    item=dict(name=m.name,base_color=list(bs.inputs['Base Color'].default_value),roughness=bs.inputs['Roughness'].default_value,metallic=bs.inputs['Metallic'].default_value)
    value=bs.inputs['Emission Strength'].default_value
    if value>0:item['emission']=value
    if item['name'] not in [x['name'] for x in materials]:materials.append(item)
fbx=OUT/'SM_AGV_Reference.fbx'
bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',use_mesh_modifiers=True,use_tspace=True,add_leaf_bones=False)
result=dict(nominal_length_m=1.6,dimensions_m=[b[1]-b[0] for b in bounds],bounds_m=bounds,source_parts=source_names,materials=materials,vertices=len(obj.data.vertices),triangles=len(obj.data.polygons),fbx=str(fbx),source=str(OUT/'AGV_Reference.blend'),front_axis='-X',scale_note='Proportions reconstructed from one image; dimensions assumed with user approval.')
(OUT/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('AGV_EXPORT_COMPLETE',json.dumps({k:v for k,v in result.items() if k not in ['source_parts','materials']}))
