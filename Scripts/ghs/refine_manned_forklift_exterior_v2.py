"""Revise the existing editable forklift silhouette against the supplied Raymond photo.

Only this asset is edited. No Unreal imports, network calls or scene resets.
"""
import bpy, math, ast, json, bmesh
from pathlib import Path
from mathutils import Vector

ROOT = Path(r'D:/UEPro/Test')
OUT = ROOT/'SourceAssets/GHS_Normal/MannedForklift'
scene = bpy.context.scene
assert scene.name == 'GHS_MannedForklift_Studio'
asset = bpy.data.collections['MannedForklift_Editable']
cols = {c.name:c for c in asset.children}
root = bpy.data.objects['MF_Root']
mats = {r:bpy.data.materials['M_MF_'+r] for r in ('Body','Blue','Frame','Metal','Rubber','Dark','Seat','Glass','Safety','Helmet','Reflective','Skin','Cloth','Navy','White','LED','Red','Amber')}
# Reuse only pure geometry helper definitions, without re-running the original scene setup.
tree = ast.parse((ROOT/'Scripts/ghs/build_manned_forklift.py').read_text(encoding='utf-8-sig'))
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef)],type_ignores=[]),'<forklift helpers>','exec'))

def remove_objects(objects):
    for o in list(objects):
        bpy.data.objects.remove(o,do_unlink=True)

def smooth_bevel(o):
    for p in o.data.polygons:p.use_smooth=True
    for m in o.modifiers:
        if m.type=='BEVEL':m.segments=5
    return o

def rounded_outline(cx, hx, hy, corner, z, steps=10):
    result=[]
    for x,y,start in [(cx+hx-corner,hy-corner,0),(cx-hx+corner,hy-corner,90),
                       (cx-hx+corner,-hy+corner,180),(cx+hx-corner,-hy+corner,270)]:
        for k in range(steps):
            a=math.radians(start+90*k/(steps-1))
            result.append((x+corner*math.cos(a),y+corner*math.sin(a),z))
    return result

def cast_shell(n,stations,role):
    vs=[]
    for z,cx,hx,hy,rad in stations:vs.extend(rounded_outline(cx,hx,hy,rad,z))
    N=40;fs=[tuple(range(N-1,-1,-1))]
    for j in range(len(stations)-1):
        for i in range(N):fs.append((j*N+i,j*N+(i+1)%N,(j+1)*N+(i+1)%N,(j+1)*N+i))
    fs.append(tuple((len(stations)-1)*N+i for i in range(N)))
    o=mesh(n,vs,fs,role,smooth=True)
    o.data.polygons[0].use_smooth=False;o.data.polygons[-1].use_smooth=False
    return o

def rectangular_strut(n,a,b,w,d,role='Frame'):
    a,b=Vector(a),Vector(b)
    ob=box(n,(a+b)/2,(w,d,(b-a).length),role,.008)
    ob.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()
    return smooth_bevel(ob)

# Lower saturation, dark structural steel and restrained blue trim.
for role,color,rough,metal in [('Body',(.53,.57,.61),.38,.17),('Blue',(.015,.060,.21),.36,.27),
                              ('Frame',(.027,.035,.045),.43,.45),('Metal',(.20,.245,.29),.37,.72),
                              ('Rubber',(.012,.014,.017),.86,0)]:
    m=mats[role];p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=rough
    p.inputs['Metallic'].default_value=metal;m.diffuse_color=(*color,1)

