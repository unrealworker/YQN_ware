import sys, math, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'video_reference'))
import common as c
import bpy
from mathutils import Vector
c.OUT=Path(r'D:\UEPro\Test\SourceAssets\GHS');c.OUT.mkdir(parents=True,exist_ok=True)
c.reset();c.begin_asset('SM_GHS_WallCharger')
def mat(n,col,r=.5,m=0):return c.material('M_VR_GHS_Charger_'+n,col,r,m)
black=mat('Powdercoat',(.022,.026,.029),.55,.3);rubber=mat('Rubber',(.009,.011,.012),.8)
red=mat('Red',(.55,.018,.023),.38,.35);steel=mat('Steel',(.23,.26,.28),.32,.8)
white=mat('Label',(.87,.88,.84),.7);yellow=mat('Warning',(.95,.65,.025));screen=mat('Screen',(.10,.29,.30),.25)
def box(n,p,s,m,e=.003):return c.box(n,p,s,m,e)
def txt(n,t,x,y,z,s,m=white):return c.text(n,t,(x,y,z),s,m,(math.pi/2,0,math.pi))
def cable(n,pts,r,m):
 d=bpy.data.curves.new(n,'CURVE');d.dimensions='3D';d.resolution_u=20;d.bevel_depth=r;d.bevel_resolution=3
 sp=d.splines.new('BEZIER');sp.bezier_points.add(len(pts)-1)
 for p,v in zip(sp.bezier_points,pts):p.co=v;p.handle_left_type='AUTO';p.handle_right_type='AUTO'
 ob=bpy.data.objects.new(n,d);bpy.context.scene.collection.objects.link(ob);return c.finish(ob,n,m)
# Wall equipment: back plane Y=0, front +Y. Origin on floor beneath assembly bounds.
cx=-.28
box('BackMount',(cx,.022,1.4),(.62,.044,.42),steel)
box('ChargerEnclosure',(cx,.112,1.4),(.60,.18,.40),black,.009)
box('FrontFace',(cx,.208,1.415),(.56,.015,.315),black)
for x in [cx-.307,cx+.307]:
 box('RedSideFold',(x,.115,1.415),(.025,.23,.43),red)
 box('RedFrontReturn',(x+(.019 if x<cx else -.019),.231,1.415),(.04,.015,.43),red)
 for z in [1.225,1.605]:c.cylinder('RailScrew',(x,.244,z),.006,.006,steel,16,'Y')
box('VentLowerChassis',(cx,.105,1.165),(.58,.17,.065),black)
for x in [cx-.26+i*.0325 for i in range(17)]:
 box('CoolingFin',(x,.171,1.164),(.009,.055,.052),steel,.001)
for x in [cx-.24+i*.045 for i in range(12)]:
 box('LowerVentSlot',(x,.217,1.22),(.028,.004,.01),rubber,.0005)
box('ControlBezel',(cx+.163,.224,1.51),(.12,.014,.084),white)
box('LCD',(cx+.148,.235,1.523),(.071,.008,.034),screen)
txt('LCDReadout','48 V',cx+.148,.242,1.516,.012)
for x in [cx+.126,cx+.153,cx+.18]:c.cylinder('ControlButton',(x,.241,1.488),.005,.004,rubber,16,'Y')
txt('Brand','Linde',cx-.17,.226,1.285,.043)
txt('Model','SELECTIVA',cx+.155,.229,1.443,.015)
box('RedBadge',(cx+.17,.226,1.29),(.12,.007,.031),red)
txt('Badge','CHARGE',cx+.17,.233,1.283,.012)
# Small hanging lead on left and distinct long paired charging leads.
for x in [cx-.24,cx+.24]:
 c.cylinder('CableGland',(x,.12,1.125),.021,.06,rubber,24)
