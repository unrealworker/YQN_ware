"""Isolated Blender FBX readback checks; never opens/modifies the UE editor."""
import bpy,json,math
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/reference_v3/architecture'
m=json.loads((OUT/'reference_shell_manifest.json').read_text(encoding='utf8'))
cad=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))
checks=[]
for row in m['meshes']:
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 for material in list(bpy.data.materials):bpy.data.materials.remove(material)
 bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']))
 objects=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(objects)==1,(row['name'],len(objects))
 ob=objects[0];ob.data.calc_loop_triangles()
 assert len(ob.data.loop_triangles)==row['triangles'],row['name']
 assert [a.name for a in ob.data.materials]==row['material_roles'],(row['name'],[a.name for a in ob.data.materials])
 points=[ob.matrix_world@Vector(p) for p in ob.bound_box]
 error=max(abs([min(v[i] for v in points),max(v[i] for v in points)][j]-row['bounds_m'][i][j]) for i in range(3) for j in range(2))
 assert error<.0001,(row['name'],error)
 assert len(ob.data.uv_layers)==1,row['name']
 assert all(math.isfinite(v) for uv in ob.data.uv_layers[0].data for v in uv.uv),row['name']
 assert all(t.area>1e-12 for t in ob.data.loop_triangles),(row['name'],'degenerate triangle')
 checks.append(dict(name=row['name'],triangles=row['triangles'],material_slots=len(row['material_roles']),bounds_error_m=error,uv_channels=1))
assert m['footprint_outline_m']==cad['footprint_outline_m']
doors={d['id']:d for d in cad['dock_doors']+cad['drive_in_doors']}
assert len(m['cad_apertures'])==74 and {a['id'] for a in m['cad_apertures']}==set(doors)
for ap in m['cad_apertures']:
 assert ap['opening_width_m']==doors[ap['id']]['opening_width_m']
 assert ap['cad_position_m']==doors[ap['id']]['position_m']
assert len(m['instances']['SM_MPR3_DockShelter'])==72
assert len(m['instances']['SM_MPR3_RollerDriveIn'])==2
assert not any('Floor' in r['name'] or 'Column' in r['name'] or 'Partition' in r['name'] for r in m['meshes'])
assert {r['name'] for r in m['meshes'] if r['instance_only']}==set(m['instances'])
for role,spec in m['materials'].items():
 for path in spec.get('textures',{}).values():assert (ROOT/path).is_file(),(role,path)
result=dict(success=True,checks=checks,footprint_exact_match=True,cad_apertures_verified=74,
    no_interior_assets_generated=True,unique_triangles=sum(r['triangles'] for r in checks),instance_count=m['optimization']['instance_count'],
    validation_boundary='Offline source/FBX only. Does not certify UE import, scene appearance or runtime performance.')
(OUT/'fbx_validation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print('REFERENCE_SHELL_FBX_VALID',len(checks),result['unique_triangles'],max(r['bounds_error_m'] for r in checks))
