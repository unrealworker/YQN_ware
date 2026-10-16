"""Manufactured warehouse robot meshes, modeled in metres. Front is Blender +Y."""
import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *

reset()

black = material('RobotGraphite', (.027, .035, .044), .29, .58)
rubber = material('RobotRubber', (.014, .018, .022), .85, .05)
silver = material('RobotMachinedSteel', (.38, .44, .49), .28, .82)
aluminum = material('RobotSatinAluminum', (.61, .68, .73), .31, .68)
blue = material('RobotStackerBlue', (.012, .26, .53), .29, .40)
blue_dark = material('RobotBlueRecess', (.008, .08, .15), .43, .52)
orange = material('RobotTransportOrange', (.98, .185, .022), .31, .28)
white = material('RobotRackWhite', (.83, .88, .91), .30, .35)
yellow = material('RobotWarningYellow', (.98, .66, .035), .42, .22)
red = material('RobotIndicatorRed', (.8, .015, .012), .25, .18, emission=2.5)
cyan = material('RobotCyanLight', (.025, .68, 1.0), .24, .12, emission=3.4)
light = material('RobotWhiteLight', (.73, .9, 1.0), .22, .1, emission=3)
glass = material('RobotSensorGlass', (.012, .038, .052), .14, .78)


def bolts(loc, axis='Y', spacing=.11, count=3):
    for i in range(count):
        p=list(loc);p[0]+=(i-(count-1)/2)*spacing
        cylinder('RecessedFastener', p, .009, .006, silver, vertices=6, axis=axis)


def wheels(width, ys, z=.135, radius=.135):
    for x in (-width/2, width/2):
        for y in ys:
            cylinder('IndustrialRubberTire', (x,y,z), radius, .075, rubber, 32, 'X')
            side=x+(.043 if x>0 else -.043)
            cylinder('WheelHubSteel', (side,y,z), radius*.57, .011, silver, 24, 'X')
            cylinder('AxleCap', (side+(.008 if x>0 else -.008),y,z), radius*.25, .018, black, 16, 'X')
            for a in range(0,360,90):
                angle=math.radians(a)
                cylinder('WheelBolt', (side+(.008 if x>0 else -.008),y+math.cos(angle)*radius*.4,z+math.sin(angle)*radius*.4), .009, .016, aluminum, 6, 'X')


def fork_pair(y0=.27, length=1.1, spread=.45, z=.075, thick=.065):
    for x in (-spread/2,spread/2):
        box('ForkHeel', (x,y0,z+.13), (.12,.12,.31), black, .015)
        # Shaped wedge tips slope down toward the floor, as on steel forks.
        v=[(x+dx,y,zz) for dx in (-.055,.055) for y,zz in [(y0,z-thick/2),(y0+length,z-thick/2),(y0+length,z+.006),(y0+length-.16,z+thick/2),(y0,z+thick/2)]]
        fs=[(0,4,3,2,1),(5,6,7,8,9)]+[(i,(i+1)%5,(i+1)%5+5,i+5) for i in range(5)]
        bevel(mesh('ForgedForkTine',v,fs,silver), .006)
        box('ForkWearStrip',(x,y0+length*.47,z+thick/2+.004),(.046,length*.65,.008),black,.001)


def warning_plate(x,y,z, width=.1):
    box('WarningLabel',(x,y,z),(width,.006,.068),yellow,.002)
    for i in range(3):
        o=box('WarningStripe',(x+(i-1)*width*.25,y+.005,z),(width*.09,.004,.06),black,.001)
        o.rotation_euler[1]=-.35


def sensor_head(x,y,z):
    rounded_box('SensorHeadHousing',(x,y,z),(.19,.14,.105),.022,black)
    box('OpticalSensorWindow',(x,y+.073,z),(.131,.008,.048),glass,.004)
    for off in (-.038,.038):
        cylinder('OpticalSensorLens',(x+off,y+.08,z),.018,.009,cyan,20,'Y')
    box('SensorTopCap',(x,y,z+.056),(.14,.1,.012),silver,.003)