cable('LeftHangingLead',[(cx-.24,.13,1.13),(-.66,.17,.88),(-.73,.16,.68),(-.67,.16,.61),(-.57,.16,.64),(-.55,.15,.78),(-.58,.14,1.12)],.010,rubber)
lead=[(-.04,.13,1.13),(.045,.16,.79),(.12,.17,.32),(.25,.18,.08),(.41,.19,.10),(.70,.18,.37),(.86,.15,.68),(.91,.11,1.10)]
cable('MainBlackChargingCable',lead,.014,rubber)
cable('PositiveRedChargingCable',[(x+.021,y-.004,z+.002) for x,y,z in lead],.009,red)
for x in [-.04,-.019]:c.cylinder('StrainRelief',(x,.13,1.11),.019,.075,rubber,24)
# Right side wall holster and heavy charging connector.
box('HolsterMount',(.91,.025,1.10),(.085,.05,.13),steel)
o=box('ChargingHandle',(.91,.10,1.095),(.115,.075,.05),rubber,.011);o.rotation_euler[1]=-.35
o=box('ConnectorNose',(.865,.10,1.12),(.056,.064,.057),black,.005);o.rotation_euler[1]=-.35
box('HandleRedRelease',(.922,.143,1.117),(.038,.012,.019),red)
cable('HandleStrainRelief',[(.91,.11,1.10),(.925,.12,1.04),(.915,.13,.99)],.019,rubber)
# Incoming power outlet, with plug and conduit.
box('WallSocket',(.38,.035,1.58),(.078,.07,.11),black)
c.cylinder('SocketRedRim',(.38,.083,1.515),.031,.047,red,32)
c.cylinder('SupplyPlug',(.38,.08,1.485),.023,.045,rubber,32)
cable('ACSupply',[(-.005,.13,1.38),(.11,.12,1.22),(.29,.09,1.25),(.38,.08,1.45)],.011,rubber)
cable('SupplyConduit',[(.38,.02,1.63),(.38,.02,1.81)],.009,steel)
# Two independent warning plates. Mesh lettering remains readable in FBX.
for z,h in [(1.59,.18),(1.32,.22)]:
 box('SafetyPlate',(.80,.011,z),(.26,.022,h),white,.002)
 box('SafetyHeader',(.80,.025,z+h/2-.021),(.248,.004,.028),red)
 txt('SafetyHeaderText','CHARGING AREA',.80,.030,z+h/2-.025,.014)
txt('SafetyNote','VENTILATE',.80,.029,1.565,.017,black)
txt('SafetyNote','NO FLAMES',.80,.029,1.527,.017,black)
txt('SafetyNote','48 V DC',.80,.029,1.337,.022,black)
txt('SafetyNote','POWER OFF',.80,.029,1.293,.018,black)
txt('SafetyNote','BEFORE SERVICE',.80,.029,1.261,.012,black)
# Lightning warning triangle beside text.
c.mesh('WarningTriangle',[(.705,.032,1.39),(.675,.032,1.343),(.735,.032,1.343)],[(0,1,2)],yellow)
c.curve('Lightning',[(.707,.035,1.383),(.696,.035,1.363),(.71,.035,1.363),(.701,.035,1.347)],.0025,black)
# From the +Y viewing side, positive X appears at the viewer's left.
# Reflect layout to preserve reference-photo handedness, retaining legible text.
for ob in list(c.ACTIVE.objects):
 ob.location.x=.113-ob.location.x
 if ob.type!='FONT':ob.scale.x*=-1
c.save_library('charger')
meta=json.loads((c.OUT/'charger.json').read_text());meta['reference_estimate']='Image-estimated dimensions: cabinet 0.60 x 0.18 x 0.40 m, center height 1.40 m; overall equipment approx 1.4-1.7 m wide and 1.8 m high; no background wall.'
(c.OUT/'charger.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
# Preview-only stage (excluded from saved model and FBX).
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=32
scene.world.color=(.25,.25,.25)
def area(p,power,size):
 d=bpy.data.lights.new('PreviewArea','AREA');d.energy=power;d.shape='DISK';d.size=size
 o=bpy.data.objects.new('PreviewArea',d);scene.collection.objects.link(o);o.location=p;o.rotation_euler=(Vector((.05,0,1))-o.location).to_track_quat('-Z','Y').to_euler()
area((1,3,4),350,3);area((-3,1,2),180,2)
d=bpy.data.cameras.new('PreviewCamera');o=bpy.data.objects.new('PreviewCamera',d);scene.collection.objects.link(o);o.location=(2.2,5,2.55);o.rotation_euler=(Vector((.1,.08,.95))-o.location).to_track_quat('-Z','Y').to_euler();d.type='ORTHO';d.ortho_scale=2.25;scene.camera=o
scene.render.resolution_x=1000;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(c.OUT/'WallCharger_Preview.png')
scene.view_settings.view_transform='AgX'
bpy.ops.render.render(write_still=True)
print('CHARGER_VERIFIED',json.dumps(meta['meshes']))
