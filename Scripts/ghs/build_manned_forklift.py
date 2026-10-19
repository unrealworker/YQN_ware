"""Reference-based seated electric forklift. Metres, X forward, separate editable parts."""
import bpy, math, json, sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(r'D:/UEPro/Test'); OUT=ROOT/'SourceAssets/GHS_Normal/MannedForklift'; OUT.mkdir(parents=True,exist_ok=True)
old_scene=bpy.context.scene
if not (ROOT/'Saved/Backups/GHS_MannedForklift_20261019/previous_blender.blend').exists():
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'Saved/Backups/GHS_MannedForklift_20261019/previous_blender.blend'),copy=True)
scene=bpy.data.scenes.new('GHS_MannedForklift_Studio'); bpy.context.window.scene=scene
scene.unit_settings.system='METRIC'; scene.unit_settings.scale_length=1
asset=bpy.data.collections.new('MannedForklift_Editable');scene.collection.children.link(asset)
cols={}
for n in ['01_Body','02_Wheels','03_Mast_Forks','04_Cockpit','05_Driver','06_Details','Studio']:
    co=bpy.data.collections.new(n); (scene.collection if n=='Studio' else asset).children.link(co);cols[n]=co
active=cols['01_Body']; mats={}; manifest=[]
colors={
 'Body':((.57,.62,.68),.42,.12),'Blue':((.012,.045,.35),.38,.12),
 'Frame':((.045,.065,.086),.45,.48),'Metal':((.29,.36,.43),.33,.72),
 'Rubber':((.013,.018,.024),.84,.0),'Dark':((.024,.034,.046),.65,.05),
 'Seat':((.035,.046,.057),.85,0),'Glass':((.025,.085,.12),.22,.27),
 'Safety':((.95,.24,.025),.68,0),'Helmet':((.95,.60,.025),.31,.02),
 'Reflective':((.73,.80,.77),.42,.15),'Skin':((.45,.245,.145),.72,0),
 'Cloth':((.12,.21,.31),.93,0),'Navy':((.025,.065,.14),.92,0),
 'White':((.79,.84,.87),.48,.02),'LED':((.34,.70,.85),.25,.05),
 'Red':((.55,.025,.015),.32,.03),'Amber':((.95,.30,.018),.24,.04)}
for key,(color,rough,metal) in colors.items():
    m=bpy.data.materials.new('M_MF_'+key);m.use_nodes=True
    node=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    node.inputs['Base Color'].default_value=(*color,1);node.inputs['Roughness'].default_value=rough;node.inputs['Metallic'].default_value=metal
    m.diffuse_color=(*color,1);mats[key]=m
    entry=dict(name=m.name,base_color=[*color,1],roughness=rough,metallic=metal)
    if key in {'LED','Amber','Red'}:
        node.inputs['Emission Color'].default_value=(*color,1);node.inputs['Emission Strength'].default_value=.35;entry['emission']=.35
    manifest.append(entry)

def mesh(n,vs,fs,role,edge=0,smooth=False):
    d=bpy.data.meshes.new(n);d.from_pydata(vs,[],fs);d.update();o=bpy.data.objects.new(n,d);active.objects.link(o);d.materials.append(mats[role])
    if smooth:
        for p in d.polygons:p.use_smooth=True
    if edge:
        mod=o.modifiers.new('Machined edge radius','BEVEL');mod.width=edge;mod.segments=3
        no=o.modifiers.new('Face normals','WEIGHTED_NORMAL');no.keep_sharp=True
    return o

def box(n,p,s,role='Body',edge=.008):
    x,y,z=s;vs=[(a*x/2,b*y/2,c*z/2) for a,b,c in [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),(1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)]]
    o=mesh(n,vs,[(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)],role,min(edge,min(s)*.22));o.location=p;return o

def profile(n,xz,width,role,edge=.014):
    vs=[(x,y,z) for y in [-width/2,width/2] for x,z in xz];N=len(xz)
    fs=[tuple(range(N-1,-1,-1)),tuple(range(N,2*N))]+[(i,(i+1)%N,(i+1)%N+N,i+N) for i in range(N)]
    return mesh(n,vs,fs,role,edge)

