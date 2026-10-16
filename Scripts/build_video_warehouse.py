"""Reconstruct the user video as an independent blue digital twin level."""
import json
import math
import traceback
from collections import Counter
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test')
SOURCE=ROOT/'SourceAssets/VideoReference'
DEST='/Game/VideoDigitalTwin'
MAP='/Game/Maps/VideoDigitalTwinWarehouse'
REPORT=ROOT/'Saved/VideoWarehouse_BuildReport.json'
assets=unreal.AssetToolsHelpers.get_asset_tools()
lib=unreal.EditorAssetLibrary
ml=unreal.MaterialEditingLibrary
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
MATS={};MESHES={};RECORDS=[]

def save(asset):
    assert lib.save_loaded_asset(asset,only_if_is_dirty=False),asset.get_path_name()

def node(mat,kind):return ml.create_material_expression(mat,kind)
def scalar(mat,value):
    n=node(mat,unreal.MaterialExpressionConstant);n.set_editor_property('r',float(value));return n
def color(mat,values):
    n=node(mat,unreal.MaterialExpressionConstant3Vector);n.set_editor_property('constant',unreal.LinearColor(*values[:3],1));return n
def link(a,b,pin,output=''):
    assert ml.connect_material_expressions(a,output,b,pin)
def product(mat,a,b):
    n=node(mat,unreal.MaterialExpressionMultiply);link(a,n,'A');link(b,n,'B');return n
def add(mat,a,b):
    n=node(mat,unreal.MaterialExpressionAdd);link(a,n,'A');link(b,n,'B');return n
def prop(n,p,output=''):assert ml.connect_material_property(n,output,p)

