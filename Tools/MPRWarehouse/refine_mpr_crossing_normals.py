"""Background Blender: smooth only the asphalt corners of two crossing ramps.

Vertices, polygons, UVs, material slots and nonlocal corner normals remain fixed.
Output is staged under Saved; the CPU verifier approves it before source replacement.
"""
import json,math
from pathlib import Path
from collections import defaultdict
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/crossing_surface_20261105'
STAGE=ROOT/'Saved/MPR/crossing_surface_20261105/ramp_normals'

def main():
    plan=json.loads((STAGE/'inputs.json').read_text(encoding='utf8'))
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    objects={}
    for row in plan['references']+plan['targets']:
        previous=set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']),use_custom_normals=True)
        added=[o for o in bpy.data.objects if o not in previous and o.type=='MESH']
        assert len(added)==1,row['name'];objects[row['name']]=added[0]
    sums=defaultdict(lambda:Vector((0,0,0)));weights=defaultdict(float)
    def key(v):return tuple(round(float(x),4)for x in v)
    for obj in objects.values():
        data=obj.data
        for face in data.polygons:
            normal=face.normal.copy();weight=max(face.area,1e-12)
            for vi in face.vertices:
                k=key(data.vertices[vi].co);sums[k]+=normal*weight;weights[k]+=weight
    report=[]
    for row in plan['targets']:
        obj=objects[row['name']];data=obj.data
        geometry_before=[tuple(v.co)for v in data.vertices],[(tuple(f.vertices),f.material_index)for f in data.polygons]
        normals=[n.vector.copy()for n in data.corner_normals];old_normals=[v.copy()for v in normals]
        edited=[]
        for face in data.polygons:
            if row['material_roles'][face.material_index]!='MPR4_TerminalAsphalt':continue
            face.use_smooth=True
            for index in face.loop_indices:
                normal=sums[key(data.vertices[data.loops[index].vertex_index].co)].normalized()
                if normal.dot(face.normal)<0:normal.negate()
                normals[index]=normal;edited.append(index)
        data.normals_split_custom_set(normals)
        assert geometry_before==([tuple(v.co)for v in data.vertices],[(tuple(f.vertices),f.material_index)for f in data.polygons])
        unchanged=[i for i in range(len(normals))if i not in set(edited)]
        error=max(((data.corner_normals[i].vector-old_normals[i]).length for i in unchanged),default=0.)
        assert error<1e-5,('Nonlocal custom normals changed',row['name'],error)
        for index,role in enumerate(row['material_roles']):
            material=data.materials[index];existing=bpy.data.materials.get(role)
            if existing is not None and existing!=material:existing.name='__Reference_'+role
            material.name=role
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
        target=STAGE/row['name'];target=target.with_suffix('.fbx')
        bpy.ops.export_scene.fbx(filepath=str(target),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',
            apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False,colors_type='LINEAR')
        report.append(dict(name=row['name'],edited_corners=len(edited),unchanged_corners=len(unchanged),
            nonlocal_normal_vector_error=error,positions_and_topology_unchanged=True))
    (STAGE/'blender_report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print('CROSSING_RAMP_NORMALS_STAGED',report,flush=True)

if __name__=='__main__':main()
