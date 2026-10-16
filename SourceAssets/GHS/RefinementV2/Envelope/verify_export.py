"""Independent imported-FBX check and visible previews of final geometry."""
import bpy, json, math, hashlib, sys
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parent
manifest=json.loads((OUT/'envelope_v2.json').read_text(encoding='utf8'))
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
checks=[]
objs={}
for entry in manifest['meshes']:
    before=set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=entry['fbx'])
    imported=[o for o in set(bpy.data.objects)-before if o.type=='MESH']
    assert len(imported)==1
    o=imported[0];objs[entry['role']]=o
    bpy.context.view_layer.objects.active=o
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True)
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    bounds=[[min(v.co[i] for v in o.data.vertices),max(v.co[i] for v in o.data.vertices)] for i in range(3)]
    for actual,expected in zip(bounds,entry['bounds_m']):
        assert max(abs(actual[i]-expected[i]) for i in range(2))<.0002,(entry['name'],bounds,entry['bounds_m'])
    slots=[m.name for m in o.data.materials]
    assert slots==entry['slots'],(slots,entry['slots'])
    sha=hashlib.sha256(Path(entry['fbx']).read_bytes()).hexdigest()
    assert sha==entry['sha256']
    checks.append({'mesh':entry['name'],'bounds_m':bounds,'slots':slots,'fbx_sha256_matches':True,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons)})
door=objs['DockDoor'];panel_faces=[];dark_area=0
for p in door.data.polygons:
    slot=door.data.materials[p.material_index].name
    if slot.endswith('_Panel') and abs(p.normal.y)>.99:
        panel_faces.append({'normal_y':p.normal.y,'area_m2':p.area})
    if slot.endswith('_Dark'):
        dark_area+=p.area
panel_positive=sum(p['area_m2'] for p in panel_faces if p['normal_y']>0)
panel_negative=sum(p['area_m2'] for p in panel_faces if p['normal_y']<0)
assert panel_positive>5 and panel_negative>5
assert abs(panel_positive-panel_negative)<.001
assert dark_area<1.0, dark_area
result={'imported_fbx_checks':checks,'door_front_panel_area_m2':panel_positive,'door_back_panel_area_m2':panel_negative,'door_dark_material_total_surface_area_m2':dark_area,'two_sided_panel_geometry_verified':True,'small_seals_only_verified':True}
if (OUT/'uv_verification.json').is_file():
    result['uv_and_explicit_tangent_verification']=json.loads((OUT/'uv_verification.json').read_text(encoding='utf8'))
(OUT/'export_verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print('INDEPENDENT_FBX_CHECKS',json.dumps(result,indent=2))
if '--no-render' in sys.argv:
    print('EXPORT_CHECKS_COMPLETE_NO_RENDER')
    raise SystemExit(0)

scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_x=1200;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.world.color=(.7,.7,.7)
display=scene.display.shading
display.light='STUDIO';display.color_type='MATERIAL'
display.show_shadows=True;display.show_cavity=True;display.cavity_type='BOTH'
display.background_type='WORLD';display.show_object_outline=True
scene.view_settings.view_transform='Standard'
bpy.ops.object.camera_add()
camera=bpy.context.object;scene.camera=camera;camera.data.type='ORTHO'
def point_camera(location,target,scale):
    camera.location=location
    camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.ortho_scale=scale
def render(name):
    scene.render.filepath=str(OUT/name);bpy.ops.render.render(write_still=True)
for role,o in objs.items():o.hide_render=role!='DockDoor'
point_camera((4,-9,5),(0,0,2.1),6.0);render('door_front.png')
point_camera((-4,9,5),(0,0,2.1),6.0);render('door_back.png')
for role,o in objs.items():o.hide_render=role=='DockDoor'
for entry in json.loads((OUT/'door_docking_targets.json').read_text(encoding='utf8'))['doors']:
    inst=door.copy();inst.data=door.data;scene.collection.objects.link(inst)
    inst.location=entry['door_center_cad_m']
    inst.rotation_euler.z=math.radians(entry['door_rotation_cad_deg'])
    inst.hide_render=False
scene.render.resolution_x=1800;scene.render.resolution_y=850
point_camera((45,-260,290),(-6,-8,0),520);render('envelope_overview.png')
point_camera((245,-75,18),(224,-42,4),50);render('envelope_east_corner.png')
print('PREVIEWS_COMPLETE')