def make_material(item):
    name=item['name'];path=DEST+'/Materials/'+name
    m=lib.load_asset(path) if lib.does_asset_exist(path) else assets.create_asset(name,DEST+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
    ml.delete_all_material_expressions(m)
    c=color(m,item['base_color'])
    m.set_editor_property('two_sided',bool(item.get('two_sided', 'opacity' in item or bool(item.get('texture')))))
    volume_height = None
    if name == 'M_VR_WallVolume':
        world = node(m,unreal.MaterialExpressionWorldPosition)
        mask = node(m,unreal.MaterialExpressionComponentMask)
        for channel in ['r','g','a']: mask.set_editor_property(channel,False)
        mask.set_editor_property('b',True);link(world,mask,'')
        volume_height = node(m,unreal.MaterialExpressionSaturate)
        link(product(m,mask,scalar(m,1/280)),volume_height,'')
        tint = node(m,unreal.MaterialExpressionLinearInterpolate)
        link(color(m,[.014,.16,.30]),tint,'A');link(color(m,[.022,.06,.12]),tint,'B');link(volume_height,tint,'Alpha')
        c = tint
    if item.get('unlit'):
        m.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
    else:
        prop(c,unreal.MaterialProperty.MP_BASE_COLOR)
        prop(scalar(m,item.get('roughness',.5)),unreal.MaterialProperty.MP_ROUGHNESS)
        prop(scalar(m,item.get('metallic',0)),unreal.MaterialProperty.MP_METALLIC)
    if item.get('texture'):
        tx=node(m,unreal.MaterialExpressionTextureSample)
        tx.set_editor_property('texture',lib.load_asset(DEST+'/Textures/'+item['texture']))
        prop(tx,unreal.MaterialProperty.MP_EMISSIVE_COLOR,'RGB')
        m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
        prop(tx,unreal.MaterialProperty.MP_OPACITY,'A')
    else:
        emission=float(item.get('emission',1 if item.get('unlit') else 0))
        if emission:
            strength=scalar(m,emission)
            if item.get('pulse'):
                t=node(m,unreal.MaterialExpressionTime)
                wave=node(m,unreal.MaterialExpressionSine);wave.set_editor_property('period',2.0);link(t,wave,'')
                strength=product(m,strength,add(m,scalar(m,.78),product(m,wave,scalar(m,.22))))
            prop(product(m,c,strength),unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        if 'opacity' in item:
            m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
            opacity=scalar(m,item['opacity'])
            if volume_height is not None:
                opacity = node(m,unreal.MaterialExpressionLinearInterpolate)
                link(scalar(m,.40),opacity,'A');link(scalar(m,.15),opacity,'B');link(volume_height,opacity,'Alpha')
            elif item.get('wall_gradient'):
                w=node(m,unreal.MaterialExpressionWorldPosition)
                mask=node(m,unreal.MaterialExpressionComponentMask)
                for channel in ['r','g','a']:mask.set_editor_property(channel,False)
                mask.set_editor_property('b',True);link(w,mask,'')
                inv=node(m,unreal.MaterialExpressionOneMinus);link(product(m,mask,scalar(m,1/310)),inv,'')
                opacity=product(m,opacity,add(m,scalar(m,.3),product(m,inv,scalar(m,.7))))
            prop(opacity,unreal.MaterialProperty.MP_OPACITY)
    ml.recompile_material(m);save(m);MATS[name]=m
    return m

def import_libraries():
    specs=[json.loads((SOURCE/(stem+'.json')).read_text()) for stem in ['storage','robots','architecture']]
    if (SOURCE/'hud.json').is_file():specs.append(json.loads((SOURCE/'hud.json').read_text()))
    if (SOURCE/'walls.json').is_file():specs.append(json.loads((SOURCE/'walls.json').read_text()))
    tex=SOURCE/'T_VR_AlarmPanel.png'
    if tex.is_file():
        task=unreal.AssetImportTask();task.filename=str(tex);task.destination_path=DEST+'/Textures';task.automated=True;task.replace_existing=True;task.save=True
        assets.import_asset_tasks([task])
    for spec in specs:
        for item in spec['materials']:
            if item['name'] not in MATS:make_material(item)
    extras=[
        dict(name='M_VR_Floor',base_color=[.012,.019,.034,1],roughness=.48,metallic=.15),
        dict(name='M_VR_Backdrop',base_color=[.0025,.005,.010,1],roughness=.8),
        dict(name='M_VR_RoomFloor',base_color=[.016,.024,.043,1],roughness=.48,metallic=.1),
        dict(name='M_VR_Grid',base_color=[.012,.054,.078,1],unlit=True,emission=.45),
        dict(name='M_VR_GridDot',base_color=[.03,.27,.34,1],unlit=True,emission=.6),
        dict(name='M_VR_Wall',base_color=[.018,.20,.46,1],opacity=.23,unlit=True,emission=.46,wall_gradient=True,two_sided=True),
        dict(name='M_VR_WallEdge',base_color=[.10,.32,.47,1],unlit=True,emission=.55),
        dict(name='M_VR_RouteInactive',base_color=[.05,.14,.25,1],unlit=True,emission=.5),
        dict(name='M_VR_RouteActive',base_color=[.025,.63,.26,1],unlit=True,emission=.85,pulse=True),
        dict(name='M_VR_RouteTicks',base_color=[.32,.52,.62,1],unlit=True,emission=.65),
        dict(name='M_VR_StatusWhite',base_color=[.78,.90,.94,1],unlit=True,emission=.85),
        dict(name='M_VR_StatusGreen',base_color=[.30,.73,.05,1],unlit=True,emission=.8),
        dict(name='M_VR_StatusRed',base_color=[1,.06,.02,1],unlit=True,emission=1.1,pulse=True),
    ]
    for item in extras:make_material(item)
    for spec in specs:
        for item in spec['meshes']:
            task=unreal.AssetImportTask();task.filename=item['fbx'];task.destination_path=DEST+'/Meshes';task.destination_name=item['name']
            task.automated=True;task.replace_existing=True;task.save=True
            opt=unreal.FbxImportUI();opt.import_mesh=True;opt.import_as_skeletal=False;opt.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
            opt.automated_import_should_detect_type=False;opt.import_materials=False;opt.import_textures=False;opt.import_animations=False
            opt.static_mesh_import_data.combine_meshes=True;opt.static_mesh_import_data.generate_lightmap_u_vs=False
            opt.static_mesh_import_data.auto_generate_collision=False
            opt.static_mesh_import_data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
            opt.static_mesh_import_data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
            task.options=opt;assets.import_asset_tasks([task])
            mesh=lib.load_asset(DEST+'/Meshes/'+item['name']);assert mesh,item['name']
            slots=mesh.get_editor_property('static_materials')
            for i,slot in enumerate(slots):
                name=str(slot.get_editor_property('imported_material_slot_name'))
                if name not in MATS:name=str(slot.get_editor_property('material_slot_name'))
                assert name in MATS,name
                slot.set_editor_property('material_interface',MATS[name]);slots[i]=slot
            mesh.set_editor_property('static_materials',slots);save(mesh);MESHES[item['name']]=mesh
    MESHES['Cube']=lib.load_asset('/Engine/BasicShapes/Cube')

def v(values):return unreal.Vector(*(float(x)*100 for x in values))
def spawn(label,mesh,pos,yaw=0,scale=(1,1,1),category='Architecture',mat=None):
    a=actors.spawn_actor_from_class(unreal.StaticMeshActor,v(pos),unreal.Rotator(pitch=0,yaw=yaw,roll=0))
    a.set_actor_label(label);a.set_folder_path('VideoTwin/'+category)
    c=a.get_component_by_class(unreal.StaticMeshComponent);c.set_static_mesh(MESHES[mesh]);c.set_mobility(unreal.ComponentMobility.STATIC);c.set_collision_profile_name('NoCollision')
    if mat:c.set_material(0,MATS[mat if mat.startswith('M_VR_') else 'M_VR_'+mat])
    a.set_actor_scale3d(unreal.Vector(*scale));a.set_editor_property('tags',['VideoDigitalTwin','TwinId='+label,'Category='+category.split('/')[0]])
    RECORDS.append(dict(id=label,mesh=mesh,position_m=list(pos),yaw=yaw,category=category))
    return a
def box(label,pos,size,mat,category='Architecture',yaw=0):return spawn(label,'Cube',pos,yaw,size,category,mat)
def line(label,points,width,mat,z=.018,category='Routes'):
    for i,(a,b) in enumerate(zip(points,points[1:])):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length>.001:box(label+'_%02d'%i,((a[0]+b[0])/2,(a[1]+b[1])/2,z),(length,width,.006),mat,category,math.degrees(math.atan2(dy,dx)))
def wall(label,a,b,height=2.8):
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);angle=math.degrees(math.atan2(dy,dx));x,y=(a[0]+b[0])/2,(a[1]+b[1])/2
    mesh_name='SM_VR_Wall_'+label
    if mesh_name in MESHES:
        return spawn(label,mesh_name,(x,y,height/2),angle,category='Architecture/TransparentPartitions')
    box(label,(x,y,height/2),(length,.035,height),'Wall','Architecture/TransparentPartitions',angle)
    for z in [.025,height-.012]:
        box(label+'_Rim'+str(z),(x,y,z),(length,.014,.014),'WallEdge','Architecture/Outlines',angle)
    for i,p in enumerate([a,b]):box(label+'_Post'+str(i),(p[0],p[1],height/2),(.018,.018,height),'WallEdge','Architecture/Outlines')

def create_architecture():
    box('DigitalTwin_DarkSurround',(0,0,-.17),(100,90,.16),'Backdrop','Architecture/Ground')
    for x in range(-48,49,2):line('GridX%d'%x,[(x,-42),(x,42)],.008,'Grid',-.080,'Architecture/Grid')
    for y in range(-42,43,2):line('GridY%d'%y,[(-48,y),(48,y)],.008,'Grid',-.080,'Architecture/Grid')
    for x in range(-40,41,4):
        for y in range(-36,37,4):box('GridPoint_%d_%d'%(x,y),(x,y,-.075),(.048,.048,.008),'GridDot','Architecture/Grid')
    box('Warehouse_Footprint',(0,0,-.075),(36,26,.14),'Floor','Architecture/Ground')
    for label,pos,size in [('RackRoom',(-10.5,-1.5,-.003),(13,11,.008)),('RearPalletRoom',(-10.5,8.1,-.003),(13,7.6,.008)),('EastGridRoom',(10,2.5,-.003),(16,7,.008)),('FrontGridRoom',(12,-8,-.003),(12,10,.008)),('TransferRoom',(.5,-10,-.003),(9,6,.008))]:box(label+'_Floor',pos,size,'RoomFloor','Architecture/Ground')
    segments=[
        ('Outer_West',(-18,-7),(-18,13)),('Outer_Back',(-18,13),(18,13)),('Outer_East',(18,13),(18,-13)),
        ('Outer_FrontA',(-18,-7),(-4,-7)),('Outer_FrontB',(-4,-13),(18,-13)),
        ('RackBack',(-18,4),(-4,4)),('RackToCorridorA',(-4,-7),(-4,-4.5)),('RackToCorridorB',(-4,-1.5),(-4,4)),
        ('PalletToCorridorA',(-4,4),(-4,7.3)),('PalletToCorridorB',(-4,10.3),(-4,13)),
        ('RearRoomBack',(1,9),(18,9)),('RearRoomSideA',(1,6),(1,13)),('RearRoomSideB',(5,6),(5,13)),('RearRoomSideC',(9,6),(9,13)),('RearRoomFrontA',(1,6),(3,6)),('RearRoomFrontB',(6,6),(9,6)),
        ('EastGridSideA',(1,-1),(1,1.0)),('EastGridSideB',(1,4),(1,6)),('EastGridBack',(9,6),(18,6)),
        ('EastGridDivider',(1,-1),(18,-1)),
        ('TransferWest',(-4,-13),(-4,-10.7)),('TransferWestB',(-4,-7.7),(-4,-7)),('TransferBack',(-4,-7),(-.8,-7)),('TransferBackB',(2.2,-7),(5,-7)),('TransferEast',(5,-7),(5,-13)),
        ('FrontGridBack',(6,-3),(18,-3)),('FrontGridWest',(6,-13),(6,-10)),
    ]
    for name,a,b in segments:wall(name,a,b)
    spawn('LIFT_02_BlueElevator','SM_VR_Elevator',(-1.5,11.0,.005),category='Architecture/Elevator')
    for name,pos,yaw in [('GATE_Rack',(-4,-3,.01),90),('GATE_UpperCrossing',(1,2.5,.01),90),('GATE_Transfer',(.7,-7,.01),0)]:spawn(name,'SM_VR_Gate',pos,yaw,category='Architecture/Gates')
    spawn('CTRL_UpperCrossing','SM_VR_ControlCabinet',(1.35,4.0,0),90,category='Architecture/Gates')
    spawn('CONVEYOR_FrontTransfer','SM_VR_Conveyor',(-1.6,-11.6,.0),90,category='Equipment/Conveyor')

def pad(label,pos,ap=False):return spawn(label,'SM_VR_AP_Pad' if ap else 'SM_VR_LM_Pad',(pos[0],pos[1],.012),category='Locations/Pads')
def pallet(label,pos):return spawn(label,'SM_VR_PalletCargo',(pos[0],pos[1],.02),category='Equipment/Cargo')
def create_storage_and_routes():
    for row,y in enumerate([-5.6,-3.1,-.6,1.9]):
        for bay in range(8):spawn('RACK_%02d_%02d'%(row+1,bay+1),'SM_VR_RackBay',(-16.9+bay*1.55,y,0),category='Equipment/Racks')
    for i,x in enumerate([-16.2,-13.8,-11.4,-9.0,-6.6]):
        for j,y in enumerate([5.35,8.35,11.25]):pad('WEST_LM_%d_%d'%(i,j),(x,y),j==2 and i in [0,3])
        for j,y in enumerate([6.55,10.35]):
            if (i,j) not in [(2,0),(3,1)]:pallet('PAL_West_%d_%d'%(i,j),(x,y))
        line('WestSpur%d'%i,[(x,5.35),(x,11.25)],.075,'RouteInactive')
    for y in [5.35,8.35,11.25]:line('WestCross'+str(y),[(-16.2,y),(-6.6,y)],.075,'RouteInactive')
    for i,x in enumerate([3.4,5.9,8.4,10.9,13.4,15.9]):
        for j,y in enumerate([-.05,2.15,4.35]):pad('EAST_LM_%d_%d'%(i,j),(x,y),i in [1,4] and j==2)
        if i!=3:pallet('PAL_East_%02d'%i,(x,5.05))
        line('EastSpur%d'%i,[(x,-.05),(x,4.35)],.075,'RouteInactive')
    for y in [-.05,2.15,4.35]:line('EastCross'+str(y),[(3.4,y),(15.9,y)],.075,'RouteInactive')
    for i,x in enumerate([7.2,9.6,12,14.4,16.8]):
        for j,y in enumerate([-12,-9.7,-7.4,-5.1]):pad('FRONT_LM_%d_%d'%(i,j),(x,y),j in [1,3] and i%2==0)
        for j,y in enumerate([-11.15,-4.3]):
            if (i,j) not in [(2,0),(3,1)]:pallet('PAL_Front_%d_%d'%(i,j),(x,y))
        line('FrontSpur%d'%i,[(x,-12),(x,-5.1)],.075,'RouteInactive')
    for y in [-12,-9.7,-7.4,-5.1]:line('FrontCross'+str(y),[(7.2,y),(16.8,y)],.075,'RouteInactive')
    for i,p in enumerate([(-1.7,-9),(.5,-9),(2.7,-9),(-1.7,-11.1),(.5,-11.1),(2.7,-11.1)]):
        pad('TRANSFER_LM%d'%i,p,i==2)
        if i in [1,2,5]:pallet('PAL_Transfer%d'%i,(p[0],p[1]+.55))
    line('MainCorridor',[(-1.7,-12),(-1.7,8.0),(-1.0,8.6),(-1.0,10.0)],.10,'RouteInactive')
    for i,y in enumerate([-6,-2,2,6]):pad('MAIN_LM%d'%i,(-1.7,y))
    line('CrossCorridor',[(-4,-3),(-1.7,-3),(2.5,-3),(2.5,2.15),(15.9,2.15)],.08,'RouteInactive')
    line('Active_GreenRoute',[(6,-.05),(12.5,-.05),(12.7,.15),(12.7,4.35)],.12,'RouteActive',.030,'Holograms/ActiveRoute')
    for i in range(15):line('RouteDot%d'%i,[(12.7,4.5+i*.12),(12.7,4.55+i*.12)],.035,'StatusGreen',.032,'Holograms/ActiveRoute')
    spawn('TARGET_ActiveRoute','SM_VR_TargetMarker',(12.7,4.35,0),category='Holograms/Targets')
    line('Active_AvoidanceRoute',[(8.1,-7.5),(10.2,-7.5),(10.9,-8.4),(12.0,-8.4),(12.5,-7.5),(16.8,-7.5)],.11,'RouteActive',.031,'Holograms/ActiveRoute')
    # Direction ticks repeat subtly along the inactive route network.
    for i in range(20):
        x=3.6+i*.62
        line('DirectionTick%d'%i,[(x-.06,2.08),(x,2.15),(x-.06,2.22)],.012,'RouteTicks',.025,'Routes/DirectionTicks')

def label_text(name,body,pos,size=.24,tint=(215,231,241,255)):
    a=actors.spawn_actor_from_class(unreal.TextRenderActor,v(pos))
    a.set_actor_label(name);a.set_folder_path('VideoTwin/Annotations')
    c=a.get_component_by_class(unreal.TextRenderComponent)
    c.set_text(body);c.set_world_size(size*100);c.set_text_render_color(unreal.Color(*tint));c.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    camera=unreal.Vector(-3500,-4200,3900)
    a.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(a.get_actor_location(),camera),False)
    return a