def blue_stacker():
    begin_asset('SM_VR_BlueStacker')
    wheels(.60,[-.29,.29],.13,.13)
    rounded_box('RoundedDriveBase',(0,-.055,.18),(.70,.95,.18),.10,black)
    rounded_box('SilverSafetyBumper',(0,-.055,.12),(.71,.96,.055),.10,aluminum)
    rounded_box('UpperBaseLip',(0,-.07,.282),(.64,.78,.06),.08,blue_dark)
    rounded_box('UprightBlueBody',(0,-.15,.77),(.56,.57,.94),.065,blue)
    box('BackPanel',(0,-.446,.80),(.43,.018,.74),blue_dark,.025)
    box('BrightVerticalIdentityLight',(0,-.46,.79),(.043,.014,.54),light,.01)
    box('LowerRearGrille',(0,-.465,.36),(.3,.02,.065),black,.008)
    for i in range(7):
        box('GrilleCoolingFin',((i-3)*.035,-.48,.36),(.008,.013,.047),silver,.001)
    for side in (-1,1):
        box('BlackCornerProtector',(side*.265,-.16,.82),(.045,.55,.97),black,.018)
        box('InsetSideBluePanel',(side*.29,-.17,.76),(.012,.36,.67),blue,.009)
        box('SideReflector',(side*.301,-.33,.86),(.008,.055,.23),light,.002)
        for z in (.47,1.05):
            cylinder('SidePanelFastener',(side*.306,-.22,z),.01,.008,silver,6,'X')
    rounded_box('ControlShoulder',(0,-.11,1.28),(.60,.57,.105),.06,black)
    box('MetalUpperControlPlate',(0,-.12,1.343),(.44,.38,.018),silver,.008)
    box('OperatorDisplay',(0,-.24,1.36),(.18,.1,.016),glass,.006)
    cylinder('EmergencyStopBase',(.17,-.22,1.365),.033,.014,yellow,24)
    cylinder('EmergencyStopButton',(.17,-.22,1.382),.021,.022,red,24)
    # Separate rear mast and steel lift guides remain legible from high angles.
    for x in (-.14,.14):
        box('BlackLiftMast',(x,.14,1.025),(.085,.11,1.48),black,.012)
        box('PolishedLiftGuide',(x,.203,1.02),(.03,.021,1.36),silver,.004)
    box('MastCrosshead',(0,.14,1.725),(.36,.14,.105),black,.016)
    box('LiftCarriage',(0,.231,.48),(.49,.09,.36),black,.013)
    bolts((0,.28,.55),spacing=.17)
    cylinder('HydraulicLiftRam',(0,.10,.83),.029,.93,silver,24)
    cylinder('HydraulicCylinder',(0,.10,.48),.045,.44,black,24)
    box('SensorMast',(0,.11,1.52),(.095,.09,.40),black,.012)
    sensor_head(0,.11,1.745)
    fork_pair(.28,1.03,.44)
    warning_plate(0,.285,.63,.14)
    for x in (-.22,.22):
        box('FrontRunningLight',(x,.334,.28),(.08,.015,.03),cyan,.004)
    bolts((0,-.461,1.12),spacing=.16)


def orange_transporter():
    begin_asset('SM_VR_OrangeTransporter')
    wheels(.78,[-.37,.37],.15,.15)
    rounded_box('HeavyRoundedBase',(0,-.08,.19),(.90,1.20,.18),.14,black)
    rounded_box('HeavyBumper',(0,-.08,.105),(.92,1.22,.07),.14,rubber)
    rounded_box('BumperMetalTrim',(0,-.08,.15),(.91,1.21,.028),.14,silver)
    # Main shell slopes toward the nose and tapers upward, unlike the blue vertical robot.
    verts=[(-.39,-.57,.27),(.39,-.57,.27),(.39,.43,.27),(-.39,.43,.27),(-.32,-.48,1.14),(.32,-.48,1.14),(.31,.31,.82),(-.31,.31,.82)]
    bevel(mesh('SlopedOrangeMonocoque',verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],orange),.035,3)
    box('BlackRearServicePanel',(0,-.586,.69),(.59,.025,.62),black,.025)
    for x in (-.27,.27):
        box('OrangeRearEdgeGuard',(x,-.61,.67),(.065,.04,.66),orange,.008)
    for i in range(9):
        box('RearVentSlat',((i-4)*.045,-.606,.71),(.012,.015,.28),silver,.002)
    for s in (-1,1):
        box('SideMaintenanceInset',(s*.386,-.17,.56),(.016,.49,.35),black,.015)
        box('SideOrangeInset',(s*.397,-.18,.56),(.008,.38,.24),orange,.01)
        for y in (-.36,.02):
            cylinder('ShellScrew',(s*.405,y,.56),.012,.008,silver,6,'X')
        box('SideAmberReflector',(s*.403,-.27,.80),(.009,.10,.035),yellow,.002)
    control=box('AngledControlConsole',(0,-.38,1.19),(.43,.33,.095),black,.021)
    control.rotation_euler[0]=.27
    screen=box('ConsoleTouchscreen',(0,-.45,1.247),(.19,.13,.018),glass,.007)
    screen.rotation_euler[0]=.27
    cylinder('StopButtonYellow',(.15,-.39,1.26),.03,.018,yellow,24)
    cylinder('StopButtonRed',(.15,-.39,1.282),.02,.025,red,24)
    for x in (-.19,.19):
        box('HeavyLiftChannel',(x,.23,.88),(.09,.12,1.12),black,.011)
        box('ChannelPolishedRail',(x,.298,.88),(.027,.016,1.02),silver,.004)
    box('CrossMastCap',(0,.23,1.43),(.47,.14,.10),black,.015)
    box('TelescopicSensorSupport',(0,.17,1.49),(.11,.095,.18),black,.01)
    sensor_head(0,.17,1.595)
    box('LiftingCarriage',(0,.32,.43),(.58,.1,.30),black,.01)
    fork_pair(.36,1.14,.52,.08,.07)
    for x in (-.30,.30):
        box('FrontWorkLamp',(x,.385,.61),(.09,.04,.065),light,.008)
    warning_plate(0,.385,.67,.18)
    bolts((0,-.608,.42),spacing=.19)


