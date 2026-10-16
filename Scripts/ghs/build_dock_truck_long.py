"""Normal-only 12 m cargo-body truck; keep rear origin, cab and tire proportions."""
import sys,json,math,hashlib
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/video_reference'))
import common as c
c.OUT=ROOT/'SourceAssets/GHS_Normal/TrucksLong';c.OUT.mkdir(parents=True,exist_ok=True)
c.reset()
colors={'Body':(.60,.65,.70),'Trim':(.30,.39,.49),'Accent':(.02,.09,.34),
        'Glass':(.025,.065,.09),'Rubber':(.018,.023,.03),'Headlight':(.66,.87,.96),'TailLight':(.5,.035,.018)}
m={k:c.material('GHSV2Truck_'+k,v,.48 if k!='Rubber' else .84,.25 if k in {'Body','Trim'} else .03) for k,v in colors.items()}
c.begin_asset('SM_GHN_LongDockTruck')
def box(n,p,s,r='Body',b=.008):return c.box(n,p,s,m[r],b)
def beam(n,a,b,r=.018,mat='Trim'):return c.beam(n,a,b,r,m[mat],12)
def profile(n,xz,w,role,edge=.025):
    verts=[(x,y,z) for y in [-w/2,w/2] for x,z in xz];count=len(xz)
    fs=[tuple(range(count-1,-1,-1)),tuple(range(count,2*count))]+[(i,(i+1)%count,(i+1)%count+count,i+count) for i in range(count)]
    o=c.mesh(n,verts,fs,m[role]);c.bevel(o,edge,2);return o
def panel(n,verts,role):
    o=c.mesh(n,verts,[tuple(range(len(verts)))],m[role]);m1=o.modifiers.new('Physical panel','SOLIDIFY');m1.thickness=.008
    return o
def wheel(x,y):
    z=.44;s=1 if y>0 else -1
    c.cylinder('Road tire',(x,y,z),.44,.26,m['Rubber'],32,'Y')
    for r,w,dy,role in [(.36,.02,.14,'Rubber'),(.255,.035,.16,'Trim'),(.16,.04,.185,'Rubber'),(.105,.055,.21,'Trim')]:
        c.cylinder('Wheel hub',(x,y+s*dy,z),r,w,m[role],24,'Y')
    for i in range(8):
        a=i*math.tau/8;c.cylinder('Wheel lug',(x+.195*math.cos(a),y+s*.19,z+.195*math.sin(a)),.017,.025,m['Trim'],8,'Y')
    for i in range(24):
        a=i*math.tau/24;o=box('Tire tread',(x+.439*math.cos(a),y,z+.439*math.sin(a)),(.04,.23,.015),'Rubber',.002);o.rotation_euler[1]=math.pi/2-a
def arch(x,y):
    n=18;vs=[(x+r*math.cos(i*math.pi/n),yy,.44+r*math.sin(i*math.pi/n)) for yy in [y-.17,y+.17] for r in [.49,.55] for i in range(n+1)]
    d=n+1;fs=[]
    for i in range(n):
        for a,b in [(0,d),(2*d,3*d),(0,2*d),(d,3*d)]:fs.append((a+i,a+i+1,b+i+1,b+i))
    c.mesh('Wheel arch',vs,fs,m['Trim'])

# Open rear, real cargo floor, panel skins and roof on the vehicle only.
box('Cargo floor',(6.0,0,1.06),(12.0,2.45,.14),'Trim')
box('Cargo roof',(6.0,0,3.69),(12.0,2.45,.09))
box('Cargo front bulkhead',(11.96,0,2.375),(.08,2.45,2.57))
for sy in [-1,1]:
    y=sy*1.205
    box('Cargo side skin',(6,y,2.375),(12,.04,2.57))
    for i in range(59):box('Side pressed rib',(.15+i*(11.7/58),sy*1.233,2.4),(.024,.018,2.45),'Body',.003)
    box('Upper bright rail',(6,sy*1.245,3.70),(12.02,.03,.065),'Trim')
    box('Side blue belt',(6,sy*1.252,1.43),(11.9,.018,.22),'Accent')
    box('Lower rub rail',(6,sy*1.258,1.16),(11.97,.035,.065),'Trim')
    for x in [.4,2.2,4,5.8,7.6,9.4,11.5]:box('Side marker',(x,sy*1.28,1.2),(.10,.015,.04),'Headlight',.002)
    box('Chassis rail',(7.05,sy*.70,.82),(13.9,.15,.23),'Rubber')
    box('Underrun rail',(7.30,sy*1.15,.57),(8.2,.08,.13),'Trim')
    for x in [3.35,6.0,8.65,11.15]:box('Underrun bracket',(x,sy*1.10,.76),(.07,.08,.34),'Rubber')
    box('Rear corner post',(.035,sy*1.205,2.385),(.08,.08,2.62),'Trim')
    # Rear shutters are folded along the side, leaving the truck waiting open.
    box('Folded rear cargo door',(.63,sy*1.29,2.38),(1.16,.055,2.47),'Body')
    for xx in [.08,.32,.91,1.13]:box('Rear door hinge',(xx,sy*1.33,2.38),(.025,.025,2.25),'Trim',.003)
    for z in [1.5,2.3,3.2]:box('Cargo hinge',(.05,sy*1.33,z),(.10,.045,.06),'Trim')
    box('Rear lamp',(-.08,sy*.8,.91),(.04,.26,.12),'TailLight')