def robot(name,mesh,pos,yaw=0,loaded=False,status=True):
    a=spawn(name,mesh,pos,yaw,category='Equipment/Robots')
    if loaded:
        r=math.radians(yaw);spawn(name+'_Load','SM_VR_PalletCargo',(pos[0]+1.0*math.sin(r),pos[1]-1.0*math.cos(r),.12),category='Equipment/Cargo')
    if status:
        spawn(name+'_StatusRing','SM_VR_StatusRing',(pos[0],pos[1],.014),category='Holograms/StatusRings')
    height=2.9 if mesh=='SM_VR_WhiteRackRobot' else 2.15
    label_text(name+'_Label',name,(pos[0],pos[1],height),.22)
    if name!='DN-1':label_text(name+'_State','0.35 m/s   79%',(pos[0],pos[1],height-.23),.115,(130,180,96,255))
    return a

def create_robots():
    robot('CDD14-1','SM_VR_BlueStacker',(6,-.05,.025),90,True)
    robot('CDD14-2','SM_VR_BlueStacker',(-1.4,-9.8,.025),0,False)
    robot('CDD14-4','SM_VR_BlueStacker',(-10,10.8,.025),90,False)
    selected=robot('CDD14-3','SM_VR_BlueStacker',(4.0,6.8,.025),15,False)
    robot('CBD50-1','SM_VR_OrangeTransporter',(9.7,-7.6,.025),35,True)
    spawn('CONE_AvoidanceObstacle','SM_VR_TrafficCone',(11.3,-7.2,.02),category='Equipment/Obstacles')
    spawn('SCAN_AvoidanceFan','SM_VR_ScanFan',(9.7,-7.6,.03),105,category='Holograms/Scanning')
    robot('HR-1','SM_VR_WhiteRackRobot',(-7.0,-4.3,.025),90,False)
    robot('DN-1','SM_VR_AlarmRobot',(-10.8,8.2,.025),20,False,False)
    spawn('ALARM_DN1_Ring','SM_VR_AlarmRing',(-10.8,8.2,.01),category='Holograms/Alarm')
    if 'SM_VR_AlarmPanel' in MESHES:
        spawn('ALARM_DN1_DiagnosticPanel','SM_VR_AlarmPanel',(-8.8,8.5,1.7),-40,category='Holograms/Alarm')
    else:label_text('DN1_AlarmText','ERROR 50001\nVEHICLE FAULT',(-8.8,8.5,1.5),.19,(255,65,20,255))
    label_text('DN1_AlarmStatus','0.00 m/s   5%',(-10.8,8.2,1.7),.12,(255,65,20,255))
    return selected

