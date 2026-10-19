"""Verify the reference worker and save the editable Blender review version."""
import bpy,bmesh,hashlib,json,math
from pathlib import Path
from mathutils import Vector
out=Path(r'D:/UEPro/Test/SourceAssets/GHS_Normal/MannedForklift')
s=bpy.context.scene;co=bpy.data.collections['05_Driver'];asset=bpy.data.collections['MannedForklift_Editable']
assert s.name=='GHS_MannedForklift_Studio'
baseline=json.loads((out/'worker_v3_vehicle_baseline.json').read_text())
def signature(o):
    h=hashlib.sha256();h.update(str(tuple(tuple(r) for r in o.matrix_world)).encode())
    if o.type=='MESH':
        h.update(str([tuple(v.co) for v in o.data.vertices]).encode());h.update(str([tuple(p.vertices) for p in o.data.polygons]).encode())
    h.update(str([m.name if m else None for m in o.data.materials] if hasattr(o.data,'materials') else []).encode())
    return h.hexdigest()
changed=[]
for name,before in baseline.items():
    obj=bpy.data.objects.get(name)
    if obj is None or signature(obj)!=before:changed.append(name)
assert not changed,changed
for c in asset.children:c.hide_render=False
dg=bpy.context.evaluated_depsgraph_get()
def bounds_of(objects):
    points=[];triangles=0
    for o in objects:
        if o.type not in {'MESH','FONT','CURVE'}:continue
        ev=o.evaluated_get(dg);me=ev.to_mesh();points.extend(o.matrix_world@v.co for v in me.vertices)
        me.calc_loop_triangles();triangles+=len(me.loop_triangles);ev.to_mesh_clear()
    assert all(math.isfinite(c) for p in points for c in p)
    return [[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)],triangles
bounds,tris=bounds_of(asset.all_objects)
worker_bounds,worker_tris=bounds_of(co.objects)
hat,_=bounds_of([o for o in co.objects if 'Helmet' in o.name])
roof,_=bounds_of([o for o in asset.all_objects if o.name.startswith('MF_V2_RoofSlat')])
assert roof[2][0]-hat[2][1]>.1
sole,_=bounds_of([o for o in co.objects if 'BootSole' in o.name])
floor,_=bounds_of([bpy.data.objects['MF_V2_FloorMat']])
assert abs(sole[2][0]-floor[2][1])<.003
surfaces={}
for name in ['DRV_Head','DRV_WorkJacket','DRV_Trousers']:
    bm=bmesh.new();bm.from_mesh(bpy.data.objects[name].data)
    surfaces[name]={'non_manifold_edges':sum(not e.is_manifold for e in bm.edges),'volume_m3':bm.calc_volume()};bm.free()
    assert surfaces[name]['non_manifold_edges']==0
assert not any('Vest' in o.name for o in co.objects)
report={'revision':'worker reference v3','reference':r'C:/Users/28109/AppData/Local/Temp/codex-clipboard-a2969de0-381b-4e20-b8f4-7a5a6da7d2fd.png',
        'blend':str(out/'manned_forklift_worker_v3.blend'),'units':'metres','dimensions_estimated':True,
        'bounds_m':bounds,'worker_bounds_m':worker_bounds,'total_triangles':tris,'worker_triangles':worker_tris,
        'worker_parts':len(co.objects),'vehicle_parts_unchanged':len(baseline),'vehicle_geometry_material_assignment_transform_changes':changed,
        'helmet_roof_clearance_m':roof[2][0]-hat[2][1],'boot_floor_gap_m':sole[2][0]-floor[2][1],
        'closed_primary_surfaces':surfaces,'unreal_imported':False,
        'appearance':['Red cap-style hardhat','Navy grey jacket and trousers','Yellow twin chest and sleeve tapes','Turn-down collar and flap chest pockets','Integrated adult face surface and short dark hair','Seated driving pose retained']}
(out/'worker_v3_validation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
s.render.resolution_x=1440;s.render.resolution_y=1260;s.render.resolution_percentage=100
s.eevee.taa_render_samples=96
s.render.filepath=str(out/'manned_forklift_worker_v3_preview.png')
for o in bpy.context.selected_objects:o.select_set(False)
bpy.ops.wm.save_as_mainfile(filepath=report['blend'])
print('WORKER_V3_VERIFIED_AND_SAVED',json.dumps(report))
bpy.ops.render.render(write_still=True)
print('WORKER_V3_FULL_PREVIEW',s.render.filepath)