# Integrated rear casting and continuous battery panels; remove the flat floating boxes.
active=cols['01_Body'];remove_objects(active.objects)
smooth_bevel(profile('MF_V2_Chassis',[(-1.18,.215),(.78,.215),(.82,.40),(.62,.53),(-.45,.53),(-.54,.58),(-1.18,.49)],.91,'Frame',.035))
cast_shell('MF_V2_CastCounterweight',[(.435,-.89,.30,.465,.14),(.46,-.87,.355,.52,.16),(.52,-.86,.37,.54,.16),(.89,-.86,.37,.54,.12),(.99,-.86,.35,.53,.105),(1.035,-.86,.32,.50,.09)],'Body')
cast_shell('MF_V2_HoodSeam',[(1.033,-.86,.322,.502,.088),(1.045,-.86,.322,.502,.088)],'Dark')
cast_shell('MF_V2_BatteryHood',[(1.045,-.86,.326,.503,.09),(1.061,-.86,.316,.493,.09),(1.080,-.86,.285,.47,.10)],'Body')
cast_shell('MF_V2_RearBumper',[(.36,-.94,.275,.47,.17),(.385,-.94,.30,.51,.17),(.438,-.94,.30,.52,.17),(.455,-.94,.285,.51,.17)],'Rubber')
# Cast body below the seat: mostly tucked behind side covers rather than a white cube.
smooth_bevel(profile('MF_V2_SeatBase',[(-.69,.48),(-.17,.48),(-.17,.83),(-.26,.97),(-.69,.97)],.65,'Frame',.04))
for side in [-1,1]:
    y=side*.534
    panel=[(-1.14,.53),(-.52,.53),(-.42,.64),(-.42,.91),(-.51,1.008),(-1.14,1.008)]
    ob=profile('MF_V2_BatteryPanelGasket',panel,.013,'Dark',.016);ob.location.y=y
    panel2=[(-1.116,.555),(-.532,.555),(-.444,.649),(-.444,.900),(-.522,.987),(-1.116,.987)]
    ob=profile('MF_V2_BatteryAccessPanel',panel2,.016,'Body',.019);ob.location.y=y+side*.012;smooth_bevel(ob)
    # Painted upper stripe and lower bumper continue the body instead of hovering above it.
    ob=profile('MF_V2_BlueShoulderStripe',[(-1.11,.932),(-.47,.932),(-.52,.989),(-1.11,.989)],.004,'Blue',.002);ob.location.y=y+side*.022
    box('MF_V2_RecessedLatch',(-.48,y+side*.024,.836),(.036,.009,.074),'Dark',.006)
    box('MF_V2_LatchLever',(-.479,y+side*.030,.836),(.014,.009,.048),'Metal',.004)
    # Thin perimeter seam, subtle paired hinge bosses, one clean fleet identifier.
    for z in [.628,.870]:
        cylinder('MF_V2_PanelHinge',(-1.094,y+side*.022,z),.012,.068,'Metal',(0,0,1),16)
    label('MF_V2_FleetMark','GHS',(-.83,y+side*.026,.845),.085,'Blue',(0,side,0))
    label('MF_V2_ModelMark','ELECTRIC 18',(-.82,y+side*.026,.763),.028,'Frame',(0,side,0))
    # Rounded arch with a real tyre clearance arc, not a thick trapezoid over the wheel.
    vs=[];cx,cz=.53,.315;rin,rout=.344,.391;segments=40
    for yy in [side*.445-.09,side*.445+.09]:
        for r in [rin,rout]:
            for i in range(segments+1):
                a=math.radians(12+156*i/segments);vs.append((cx+r*math.cos(a),yy,cz+r*math.sin(a)))
    N=segments+1;fs=[]
    for i in range(segments):
        for a,b in [(0,N),(N,3*N),(3*N,2*N),(2*N,0)]:fs.append((a+i,a+i+1,b+i+1,b+i))
    fs.extend([(0,N,3*N,2*N),(N-1,2*N-1,4*N-1,3*N-1)])
    mesh('MF_V2_ArchedWheelGuard',vs,fs,'Frame',.004,True)
    # Outer mounting tab is modest and follows the reference opening.
    ob=profile('MF_V2_FenderShoulder',[(.19,.61),(.25,.716),(.62,.716),(.71,.663),(.64,.651),(.27,.65)],.16,'Body',.012);ob.location.y=side*.435
    ob=profile('MF_V2_Sill', [(-.45,.255),(.18,.255),(.18,.34),(-.40,.34)],.11,'Frame',.012);ob.location.y=side*.46
    box('MF_V2_EntryStep',(-.075,side*.48,.345),(.47,.23,.055),'Frame',.012)
    box('MF_V2_StepInset',(-.075,side*.493,.376),(.405,.18,.008),'Rubber',.003)
    for ix in range(8):
        for iy in range(3):
            b=box('MF_V2_StepGrip',(-.25+ix*.05,side*(.435+iy*.05),.383),(.023,.011,.006),'Metal',.002);b.rotation_euler.z=.55
    box('MF_V2_EntryScuffPlate',(-.14,side*.397,.494),(.54,.042,.018),'Metal',.004)
box('MF_V2_Footwell',(.035,0,.473),(.82,.78,.064),'Dark',.015)
box('MF_V2_FloorMat',(.01,0,.509),(.70,.66,.009),'Rubber',.009)

# Lathed solid rubber tyres with rounded shoulders and recessed dark industrial hubs.
active=cols['02_Wheels'];remove_objects(active.objects)
def lathe_y(name,x,y,z,stations,role,segments=96):
    vs=[]
    for offset,r in stations:
        for i in range(segments):
            a=math.tau*i/segments;vs.append((x+r*math.cos(a),y+offset,z+r*math.sin(a)))
    fs=[]
    for j in range(len(stations)-1):
        for i in range(segments):fs.append((j*segments+i,j*segments+(i+1)%segments,(j+1)*segments+(i+1)%segments,(j+1)*segments+i))
    return mesh(name,vs,fs,role,smooth=True)
