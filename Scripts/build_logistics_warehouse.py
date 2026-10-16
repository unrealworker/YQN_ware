"""Assemble the authorized logistics park as a separate UE 5.4 map."""
import json
import math
import random
import traceback
from collections import Counter
from pathlib import Path
import unreal

ROOT = Path(r"D:\UEPro\Test")
SOURCE = ROOT / "SourceAssets/LogisticsWarehouse"
DEST = "/Game/LogisticsWarehouse"
MAP = "/Game/Maps/LogisticsWarehouse"
REPORT = ROOT / "Saved/Warehouse_BuildReport.json"
random.seed(17)
assets = unreal.AssetToolsHelpers.get_asset_tools()
lib = unreal.EditorAssetLibrary
ml = unreal.MaterialEditingLibrary
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
MATS = {}
MESHES = {}
RECORDS = []

def expression(mat, cls, x=0, y=0):
    return ml.create_material_expression(mat, cls, x, y)

def scalar(mat, value, prop=None):
    node = expression(mat, unreal.MaterialExpressionConstant)
    node.set_editor_property("r", value)
    if prop is not None:
        ml.connect_material_property(node, "", prop)
    return node

def vector(mat, color):
    node = expression(mat, unreal.MaterialExpressionConstant3Vector)
    node.set_editor_property("constant", unreal.LinearColor(*color[:3], 1))
    return node

def connect(a, b, input_name, output=""):
    # MaterialEditingLibrary uses shortened graph pin names in UE 5.4.
    pin = {"Coordinates": "UVs", "Input": ""}.get(input_name, input_name)
    assert ml.connect_material_expressions(a, output, b, pin), (a.get_name(), b.get_name(), pin)