def cylinder(n,p,r,depth,role='Metal',axis=(0,0,1),segments=32):
    vs=[(r*math.cos(i*math.tau/segments),r*math.sin(i*math.tau/segments),z) for z in [-depth/2,depth/2] for i in range(segments)]
    fs=[tuple(range(segments-1,-1,-1)),tuple(range(segments,2*segments))]+[(i,(i+1)%segments,(i+1)%segments+segments,i+segments) for i in range(segments)]
    o=mesh(n,vs,fs,role);o.location=p;o.rotation_euler=Vector(axis).to_track_quat('Z','Y').to_euler()
    for f in o.data.polygons:f.use_smooth=len(f.vertices)==4
    return o

def rod(n,a,b,r=.018,role='Frame',segments=12):
    a,b=Vector(a),Vector(b);return cylinder(n,(a+b)/2,r,(b-a).length,role,b-a,segments)

def tube(n,points,r=.012,role='Frame',closed=False):
    # Parallel frame tube with circular cross-sections, suitable for cables and bent guards.
    pts=[Vector(p) for p in points];N=10;vs=[]
    for i,p in enumerate(pts):
        tangent=(pts[min(i+1,len(pts)-1)]-pts[max(0,i-1)]).normalized();q=tangent.to_track_quat('Z','Y')
        vs += [p+q@Vector((r*math.cos(j*math.tau/N),r*math.sin(j*math.tau/N),0)) for j in range(N)]
    fs=[]
    for i in range(len(pts)-1):
        for j in range(N):fs.append((i*N+j,i*N+(j+1)%N,(i+1)*N+(j+1)%N,(i+1)*N+j))
    fs.extend([tuple(range(N-1,-1,-1)),tuple((len(pts)-1)*N+j for j in range(N))]);return mesh(n,vs,fs,role,smooth=True)

def ring(n,center,r,minor,normal=(0,0,1),role='Metal',segments=48):
    C=Vector(center);Q=Vector(normal).to_track_quat('Z','Y');vs=[];K=10
    for i in range(segments):
        a=math.tau*i/segments
        for j in range(K):
            b=math.tau*j/K;vs.append(C+Q@Vector(((r+minor*math.cos(b))*math.cos(a),(r+minor*math.cos(b))*math.sin(a),minor*math.sin(b))))
    fs=[(i*K+j,i*K+(j+1)%K,((i+1)%segments)*K+(j+1)%K,((i+1)%segments)*K+j) for i in range(segments) for j in range(K)]
    return mesh(n,vs,fs,role,smooth=True)

def label(n,txt,p,size,role='White',normal=(0,-1,0),up=(0,0,1)):
    d=bpy.data.curves.new(n,'FONT');d.body=txt;d.size=size;d.align_x='CENTER';d.extrude=.00035;d.resolution_u=3
    o=bpy.data.objects.new(n,d);active.objects.link(o);d.materials.append(mats[role]);o.location=p
    o.rotation_euler=Vector(normal).to_track_quat('Z','Y').to_euler();return o

# Low chassis, sculpted rear battery enclosure and blue belt match the warehouse vehicles.
profile('MF_Chassis', [(-1.10,.20),(.77,.20),(.80,.48),(.43,.62),(-.86,.62),(-1.16,.48)],.87,'Frame',.028)
profile('MF_RearCounterweight',[(-1.16,.40),(-.61,.40),(-.59,.89),(-.68,1.06),(-1.04,1.06),(-1.16,.91)],1.04,'Body',.055)
box('MF_RearBlueBand',(-1.171,0,.69),(.018,.92,.22),'Blue',.006)
box('MF_BatteryHood',(-.78,0,1.055),(.62,.98,.055),'Blue',.022)
box('MF_SeatPedestal',(-.48,0,.79),(.58,.63,.30),'Body',.032)
box('MF_RearLowerBumper',(-1.177,0,.38),(.075,.98,.10),'Rubber',.014)
for sy in [-1,1]:
    y=sy*.492
    box('MF_BatterySidePanel',(-.82,y,.78),(.53,.028,.40),'Body',.018)
    box('MF_BlueSideBelt',(-.82,y+sy*.018,.97),(.52,.022,.105),'Blue',.012)
    box('MF_SideLatch',(-.65,y+sy*.025,.80),(.045,.012,.10),'Frame',.003)
    label('MF_FleetMark','GHS  |  E18',(-.86,y+sy*.035,.71),.068,'Blue',(0,sy,0))
    for x in [-1.015,-.635]:
        for z in [.59,.91]:cylinder('MF_PanelFastener',(x,y+sy*.02,z),.010,.012,'Metal',(0,sy,0),8)
    # Front fender profiles do not enclose the open driving footwell.
    o=profile('MF_FrontFender',[(.19,.56),(.27,.70),(.75,.70),(.85,.52),(.80,.48),(.27,.48)],.19,'Body',.022);o.location.y=sy*.46
    box('MF_EntryStep',(-.01,sy*.46,.36),(.45,.26,.075),'Frame',.014)
    for i in range(6):box('MF_AntiSlipTread',(-.19+i*.07,sy*.48,.401),(.022,.21,.009),'Rubber',.002)
