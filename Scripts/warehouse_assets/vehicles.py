"""Real-scale logistics vehicles; front is Blender +X, bases at ground Z=0."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *
from math import pi, sin, cos

reset()
white = material('Vehicle_EnamelWhite', (.82,.85,.86), .29, .28, texture_role='metal')
silver = material('Vehicle_BrushedAluminium', (.42,.46,.49), .27, .85, texture_role='metal')
black = material('Vehicle_Chassis', (.035,.043,.048), .5, .65, texture_role='metal')
rubber = material('Vehicle_TireRubber', (.018,.021,.023), .86)
tread = material('Vehicle_TreadEdges', (.027,.03,.032), .89)
glass = material('Vehicle_GlassBlue', (.035,.095,.13), .13, .28, glass=True)
red = material('Vehicle_RedLens', (.48,.012,.008), .24, .1, emission=.7)
amber = material('Vehicle_AmberLens', (.95,.31,.014), .23, .1, emission=.6)
lamp = material('Vehicle_Headlight', (.77,.89,1), .15, .3, emission=1.5)
yellow = material('Vehicle_ForkliftAmber', (.9,.43,.024), .34, .35, texture_role='metal')
wood = material('Vehicle_PalletTimber', (.37,.24,.125), .85, texture_role='wood')
wood2 = material('Vehicle_PalletLightTimber', (.5,.34,.19), .85, texture_role='wood')
cartons = [material('Vehicle_Carton'+str(i), c, .88) for i,c in enumerate([(.48,.31,.15),(.59,.40,.22),(.67,.49,.29),(.52,.35,.19)])]
tape = material('Vehicle_PackingTape', (.67,.53,.34), .38)

def profile(name, xz, width, mat, bevel=.04):
    verts=[(x,y,z) for y in [-width/2,width/2] for x,z in xz]
    n=len(xz)
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    obj=mesh(name,verts,faces,mat)
    if bevel:
        mod=obj.modifiers.new('Soft manufactured edges','BEVEL'); mod.width=bevel;mod.segments=3
        obj.modifiers.new('Normals','WEIGHTED_NORMAL')
    return obj

def panel(name, verts, mat):
    obj=mesh(name,verts,[tuple(range(len(verts)))],mat)
    mod=obj.modifiers.new('Panel thickness','SOLIDIFY');mod.thickness=.008
    return obj

def grounded_export(name):
    bpy.context.view_layer.update()
    objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
    floor=min((obj.matrix_world @ Vector(corner)).z for obj in objects for corner in obj.bound_box)
    for obj in objects:obj.location.z-=floor
    return export_asset(name,objects)

def wheel(x,y,z,r,w,tag='Wheel',detail=True):
    cylinder(tag+' tire',(x,y,z),r,w,rubber,32,(pi/2,0,0))
    # Sidewall bead and depressed wheel barrel are visible from the exterior.
    sign=1 if y>0 else -1
    out=y+sign*(w/2+.006)
    cylinder(tag+' sidewall',(x,out,z),r*.91,.016,tread,32,(pi/2,0,0))
    cylinder(tag+' rim',(x,out+sign*.012,z),r*.61,.035,silver,24,(pi/2,0,0))
    cylinder(tag+' hub',(x,out+sign*.036,z),r*.26,.06,black,24,(pi/2,0,0))
    cylinder(tag+' hub cap',(x,out+sign*.07,z),r*.18,.018,silver,24,(pi/2,0,0))
    if detail:
        for a in range(8):
            theta=a*pi/4
            cylinder(tag+' lug',(x+r*.38*cos(theta),out+sign*.045,z+r*.38*sin(theta)),r*.035,.025,silver,8,(pi/2,0,0))
        for i in range(32):
            theta=i*2*pi/32
            obj=box(tag+' tread block',(x+r*.996*cos(theta),y,z+r*.996*sin(theta)),(.045,w*.9,.025),tread,.003)
            obj.rotation_euler[1]=pi/2-theta

def axle(x,z,r,width=2.3,w=.28,tag='Axle'):
    cylinder(tag+' shaft',(x,0,z),.075,width,black,16,(pi/2,0,0))
    for sy in [-1,1]: wheel(x,sy*(width/2-w/2),z,r,w,tag)

def arch(x,y,z,r,width,mat):
    n=16; verts=[]
    for sy in [-1,1]:
        for rr in [r,r+.09]:
            verts += [(x+rr*cos(i*pi/n),y+sy*width/2,z+rr*sin(i*pi/n)) for i in range(n+1)]
    stride=n+1;faces=[]
    for i in range(n):
        for a,b in [(0,stride),(2*stride,3*stride),(0,2*stride),(stride,3*stride)]:
            faces.append((a+i,a+i+1,b+i+1,b+i))
    mesh('Wheel arch',verts,faces,mat)

def semi_truck():
    # 13.4 m European box trailer, cab-over tractor and five-wheel connection.
    box('Trailer box',(-1.6,0,2.69),(13.4,2.55,2.82),white,.035)
    box('Trailer lower rail',(-1.6,0,1.3),(13.4,2.59,.16),silver,.015)
    for y in [-1.28,1.28]:box('Trailer roof side rail',(-1.6,y,4.065),(13.42,.035,.07),silver,.007)
    for x in [-8.3,5.1]:box('Trailer roof end rail',(x,0,4.065),(.035,2.55,.07),silver,.007)
    for sy in [-1,1]:
        for i in range(76):
            box('Trailer pressed vertical rib',(-8.2+i*.175,sy*1.286,2.71),(.035,.027,2.64),white,.006)
        box('Trailer rub rail',(-1.6,sy*1.3,1.46),(13.35,.035,.065),silver,.005)
        for x in [-7.8,-5.6,-3.3,-1.0,1.3,3.6,4.8]:
            box('Trailer amber side marker',(x,sy*1.313,1.48),(.15,.023,.065),amber,.008)
        for x in [-7.8,-6.8,-5.8,-4.8,-3.8,-2.8,-1.8,-.8,.2,1.2,2.2,3.2,4.2]:
            box('Trailer reflective tape',(x,sy*1.315,1.35),(.42,.012,.035),red,.002)
        box('Trailer side underrun beam',(-.4,sy*1.13,.69),(5.0,.09,.14),silver,.015)
        for x in [-2.4,1.6]: box('Side underrun bracket',(x,sy*1.08,.9),(.08,.08,.49),black,.005)
    for y in [-.76,.76]:box('Trailer chassis',(-1.6,y,1.13),(13.1,.15,.26),black,.015)
    for x in [-6.6,-5.35,-4.1]:
        axle(x,.51,.51,2.48,.32,'Trailer axle')
        for y in [-1.09,1.09]:arch(x,y,.51,.55,.37,black)
    for y in [-.9,.9]:
        cylinder('Landing gear',(2.2,y,.72),.065,.95,black,16)
        box('Landing foot',(2.2,y,.25),(.3,.29,.06),black,.01)
    box('Rear underrun bumper',(-8.45,0,.55),(.15,2.38,.15),silver,.02)
    for y in [-.95,.95]:box('Rear bumper upright',(-8.34,y,.85),(.12,.1,.64),black,.01)
    for y in [-.64,.64]:
        box('Trailer rear door',(-8.321,y,2.72),(.038,1.23,2.6),white,.007)
        for yy in [y-.5,y+.5]:
            cylinder('Rear door lock bar',(-8.36,yy,2.73),.02,2.32,silver,12)
            box('Rear door latch',(-8.39,yy,2.12),(.045,.14,.035),silver,.003)
        for z in [1.65,2.5,3.45]:box('Door hinge',(-8.365,y+(.59 if y>0 else -.59),z),(.06,.11,.09),silver,.005)
        box('Trailer tail light',(-8.41,y,.96),(.045,.36,.12),red,.016)
    # Tractor frame, powertrain and fuel equipment.
    for y in [-.62,.62]:box('Tractor frame',(4.78,y,.84),(6.63,.18,.24),black,.025)
    box('Fifth wheel plate',(3.9,0,1.12),(1.3,1.32,.12),black,.05)
    for x in [2.2,3.4]:axle(x,.51,.51,2.48,.33,'Tractor rear axle')
    axle(7.15,.51,.51,2.41,.32,'Steering axle')
    for sy in [-1,1]:
        box('Tractor rear fender',(2.8,sy*1.06,1.12),(2.36,.45,.11),black,.03)
        tank=cylinder('Aluminium fuel tank',(4.72,sy*.91,.72),.35,1.12,silver,32,(0,pi/2,0))
        for x in [4.36,5.08]:box('Fuel tank strap',(x,sy*.91,.74),(.065,.69,.59),black,.015)
    profile('Cab sculpted shell',[(5.43,1.02),(8.14,1.02),(8.14,2.18),(7.9,3.36),(7.4,3.69),(5.66,3.69),(5.43,3.4)],2.42,white,.09)
    # Front windshield follows the raked front surface, with center mullion.
    panel('Cab windshield',[(8.133,-1.055,2.31),(8.133,1.055,2.31),(7.944,1.055,3.23),(7.944,-1.055,3.23)],glass)
    beam('Windshield center bar',(8.14,0,2.31),(7.95,0,3.23),.018,black)
    for sy in [-1,1]:
        y=sy*1.217
        panel('Driver side window',[(6.43,y,2.31),(8.01,y,2.31),(7.82,y,3.22),(6.43,y,3.22)],glass)
        box('Cab side door seam',(6.35,y,2.03),(.018,.015,2.12),black,.002)
        box('Cab handle',(6.56,sy*1.235,2.14),(.22,.045,.06),black,.01)
        for z in [.63,.86]:box('Cab entry tread',(6.25,sy*1.22,z),(.72,.34,.075),silver,.015)
        arch(7.15,sy*1.09,.51,.56,.37,white)
        beam('Mirror mounting lower',(7.8,sy*1.19,2.3),(7.97,sy*1.53,2.58),.025,black)
        beam('Mirror mounting upper',(7.75,sy*1.19,3.15),(7.97,sy*1.53,2.98),.025,black)
        box('Exterior mirror',(7.98,sy*1.55,2.83),(.2,.14,.53),black,.045)
        box('Mirror glass',(7.867,sy*1.55,2.83),(.01,.115,.44),silver,.015)
        box('Tractor front lamp',(8.19,sy*.88,1.37),(.06,.49,.23),lamp,.035)
        box('Tractor indicator',(8.192,sy*1.12,1.38),(.065,.085,.19),amber,.015)
    box('Front grille',(8.199,0,1.9),(.035,1.68,.52),black,.025)
    for z in [1.69,1.81,1.93,2.05]:box('Grille bright slat',(8.222,0,z),(.025,1.61,.026),silver,.005)
    box('Tractor bumper',(8.2,0,1.05),(.22,2.47,.22),white,.055)
    box('License bracket',(8.321,0,1.08),(.012,.43,.12),black,.005)
    for y in [-.58,.58]:beam('Windshield wiper',(8.145,y,2.34),(8.07,y+.3,2.64),.013,black)
    box('Roof air deflector',(5.94,0,3.8),(1.1,2.15,.28),white,.12)
    return grounded_export('SM_SemiTruck')

def delivery_van():
    profile('Van body sculpt', [(-2.9,.56),(2.9,.56),(2.9,1.14),(2.6,1.41),(1.91,1.48),(1.04,2.55),(.69,2.72),(-2.65,2.72),(-2.9,2.48)],2.03,white,.11)
    for x in [-1.93,1.87]:
        axle(x,.36,.36,2.08,.22,'Van wheel')
        for sy in [-1,1]:arch(x,sy*.95,.36,.395,.22,black)
    box('Van front bumper',(2.9,0,.69),(.17,2.03,.24),black,.055)
    box('Van rear bumper',(-2.94,0,.67),(.12,2.05,.17),black,.04)
    panel('Van windshield',[(1.91,-.86,1.53),(1.91,.86,1.53),(1.12,.86,2.47),(1.12,-.86,2.47)],glass)
    for sy in [-1,1]:
        panel('Van cab side glass',[(.15,sy*1.025,1.49),(1.83,sy*1.025,1.49),(.99,sy*1.025,2.46),(.15,sy*1.025,2.46)],glass)
        box('Van cab door seam',(.035,sy*1.027,1.5),(.018,.012,1.82),black,.002)
        box('Van door handle',(.3,sy*1.049,1.35),(.19,.035,.055),black,.01)
        box('Cargo sliding door seam',(-2.14,sy*1.029,1.66),(.016,.014,1.85),silver,.001)
        box('Cargo sliding rail',(-1.18,sy*1.04,1.35),(1.75,.025,.035),silver,.003)
        box('Cargo panel rub strip',(-1.05,sy*1.042,.87),(3.4,.045,.09),black,.015)
        beam('Van mirror arm',(1.12,sy*1.01,1.72),(1.25,sy*1.19,1.82),.025,black)
        box('Van mirror',(1.24,sy*1.22,1.84),(.2,.14,.28),black,.045)
        box('Van headlight',(2.83,sy*.74,1.18),(.11,.41,.22),lamp,.04)
        box('Van rear light',(-2.924,sy*.85,1.55),(.036,.17,.58),red,.03)
        box('Van rear door',(-2.925,sy*.48,1.72),(.026,.93,1.77),white,.02)
        box('Rear handle',(-2.95,sy*.1,1.32),(.032,.055,.18),black,.006)
    box('Van radiator grille',(2.956,0,.99),(.04,1.04,.26),black,.04)
    for y in [-.3,.3]:beam('Van wiper',(1.91,y,1.55),(1.72,y+.28,1.8),.01,black)
    box('Rear license plate',(-2.96,0,.99),(.015,.4,.12),black,.005)
    return grounded_export('SM_DeliveryVan')

def forklift():
    profile('Forklift counterweight',[(-1.4,.28),(-1.4,.98),(-1.18,1.36),(-.42,1.36),(-.2,.61),(1.05,.61),(1.05,.28)],1.14,yellow,.1)
    box('Forklift underframe',(-.1,0,.33),(2.4,1.05,.19),black,.04)
    axle(.71,.32,.32,1.33,.26,'Forklift front')
    axle(-.98,.25,.25,1.12,.23,'Forklift rear')
    box('Operator deck',(-.02,0,.63),(1.3,.99,.12),black,.025)
    box('Operator seat base',(-.54,0,1.01),(.54,.6,.18),rubber,.065)
    seat=box('Operator seat back',(-.78,0,1.34),(.15,.61,.66),rubber,.06);seat.rotation_euler[1]=-.12
    beam('Steering column',(.34,0,.78),(.14,0,1.36),.045,black)
    bpy.ops.mesh.primitive_torus_add(major_radius=.18,minor_radius=.022,major_segments=24,minor_segments=8,location=(.14,0,1.39),rotation=(0,.3,0))
    bpy.context.object.data.materials.append(black)
    for sy in [-1,1]:
        for x in [-.97,.57]:beam('Overhead guard upright',(x,sy*.5,.65),(x,sy*.5,2.24),.041,black)
        box('Overhead side rail',(-.2,sy*.52,2.24),(1.68,.075,.09),black,.018)
    for x in [-.96,-.58,-.2,.18,.56]:box('Overhead guard crossbar',(x,0,2.24),(.05,1.12,.075),black,.015)
    for y in [-.4,.4]:
        box('Forklift outer mast',(1.07,y,1.52),(.14,.12,2.96),black,.015)
        box('Forklift inner mast',(1.18,y*.76,1.56),(.08,.09,2.82),silver,.012)
        cylinder('Lift ram',(1.0,y*.7,1.3),.045,1.5,silver,16)
        beam('Lift chain',(1.06,y*.62,.41),(1.06,y*.62,2.93),.013,black)
    for z in [.41,1.45,2.94]:box('Mast crossbeam',(1.08,0,z),(.14,.89,.12),black,.015)
    box('Fork carriage',(1.22,0,.69),(.13,1.08,.83),black,.015)
    for sy in [-1,1]:
        box('Fork heel',(1.34,sy*.34,.53),(.075,.13,.66),silver,.008)
        profile('Tapered lifting fork',[(1.31,.19),(2.43,.19),(2.48,.23),(1.38,.28),(1.31,.28)],.13,silver,.004).location.y=sy*.34
    for y in [-.28,0,.28]:box('Load backrest bar',(1.245,y,1.11),(.05,.025,.72),black,.005)
    for y in [-.56,.56]:box('Forklift front light',(.62,y,1.9),(.14,.12,.13),lamp,.015)
    cylinder('Warning beacon',(-.71,.25,2.38),.075,.18,amber,24)
    for i in range(2):beam('Hydraulic lever',(.29,.3+i*.1,.79),(.19,.3+i*.1,1.16),.018,black)
    return grounded_export('SM_Forklift')

def pallet(z=0):
    for x in [-.48,0,.48]:
        for y in [-.36,0,.36]:box('Pallet block',(x,y,z+.074),(.16,.16,.12),wood,.006)
    for y in [-.4,0,.4]:box('Pallet bottom plank',(0,y,z+.02),(1.2,.17,.04),wood,.006)
    for x in [-.49,0,.49]:box('Pallet stringer',(x,0,z+.13),(.16,1,.04),wood,.004)
    for i in range(5):box('Pallet deck plank',(-.5+i*.25,0,z+.168),(.2,1,.038),wood2 if i%2 else wood,.004)

def loaded_pallet():
    pallet()
    for layer in range(3):
        for ix in range(3):
            for iy in range(2):
                x=-.395+ix*.395;y=-.242+iy*.484;z=.19+layer*.395
                box('Shipping carton',(x,y,z+.192),(.377,.465,.384),cartons[(layer+ix+iy)%4],.01)
                box('Carton tape strip',(x,y,z+.386),(.048,.464,.003),tape,.001)
                box('Carton tape end',(x,y-.234,z+.3),(.048,.003,.165),tape,.001)
    return grounded_export('SM_LoadedPallet')

assets=[semi_truck(),delivery_van(),forklift(),loaded_pallet()]
for i in range(7):pallet(i*.19)
assets.append(grounded_export('SM_PalletStack'))
for asset in assets:
    asset['front_axis']='+X';asset['ground_z_m']=0
save_manifest('vehicles.json',assets)
print('VEHICLE_BOUNDS',[(a['name'],a['bounds_m'],a['polygons']) for a in assets])