def make_material(item):
    name = item["name"]
    path = DEST + "/Materials/" + name
    mat = lib.load_asset(path) if lib.does_asset_exist(path) else assets.create_asset(name, DEST + "/Materials", unreal.Material, unreal.MaterialFactoryNew())
    ml.delete_all_material_expressions(mat)
    mat.set_editor_property("two_sided", bool(item.get("two_sided") or item.get("glass")))
    color = vector(mat, item["base_color"])
    base = color
    texture_role = item.get("texture_role")
    texture_names = {"concrete":"T_Concrete_Poured", "metal":"T_Metal_Steel", "wood":"T_Wood_Pine", "bark":"T_Wood_Oak", "asphalt":"T_Ground_Gravel", "grass":"T_Ground_Grass", "gravel":"T_Ground_Gravel"}
    if texture_role in texture_names:
        tex_base = "/Game/StarterContent/Textures/" + texture_names[texture_role]
        texture = lib.load_asset(tex_base + "_D")
        tex = expression(mat, unreal.MaterialExpressionTextureSample, -800, 0)
        tex.set_editor_property("texture", texture)
        if item.get("world_xy"):
            world = expression(mat, unreal.MaterialExpressionWorldPosition)
            mask = expression(mat, unreal.MaterialExpressionComponentMask)
            mask.set_editor_property("r", True); mask.set_editor_property("g", True)
            connect(world, mask, "Input")
            uv = expression(mat, unreal.MaterialExpressionMultiply)
            connect(mask, uv, "A"); connect(scalar(mat, item.get("uv_per_cm", .003)), uv, "B")
        else:
            uv = expression(mat, unreal.MaterialExpressionTextureCoordinate)
            uv.set_editor_property("u_tiling", 1.0); uv.set_editor_property("v_tiling", 1.0)
        connect(uv, tex, "Coordinates")
        desat = expression(mat, unreal.MaterialExpressionDesaturation)
        connect(tex, desat, "Input", "RGB")
        connect(scalar(mat, 0.7 if texture_role in {"wood", "grass", "bark"} else 1.0), desat, "Fraction")
        product = expression(mat, unreal.MaterialExpressionMultiply)
        connect(desat, product, "A"); connect(color, product, "B")
        base = expression(mat, unreal.MaterialExpressionLinearInterpolate)
        connect(color, base, "A"); connect(product, base, "B")
        connect(scalar(mat, .75 if texture_role in {"grass", "asphalt", "gravel"} else .42), base, "Alpha")
        normal = lib.load_asset(tex_base + "_N") if lib.does_asset_exist(tex_base + "_N") else None
        if normal:
            ntex = expression(mat, unreal.MaterialExpressionTextureSample, -800, 250)
            ntex.set_editor_property("texture", normal)
            ntex.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
            connect(uv, ntex, "Coordinates")
            ml.connect_material_property(ntex, "RGB", unreal.MaterialProperty.MP_NORMAL)
    ml.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    scalar(mat, item.get("roughness", .65), unreal.MaterialProperty.MP_ROUGHNESS)
    scalar(mat, item.get("metallic", 0), unreal.MaterialProperty.MP_METALLIC)
    if item.get("glass"):
        mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        scalar(mat, .62, unreal.MaterialProperty.MP_OPACITY)
        scalar(mat, .75, unreal.MaterialProperty.MP_SPECULAR)
    if item.get("foliage"):
        mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
        ml.connect_material_property(color, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    if item.get("emission"):
        emit = expression(mat, unreal.MaterialExpressionMultiply)
        connect(color, emit, "A"); connect(scalar(mat, float(item["emission"])), emit, "B")
        ml.connect_material_property(emit, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    ml.recompile_material(mat)
    assert lib.save_loaded_asset(mat)
    MATS[name] = mat
    return mat

def import_assets():
    specs = [json.loads((SOURCE / filename).read_text(encoding="utf-8")) for filename in ["architecture.json", "vehicles.json", "vegetation.json", "site_details.json"]]
    for spec in specs:
        for item in spec["materials"]:
            if item["name"] not in MATS:
                make_material(item)
    extra = [
        ("Asphalt", (.12,.13,.14), .93, "asphalt"),
        ("ApronConcrete", (.53,.54,.52), .86, "concrete"),
        ("Sidewalk", (.62,.59,.52), .82, "concrete"),
        ("LandscapeGrass", (.17,.25,.075), .95, "grass"),
        ("GravelShoulder", (.36,.34,.29), .94, "gravel"),
        ("RoadWhite", (.83,.83,.76), .78, None),
        ("RoadYellow", (.92,.58,.035), .77, None),
        ("DrainDark", (.035,.042,.044), .8, None),
        ("SignNavy", (.018,.065,.09), .55, None),
        ("SignWhite", (.83,.87,.87), .5, None),
        ("LandscapingSoil", (.095,.06,.032), .97, "gravel"),
    ]
    for name, color, roughness, role in extra:
        make_material(dict(name="M_WH_"+name, base_color=[*color,1], roughness=roughness, metallic=0, texture_role=role, world_xy=True))
    for spec in specs:
        for item in spec["meshes"]:
            path = DEST + "/Meshes/" + item["name"]
            if lib.does_asset_exist(path):
                mesh = lib.load_asset(path)
            else:
                task = unreal.AssetImportTask()
                task.filename = item["fbx"]
                task.destination_path = DEST + "/Meshes"
                task.destination_name = item["name"]
                task.automated = True; task.replace_existing = True; task.save = True
                opt = unreal.FbxImportUI()
                opt.import_mesh = True; opt.import_as_skeletal = False
                opt.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
                opt.automated_import_should_detect_type = False
                opt.import_materials = False; opt.import_textures = False; opt.import_animations = False
                data = opt.static_mesh_import_data
                data.combine_meshes = True; data.generate_lightmap_u_vs = False
                data.auto_generate_collision = False
                data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
                data.normal_generation_method = unreal.FBXNormalGenerationMethod.BUILT_IN
                task.options = opt
                assets.import_asset_tasks([task])
                mesh = lib.load_asset(path)
            assert isinstance(mesh, unreal.StaticMesh), path
            slots = mesh.get_editor_property("static_materials")
            for index, slot in enumerate(slots):
                name = str(slot.get_editor_property("imported_material_slot_name"))
                if name not in MATS:
                    name = str(slot.get_editor_property("material_slot_name"))
                assert name in MATS, name
                slot.set_editor_property("material_interface", MATS[name])
                slots[index] = slot
            mesh.set_editor_property("static_materials", slots)
            assert lib.save_loaded_asset(mesh,only_if_is_dirty=False)
            MESHES[item["name"]] = mesh
    MESHES["Cube"] = lib.load_asset("/Engine/BasicShapes/Cube")
    MESHES["Cylinder"] = lib.load_asset("/Engine/BasicShapes/Cylinder")
    MESHES["Bush"] = lib.load_asset("/Game/StarterContent/Props/SM_Bush")
    MESHES["Rock"] = lib.load_asset("/Game/StarterContent/Props/SM_Rock")

def vmetres(values):
    return unreal.Vector(*(float(x)*100 for x in values))

def spawn(name, mesh_name, loc, yaw=0, scale=(1,1,1), category="Site", mat=None, collision=False):
    actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, vmetres(loc), unreal.Rotator(pitch=0,yaw=yaw,roll=0))
    actor.set_actor_label(name)
    actor.set_folder_path(category)
    comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    comp.set_mobility(unreal.ComponentMobility.STATIC)
    comp.set_static_mesh(MESHES[mesh_name])
    actor.set_actor_scale3d(unreal.Vector(*scale))
    comp.set_collision_profile_name("BlockAll" if collision else "NoCollision")
    if mat:
        comp.set_material(0, MATS[mat] if isinstance(mat,str) else mat)
    actor.set_editor_property("tags", ["LogisticsWarehouse", "TwinId="+name, "Category="+category.split("/")[0]])
    RECORDS.append(dict(id=name, category=category, mesh=mesh_name, position_m=list(loc), yaw=yaw))
    return actor

def box(name, loc, size, mat, category="Site", yaw=0, collision=True):
    return spawn(name, "Cube", loc, yaw, size, category, "M_WH_"+mat, collision)

def strip(name, a, b, width=.12, mat="RoadWhite", z=.065):
    dx,dy=b[0]-a[0],b[1]-a[1]
    return box(name, ((a[0]+b[0])/2,(a[1]+b[1])/2,z), (math.hypot(dx,dy),width,.012), mat, "Roads/Markings", math.degrees(math.atan2(dy,dx)), False)

def arrow(name,x,y,yaw=0):
    # White directional arrow assembled from a shaft and two angled strokes.
    def p(a,b):
        r=math.radians(yaw)
        return (x+a*math.cos(r)-b*math.sin(r), y+a*math.sin(r)+b*math.cos(r))
    strip(name+"_Shaft",p(-1.8,0),p(1.4,0),.24)
    strip(name+"_HeadL",p(1.4,0),p(.2,.85),.24)
    strip(name+"_HeadR",p(1.4,0),p(.2,-.85),.24)

def text(name, value, loc, size=.5, yaw=90, color=(220,225,225)):
    actor=actors.spawn_actor_from_class(unreal.TextRenderActor, vmetres(loc), unreal.Rotator(pitch=0,yaw=yaw,roll=0))
    actor.set_actor_label(name); actor.set_folder_path("Signs")
    comp=actor.get_component_by_class(unreal.TextRenderComponent)
    comp.set_text(value); comp.set_world_size(size*100)
    comp.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    comp.set_text_render_color(unreal.Color(*color,255))
    actor.set_editor_property("tags",["LogisticsWarehouse","TwinId="+name])
    RECORDS.append(dict(id=name,category="Signs",position_m=list(loc)))
    return actor

def light(name, loc, color=(1,.86,.63), intensity=8000, radius=20):
    actor=actors.spawn_actor_from_class(unreal.PointLight, vmetres(loc))
    actor.set_actor_label(name); actor.set_folder_path("Lighting/Practical")
    comp=actor.get_component_by_class(unreal.PointLightComponent)
    comp.set_mobility(unreal.ComponentMobility.MOVABLE)
    comp.set_intensity(intensity)
    comp.set_light_color(unreal.LinearColor(*color,1))
    comp.set_attenuation_radius(radius*100)
    comp.set_cast_shadows(False)
    return actor

def make_scene():
    if lib.does_asset_exist(MAP):
        assert levels.load_level(MAP)
    else:
        assert levels.new_level_from_template(MAP,"/Engine/Maps/Templates/Template_Default")
    for a in actors.get_all_level_actors():
        if isinstance(a, unreal.StaticMeshActor) or "LogisticsWarehouse" in [str(t) for t in a.tags] or str(a.get_folder_path()).startswith("Lighting/Practical"):
            actors.destroy_actor(a)
    # Preserve the template's calibrated sun, sky and skylight; expand to a site scale.
    for a in actors.get_all_level_actors():
        if isinstance(a, unreal.DirectionalLight):
            a.set_actor_rotation(unreal.Rotator(pitch=-38,yaw=-32,roll=0),False)
            c=a.get_component_by_class(unreal.DirectionalLightComponent)
            c.set_mobility(unreal.ComponentMobility.MOVABLE)
            c.set_intensity(60000)
            c.set_light_color(unreal.LinearColor(1,.955,.87,1))
            c.set_atmosphere_sun_light(True)
            c.set_atmosphere_sun_light_index(0)
            a.set_actor_label("Sun_LateAfternoon")
        if isinstance(a, unreal.SkyLight):
            c=a.get_component_by_class(unreal.SkyLightComponent)
            c.set_mobility(unreal.ComponentMobility.MOVABLE)
            c.set_intensity(1.15)
            c.set_editor_property("real_time_capture",True)
    setup_daylight_sky()
    box("Terrain_Context",(0,0,-.3),(1400,1400,.5),"LandscapeGrass","Landscape/Ground")
    box("Site_GravelBase",(0,10,-.04),(240,180,.08),"GravelShoulder","Landscape/Ground")
    box("South_Lawn",(0,-49,-.005),(190,20,.09),"LandscapeGrass","Landscape/Ground")
    box("West_Lawn",(-89,6,-.005),(17,138,.09),"LandscapeGrass","Landscape/Ground")
    box("North_Lawn",(0,99,-.005),(238,10,.09),"LandscapeGrass","Landscape/Ground")
    box("East_Lawn",(116,11,-.005),(8,161,.09),"LandscapeGrass","Landscape/Ground")
    box("Office_Lawn",(70,-39,-.005),(48,32,.09),"LandscapeGrass","Landscape/Ground")
    for name,loc,size in [
        ("Road_North",(0,85,.005),(222,12,.1)),("Road_South",(0,-65,.005),(222,12,.1)),
        ("Road_West",(-105,10,.005),(12,150,.1)),("Road_East",(105,10,.005),(12,150,.1)),
        ("Road_ParkingAccess",(88,20,.005),(8,118,.1)),("Road_Entrance",(85,103,.005),(14,26,.1)),
        ("Truck_Apron",(-20,48,.01),(124,62,.12)),("Office_Parking",(68,25,.005),(28,102,.1)),
        ("Fire_Access_West",(-76,-10,.005),(10,77,.1)),("Fire_Access_South",(-20,-44,.005),(122,9,.1)),
        ("Fire_Access_Connector",(-76,-52,.005),(10,22,.1)),("Container_Hardstand",(-89,-10,.005),(11,50,.1))]:
        box(name,loc,size,"ApronConcrete" if name=="Truck_Apron" else "Asphalt","Roads/Surfaces")
    # Panel joints in the concrete apron are narrow, dark and flush.
    for i,x in enumerate(range(-80,43,8)):
        box("ApronJointX_%02d"%i,(x,48,.074),(.018,62,.006),"DrainDark","Roads/ExpansionJoints",collision=False)
    for i,y in enumerate(range(18,80,8)):
        box("ApronJointY_%02d"%i,(-20,y,.074),(124,.018,.006),"DrainDark","Roads/ExpansionJoints",collision=False)
    # Curbs and pedestrian paths.
    box("Office_Sidewalk",(43,18.4,.11),(25,3.4,.22),"Sidewalk","Roads/Sidewalks")
    box("Office_EntryLanding",(43,14,.11),(5,8,.22),"Sidewalk","Roads/Sidewalks")
    box("Office_EntranceWalk",(43,34,.1),(3,30,.2),"Sidewalk","Roads/Sidewalks")
    for x in [-111.5,-98.5,98.5,111.5]:
        box("Curb_X_"+str(x),(x,10,.14),(.28,137 if abs(x)<100 else 161,.28),"Sidewalk","Roads/Curbs")
    for y in [-71.5,-58.5,78.5,91.5]:
        spans={-71.5:[(-111,111)],-58.5:[(-98.5,-81),(-71,98.5)],
               78.5:[(-98.5,-82),(42,54),(92,98.5)],91.5:[(-111,75),(95,111)]}[y]
        for lo,hi in spans:
            box("Curb_Y_%s_%s"%(y,lo),((lo+hi)/2,y,.14),(hi-lo,.28,.28),"Sidewalk","Roads/Curbs")
    for y in [-65,85]:
        for x in range(-96,99,9):
            strip("RoadDash_%s_%s"%(x,y),(x,y),(x+4,y),.14)
        for offset in [-5.2,5.2]:
            strip("RoadEdge_%s_%s"%(y,offset),(-98,y+offset),(98,y+offset),.13)
    for x in [-105,105]:
        for y in range(-50,73,9):
            strip("RoadDash_%s_%s"%(x,y),(x,y),(x,y+4),.14)
    for n,(x,y,r) in enumerate([(-65,88,0),(25,88,0),(64,82,180),(-38,82,180),(-105,-24,90),(105,35,-90),(25,-62,180)]):
        arrow("TrafficArrow%02d"%n,x,y,r)
    # Zebra crossings near office and gate.
    for crossing,x0,y0 in [("Office",88,50),("Gate",85,94)]:
        for i in range(8):
            box(crossing+"Crosswalk%02d"%i,(x0-3.5+i,y0,.067),(.5,4,.014),"RoadWhite","Roads/Markings",collision=False)

    shell=spawn("WH01_MainWarehouse","SM_WarehouseShell",(-20,-10,0),category="Buildings/Warehouse")
    box("WH01_FloorCollision",(-20,-10,1.09),(95.4,53.4,.20),"ApronConcrete","Buildings/Warehouse")
    roof=spawn("WH01_RemovableRoof","SM_WarehouseRoof",(-20,-10,0),category="Buildings/Warehouse_Roof")
    roof.set_editor_property("tags",["LogisticsWarehouse","TwinId=WH01_RemovableRoof","RemovableRoof"])
    spawn("OFF01_OperationsOffice","SM_OfficeAnnex",(43,-2,0),category="Buildings/Office")
    # Independent safety signs at every dock; imported frontage faces UE +Y.
    for i in range(10):
        x=-60.5+9*i
        box("DockSignBoard%02d"%(i+1),(x,18.08,6.1),(1.6,.10,.8),"SignNavy","Signs")
        text("DockLabel%02d"%(i+1),"%02d"%(i+1),(x,18.15,5.82),.56)
        strip("DockLaneL%02d"%i,(x-2,18.6),(x-2,40),.14,"RoadYellow",.078)
        strip("DockLaneR%02d"%i,(x+2,18.6),(x+2,40),.14,"RoadYellow",.078)
        strip("DockStop%02d"%i,(x-2,40),(x+2,40),.18,"RoadYellow",.078)
        box("DockDrain%02d"%i,(x,19.2,.079),(4.8,.26,.018),"DrainDark","Site/Drainage",collision=False)
        for xx in [x-2.3,x+2.3]:
            spawn("DockBollard_%02d_%s"%(i,xx),"Cylinder",(xx,19.3,.55),scale=(.16,.16,1.1),category="Site/Safety",mat="M_WH_RoadYellow",collision=True)
    box("Warehouse_FasciaSign",(-20,17.58,10.1),(29,.16,1.8),"SignNavy","Signs")
    text("Warehouse_Name","NORTHPOINT  /  LOGISTICS",(-20,17.69,9.67),.95)
    text("Office_Name","OPERATIONS",(43,8.17,7.1),.65)

    for index in [0,2,5,8]:
        spawn("TRK_%02d_Docked"%(index+1),"SM_SemiTruck",(-60.5+index*9,26.05,.08),90,category="Vehicles/Trucks")
    spawn("TRK_11_Arrival","SM_SemiTruck",(18,65,.07),180,category="Vehicles/Trucks")
    spawn("VAN_01","SM_DeliveryVan",(70,53,.06),90,category="Vehicles/Vans")
    spawn("VAN_02","SM_DeliveryVan",(-39,71,.08),0,category="Vehicles/Vans")
    spawn("FLT_01_Loading","SM_Forklift",(-24,44,.08),-35,category="Vehicles/Forklifts")
    spawn("FLT_02_Storage","SM_Forklift",(8,-4,1.2),0,category="Vehicles/Forklifts")
    # Warehouse rack rows retain independent stable identifiers for twin data binding.
    for row,y in enumerate([-28,-17,-6,5]):
        for bay in range(16):
            x=-62+bay*5.4
            spawn("RACK_%s_%02d"%(chr(65+row),bay+1),"SM_RackUnit",(x,y,1.2),category="Storage/Racks")
            for tier,z in enumerate([2.055,4.105,6.155]):
                for half in [-.66,.66]:
                    if random.random()>.12:
                        spawn("PAL_%d_%02d_%d_%s"%(row,bay,tier,"L" if half<0 else "R"),"SM_LoadedPallet",(x+half,y,z+1.2),scale=(.94,.94,.9),category="Storage/Pallets")
    for i,(x,y) in enumerate([(-18,41),(-16,41),(-14,41),(-42,43),(-44,43),(18,45)]):
        spawn("STAGE_Pallet_%02d"%i,"SM_LoadedPallet",(x,y,.08),category="Storage/Staging")
    spawn("EMPTY_Pallets","SM_PalletStack",(-11,42,.08),category="Storage/Staging")
    for i,y in enumerate([-26,-15,-4,7]):
        spawn("CONT_%02d"%(i+1),"SM_ShippingContainer",(-89,y,.08),90,category="Storage/Containers")
    # Parking spaces and wheel stops (office staff area).
    for i in range(14):
        y=-18+i*4.7
        for side,x in enumerate([61,76]):
            for dy in [-2.1,2.1]:
                strip("Parking_%d_%d_%s"%(side,i,dy),(x-2.8,y+dy),(x+2.8,y+dy),.1)
            box("WheelStop_%d_%d"%(side,i),(x+2.3,y,.14),(.18,1.8,.18),"Sidewalk","Roads/Parking")
            if (i+side)%3 != 1:
                spawn("CAR_%d_%02d"%(side,i),"SM_StaffCar",(x,y,.06),0 if side else 180,category="Vehicles/Cars")
    # Gatehouse, traffic control and secure perimeter.
    spawn("GATE01_Guardhouse","SM_Guardhouse",(73,96,.08),category="Buildings/Gate")
    spawn("GATE01_EntryBarrier","SM_SecurityBarrier",(79,94,.08),category="Site/Gates")
    spawn("GATE01_ExitBarrier","SM_SecurityBarrier",(88,94,.08),category="Site/Gates")
    text("Gate_SiteName","NORTHPOINT LOGISTICS",(73,97.82,2.6),.28)
    for side,x in enumerate([-119,119]):
        for j in range(29):
            spawn("FENCE_%d_%02d"%(side,j),"SM_PerimeterFence",(x,-75+j*6,.02),90,category="Site/Fence")
    for side,y in enumerate([-79,99]):
        for j in range(39):
            x=-114+j*6
            if y==99 and 67<x<96:
                continue
            spawn("FENCE_Y%d_%02d"%(side,j),"SM_PerimeterFence",(x,y,.02),category="Site/Fence")
    # Roadside trees, office landscaping and a distant vegetated context.
    tree_points=[]
    for x in range(-110,64,13): tree_points.append((x,96))
    for x in range(-96,99,16): tree_points.append((x,-52))
    for y in range(-48,74,14): tree_points.extend([(-115,y),(115,y)])
    for x in [52,67,82]: tree_points.append((x,-42))
    for i,(x,y) in enumerate(tree_points):
        species=["SM_Tree_Plane_A","SM_Tree_Plane_B","SM_Tree_Columnar"][i%3]
        s=random.uniform(.88,1.13)
        spawn("TREE_%03d"%i,species,(x,y,0),random.randrange(360),(s,s,s),"Landscape/Trees")
        spawn("TreeSoil_%03d"%i,"Cylinder",(x,y,.035),scale=(2.9,2.9,.06),category="Landscape/TreeBeds",mat="M_WH_LandscapingSoil")
    for i in range(44):
        x=-230+i*11.2
        y=-104-random.uniform(0,22)
        s=random.uniform(1.1,1.7)
        spawn("BACKGROUND_TREE_%02d"%i,"SM_Tree_Plane_A",(x,y,-.05),random.randrange(360),(s,s,s),"Landscape/Context")
    for i in range(65):
        if i<32:
            x,y=-112+(i%16)*11,95+random.uniform(-1,1)
        else:
            x,y=51+(i%4)*4.5,-37+(i//4%6)*2.6
        s=random.uniform(.7,1.25)
        spawn("SHRUB_%03d"%i,"Bush",(x,y,.03),random.randrange(360),(s,s,s),"Landscape/Shrubs")
    for i,(x,y) in enumerate([(50,-39),(80,-43),(-110,71),(-113,-49)]):
        spawn("LandscapeRock_%02d"%i,"Rock",(x,y,-.05),i*75,(1.2,1,.65),"Landscape/Rocks")
    # Practical fixtures remain separate from the sun and sky.
    lamp_positions=[(-95,-44),(-95,10),(-95,65),(48,67),(97,62),(97,10),(97,-43),(-58,75),(0,75),(56,-43)]
    for i,(x,y) in enumerate(lamp_positions):
        spawn("LAMP_%02d"%(i+1),"SM_YardLightPole",(x,y,.05),90 if x<0 else -90,category="Lighting/Fixtures")
        light("LAMP_%02d_Light"%(i+1),(x,y,7.8),intensity=4500,radius=20)
    for i,x in enumerate([-55,-30,-5,20]):
        light("Warehouse_HighBay_%02d"%i,(x,-10,10.5),(1,.96,.87),6500,22)
    for a in actors.get_all_level_actors():
        if isinstance(a,unreal.PlayerStart):
            a.set_actor_location(vmetres((-50,58,2.0)),False,False)
            a.set_actor_rotation(unreal.Rotator(pitch=-5,yaw=-62,roll=0),False)
    camera_specs=[("CAM_Overview",(-168,208,132),(-5,8,0),52),
                  ("CAM_Loading",(-78,87,8),(-20,18,5),58),
                  ("CAM_Gate",(111,126,5),(42,25,4),60),
                  ("CAM_Interior",(-58,11,5),(-18,-20,4),65)]
    for name,pos,target,fov in camera_specs:
        a=actors.spawn_actor_from_class(unreal.CameraActor,vmetres(pos))
        a.set_actor_label(name); a.set_folder_path("Cameras")
        a.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(vmetres(pos),vmetres(target)),False)
        c=a.get_component_by_class(unreal.CameraComponent)
        c.set_field_of_view(fov); c.set_editor_property("constrain_aspect_ratio",False)
        a.set_editor_property("tags",["LogisticsWarehouse","TwinId="+name])
    pos,target=camera_specs[0][1:3]
    unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(vmetres(pos),unreal.MathLibrary.find_look_at_rotation(vmetres(pos),vmetres(target)))
    actors.set_selected_level_actors([])
    assert levels.save_current_level()
    result=dict(success=True,map=MAP,asset_mesh_count=len(MESHES)-4,material_count=len(MATS),actor_records=len(RECORDS),
                categories=dict(Counter(r["category"].split("/")[0] for r in RECORDS)),records=RECORDS,
                scope="Generic logistics scene; no live telemetry connected",roof="WH01_RemovableRoof")
    REPORT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    (SOURCE/"twin_asset_registry.json").write_text(json.dumps(RECORDS,indent=2),encoding="utf-8")
    unreal.log("WAREHOUSE_BUILD_COMPLETE "+json.dumps({k:v for k,v in result.items() if k!="records"}))

def setup_daylight_sky():
    existing=actors.get_all_level_actors()
    for a in existing:
        if "BP_Sky_Sphere" in a.get_class().get_name() or isinstance(a,unreal.AtmosphericFog):
            a.set_actor_hidden_in_game(True)
            a.set_is_temporarily_hidden_in_editor(True)
            for component in a.get_components_by_class(unreal.SceneComponent):
                component.set_visibility(False,True)
    atmosphere=next((a for a in existing if isinstance(a,unreal.SkyAtmosphere)),None)
    if not atmosphere:
        atmosphere=actors.spawn_actor_from_class(unreal.SkyAtmosphere,unreal.Vector(0,0,0))
    atmosphere.set_actor_label("Sky_PhysicalAtmosphere")
    atmosphere.set_folder_path("Lighting/Sky")
    atmosphere.set_editor_property("tags",["LogisticsWarehouse","TwinId=ENV_Sky"])
    for a in actors.get_all_level_actors():
        if isinstance(a,unreal.DirectionalLight):
            c=a.get_component_by_class(unreal.DirectionalLightComponent)
            c.set_atmosphere_sun_light(True)
            c.set_atmosphere_sun_light_index(0)
        if isinstance(a,unreal.SkyLight):
            c=a.get_component_by_class(unreal.SkyLightComponent)
            c.set_editor_property("source_type",unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
            c.set_editor_property("real_time_capture",True)
            c.set_intensity(1.0)
        if isinstance(a,unreal.ExponentialHeightFog):
            a.get_component_by_class(unreal.ExponentialHeightFogComponent).set_fog_density(.0015)
    post=next((a for a in actors.get_all_level_actors() if a.get_actor_label()=="PP_NaturalExposure"),None)
    if not post:
        post=actors.spawn_actor_from_class(unreal.PostProcessVolume,unreal.Vector(0,0,0))
    post.set_actor_label("PP_NaturalExposure")
    post.set_folder_path("Lighting/Sky")
    post.set_editor_property("unbound",True)
    settings=post.get_editor_property("settings")
    settings.set_editor_property("override_auto_exposure_bias",True)
    settings.set_editor_property("auto_exposure_bias",.5)
    post.set_editor_property("settings",settings)
    post.set_editor_property("tags",["LogisticsWarehouse","TwinId=ENV_Exposure"])

try:
    import_assets()
    make_scene()
except Exception:
    REPORT.write_text(json.dumps(dict(success=False,error=traceback.format_exc()),indent=2),encoding="utf-8")
    raise