box('MF_Footwell',(.05,0,.48),(.82,.77,.07),'Dark',.015)
for x in [-.30,-.17,-.04,.09,.22,.35]:box('MF_FloorMatGroove',(x,0,.521),(.012,.60,.008),'Rubber',.002)

active=cols['02_Wheels']
for side in [-1,1]:
    for x,r,w,y,n in [(.53,.315,.205,.49,'Front'),(-.92,.215,.16,.42,'Rear')]:
        name='MF_'+n+('_L' if side>0 else '_R');cy=side*y
        cylinder(name+'_SolidTire',(x,cy,r),r,w,'Rubber',(0,1,0),48)
        ring(name+'_Sidewall',(x,cy+side*w*.48,r),r*.79,.032,(0,1,0),'Rubber')
        cylinder(name+'_Rim',(x,cy+side*(w*.5+.007),r),r*.57,.034,'Body',(0,1,0),32)
        cylinder(name+'_Hub',(x,cy+side*(w*.5+.028),r),r*.25,.055,'Metal',(0,1,0),24)
        ring(name+'_RimLip',(x,cy+side*(w*.5+.03),r),r*.53,.012,(0,1,0),'Metal')
        for i in range(6):
            a=i*math.tau/6;cylinder(name+'_Lug',(x+r*.38*math.cos(a),cy+side*(w*.5+.03),r+r*.38*math.sin(a)),.012,.018,'Frame',(0,1,0),6)
        for i in range(32):
            a=i*math.tau/32
            ob=box(name+'_Tread',(x+(r-.002)*math.cos(a),cy,r+(r-.002)*math.sin(a)),(.040,w*.94,.014),'Rubber',.003);ob.rotation_euler[1]=math.pi/2-a
        cylinder(name+'_Axle',(x,0,r),r*.14,2*y,'Frame',(0,1,0),16)

active=cols['04_Cockpit']
box('MF_SeatSuspension',(-.48,0,.961),(.40,.43,.055),'Frame')
box('MF_SeatCushion',(-.46,0,1.025),(.48,.47,.105),'Seat',.045)
back=box('MF_SeatBack',(-.725,0,1.285),(.105,.47,.48),'Seat',.043);back.rotation_euler[1]=-.10
for sy in [-1,1]:
    ob=box('MF_SeatBolster',(-.47,sy*.224,1.07),(.43,.07,.12),'Seat',.028);ob.rotation_euler[0]=sy*.15
    box('MF_BackBolster',(-.675,sy*.215,1.31),(.12,.08,.37),'Seat',.024)
    rod('MF_ArmrestSupport',(-.57,sy*.29,1.12),(-.57,sy*.29,1.27),.021)
    box('MF_Armrest',(-.45,sy*.29,1.29),(.34,.067,.058),'Seat',.025)
    box('MF_SeatBeltAnchor',(-.60,sy*.25,1.04),(.05,.04,.045),'Metal')
box('MF_SeatBeltLatch',(-.23,-.24,1.09),(.06,.045,.055),'Red')
# Open overhead cage with actual posts and longitudinal roof bars.
for sy in [-1,1]:
    rod('MF_RearGuardPost',(-.92,sy*.49,.88),(-.85,sy*.49,2.135),.035,'Frame',12)
    rod('MF_FrontGuardPost',(.39,sy*.49,.57),(.49,sy*.49,2.135),.035,'Frame',12)
    box('MF_RoofSideRail',(-.18,sy*.49,2.16),(1.43,.085,.095),'Frame',.020)
    rod('MF_EntryGrabHandle',(.35,sy*.53,1.04),(.38,sy*.53,1.36),.019,'Metal')
    # Small work lights at cage corners, not a solid roof obscuring the driver.
    box('MF_WorkLampHousing',(.51,sy*.45,2.05),(.09,.15,.095),'Frame',.018)
    box('MF_WorkLampLens',(.56,sy*.45,2.05),(.012,.118,.065),'LED',.008)