box('Rear upper frame',(0,0,3.66),(.10,2.5,.08),'Trim')
box('Rear bumper',(-.10,0,.52),(.16,2.36,.13),'Trim')
box('Rear license',(-.19,0,.55),(.015,.4,.1),'Accent',.002)
for x in [1.12,2.22,13.48]:
    c.cylinder('Axle',(x,0,.44),.065,2.18,m['Rubber'],16,'Y')
    for sy in [-1,1]:wheel(x,sy*1.04);arch(x,sy*1.07)
# Capture cabin parts, then translate their complete geometry by 6 m.
# Wheels/axles were already generated at their final positions above.
pre_cabin_names = {o.name for o in c.ACTIVE.objects}
# Cab-over engine profile with raked glazing and a distinct driving cabin.
profile('Sculpted cab',[(6.23,.76),(8.55,.76),(8.55,1.98),(8.35,2.98),(7.92,3.28),(6.42,3.28),(6.23,3.10)],2.32,'Body',.07)
panel('Windscreen',[(8.557,-1.01,2.05),(8.557,1.01,2.05),(8.375,1.01,2.89),(8.375,-1.01,2.89)],'Glass')
box('Windscreen center',(8.46,0,2.49),(.025,.028,.85),'Trim')
for sy in [-1,1]:
    panel('Side glazing',[(6.78,sy*1.169,2.05),(8.43,sy*1.169,2.05),(8.26,sy*1.169,2.90),(6.78,sy*1.169,2.90)],'Glass')
    box('Cab door seam',(6.69,sy*1.169,1.70),(.012,.012,1.85),'Trim',.001)
    box('Cab door handle',(6.90,sy*1.19,1.85),(.20,.03,.045),'Rubber')
    box('Cab blue belt',(7.15,sy*1.174,1.54),(1.65,.025,.20),'Accent')
    for z in [.50,.68]:box('Cab step',(6.55,sy*1.18,z),(.55,.26,.065),'Trim')
    beam('Mirror stay',(8.16,sy*1.15,2.35),(8.23,sy*1.43,2.48),.025,'Rubber')
    box('Mirror housing',(8.22,sy*1.44,2.61),(.16,.12,.39),'Trim',.025)
    box('Mirror surface',(8.13,sy*1.44,2.61),(.008,.10,.33),'Glass',.002)
    box('Headlamp',(8.59,sy*.82,1.26),(.055,.43,.18),'Headlight',.025)
    beam('Windshield wiper',(8.57,sy*.30,2.09),(8.50,sy*.70,2.35),.012,'Rubber')
box('Front grille',(8.60,0,1.68),(.04,1.65,.38),'Rubber',.015)
for z in [1.55,1.65,1.75]:box('Grille slat',(8.63,0,z),(.02,1.57,.022),'Trim',.003)
box('Front bumper',(8.58,0,.92),(.22,2.37,.21),'Accent',.04)
box('Front license',(8.70,0,.97),(.012,.43,.11),'Trim',.002)
box('Cab roof lip',(7.31,0,3.27),(1.65,2.23,.09),'Body',.03)
for part in c.ACTIVE.objects:
    if part.name not in pre_cabin_names:
        part.location.x += 6.0

# Compare evaluated geometry to the original editable library before export.
# This checks the shapes, rather than merely asserting the new parameter values.
new_parts = {o.name: o for o in c.ACTIVE.objects}
source_blend = ROOT/'SourceAssets/GHS/RefinementV2/Trucks/dock_truck_v2.blend'
with bpy.data.libraries.load(str(source_blend), link=False) as (source, loaded):
    original_names = tuple(source.objects)
    loaded.objects = list(original_names)
original_parts = dict(zip(original_names, loaded.objects))
reference = bpy.data.collections.new('OriginalTruckGeometryCheck')
bpy.context.scene.collection.children.link(reference)
for obj in original_parts.values(): reference.objects.link(obj)
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()

