"""Apply physical CAD outlines and explicit column clearances to the live map."""
import copy
import hashlib
import json
import math
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test')
SOURCE=ROOT/'SourceAssets/GHS'
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from ue_instancing import spawn_group
LAYOUT=json.loads((SOURCE/'clearance_layout.json').read_text(encoding='utf-8'))
PLAN=json.loads((ROOT/'Saved/GHS_ClearancePlan.json').read_text(encoding='utf-8'))
assert PLAN['after_column_clearance_collision_count']==0 and not PLAN['after_collision_counts']
EDITOR=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert EDITOR.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
registry_path=SOURCE/'ue_scene_registry.json'
registry=json.loads(registry_path.read_text(encoding='utf-8'))
original_level=ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap'
original_sha=hashlib.sha256(original_level.read_bytes()).hexdigest()
report=dict(success=False,map='/Game/Maps/GHS_CAD_DigitalTwin',changes=[])
report_path=ROOT/'Saved/GHS_ClearanceApplied.json'
by_label={a.get_actor_label():a for a in ACTORS.get_all_level_actors()}
groups={g['actor']:g for g in registry['groups']}

def vector(p):return unreal.Vector(p[0]*100,-p[1]*100,p[2]*100)
def transform(row):return unreal.Transform(location=vector(row['position_m']),rotation=unreal.Rotator(pitch=0,yaw=-row['rotation_deg'],roll=0),scale=unreal.Vector(*row['scale']))
def record(row,p,scale,yaw):
    result=dict(id=row['id'],position_m=list(p),scale=list(scale),rotation_deg=yaw,source_handles=row['source_handles'])
    for key in ['parent_cad_id','design_adjustment','nominal_size_m','trimmed_geometry_size_m','blocking_column_ids']:
        if key in row:result[key]=row[key]
    return result

def physical_record(row,mesh,kind):
    b=mesh.get_bounds();width=b.box_extent.x*2/100;depth=b.box_extent.y*2/100
    x,y=row['position_m'];w,d=row['size_m'];yaw=row['rotation_deg']
    if kind=='racks':w,d=d,w;yaw+=90
    scales=(w/width,d/depth,1)
    # The imported mesh origin/LOD bounds are slightly asymmetric. Place the
    # actual world-space bounds centre at the physical CAD centre.
    theta=math.radians(-yaw);ox=b.origin.x*scales[0];oy=b.origin.y*scales[1]
    dx=math.cos(theta)*ox-math.sin(theta)*oy;dy=math.sin(theta)*ox+math.cos(theta)*oy
    z=.012 if kind=='storage' else max(0,(b.box_extent.z-b.origin.z)/100)
    result=record(row,(x-dx/100,y+dy/100,z),scales,yaw)
    result.update(physical_cad_center_m=[x,y],physical_cad_size_m=row['size_m'],physical_cad_rotation_deg=row['rotation_deg'],actual_mesh_bounds_normalized=True)
    return result

def update_group(label,rows,material=None):
    actor=by_label[label];component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    before=component.get_instance_count()
    component.clear_instances()
    indices=component.add_instances([transform(row) for row in rows],should_return_indices=True,world_space=True,update_navigation=False)
    assert component.get_instance_count()==len(rows)==len(indices)
    if material:component.set_material(0,material)
    actor.set_editor_property('tags',['GHSDigitalTwin','HISMGroup','ClearanceCorrected','InstanceCount='+str(len(rows))])
    groups[label]['instances']=rows;groups[label]['count']=len(rows)
    if material:groups[label]['material_override']=material.get_name().replace('M_GHS_','M_VR_')
    report['changes'].append(dict(actor=label,before=before,after=len(rows)))

