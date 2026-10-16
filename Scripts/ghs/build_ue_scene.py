"""Compose the GHS current CAD plan in its own level using the approved style."""
import hashlib
import importlib
import json
import math
import shutil
import sys
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from cad_rack_revision_state import refuse_legacy_rebuild
refuse_legacy_rebuild('build_ue_scene.py')
import ue_instancing
importlib.reload(ue_instancing)
spawn_group=ue_instancing.spawn_group
SOURCE=ROOT/'SourceAssets/GHS'
MAP='/Game/Maps/GHS_CAD_DigitalTwin'
TEMPLATE='/Game/Maps/VideoDigitalTwinWarehouse'
DEST='/Game/GHSDigitalTwin'
CAD=json.loads((SOURCE/'cad_layout.json').read_text(encoding='utf-8'))
ASSETS=unreal.EditorAssetLibrary
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ML=unreal.MaterialEditingLibrary
REPORT_PATH=ROOT/'Saved/GHS_BuildReport.json'
REPORT=dict(success=False,map=MAP,cad_units=CAD['units'],units_to_m=CAD['units_to_m'],
            origin_dxf_xy=CAD['origin_dxf_xy'],groups=[],individuals=[],assumptions=[])
MESHES={};MATERIALS={};GROUP_RECORDS=[];INDIVIDUALS=[]

def checkpoint(stage):
    REPORT['stage']=stage
    REPORT_PATH.write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
    unreal.log('GHS_BUILD_STAGE '+stage)

def vector(p):return unreal.Vector(float(p[0])*100,-float(p[1])*100,float(p[2] if len(p)>2 else 0)*100)

def transform(p,yaw=0,scale=(1,1,1)):
    return unreal.Transform(location=vector(p),rotation=unreal.Rotator(pitch=0,yaw=-yaw,roll=0),scale=unreal.Vector(*scale))

def mesh(name):
    if name not in MESHES:
        path='/Engine/BasicShapes/Cube' if name=='Cube' else DEST+'/Meshes/'+name
        MESHES[name]=ASSETS.load_asset(path);assert MESHES[name],path
    return MESHES[name]

def material(name):
    if name not in MATERIALS:
        path='/Game/VideoDigitalTwin/Materials/'+name
        MATERIALS[name]=ASSETS.load_asset(path);assert MATERIALS[name],path
    return MATERIALS[name]

def spawn(label,mesh_name,p,yaw=0,scale=(1,1,1),folder='Equipment',mat=None,movable=False,source=None):
    a=ACTORS.spawn_actor_from_class(unreal.StaticMeshActor,vector(p),unreal.Rotator(pitch=0,yaw=-yaw,roll=0))
    a.set_actor_label(label);a.set_folder_path('GHS/'+folder)
    c=a.get_component_by_class(unreal.StaticMeshComponent)
    c.set_static_mesh(mesh(mesh_name));c.set_mobility(unreal.ComponentMobility.MOVABLE if movable else unreal.ComponentMobility.STATIC)
    c.set_collision_profile_name('NoCollision')
    if mat:c.set_material(0,material(mat))
    a.set_actor_scale3d(unreal.Vector(*scale))
    a.set_editor_property('tags',['GHSDigitalTwin','TwinId='+label]+(['CAD='+','.join(source)] if source else []))
    record=dict(id=label,mesh=mesh_name,position_m=list(p),rotation_deg=yaw,scale=list(scale),folder=folder)
    if source:record['source_handles']=source
    INDIVIDUALS.append(record)
    return a

def group(label,mesh_name,items,folder,mat=None):
    if not items:return None
    a=spawn_group(label,'GHS/'+folder,mesh(mesh_name),[transform(i['position_m'],i.get('rotation_deg',0),i.get('scale',(1,1,1))) for i in items])
    c=a.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    if mat:c.set_material(0,material(mat))
    GROUP_RECORDS.append(dict(actor=label,mesh=mesh_name,count=len(items),material_override=mat,instances=items))
    REPORT['groups'].append(dict(actor=label,count=len(items),mesh=mesh_name))
    return a

def item(label,p,scale,angle=0,source=None):
    r=dict(id=label,position_m=list(p),rotation_deg=angle,scale=list(scale))
    if source:r['source_handles']=source
    return r

def segment(label,a,b,width,z,height=.008,source=None):
    dx,dy=b[0]-a[0],b[1]-a[1]
    length=math.hypot(dx,dy)
    if length<.002:return None
    return item(label,((a[0]+b[0])/2,(a[1]+b[1])/2,z),(length,width,height),math.degrees(math.atan2(dy,dx)),source)

