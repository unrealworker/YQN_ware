"""A metre-scale rigid box truck, rear origin and nose +X, for every GHS dock."""
import sys,json,math,hashlib
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/video_reference'))
import common as c
c.OUT=ROOT/'SourceAssets/GHS/RefinementV2/Trucks';c.OUT.mkdir(parents=True,exist_ok=True)
c.reset()
colors={'Body':(.60,.65,.70),'Trim':(.30,.39,.49),'Accent':(.02,.09,.34),
        'Glass':(.025,.065,.09),'Rubber':(.018,.023,.03),'Headlight':(.66,.87,.96),'TailLight':(.5,.035,.018)}
m={k:c.material('GHSV2Truck_'+k,v,.48 if k!='Rubber' else .84,.25 if k in {'Body','Trim'} else .03) for k,v in colors.items()}
c.begin_asset('SM_GHS_V2DockTruck')
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
box('Cargo floor',(3.0,0,1.06),(6.0,2.45,.14),'Trim')
box('Cargo roof',(3.0,0,3.69),(6.0,2.45,.09))
box('Cargo front bulkhead',(5.96,0,2.375),(.08,2.45,2.57))
for sy in [-1,1]:
    y=sy*1.205
    box('Cargo side skin',(3,y,2.375),(6,.04,2.57))
    for i in range(29):box('Side pressed rib',(.15+i*.201,sy*1.233,2.4),(.024,.018,2.45),'Body',.003)
    box('Upper bright rail',(3,sy*1.245,3.70),(6.02,.03,.065),'Trim')
    box('Side blue belt',(3,sy*1.252,1.43),(5.9,.018,.22),'Accent')
    box('Lower rub rail',(3,sy*1.258,1.16),(5.97,.035,.065),'Trim')
    for x in [.4,2.2,4,5.5]:box('Side marker',(x,sy*1.28,1.2),(.10,.015,.04),'Headlight',.002)
    box('Chassis rail',(4.05,sy*.70,.82),(7.9,.15,.23),'Rubber')
    box('Underrun rail',(4.30,sy*1.15,.57),(2.2,.08,.13),'Trim')
    for x in [3.35,5.15]:box('Underrun bracket',(x,sy*1.10,.76),(.07,.08,.34),'Rubber')
    box('Rear corner post',(.035,sy*1.205,2.385),(.08,.08,2.62),'Trim')
    # Rear shutters are folded along the side, leaving the truck waiting open.
    box('Folded rear cargo door',(.63,sy*1.29,2.38),(1.16,.055,2.47),'Body')
    for xx in [.08,.32,.91,1.13]:box('Rear door hinge',(xx,sy*1.33,2.38),(.025,.025,2.25),'Trim',.003)
    for z in [1.5,2.3,3.2]:box('Cargo hinge',(.05,sy*1.33,z),(.10,.045,.06),'Trim')
    box('Rear lamp',(-.08,sy*.8,.91),(.04,.26,.12),'TailLight')
box('Rear upper frame',(0,0,3.66),(.10,2.5,.08),'Trim')
box('Rear bumper',(-.10,0,.52),(.16,2.36,.13),'Trim')
box('Rear license',(-.19,0,.55),(.015,.4,.1),'Accent',.002)
for x in [1.12,2.22,7.48]:
    c.cylinder('Axle',(x,0,.44),.065,2.18,m['Rubber'],16,'Y')
    for sy in [-1,1]:wheel(x,sy*1.04);arch(x,sy*1.07)
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
c.save_library('dock_truck_v2')
p=c.OUT/'dock_truck_v2.json';d=json.loads(p.read_text())
for rec in d['meshes']:
    rec['fbx_sha256']=hashlib.sha256(Path(rec['fbx']).read_bytes()).hexdigest()
    rec.update(slot_roles=[s.rsplit('_',1)[-1] for s in rec['slots']],rear_origin_m=[0,0,0],forward_axis='+X',
        estimated_dimensions=True,physical_body_width_m=2.58,mirror_width_m=3.0,origin_m=[0,0,0])
d['design']='Medium rigid box truck, three axles, open rear doors folded against sides; unmeasured visual dimensions'
p.write_text(json.dumps(d,indent=2),encoding='utf-8')
# Actual Blender preview, preserving the exported editable library.
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=24
scene.world.color=(.25,.25,.25)
bpy.ops.object.camera_add(location=(13,-10,7));camera=bpy.context.object
camera.rotation_euler=(Vector((4,0,1.6))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=50;scene.camera=camera
bpy.ops.object.light_add(type='AREA',location=(3,-4,8));bpy.context.object.data.energy=1800;bpy.context.object.data.shape='DISK';bpy.context.object.data.size=6
scene.render.resolution_x=1280;scene.render.resolution_y=720;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(c.OUT/'dock_truck_preview.png')
bpy.ops.render.render(write_still=True)
