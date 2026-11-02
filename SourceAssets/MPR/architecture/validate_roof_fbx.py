"""Run with isolated Blender; verifies only the two revised roof-detail FBXs."""
import bpy,json
from pathlib import Path
from mathutils import Vector
out=Path(__file__).resolve().parent
root=out.parents[2]
manifest=json.loads((out/'mpr_architecture.json').read_text(encoding='utf8'))
results=[]
for spec in manifest['meshes']:
    if spec['name'] not in ['SM_MPR_RoofSolar','SM_MPR_RoofPlant']:continue
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(root/spec['fbx']))
    objects=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(objects)==1
    obj=objects[0];obj.data.calc_loop_triangles()
    assert len(obj.data.loop_triangles)==spec['triangles']
    assert [m.name.split('.')[0] for m in obj.data.materials]==spec['material_roles']
    pts=[obj.matrix_world@Vector(p) for p in obj.bound_box]
    error=max(abs([min(v[i] for v in pts),max(v[i] for v in pts)][j]-spec['bounds_m'][i][j]) for i in range(3) for j in range(2))
    assert error<.0001
    results.append(dict(name=spec['name'],triangles=spec['triangles'],slots=len(obj.data.materials),bounds_error_m=error))
(out/'roof_fbx_validation.json').write_text(json.dumps(dict(success=True,checks=results),indent=2),encoding='utf8')
print(results)