def rack_robot():
    begin_asset('SM_VR_WhiteRackRobot')
    wheels(.83,[-.32,.32],.13,.13)
    rounded_box('RackRobotDriveBase',(0,-.03,.19),(.98,1.08,.19),.12,black)
    rounded_box('WhiteBumperSurround',(0,-.03,.29),(1.0,1.10,.085),.12,white)
    rounded_box('CyanDriveDeck',(0,-.04,.35),(.84,.91,.065),.10,cyan)
    # Bright portal and contrasting rails: 0.85 m outside width, 2.60 m height.
    for x in (-.35,.35):
        box('WhitePortalColumn',(x,-.20,1.47),(.15,.20,2.06),white,.026)
        box('BlackLiftRailRecess',(x,-.086,1.43),(.075,.025,1.88),black,.009)
        box('StainlessLiftRail',(x,-.065,1.43),(.029,.018,1.82),silver,.004)
        box('RearWhiteColumnInset',(x,-.31,1.47),(.095,.012,1.75),aluminum,.005)
        for z in (.57,2.28):
            cylinder('PortalBolt',(x,-.326,z),.013,.008,silver,6,'Y')
    box('WhitePortalBridge',(0,-.20,2.50),(.85,.24,.20),white,.03)
    box('TopBridgeDarkInset',(0,-.067,2.50),(.47,.014,.095),black,.008)
    box('BridgeSensorStrip',(0,-.054,2.50),(.26,.012,.027),cyan,.004)
    box('PortalLowerBridge',(0,-.20,.51),(.85,.22,.16),white,.018)
    cylinder('VerticalLiftActuator',(0,-.18,1.44),.025,1.75,silver,24)
    box('CentralCableChain',(.18,-.16,1.48),(.05,.06,1.66),black,.007)
    for i in range(26):
        box('CableChainLink',(.18,-.122,.69+i*.060),(.057,.015,.018),silver,.002)
    box('ElevatorCarriage',(0,.015,1.20),(.76,.16,.30),aluminum,.022)
    for x in (-.27,.27):
        cylinder('CarriageRoller',(x,.105,1.20),.065,.035,black,24,'Y')
        cylinder('CarriageRollerHub',(x,.126,1.20),.027,.011,silver,20,'Y')
    # Forward telescopic bin shelf, with a shallow back wall and side guides.
    box('TelescopicInnerSlide',(0,.38,1.135),(.54,.62,.075),black,.009)
    box('ForwardBinShelf',(0,.68,1.20),(.69,.92,.065),white,.016)
    box('ShelfLeadingSteelLip',(0,1.143,1.20),(.70,.025,.041),silver,.005)
    for x in (-.31,.31):
        box('ShelfSideGuide',(x,.69,1.25),(.035,.85,.055),silver,.007)
    # Asymmetric U cradle to the left: returns toward the portal at both ends.
    box('CradleSideBeam',(-.67,-.08,1.04),(.11,.87,.16),white,.025)
    for y in (-.46,.30):
        box('CradleReturn',(-.48,y,1.04),(.46,.11,.16),white,.023)
    box('CradleInnerTray',(-.53,-.08,.966),(.39,.69,.026),aluminum,.008)
    for x in (-.20,.20):
        box('BaseRunningLight',(x,.527,.35),(.12,.016,.035),light,.005)
    box('OnboardComputerHousing',(.37,-.32,.64),(.18,.3,.32),white,.025)
    box('ComputerScreen',(.37,-.478,.67),(.10,.013,.10),glass,.009)
    warning_plate(0,.105,1.32,.12)