def light(kind,name,pos,rotation,intensity,color_value,**settings):
    a=actors.spawn_actor_from_class(kind,v(pos),unreal.Rotator(**rotation));a.set_actor_label(name);a.set_folder_path('VideoTwin/Lighting')
    c=a.get_component_by_class(unreal.LightComponent);c.set_mobility(unreal.ComponentMobility.MOVABLE);c.set_intensity(intensity)
    c.set_light_color(unreal.LinearColor(*color_value,1))
    for k,value in settings.items():c.set_editor_property(k,value)
    return a

def create_lighting_and_cameras():
    light(unreal.DirectionalLight,'Cool_Overhead_Key',(0,0,20),dict(pitch=-62,yaw=-25,roll=0),.22,(.64,.76,1.0),light_source_angle=6.0)
    for i,(x,y) in enumerate([(-11,-2),(-11,8),(10,1),(11,-9)]):
        light(unreal.RectLight,'Softbox_Cool_%d'%i,(x,y,8),dict(pitch=-90,yaw=0,roll=0),110,(.64,.77,1),source_width=1100.0,source_height=850.0,attenuation_radius=1900.0)
    light(unreal.RectLight,'Elevator_Cyan_Spill',(-1.5,9.8,2.65),dict(pitch=-60,yaw=-90,roll=0),50,(.1,.55,1),source_width=170.0,source_height=75.0,attenuation_radius=550.0)
    light(unreal.PointLight,'Selected_Robot_Cyan',(4.0,6.8,.7),dict(pitch=0,yaw=0,roll=0),4,(.04,.55,1),attenuation_radius=180.0,source_radius=12.0)
    post=actors.spawn_actor_from_class(unreal.PostProcessVolume,unreal.Vector(0,0,0));post.set_actor_label('VideoTwin_Look');post.set_folder_path('VideoTwin/Lighting');post.set_editor_property('unbound',True)
    settings=post.get_editor_property('settings')
    for field,value in [('auto_exposure_min_brightness',0.0),('auto_exposure_max_brightness',0.0),('auto_exposure_bias',0.0),('bloom_intensity',.22),('vignette_intensity',.15),('motion_blur_amount',0.0),('film_grain_intensity',0.0)]:
        settings.set_editor_property('override_'+field,True);settings.set_editor_property(field,value)
    post.set_editor_property('settings',settings)
    views=[('Overview',(-35,-42,39),(0,0,.2),46),('Route',(-2,-12,15),(9.7,1.8,.4),45),('Racks',(-26,-17,15),(-10.3,-1.7,1.0),43),('Alarm',(-21,-4,14),(-10.8,8.2,.2),43),('Elevator',(-11,-3,11),(-1.5,10.8,1.0),42)]
    for name,pos,target,fov in views:
        a=actors.spawn_actor_from_class(unreal.CameraActor,v(pos),unreal.MathLibrary.find_look_at_rotation(v(pos),v(target)))
        a.set_actor_label('CAM_Video_'+name);a.set_folder_path('VideoTwin/Cameras')
        c=a.get_component_by_class(unreal.CameraComponent);c.set_field_of_view(fov);c.set_editor_property('constrain_aspect_ratio',False)
        if name=='Overview':unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(a.get_actor_location(),a.get_actor_rotation())

def main():
    import_libraries()
    assert levels.new_level(MAP),'Could not create independent video map'
    create_architecture();create_storage_and_routes();create_robots();create_lighting_and_cameras()
    actors.set_selected_level_actors([])
    assert levels.save_current_level();assert lib.save_directory(DEST,only_if_is_dirty=False,recursive=True)
    (SOURCE/'scene_registry.json').write_text(json.dumps(RECORDS,indent=2),encoding='utf-8')
    report=dict(success=True,map=MAP,actor_count=len(actors.get_all_level_actors()),mesh_count=len(MESHES)-1,material_count=len(MATS),registered_actors=len(RECORDS),categories=dict(Counter(r['category'].split('/')[0] for r in RECORDS)),scale='Estimated using 1.2 x 1.0 m pallet; no measured dimensions in video',scope='Blue digital twin warehouse only; control room excluded',live_telemetry=False)
    REPORT.write_text(json.dumps(report,indent=2),encoding='utf-8');unreal.log('VIDEO_WAREHOUSE_BUILD_COMPLETE '+json.dumps(report))

try:main()
except Exception:
    REPORT.write_text(json.dumps(dict(success=False,error=traceback.format_exc()),indent=2),encoding='utf-8');raise