def text_label(label,body,p,size,face=None,color=(150,205,226,255),flat=False):
    a=ACTORS.spawn_actor_from_class(unreal.TextRenderActor,vector(p))
    a.set_actor_label(label);a.set_folder_path('GHS/Annotations')
    c=a.get_component_by_class(unreal.TextRenderComponent)
    c.set_text(body);c.set_world_size(size*100);c.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    c.set_text_render_color(unreal.Color(*color))
    if flat:a.set_actor_rotation(unreal.Rotator(pitch=90,yaw=90,roll=0),False)
    else:a.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(a.get_actor_location(),vector(face or (150,25,14))),False)
    return a

def build_architecture():
    spawn('GHS_CAD_ExactFootprint','SM_GHS_CAD_Floor',(0,0,0),folder='Architecture')
    spawn('GHS_DarkSurround','Cube',(-6,-8,-.35),scale=(560,230,.3),folder='Environment',mat='M_VR_Backdrop')
    grid=[]
    for x in range(-270,271,5):grid.append(segment('GridX_'+str(x),(x,-115),(x,100),.015,.006))
    for y in range(-115,101,5):grid.append(segment('GridY_'+str(y),(-275,y),(265,y),.015,.006))
    group('GHS_ContextGrid','Cube',grid,'Environment','M_VR_Grid')
    panels=[];caps=[];trims=[]
    for w in CAD['walls']:
        a,b=w['points_m'];dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        angle=math.degrees(math.atan2(dy,dx));h=w['height_m'];th=w['thickness_m'];x,y=(a[0]+b[0])/2,(a[1]+b[1])/2
        src=w['source_handles'];id=w['id']
        panels.append(item(id,(x,y,h/2),(length,th/.2,h-.05),angle,src))
        caps.append(item(id+'_Top',(x,y,h-.018),(length,th,.036),angle,src))
        caps.append(item(id+'_Bottom',(x,y,.015),(length,th,.03),angle,src))
        for n,p in enumerate([a,b]):caps.append(item(id+'_End'+str(n),(*p,h/2),(.024,th,h),angle,src))
        for side in [-1,1]:
            off=side*(th/2-.006)
            trims.append(item(id+'_Rim'+str(side),(x-math.sin(math.radians(angle))*off,y+math.cos(math.radians(angle))*off,h+.003),(length,.012,.016),angle,src))
    group('GHS_CAD_WallFaces','SM_GHS_WallPanelUnit',panels,'Architecture/Walls')
    group('GHS_CAD_WallSections','Cube',caps,'Architecture/Walls','M_VR_WallSection')
    group('GHS_CAD_WallEdges','Cube',trims,'Architecture/Walls','M_VR_WallTrim')
    cols=[];collars=[]
    for row in CAD['columns']:
        x,y=row['position_m'];sx,sy=row['size_m'];ang=row['rotation_deg']
        cols.append(item(row['id'],(x,y,1.7),(sx,sy,3.4),ang,row['source_handles']))
        collars.append(item(row['id']+'_Foot',(x,y,.08),(sx+.10,sy+.10,.16),ang,row['source_handles']))
    group('GHS_CAD_Columns','Cube',cols,'Architecture/Columns','M_VR_StorageSteelLight')
    group('GHS_ColumnBases','Cube',collars,'Architecture/Columns','M_VR_WallSection')
    # Preserve actual door leaf/swing geometry as subtle ground clearance lines.
    door_handles={r['source_handles'][-1] for r in CAD['doors']}
    lines=[]
    for g in CAD['geometry']:
        if not any(h in door_handles for h in g.get('source_handles',[])):continue
        for j,(a,b) in enumerate(zip(g['points_m'],g['points_m'][1:])):
            row=segment('Door_'+g['source_handles'][-1]+'_'+str(j),a,b,.018,.012,source=g['source_handles'])
            if row:lines.append(row)
    group('GHS_CAD_DoorClearances','Cube',lines,'Architecture/Doors','M_VR_WallTrim')
    REPORT['assumptions']+=['Cutaway wall height 2.8m; 271 paired wall thicknesses measured, 59 single-face widths estimated.',
                            'Column display height 3.4m; source CAD determines XY and cross section.']