def alarm_robot():
    begin_asset('SM_VR_AlarmRobot')
    wheels(.80,[-.37,.37],.13,.13)
    rounded_box('LowIndustrialChassis',(0,-.04,.18),(.94,1.18,.19),.14,black)
    rounded_box('OuterImpactBumper',(0,-.04,.10),(.98,1.22,.055),.14,rubber)
    rounded_box('AmberChassisTrim',(0,-.04,.27),(.88,1.10,.034),.12,orange)
    rounded_box('DarkMechanismDeck',(0,-.04,.33),(.82,1.0,.09),.09,black)
    for x in (-.29,.29):
        box('SteelChassisRail',(x,-.04,.41),(.075,.92,.065),silver,.011)
        for y in (-.4,.34):
            cylinder('DeckTieBolt',(x,y,.45),.014,.012,aluminum,6)
    box('LowBatteryPack',(0,-.22,.50),(.43,.43,.24),black,.025)
    box('OrangeServiceLid',(0,-.22,.63),(.42,.40,.026),orange,.01)
    for i in range(7):
        box('BatteryVent',((i-3)*.046,-.22,.646),(.015,.27,.007),black,.002)
    for x in (-.24,.24):
        box('ExposedLiftMechanism',(x,.25,.55),(.09,.35,.28),black,.012)
        cylinder('LiftHydraulicRam',(x,.25,.68),.024,.28,silver,20)
    box('LowFrontCrossbeam',(0,.49,.43),(.73,.07,.10),silver,.014)
    for x in (-.32,.32):
        box('AlarmRedLamp',(x,.54,.39),(.09,.025,.052),red,.005)
    box('RearSensorPedestal',(0,-.43,.78),(.12,.10,.22),black,.01)
    sensor_head(0,-.43,.935)
    warning_plate(0,.532,.48,.17)
    # Short front supports allow pallets to be placed independently in UE.
    fork_pair(.47,.66,.48,.075,.055)


def cone():
    begin_asset('SM_VR_TrafficCone')
    rounded_box('ConeRubberFoot',(0,0,.025),(.37,.37,.05),.035,rubber)
    rounded_box('OrangeConeFoot',(0,0,.055),(.33,.33,.035),.025,orange)
    bpy.ops.mesh.primitive_cone_add(vertices=48,radius1=.135,radius2=.025,depth=.52,location=(0,0,.3275))
    finish(bpy.context.object,'ConeOrangeBody',orange)
    # White reflective bands are actual tapered cone strips with matching radii.
    for z0,z1 in ((.21,.28),(.37,.43)):
        def rad(z):return .135+(.025-.135)*((z-.0675)/.52)
        bpy.ops.mesh.primitive_cone_add(vertices=48,radius1=rad(z0)+.001,radius2=rad(z1)+.001,depth=z1-z0,location=(0,0,(z0+z1)/2))
        finish(bpy.context.object,'ReflectiveConeBand',white)
    cylinder('ConeTip',(0,0,.591),.026,.012,orange,32)


blue_stacker()
orange_transporter()
rack_robot()
alarm_robot()
cone()
save_library('robots')

# Optional review render is created only after the unmodified source library is saved.
if '--preview' in sys.argv:
    from mathutils import Vector
    for (name,col),offset in zip(ASSETS,[-3.0,-1.40,.35,2.35,3.65]):
        for obj in col.objects:
            obj.location.x += offset
    scene=bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.006))
    floor=bpy.context.object
    floor.data.materials.append(material('RobotReviewFloor',(.04,.055,.075),.72))
    world=bpy.data.worlds.new('RobotReviewWorld')
    world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(.16,.21,.29,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.6
    scene.world=world
    for name,pos,power,size in [('Key',(-3,3,7),1700,7),('Fill',(5,1,5),1400,6),('Rim',(0,-4,5),2000,5)]:
        data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
        obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=pos
        obj.rotation_euler=(Vector((0,0,1))-obj.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('RobotReviewCamera');camera=bpy.data.objects.new('RobotReviewCamera',data)
    scene.collection.objects.link(camera);camera.location=(4.2,9.5,6.0)
    camera.rotation_euler=(Vector((0,.1,1))-camera.location).to_track_quat('-Z','Y').to_euler()
    data.type='ORTHO';data.ortho_scale=9.9;scene.camera=camera
    engines={e.identifier for e in scene.render.bl_rna.properties['engine'].enum_items}
    scene.render.engine='BLENDER_EEVEE' if 'BLENDER_EEVEE' in engines else 'CYCLES'
    if scene.render.engine=='CYCLES':scene.cycles.samples=16
    scene.render.resolution_x=1800;scene.render.resolution_y=950;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.render.filepath=str(OUT/'robots_preview.png')
    bpy.ops.render.render(write_still=True)