def vertices_world(obj, dx=0):
    evaluated = obj.evaluated_get(deps)
    mesh = evaluated.to_mesh()
    points = []
    for vertex in mesh.vertices:
        p = obj.matrix_world @ vertex.co
        points.append((p.x + dx, p.y, p.z))
    evaluated.to_mesh_clear()
    return points

def compare_shape(name, dx):
    old = vertices_world(original_parts[name], dx)
    new = vertices_world(new_parts[name])
    assert len(old) == len(new), (name, len(old), len(new))
    error = max((Vector(a)-Vector(b)).length for a,b in zip(old,new))
    assert error < 0.00001, (name, error)
    return dict(name=name, translation_m=[dx,0,0], maximum_vertex_error_m=error,
                vertices=len(old))

cabin_checks = [compare_shape(name,6.0) for name in new_parts if name not in pre_cabin_names]
wheel_checks = []
wheel_prefixes = ('Road tire', 'Wheel hub', 'Wheel lug', 'Tire tread', 'Wheel arch', 'Axle')
rear_prefixes = ('Rear corner post', 'Folded rear cargo door', 'Rear door hinge',
                 'Cargo hinge', 'Rear lamp', 'Rear upper frame', 'Rear bumper', 'Rear license')
rear_checks = []
for name,obj in original_parts.items():
    if name.startswith(wheel_prefixes):
        points = vertices_world(obj)
        x = (min(p[0] for p in points) + max(p[0] for p in points)) / 2
        wheel_checks.append(compare_shape(name,6.0 if x>6 else 0.0))
    if name.startswith(rear_prefixes): rear_checks.append(compare_shape(name,0.0))
dimension_checks = {}
for name in ('Cargo floor','Cargo roof','Cargo side skin','Cargo side skin.001'):
    old,new=vertices_world(original_parts[name]),vertices_world(new_parts[name])
    old_size=[max(p[a] for p in old)-min(p[a] for p in old) for a in range(3)]
    new_size=[max(p[a] for p in new)-min(p[a] for p in new) for a in range(3)]
    assert abs(new_size[0]-2*old_size[0])<.00001
    assert all(abs(old_size[a]-new_size[a])<.00001 for a in (1,2))
    dimension_checks[name]=dict(before_m=old_size,after_m=new_size)
verification = dict(success=True, source_blend=str(source_blend),
    cabin_geometry_checks=cabin_checks, wheel_axle_geometry_checks=wheel_checks,
    unchanged_rear_geometry_checks=rear_checks, doubled_cargo_dimensions=dimension_checks,
    source_part_count=len(original_parts), long_part_count=len(new_parts))
assert len(cabin_checks)>20 and len(wheel_checks)>200 and len(rear_checks)>20
for obj in original_parts.values(): bpy.data.objects.remove(obj,do_unlink=True)
bpy.data.collections.remove(reference)
(c.OUT/'geometry_verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
c.save_library('dock_truck_long')
p=c.OUT/'dock_truck_long.json';d=json.loads(p.read_text())
for rec in d['meshes']:
    rec['fbx_sha256']=hashlib.sha256(Path(rec['fbx']).read_bytes()).hexdigest()
    rec.update(slot_roles=[s.rsplit('_',1)[-1] for s in rec['slots']],rear_origin_m=[0,0,0],forward_axis='+X',
        estimated_dimensions=True,physical_body_width_m=2.58,mirror_width_m=3.0,origin_m=[0,0,0])
d['design']='Long box truck: cargo body 12 m, cab and wheel proportions unchanged, original rear docking origin; unmeasured visual design'
d['cargo_length_m']=12.0
d['original_cargo_length_m']=6.0
d['cab_translation_m']=[6.0,0,0]
d['axle_positions_m']=[1.12,2.22,13.48]
d['tire_radius_m']=.44
p.write_text(json.dumps(d,indent=2),encoding='utf-8')
# Actual Blender preview, preserving the exported editable library.
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=24
scene.world.color=(.25,.25,.25)
bpy.ops.object.camera_add(location=(21,-18,11));camera=bpy.context.object
camera.rotation_euler=(Vector((7.1,0,1.8))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=50;scene.camera=camera
bpy.ops.object.light_add(type='AREA',location=(7,-4,10));bpy.context.object.data.energy=3000;bpy.context.object.data.shape='DISK';bpy.context.object.data.size=6
scene.render.resolution_x=1280;scene.render.resolution_y=720;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(c.OUT/'dock_truck_long_preview.png')
bpy.ops.render.render(write_still=True)
