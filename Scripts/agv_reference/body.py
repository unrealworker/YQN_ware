"""Reference-derived low-profile AGV chassis and load platform."""
from agv_common import *

def face_plate(name,x,y,z,width,height,depth,mat,r=.008):
    o=rounded_box(name,(0,0,0),(height,width,depth),r,mat,.0008)
    o.rotation_euler=(0,-math.pi/2,0);o.location=(x,y,z)
    return o

def build_body():
    grey=material('GraphitePaint',(.065,.077,.094),.36,.42)
    grey2=material('PanelPaint',(.080,.094,.113),.40,.35)
    dark=material('DarkMetal',(.028,.035,.045),.37,.65)
    black=material('Rubber',(.012,.014,.017),.67,.03)
    yellow=material('SafetyYellow',(.92,.48,.008),.33,.10)
    chrome=material('Chrome',(.5,.55,.60),.24,.92)
    white=material('LabelWhite',(.78,.80,.78),.50,.12)
    glass=material('OpticalGlass',(.006,.015,.022),.13,.4)
    red=material('TailRed',(.55,.006,.009),.20,.12,emission=.08)
    led=material('Headlamp',(.76,.84,.91),.20,.3,emission=.5)
    deck=material('PlatformSteel',(.135,.157,.185),.33,.62)

    collection('01_Chassis')
    main=rounded_box('Chassis_RoundedShell',(0,0,.287),(1.56,.872,.386),.145,grey,.003)
    bpy.context.view_layer.objects.active=main
    main.select_set(True)
    for mod in list(main.modifiers): bpy.ops.object.modifier_apply(modifier=mod.name)
    for x in [-.40,.54]:
        cutter=cylinder('Temporary_WheelArch',(x,0,.162),.179,1.12,grey,96,'Y')
        mod=main.modifiers.new('True wheel arch cutout','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
        bpy.context.view_layer.objects.active=main
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter,do_unlink=True)
    bevel(main,.0018,3)
    rounded_box('Upper_Deck',(0,0,.479),(1.56,.867,.022),.14,dark,.0015)
    perimeter_ring('Yellow_ImpactRail',1.60,.912,.16,.493,.041,.045,yellow)
    # The lower bumper wraps the front and rear without crossing the wheel openings.
    front=rounded_points(1.60,.914,.155)
    frontpoints=[(x,y,.073) for x,y in front if x<-.54]
    frontpoints=sorted(frontpoints,key=lambda p:p[1])
    line('Front_RubberSafetyBumper',frontpoints,.021,black)
    line('Rear_RubberSafetyBumper',[(x,y,.073) for x,y in front if x>.67],.019,black)
    box('Underbody_Frame',(0,0,.082),(1.27,.60,.04),dark,.006)
    # A perimeter gasket divides the front's removable lower cover.
    lower=rounded_points(1.568,.88,.147)
    line('Front_PanelSeam',[(x,y,.223) for x,y in sorted([p for p in lower if p[0]<-.60],key=lambda p:p[1])],.002,black)
    for y in [-.30,.30]:
        box('Front_BumperMount',(-.782,y,.087),(.045,.052,.027),dark,.004)
    for x in [-.74,.74]:
        for y in [-.325,.325]:bolt('YellowRail_Fastener',(x,y,.516),.0031,.0015)
    for x in [-.55,-.10,.3,.65]:
        for y in [-.43,.43]:bolt('TopDeck_Fastener',(x,y,.493),.0027,.0013)

    collection('02_ServicePanels')
    for sign in [-1,1]:
        y=sign*.438
        box('BatteryDoor_Gasket',(.075,y,.272),(.495,.008,.328),black,.004)
        box('Battery_ServiceDoor',(.075,y+sign*.005,.272),(.480,.009,.313),grey2,.003)
        for x in [-.164,.313]:
            for z in [.126,.418]:bolt('ServiceDoor_Screw',(x,y+sign*.012,z),.003,.0018,'-Y' if sign<0 else 'Y')
        for z in [.17,.374]:
            box('Door_Hinge',(.309,y+sign*.015,z),(.015,.014,.035),chrome,.002)
            cylinder('Door_HingePin',(.310,y+sign*.019,z),.004,.034,dark,24,'Z')
        box('Recessed_Latch',(-.164,y+sign*.012,.263),(.027,.012,.075),black,.004)
        box('Latch_Handle',(-.166,y+sign*.020,.263),(.008,.009,.050),dark,.002)
        for x in [-.69,.756]:
            edge_y=.291+math.sqrt(max(0,.145**2-(abs(x)-.635)**2))
            box('Corner_RubberGuard',(x,sign*(edge_y+.006),.180),(.038,.018,.15),black,.003)
        # Rear service recess and small diagonal warning strips.
        box('Rear_SideSensor',(.711,sign*.426,.405),(.047,.016,.035),black,.004)
        for i in range(3):
            b=box('Rear_HazardStripe',(.664+i*.016,sign*(.291+math.sqrt(.145**2-(.029+i*.016)**2)+.003),.313),(.012,.006,.035),yellow,.001)
            b.rotation_euler[1]=-.45
        box('Service_WarningLabel',(-.224,y+sign*.009,.390),(.035,.002,.047),white,.0004)
        box('Service_WarningHeader',(-.224,y+sign*.011,.405),(.032,.001,.010),yellow,.0002)

    collection('03_Front_Fascia')
    for y in [-.265,.265]:
        face_plate('Headlight_BlackBezel',-.782,y,.337,.169,.062,.012,black,.015)
        face_plate('Headlight_ChromeLip',-.790,y,.337,.139,.043,.006,chrome,.011)
        face_plate('Headlight_SmokedLens',-.794,y,.337,.129,.037,.004,glass,.009)
        for i in range(7):
            face_plate('Headlight_LED',-.798,y-.052+i*.0173,.337,.010,.023,.002,led,.002)
        for yy in [y-.075,y+.075]:bolt('Lamp_Fixing',(-.790,yy,.337),.0022,.0014,'-X')
    face_plate('Front_DiagnosticRecess',-.789,0,.338,.155,.049,.009,black,.005)
    face_plate('Identity_Plate',-.801,0,.453,.192,.048,.004,chrome,.003)
    face_plate('Identity_Insert',-.804,0,.453,.178,.038,.002,white,.002)
    text('Front_Identification','AG',(-.806,0,.457),.024,dark)
    text('Front_IdentificationRule','________',(-.806,0,.441),.012,dark)
    # Yellow lowered central fascia follows the characteristic notch under the top rail.
    vv=[(-.783,-.14,.491),(-.783,.14,.491),(-.783,.108,.424),(-.783,-.108,.424)]
    patch=mesh('Yellow_FrontCenterApron',vv,[(3,2,1,0)],yellow)
    so=patch.modifiers.new('Apron thickness','SOLIDIFY');so.thickness=.004
    text('Raised_Front_AG','AG',(-.789,.050,.176),.040,chrome)
    text('Raised_Front_Tail','GEAR',(-.789,-.051,.176),.025,chrome)
    for y in [-.35,-.18,.18,.35]:bolt('LowerFascia_Screw',(-.781,y,.202),.0025,.0014,'-X')
    # Small red scanning module standing ahead of the cargo platform.
    sensor=box('Front_SafetySensorBase',(-.690,0,.514),(.110,.13,.016),black,.003)
    box('Front_SafetySensorHousing',(-.686,0,.546),(.084,.112,.059),dark,.008)
    face_plate('Front_SafetySensor_RedWindow',-.731,0,.542,.083,.027,.005,red,.003)
    for y in [-.057,.057]:bolt('SafetySensor_Mount',(-.695,y,.525),.003,.0015)
    for y in [-.30,.30]:
        face_plate('Rear_RedReflector',.785,y,.265,.085,.031,.003,red,.003)

    collection('04_Load_Platform')
    for x in [-.55,.27]:
        for y in [-.29,.29]:
            box('Platform_Foot',(x,y,.508),(.095,.080,.012),dark,.003)
            box('Platform_Standoff',(x,y,.533),(.050,.048,.044),grey,.002)
            for xx in [x-.032,x+.032]:bolt('Platform_FootBolt',(xx,y,.516),.0031,.002)
    for y in [-.305,.305]:box('Platform_UnderRail',(-.125,y,.542),(.94,.036,.022),dark,.003)
    rounded_box('CargoPlate_Edge',(-.125,0,.561),(1.03,.758,.025),.032,dark,.001)
    rounded_box('CargoPlate_Top',(-.125,0,.575),(1.026,.754,.007),.030,deck,.001)
    for x in [-.59,-.36,-.12,.11,.34]:
        for y in [-.335,.335]:bolt('CargoPlate_CountersunkBolt',(x,y,.5795),.0045,.0012)
    for y in [-.16,.16]:
        for x in [-.59,.34]:bolt('CargoPlate_EndBolt',(x,y,.5795),.0045,.0012)
    for x in [-.40,.10]:
        for y in [-.11,.11]:bolt('CargoPlate_CenterBolt',(x,y,.5795),.0028,.001)

    collection('05_Controller_Cabinet')
    box('Controller_BaseGasket',(.565,0,.521),(.425,.677,.022),black,.006)
    box('Controller_Cabinet',(.565,0,.669),(.390,.644,.312),grey,.009)
    box('Controller_TopCover',(.565,0,.827),(.394,.648,.014),grey,.004)
    face_plate('Controller_FrontPanel',.365,0,.674,.621,.276,.007,grey,.005)
    for y in [-.286,.286]:
        for z in [.550,.797]:bolt('Controller_FrontBolt',(.359,y,z),.0035,.0017,'-X')
    text('Cabinet_AG_Emblem','AG',(.357,.079,.729),.069,chrome)
    # Preserve the visible fine marking as simple narrow strokes at this resolution.
    for i,length in enumerate([.135,.118,.128]):
        face_plate('Cabinet_EmblemMicroline',.357,-.056,.744-i*.011,length,.002,.001,chrome,.0005)
    for sign in [-1,1]:
        y=sign*.326
        box('Cabinet_Door_Gasket',(.575,y,.671),(.302,.008,.256),black,.006)
        box('Cabinet_Door_Panel',(.575,y+sign*.005,.671),(.282,.009,.236),grey2,.005)
        for z in [.578,.766]:
            box('Cabinet_SilverHinge',(.690,y+sign*.012,z),(.018,.010,.024),chrome,.001)
            bolt('Cabinet_HingeScrew',(.689,y+sign*.019,z),.0026,.0012,'-Y' if sign<0 else 'Y')
        box('Cabinet_KeyLock',(.470,y+sign*.012,.659),(.016,.010,.064),black,.004)
        cylinder('Cabinet_Keyhole',(.470,y+sign*.020,.669),.004,.002,chrome,24,'Y')
        for x in [.407,.733]:
            for z in [.545,.803]:bolt('Cabinet_RimScrew',(x,y+sign*.005,z),.003,.0015,'-Y' if sign<0 else 'Y')
    for x in [.399,.732]:
        for y in [-.281,.281]:bolt('Cabinet_TopScrew',(x,y,.836),.0035,.0015)