for side in [-1,1]:
    for x,r,w,cy,front in [(.53,.315,.205,.49,True),(-.92,.215,.16,.42,False)]:
        y=side*cy;name='MF_V2_'+('Front' if front else 'Rear')+('_L' if side>0 else '_R')
        # Slightly crowned tread and rounded bead; closed cross section around the rim.
        outline=[(-.50,.58),(-.53,.69),(-.51,.80),(-.45,.91),(-.35,.976),(-.24,.991),(-.12,.997),(0,1),(.12,.997),(.24,.991),(.35,.976),(.45,.91),(.51,.80),(.53,.69),(.50,.58)]
        stations=[(a*w,b*r) for a,b in outline];stations.append(stations[0])
        lathe_y(name+'_RoundedSolidTyre',x,y,r,stations,'Rubber')
        # Moulded grooves lie in the tread: closely spaced dark zigzag cuts instead of raised blocks.
        for i in range(44 if front else 36):
            a=math.tau*i/(44 if front else 36)
            for s in [-1,1]:
                points=[]
                for k in range(6):
                    yy=s*(.02+.39*k/5)*w;aa=a+s*.055*k/5
                    rr=r*(1-.09*(abs(yy)/(w*.5))**4)+.0006
                    points.append((x+rr*math.cos(aa),y+yy,r+rr*math.sin(aa)))
                tube(name+'_MouldedTreadGroove',points,.0022,'Dark')
        for sy in [-1,1]:
            outer=y+sy*w*.505
            ring(name+'_SidewallBead',(x,outer,r),r*.75,.004,(0,1,0),'Dark',64)
            ring(name+'_RimSeat',(x,outer-sy*.003,r),r*.596,.010,(0,1,0),'Rubber',64)
        # Dish-shaped rim with outer lip and a recessed hub face; no white toy wheel.
        rimprof=[(0,r*.58),(.006,r*.58),(.012,r*.55),(.008,r*.50),(-.019,r*.40),(-.025,r*.23),(-.022,0)]
        lathe_y(name+'_DishedRim',x,y+side*w*.49,r,[(side*d,rr) for d,rr in rimprof],'Metal',64)
        cylinder(name+'_Hub',(x,y+side*w*.51,r),r*.225,.038,'Frame',(0,1,0),48)
        cylinder(name+'_AxleCap',(x,y+side*(w*.51+.022),r),r*.13,.016,'Metal',(0,1,0),32)
        for i in range(8 if front else 5):
            a=i*math.tau/(8 if front else 5)
            p=(x+r*.33*math.cos(a),y+side*w*.51,r+r*.33*math.sin(a))
            cylinder(name+'_RecessedBoltWasher',p,.015 if front else .011,.008,'Dark',(0,1,0),24)
            cylinder(name+'_HexNut',(p[0],p[1]+side*.007,p[2]),.010 if front else .007,.010,'Metal',(0,1,0),6)
        cylinder(name+'_Axle',(x,0,r),r*.13,2*cy,'Frame',(0,1,0),24)

# Box-section safety cage with shaped side rails, following the reference's side silhouette.
active=cols['04_Cockpit']
cageprefix=('MF_RearGuardPost','MF_FrontGuardPost','MF_RoofSideRail','MF_RoofCrossmember','MF_OverheadSafetyBar','MF_OverheadRearCover','MF_EntryGrabHandle','MF_WorkLamp')
remove_objects([o for o in active.objects if o.name.startswith(cageprefix)])
for side in [-1,1]:
    y=side*.49
    rectangular_strut('MF_V2_RearGuardPost',(-1.035,y,1.012),(-.98,y,2.175),.064,.060)
    # Slight rear rake matches the photo; posts meet a shaped reinforced shoulder at roof level.
    rectangular_strut('MF_V2_FrontGuardPost',(.40,y,.688),(.22,y,2.155),.064,.062)
    for x,z in [(-1.027,1.054),(.398,.718)]:
        box('MF_V2_GuardFootPlate',(x,y,z),(.12,.11,.025),'Frame',.007)
    outline=[(-1.044,2.105),(-1.044,2.205),(-.975,2.25),(.19,2.25),(.305,2.205),(.40,2.112),(.314,2.102),(.24,2.154),(-.94,2.154)]
    ob=profile('MF_V2_ShapedRoofRail',outline,.082,'Frame',.014);ob.location.y=y;smooth_bevel(ob)
    # Open integral mounting gussets; small handles provide the recognizable entry profile.
    ob=profile('MF_V2_RoofGusset',[(.185,1.96),(.16,2.17),(.29,2.178),(.32,2.12)],.035,'Frame',.009);ob.location.y=y
    tube('MF_V2_EntryHandle',[(.358,y+side*.055,1.03),(.30,y+side*.08,1.06),(.273,y+side*.08,1.29),(.323,y+side*.055,1.33)],.015,'Rubber')
    cylinder('MF_V2_WorkLampHousing',(.305,y,2.044),.055,.071,'Dark',(1,0,0),32)
    cylinder('MF_V2_WorkLampRim',(.345,y,2.044),.048,.008,'Metal',(1,0,0),32)
    cylinder('MF_V2_WorkLampLens',(.351,y,2.044),.041,.004,'LED',(1,0,0),32)