for x in [-.86,.50]:box('MF_RoofCrossmember',(x,0,2.16),(.085,1.04,.095),'Frame',.018)
for y in [-.32,-.16,0,.16,.32]:box('MF_OverheadSafetyBar',(-.18,y,2.175),(1.31,.035,.065),'Frame',.008)
box('MF_OverheadRearCover',(-.69,0,2.18),(.37,.94,.055),'Body',.020)
# Steering column, dashboard, readout and hand levers.
rod('MF_SteeringColumn',(.27,0,.56),(.10,0,1.25),.040,'Frame',20)
normal=Vector((-.55,0,.835)).normalized();center=Vector((.10,0,1.25))
ring('MF_SteeringWheel',center,.18,.018,normal,'Rubber')
cylinder('MF_SteeringHub',center,.049,.032,'Frame',normal,24)
q=normal.to_track_quat('Z','Y')
for i in range(3):
    v=q@Vector((.16*math.cos(i*math.tau/3),.16*math.sin(i*math.tau/3),0));rod('MF_SteeringSpoke',center,center+v,.012,'Metal')
box('MF_Console',(.36,.0,.94),(.17,.56,.16),'Frame',.028)
ob=box('MF_DigitalDisplay',(.272,-.12,1.00),(.012,.17,.083),'Glass',.005);ob.rotation_euler[1]=-.20
for y in [-.17,-.13,-.09]:box('MF_DisplayGlyph',(.263,y,1.00),(.004,.018,.033),'LED',.001)
for y in [.07,.13,.19]:
    rod('MF_HydraulicLever',(.29,y,.99),(.17,y,1.12),.010,'Metal')
    cylinder('MF_LeverGrip',(.17,y,1.12),.023,.05,'Rubber',(0,0,1),16)
for y in [-.15,.15]:
    ob=box('MF_FootPedal',(.28,y,.56),(.16,.095,.045),'Rubber',.009);ob.rotation_euler[1]=-.25

active=cols['03_Mast_Forks']
# Two C-channel mast rails, inner stages, rollers and hydraulic cylinders.
for sy in [-1,1]:
    y=sy*.35
    box('MF_OuterMastWeb',(.74,y,1.22),(.115,.055,1.85),'Frame',.008)
    for x in [.67,.82]:box('MF_OuterMastFlange',(x,y,1.22),(.045,.14,1.88),'Frame',.006)
    box('MF_InnerMastRail',(.85,sy*.265,1.16),(.078,.075,1.81),'Metal',.004)
    for z in [.49,1.13,1.91]:cylinder('MF_MastRoller',(.79,sy*.285,z),.056,.065,'Metal',(0,1,0),20)
    cylinder('MF_LiftRamBarrel',(.73,sy*.18,.71),.043,.78,'Frame',(0,0,1),20)
    cylinder('MF_LiftRamChrome',(.73,sy*.18,1.30),.025,.49,'Metal',(0,0,1),20)
    cylinder('MF_ChainPulley',(.79,sy*.18,1.58),.070,.045,'Metal',(0,1,0),24)
    for i in range(34):
        z=.42+i*.043
        box('MF_LiftChainLink',(.90,sy*.18,z),(.018,.026,.034),'Metal',.002)
        cylinder('MF_ChainPin',(.911,sy*.18,z),.007,.032,'Frame',(0,1,0),8)
    tube('MF_HydraulicHose',[(.46,sy*.30,.54),(.63,sy*.27,.42),(.70,sy*.19,.52),(.70,sy*.19,1.40),(.73,sy*.19,1.47),(.79,sy*.19,1.43),(.84,sy*.19,.67)],.010,'Rubber')
    rod('MF_TiltRam',(.28,sy*.32,.40),(.70,sy*.32,.65),.035,'Frame',16)
    rod('MF_TiltPiston',(.49,sy*.32,.52),(.76,sy*.32,.68),.022,'Metal',16)
for z in [.31,2.12]:box('MF_MastCrossmember',(.75,0,z),(.18,.86,.085),'Frame',.008)
for z in [.29,.63]:box('MF_CarriageCrossbar',(.96,0,z),(.12,.91,.10),'Frame',.010)
# Cargo backrest with open rectangular bars.
for y in [-.46,.46]:box('MF_LoadBackrestSide',(1.00,y,.81),(.055,.045,.90),'Frame',.006)
for z in [.38,1.25]:box('MF_LoadBackrestCross',(1.00,0,z),(.055,.96,.055),'Frame',.006)
for y in [-.34,-.22,-.11,0,.11,.22,.34]:box('MF_LoadBackrestGrille',(1.00,y,.82),(.035,.027,.81),'Frame',.003)
for y in [-.30,.30]:
    o=profile('MF_ForkBlade',[(.99,.065),(2.19,.065),(2.19,.083),(2.04,.11),(1.11,.11),(1.11,.65),(.99,.65)],.125,'Metal',.007);o.location.y=y
    box('MF_ForkHeel',(.99,y,.48),(.045,.14,.24),'Blue',.006)
    cylinder('MF_ForkLock',(.97,y,.70),.018,.07,'Metal',(0,0,1),12)