try:
    assert LEVELS.save_current_level()
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    backup=ROOT/'Saved/Backups'/('GHS_Clearance_'+stamp)
    backup.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'Content/Maps/GHS_CAD_DigitalTwin.umap',backup/'GHS_CAD_DigitalTwin.umap')
    shutil.copy2(registry_path,backup/'ue_scene_registry.json')
    for name in ['GHS_BuildReport','GHS_Verification','GHS_InstanceMaterials']:
        p=ROOT/'Saved'/(name+'.json')
        if p.is_file():shutil.copy2(p,backup/p.name)
    wall=by_label['GHS_CAD_WallFaces'].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent).get_material(0)
    assert wall and wall.get_name()=='M_GHS_WallVolume'
    cols=[];bases=[]
    for row in LAYOUT['columns']:
        x,y=row['position_m'];sx,sy=row['size_m'];angle=row['rotation_deg']
        cols.append(record(row,(x,y,1.7),(sx,sy,3.4),angle))
        base=record(row,(x,y,.08),(sx+.1,sy+.1,.16),angle);base['id']+='_Foot';bases.append(base)
    update_group('GHS_CAD_Columns',cols,wall)
    update_group('GHS_ColumnBases',bases)
    for label,category in [('GHS_CAD_PalletCargo','storage'),('GHS_CAD_Racks','racks'),('GHS_CAD_DockRacks','equipment')]:
        component=by_label[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        mesh=component.get_editor_property('static_mesh')
        update_group(label,[physical_record(row,mesh,category) for row in LAYOUT[category]])
    lines=[]
    for row in LAYOUT['blocked_storage']:
        x,y=row['position_m'];sx,sy=row['size_m'];angle=row['rotation_deg'];theta=math.radians(angle)
        cs=[]
        for px,py in [(-sx/2,-sy/2),(sx/2,-sy/2),(sx/2,sy/2),(-sx/2,sy/2)]:
            cs.append((x+px*math.cos(theta)-py*math.sin(theta),y+px*math.sin(theta)+py*math.cos(theta)))
        for index,(a,b) in enumerate(zip(cs,cs[1:]+cs[:1])):
            dx,dy=b[0]-a[0],b[1]-a[1]
            item=record(row,((a[0]+b[0])/2,(a[1]+b[1])/2,.014),(math.hypot(dx,dy),.012,.006),math.degrees(math.atan2(dy,dx)))
            item.update(id=row['id']+'_EmptyBoundary_'+str(index),parent_cad_id=row['id'],status='ColumnClearanceNoCargo')
            lines.append(item)
    label='GHS_ColumnOccupiedStorageOutlines'
    if label not in by_label:
        actor=spawn_group(label,'GHS/Storage/ColumnClearance',unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube'),[transform(i) for i in lines])
        by_label[label]=actor
        groups[label]=dict(actor=label,mesh='Cube',count=len(lines),material_override='M_VR_WallTrim',instances=lines)
        registry['groups'].append(groups[label])
    else:update_group(label,lines)
    by_label[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent).set_material(0,unreal.EditorAssetLibrary.load_asset('/Game/GHSDigitalTwin/Materials/Instanced/M_GHS_WallTrim'))
    ACTORS.set_selected_level_actors([])
    # Do not inherit temporary user isolation/hiding for the groups just fixed.
    for label in ['GHS_CAD_Columns','GHS_ColumnBases','GHS_CAD_Racks','GHS_CAD_PalletCargo','GHS_CAD_DockRacks','GHS_ColumnOccupiedStorageOutlines']:
        by_label[label].set_is_temporarily_hidden_in_editor(False)
    registry['clearance_layout']='SourceAssets/GHS/clearance_layout.json'
    registry['blocked_storage']=LAYOUT['blocked_storage']
    registry['excluded_column_candidates']=LAYOUT['excluded_candidates']
    registry['clearance_policy']=LAYOUT['policy']
    registry_path.write_text(json.dumps(registry,indent=2),encoding='utf-8')
    # Refresh persisted material slot mapping after the column material change.
    material_path=ROOT/'Saved/GHS_InstanceMaterials.json'
    mats=json.loads(material_path.read_text())
    mats['groups']=[dict(actor=g['actor'],materials=[by_label[g['actor']].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent).get_material(i).get_path_name() for i in range(by_label[g['actor']].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent).get_num_materials())]) for g in registry['groups']]
    material_path.write_text(json.dumps(mats,indent=2))
    assert LEVELS.save_current_level()
    assert hashlib.sha256(original_level.read_bytes()).hexdigest()==original_sha
    build_path=ROOT/'Saved/GHS_BuildReport.json';build=json.loads(build_path.read_text())
    build.update(actor_count=len(ACTORS.get_all_level_actors()),instanced_count=sum(g['count'] for g in registry['groups']),
        groups=[dict(actor=g['actor'],count=g['count'],mesh=g['mesh']) for g in registry['groups']],
        displayed_columns=170,loaded_pallet_positions=len(LAYOUT['storage']),blocked_pallet_positions=len(LAYOUT['blocked_storage']),
        displayed_rack_segments=len(LAYOUT['racks']),clearance_corrected=True)
    build_path.write_text(json.dumps(build,indent=2))
    report.update(success=True,backup=str(backup),column_material=wall.get_path_name(),original_level_preserved=True,
        source_level_sha256=original_sha,counts=PLAN['counts'],instance_count=build['instanced_count'],actor_count=build['actor_count'])
    report_path.write_text(json.dumps(report,indent=2))
    unreal.log('GHS_CLEARANCE_FIX_SAVED')
except Exception:
    report['error']=traceback.format_exc();report_path.write_text(json.dumps(report,indent=2));raise