for x in [-.995,.254]:smooth_bevel(box('MF_V2_RoofHeader',(x,0,2.182),(.078,1.02,.082),'Frame',.013))
for y in [-.32,-.16,0,.16,.32]:smooth_bevel(box('MF_V2_RoofSlat',(-.37,y,2.207),(1.18,.027,.042),'Frame',.005))
box('MF_V2_RearRoofMount',(-.88,0,2.213),(.17,.96,.025),'Frame',.009)

# Existing cabin remains simple. Round only the visible seat edge and remove bright pedestals.
for o in active.objects:
    if o.type=='MESH' and o.name.startswith(('MF_SeatCushion','MF_SeatBack','MF_SeatBolster','MF_BackBolster','MF_Armrest')):
        smooth_bevel(o)

# Reduce the apparent mass of mast flanges and fork shoes; retain existing mechanical assembly.
active=cols['03_Mast_Forks']
remove_objects([o for o in active.objects if o.name.startswith(('MF_ForkBlade','MF_ForkHeel'))])
for y in [-.30,.30]:
    # A genuine tapered blade with a radiused heel, and a slimmer upright than version 1.
    blade=[(.978,.075),(1.01,.052),(1.15,.043),(2.19,.043),(2.20,.055),(2.14,.069),(1.28,.103),(1.095,.108),(1.065,.132),(1.065,.644),(.978,.644)]
    ob=profile('MF_V2_TaperedForgedFork',blade,.112,'Frame',.004);ob.location.y=y;smooth_bevel(ob)
    box('MF_V2_ForkCarriageHook',(1.014,y,.601),(.12,.137,.068),'Blue',.005)
for o in active.objects:
    if o.name.startswith('MF_InnerMastRail'):
        o.data.materials.clear();o.data.materials.append(mats['Frame'])
    if o.name.startswith('MF_OuterMastFlange'):o.scale.y=.84
    if o.name.startswith('MF_MastCrossmember'):o.scale.z=.78
    if o.name.startswith('MF_LoadBackrestGrille'):o.scale.y=.78
    if o.type=='MESH' and o.name.startswith(('MF_OuterMast','MF_CarriageCrossbar','MF_LoadBackrest')):smooth_bevel(o)

# Tidy external trim so the redesigned rear does not retain detached version-1 accessories.
active=cols['06_Details']
remove_objects([o for o in active.objects if o.name.startswith(('MF_TailLamp','MF_Reflector','MF_RearVent','MF_VentLouvre','MF_RearFleetNumber'))])
for side in [-1,1]:
    box('MF_V2_RearLampHousing',(-1.232,side*.30,.92),(.018,.18,.068),'Dark',.010)
    box('MF_V2_RearLampLens',(-1.244,side*.30,.927),(.012,.135,.039),'Red',.007)
    box('MF_V2_Reflector',(-1.245,side*.31,.555),(.010,.10,.026),'Reflective',.005)
box('MF_V2_RearVentRecess',(-1.232,0,.743),(.012,.40,.16),'Dark',.012)
for z in [.689,.716,.743,.770,.797]:box('MF_V2_RearVentSlat',(-1.241,0,z),(.012,.38,.013),'Frame',.003)
label('MF_V2_RearFleetNumber','GHS  |  01',(-1.246,0,.87),.045,'Blue',(-1,0,0))
for o in active.objects:
    if o.name.startswith(('MF_Beacon','MF_AmberBeacon')):o.location.x-=.18

# Attach revised components without changing the existing asset pivot.
for o in asset.all_objects:
    if o.type in {'MESH','FONT','CURVE'} and o.parent is None:o.parent=root
    if o.type=='MESH':
        bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
bpy.context.view_layer.update()
# Lower product-view camera reveals roof silhouette, wheels and seated operator together.
cam=scene.camera
cam.location=(5.0,-7.8,3.05)
cam.rotation_euler=(Vector((.30,0,1.09))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.ortho_scale=4.55
scene.render.resolution_x=1440;scene.render.resolution_y=1260
scene.render.filepath=str(OUT/'manned_forklift_v2_preview.png')
root['revision']='v2_reference_exterior'
root['UnrealImport']='Paused by user. Blender review only.'
print('EXTERIOR_REFINED',len(list(asset.all_objects)))