# Isolated warning placards and high visibility edge strips.
active=cols['06_Details']
for sy in [-1,1]:
    box('MF_MastWarning',(.84,sy*.43,1.12),(.06,.012,.15),'Helmet',.003)
    for z in [1.07,1.11,1.15]:box('MF_WarningInk',(.846,sy*.437,z),(.047,.006,.013),'Dark',.001)
    box('MF_TailLamp',(-1.185,sy*.34,.91),(.02,.13,.055),'Red',.010)
    box('MF_Reflector',(-1.187,sy*.35,.48),(.015,.105,.035),'Reflective',.005)
    box('MF_RearVent',(-1.19,sy*.13,.76),(.010,.17,.18),'Dark',.006)
    for z in [.70,.74,.78,.82]:box('MF_VentLouvre',(-1.198,sy*.13,z),(.008,.16,.010),'Body',.002)
rod('MF_RearTowPin',(-1.18,0,.28),(-1.24,0,.28),.026,'Metal')
cylinder('MF_BeaconBase',(-.70,.32,2.225),.065,.045,'Dark')
cylinder('MF_AmberBeacon',(-.70,.32,2.292),.051,.09,'Amber',segments=32)
for z in [2.26,2.29,2.32]:ring('MF_BeaconLensRing',(-.70,.32,z),.052,.004,(0,0,1),'Amber',24)
label('MF_RearFleetNumber','MF-01',(-1.203,0,.69),.085,'White',(-1,0,0))

# Driver is authored separately to retain local editability.
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
if (ROOT/'Scripts/ghs/build_forklift_driver.py').exists():
    import importlib,build_forklift_driver
    importlib.reload(build_forklift_driver)
    driver=build_forklift_driver.build_driver(scene,cols['05_Driver'],mats)
else:driver=[]

# Neutral studio lighting, separate from exported geometry.
active=cols['Studio']
box('Studio_Ground',(0,0,-.075),(200,200,.10),'Body',0)
world=bpy.data.worlds.new('MannedForklift_StudioWorld');world.use_nodes=True
bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.34,.39,.46,1);bg.inputs['Strength'].default_value=.45;scene.world=world
for name,p,power,size in [('Key',(2,-4,6),1000,5),('Fill',(-4,-1,3.5),650,4),('Rim',(1,4,5),1300,3)]:
    d=bpy.data.lights.new('Studio_'+name,'AREA');d.energy=power;d.shape='DISK';d.size=size
    o=bpy.data.objects.new(d.name,d);active.objects.link(o);o.location=p;o.rotation_euler=(Vector((0,0,1))-o.location).to_track_quat('-Z','Y').to_euler()
camd=bpy.data.cameras.new('ForkliftPresentationCamera');cam=bpy.data.objects.new(camd.name,camd);active.objects.link(cam)
cam.location=(4.9,-6.8,3.65);cam.rotation_euler=(Vector((.28,0,1.05))-cam.location).to_track_quat('-Z','Y').to_euler();camd.type='ORTHO';camd.ortho_scale=4.75;scene.camera=cam
scene.render.engine=old_scene.render.engine
scene.render.resolution_x=1200;scene.render.resolution_y=1050;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(OUT/'manned_forklift_preview.png')
scene.view_settings.view_transform='AgX';scene.view_settings.exposure=0;scene.render.film_transparent=False
# Place the viewport on the model, with materials visible and studio overlays off.
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        area.spaces.active.region_3d.view_distance=5.3;area.spaces.active.region_3d.view_location=(.3,0,1.05)
        area.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion();area.spaces.active.shading.type='MATERIAL'
        area.spaces.active.overlay.show_overlays=False
for o in bpy.context.selected_objects:o.select_set(False)
bpy.context.view_layer.update()
(OUT/'material_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print('FORKLIFT_BUILT',len(list(asset.all_objects)),'driver_parts',len(driver))