def build_storage():
    # Rack source long dimension is X=1.5m; CAD rack long axis is usually Y.
    racks=[]
    for row in CAD['racks']:
        x,y=row['position_m'];sx,sy=row['size_m']
        racks.append(item(row['id'],(x,y,0),(sy/1.5,sx/.852,1),row['rotation_deg']+90,row['source_handles']))
    group('GHS_CAD_Racks','SM_GHS_Shared_RackBay',racks,'Storage/Racks')
    cargo=[]
    for row in CAD['storage']:
        x,y=row['position_m'];sx,sy=row['size_m']
        cargo.append(item(row['id'],(x,y,.012),(sx/1.2,sy,1),row['rotation_deg'],row['source_handles']))
    group('GHS_CAD_PalletCargo','SM_GHS_Shared_PalletCargo',cargo,'Storage/FloorPallets')
    dock=[]
    for row in CAD['equipment']:
        x,y=row['position_m'];sx,sy=row['size_m']
        dock.append(item(row['id'],(x,y,0),(sx/1.5,sy/.852,1),row['rotation_deg'],row['source_handles']))
    group('GHS_CAD_DockRacks','SM_GHS_Shared_RackBay',dock,'Storage/DockRacks')
    REPORT['assumptions'].append('Rack and cargo heights/appearance reuse the approved scene; CAD fixes horizontal footprints and positions. No added conveyors.')

def fx(parent,label,kind,radius,phase):
    parent_mat=ASSETS.load_asset('/Game/VideoDigitalTwin/FX/M_VR_FX_'+kind);assert parent_mat
    mi_name='MI_GHS_'+label.replace('-','_')+'_'+kind
    path=DEST+'/FX/'+mi_name
    mi=ASSETS.load_asset(path) if ASSETS.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(mi_name,DEST+'/FX',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    ML.set_material_instance_parent(mi,parent_mat)
    ML.set_material_instance_scalar_parameter_value(mi,'Speed',1)
    ML.set_material_instance_scalar_parameter_value(mi,'Phase',phase)
    ML.set_material_instance_vector_parameter_value(mi,'Tint',unreal.LinearColor(.04,.8,.30,1))
    ML.update_material_instance(mi);assert ASSETS.save_loaded_asset(mi,only_if_is_dirty=False)
    p=parent.get_actor_location();a=ACTORS.spawn_actor_from_class(unreal.DecalActor,unreal.Vector(p.x,p.y,1.5))
    a.set_actor_label('FX_'+label+'_'+kind);a.set_folder_path('GHS/FX')
    c=a.get_component_by_class(unreal.DecalComponent);c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property('decal_size',unreal.Vector(3,radius,radius));c.set_decal_material(mi)
    c.set_fade_screen_size(.001);c.set_sort_order(30 if kind=='Diffusion' else 20)
    a.set_actor_rotation(unreal.Rotator(pitch=-90,yaw=parent.get_actor_rotation().yaw+(180 if kind=='Radar' else 0),roll=0),False)
    rule=unreal.AttachmentRule.KEEP_WORLD
    assert a.attach_to_actor(parent,'',rule,rule,rule,False)
    a.set_editor_property('tags',['GHSDigitalTwin','AGVAnimatedFX','FXOwner='+label,'NoEffectMesh'])
    return a

def build_charging_and_agvs():
    support=[];support_caps=[];support_edges=[];bay_lines=[];robot_positions=[]
    for i,row in enumerate(CAD['chargers']):
        x,y=row['parking_center_m'];ang=row['rotation_deg'];rad=math.radians(ang)
        long_axis=(-math.sin(rad),math.cos(rad));cross_axis=(math.cos(rad),math.sin(rad))
        # Wall-mounted hardware is a photo-driven addition. CAD fixes the bay;
        # a short service partition beyond its end gives it a physical support.
        mount=(x+long_axis[0]*1.73,y+long_axis[1]*1.73)
        support.append(item('Support_'+str(i+1),(*mount,1.05),(1.92,1,2.06),ang))
        support_caps.append(item('SupportTop_'+str(i+1),(*mount,2.09),(1.92,.2,.04),ang))
        for side in [-1,1]:
            p=(mount[0]+cross_axis[0]*side*.95,mount[1]+cross_axis[1]*side*.95)
            support_edges.append(item('SupportEdge_'+str(i+1)+'_'+str(side),(*p,1.05),(.024,.2,2.1),ang))
        charger_p=(mount[0]-long_axis[0]*.105,mount[1]-long_axis[1]*.105,0)
        spawn('GHS_CH_%02d'%(i+1),'SM_GHS_WallCharger',charger_p,ang+180,folder='Equipment/Chargers',source=row['source_handles'])
        sx,sy=row['size_m'];corners=[]
        for xx,yy in [(-sx/2,-sy/2),(sx/2,-sy/2),(sx/2,sy/2),(-sx/2,sy/2)]:
            corners.append((x+cross_axis[0]*xx+long_axis[0]*yy,y+cross_axis[1]*xx+long_axis[1]*yy))
        for j,(a,b) in enumerate(zip(corners,corners[1:]+corners[:1])):
            bay_lines.append(segment('Bay_%02d_%d'%(i+1,j),a,b,.028,.015,source=row['source_handles']))
        text_label('CH_BayLabel_%02d'%(i+1),'CH-%02d'%(i+1),(x-long_axis[0]*1.05,y-long_axis[1]*1.05,.025),.18,flat=True)
        if i%8 in [1,3,5,7]:robot_positions.append((x,y,ang,'Charging bay visualization'))
    group('GHS_ChargingSupportPanels','SM_GHS_WallPanelUnit',support,'Equipment/ChargerSupports')
    group('GHS_ChargingSupportCaps','Cube',support_caps,'Equipment/ChargerSupports','M_VR_WallSection')
    group('GHS_ChargingSupportEnds','Cube',support_edges,'Equipment/ChargerSupports','M_VR_WallSection')
    group('GHS_CAD_ChargingBayOutlines','Cube',bay_lines,'Locations/ChargingBays','M_VR_RouteInactive')
    for x in [-215,-175,-110,-25,65,205]:robot_positions.append((x,55.2,-90,'Clear aisle visualization; not surveyed AGV position'))
    for i,(x,y,ang,note) in enumerate(robot_positions):
        name='GHS_AGV_%02d'%(i+1)
        robot=spawn(name,'SM_GHS_KukaLowProfileAGV',(x,y,.005),ang,folder='Equipment/AGVs',movable=True)
        robot.set_editor_property('tags',list(robot.tags)+['PlacementAssumption='+note])
        fx(robot,name,'Diffusion',115,i*.173)
        if i>=28:fx(robot,name,'Radar',300,i*.231)
        if i<8:text_label(name+'_Label','KMP-%02d'%(i+1),(x,y,1),.13,face=(155,28,13))
    REPORT['robot_count']=len(robot_positions)
    REPORT['charging_bay_count']=len(CAD['chargers'])
    REPORT['fx_count']=len(robot_positions)+6
    REPORT['assumptions']+=['56 charger support partitions and mounting points inferred from photo; CAD contains parking bays only.',
                            '34 AGVs are display placements, 28 in measured charging bays and 6 in clear north aisle. No live telemetry or route claim.']

def build_environment(retained):
    from uniform_lighting import configure
    configure()

def build_cameras():
    views=[('Overview',(25,-405,365),(-6,-4,0),54),
           ('CADPlan',(-6,-8,420),(-6,-7.99,0),69),
           ('RackAisles',(-183,-28,15),(-198,4,1),55),
           ('FloorStorage',(17,-49,23),(-4,-13,.5),55),
           ('Charging',(158,21,18),(154,45,1),56),
           ('AGV_Charger',(142,40,3.4),(146.3,44.4,.8),53)]
    for name,p,t,fov in views:
        a=ACTORS.spawn_actor_from_class(unreal.CameraActor,vector(p),unreal.MathLibrary.find_look_at_rotation(vector(p),vector(t)))
        a.set_actor_label('CAM_GHS_'+name);a.set_folder_path('GHS/Cameras')
        c=a.get_component_by_class(unreal.CameraComponent);c.set_field_of_view(fov);c.set_editor_property('constrain_aspect_ratio',False)
        if name=='CADPlan':a.set_actor_rotation(unreal.Rotator(pitch=-90,yaw=-90,roll=0),False)
        if name=='Overview':EDITOR.set_level_viewport_camera_info(a.get_actor_location(),a.get_actor_rotation())
    text_label('GHS_SiteTitle','GHS  |  DIGITAL TWIN',(-6,-88,.05),3.5,flat=True)
    text_label('GHS_RackZone','RACK STORAGE',(-150,-49,.03),1.6,flat=True)
    text_label('GHS_PalletZone','PALLET STORAGE',(20,-49,.03),1.6,flat=True)
    text_label('GHS_ChargingZone','CHARGING  /  56 BAYS',(165,34,.03),.6,flat=True)

try:
    assert CAD.get('schema_version')==2
    assert len(CAD['storage'])==7530 and len(CAD['racks'])==1607 and len(CAD['chargers'])==56
    assert json.loads((ROOT/'Saved/GHS_AssetImport.json').read_text())['success']
    checkpoint('preserve_source_and_create_map')
    assert LEVELS.save_current_level()
    source_file=ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap'
    before_hash=hashlib.sha256(source_file.read_bytes()).hexdigest()
    if ASSETS.does_asset_exist(MAP):
        assert LEVELS.load_level(MAP)
        backup=ROOT/'Saved/Backups'/('GHS_BeforeRebuild_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.umap')
        backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/'Content/Maps/GHS_CAD_DigitalTwin.umap',backup)
        assert LEVELS.load_level(TEMPLATE)
        # Retry only works on the explicitly named GHS map; never delete template.
        assert ASSETS.delete_asset(MAP)
    assert LEVELS.new_level_from_template(MAP,TEMPLATE)
    assert EDITOR.get_editor_world().get_path_name().split('.')[0]==MAP
    keep=[];remove=[]
    for a in ACTORS.get_all_level_actors():
        if isinstance(a,(unreal.Light,unreal.SkyLight,unreal.PostProcessVolume)):keep.append(a)
        elif isinstance(a,(unreal.StaticMeshActor,unreal.DecalActor,unreal.TextRenderActor,unreal.CameraActor)):remove.append(a)
    assert ACTORS.destroy_actors(remove)
    unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous([DEST],force_rescan=True)
    checkpoint('cad_architecture');build_architecture()
    checkpoint('cad_storage_instances');build_storage()
    checkpoint('charging_and_new_agvs');build_charging_and_agvs()
    checkpoint('approved_environment');build_environment(keep);build_cameras()
    exec(compile((ROOT/'Scripts/ghs/persist_instance_materials.py').read_text(encoding='utf-8'),'ghs_material_support.py','exec'),{})
    ACTORS.set_selected_level_actors([])
    assert LEVELS.save_current_level()
    assert hashlib.sha256(source_file.read_bytes()).hexdigest()==before_hash,'Original video level changed'
    (SOURCE/'ue_scene_registry.json').write_text(json.dumps(dict(map=MAP,coordinate_mapping='UE centimetres = (CAD local X, -CAD local Y, Z)*100',
        origin_dxf_xy=CAD['origin_dxf_xy'],units_to_m=CAD['units_to_m'],groups=GROUP_RECORDS,individuals=INDIVIDUALS),indent=2),encoding='utf-8')
    REPORT.update(success=True,stage='saved',actor_count=len(ACTORS.get_all_level_actors()),individuals=INDIVIDUALS,
        source_level_sha256=before_hash,original_level_preserved=True,instanced_count=sum(g['count'] for g in GROUP_RECORDS),
        cad_racks=1607,cad_pallets=7530,cad_columns=206,cad_wall_segments=330,cad_doors=55,cad_dock_racks=87,
        footprint_m=[465.7344,137.16],cad_footprint_area_m2=56116.0983,conveyors_added=0)
    REPORT_PATH.write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
    if (SOURCE/'clearance_layout.json').is_file():
        exec(compile((ROOT/'Scripts/ghs/apply_clearance_fix.py').read_text(encoding='utf-8'),'ghs_clearance_fix.py','exec'),{})
    if (SOURCE/'joined_walls.json').is_file():
        exec(compile((ROOT/'Scripts/ghs/apply_joined_walls.py').read_text(encoding='utf-8'),'ghs_joined_walls.py','exec'),{})
    if (SOURCE/'column_outline_style.json').is_file():
        exec(compile((ROOT/'Scripts/ghs/apply_column_outlines.py').read_text(encoding='utf-8'),'ghs_column_outlines.py','exec'),{})
    exec(compile((ROOT/'Scripts/ghs/apply_uniform_lighting.py').read_text(encoding='utf-8'),'ghs_uniform_lighting.py','exec'),{})
    if (SOURCE/'Presentation/presentation_storage.json').is_file():
        import runpy
        runpy.run_path(str(ROOT/'Scripts/ghs/rebuild_presentation_refinement.py'),run_name='__main__')
    unreal.log('GHS_CAD_SCENE_SAVED')
except Exception:
    REPORT['error']=traceback.format_exc();REPORT_PATH.write_text(json.dumps(REPORT,indent=2),encoding='utf-8');raise
