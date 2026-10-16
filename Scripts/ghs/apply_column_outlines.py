"""Add closed cyan column edges, entirely contained within each CAD column."""
import copy,hashlib,json,math,shutil,sys,traceback
from datetime import datetime
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test');SOURCE=ROOT/'SourceAssets/GHS'
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from ue_instancing import spawn_group
style=json.loads((SOURCE/'column_outline_style.json').read_text())
edge=style['edge_width_m'];assert 0<edge<.05
registry_path=SOURCE/'ue_scene_registry.json'
registry=json.loads(registry_path.read_text());before=copy.deepcopy(registry)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
by_label={a.get_actor_label():a for a in actors.get_all_level_actors()}
groups={g['actor']:g for g in registry['groups']};columns=groups['GHS_CAD_Columns']['instances']
assert len(columns)==170
label='GHS_ColumnEdgeOutlines';report_path=ROOT/'Saved/GHS_ColumnOutlinesApplied.json'
report=dict(success=False,edge_width_m=edge,source_column_ids=[r['id'] for r in columns])
source_map=ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap'
source_sha=hashlib.sha256(source_map.read_bytes()).hexdigest()
def transform(row):
    x,y,z=row['position_m']
    return unreal.Transform(location=unreal.Vector(x*100,-y*100,z*100),rotation=unreal.Rotator(pitch=0,yaw=-row['rotation_deg'],roll=0),scale=unreal.Vector(*row['scale']))
try:
    assert levels.save_current_level()
    backup=ROOT/'Saved/Backups'/('GHS_ColumnOutlines_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'Content/Maps/GHS_CAD_DigitalTwin.umap',backup/'GHS_CAD_DigitalTwin.umap')
    shutil.copy2(registry_path,backup/'ue_scene_registry.json')
    for name in ['GHS_BuildReport','GHS_InstanceMaterials','GHS_JoinedWallsVerification']:
        p=ROOT/'Saved'/(name+'.json')
        if p.is_file():shutil.copy2(p,backup/p.name)
    report['backup']=str(backup)
    rows=[]
    for column in columns:
        w,d,h=column['scale'];assert min(w,d,h)>2*edge
        x,y,z=column['position_m'];angle=column['rotation_deg'];theta=math.radians(angle)
        parts=[]
        # Full-width X strips meet shorter Y strips; corners have no overlaps.
        for level,sign in [('Bottom',-1),('Top',1)]:
            cz=sign*(h-edge)/2
            for side in [-1,1]:
                parts.append((level+'_X_'+str(side),(0,side*(d-edge)/2,cz),(w,edge,edge)))
                parts.append((level+'_Y_'+str(side),(side*(w-edge)/2,0,cz),(edge,d-2*edge,edge)))
        for sx in [-1,1]:
            for sy in [-1,1]:
                parts.append(('Vertical_'+str(sx)+'_'+str(sy),(sx*(w-edge)/2,sy*(d-edge)/2,0),(edge,edge,h-2*edge)))
        for name,(ox,oy,oz),scale in parts:
            rows.append(dict(id=column['id']+'_Outline_'+name,parent_column_id=column['id'],edge_name=name,
                position_m=[x+ox*math.cos(theta)-oy*math.sin(theta),y+ox*math.sin(theta)+oy*math.cos(theta),z+oz],
                rotation_deg=angle,scale=list(scale),source_handles=column['source_handles']))
    assert len(rows)==2040
    wall=by_label['GHS_CAD_WallEdges'].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent).get_material(0)
    assert wall.get_path_name().split('.')[0]==style['material']
    if label in by_label:
        actor=by_label[label];component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        component.clear_instances();component.add_instances([transform(r) for r in rows],should_return_indices=True,world_space=True,update_navigation=False)
    else:
        actor=spawn_group(label,'GHS/Architecture/Columns',unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube'),[transform(r) for r in rows])
        component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    component.set_material(0,wall);assert component.get_instance_count()==2040
    actor.set_is_temporarily_hidden_in_editor(False)
    actor.set_editor_property('tags',['GHSDigitalTwin','HISMGroup','ColumnOutlines','InstanceCount=2040'])
    row=dict(actor=label,mesh='Cube',count=len(rows),material_override='M_VR_WallTrim',instances=rows)
    registry['groups']=[row if g['actor']==label else g for g in registry['groups']]
    if label not in groups:registry['groups'].append(row)
    assert registry['individuals']==before['individuals']
    assert all(g==next(old for old in before['groups'] if old['actor']==g['actor']) for g in registry['groups'] if g['actor']!=label)
    registry['column_outline_style']='SourceAssets/GHS/column_outline_style.json'
    registry_path.write_text(json.dumps(registry,indent=2))
    material_path=ROOT/'Saved/GHS_InstanceMaterials.json';materials=json.loads(material_path.read_text())
    materials['groups']=[g for g in materials['groups'] if g['actor']!=label]+[dict(actor=label,materials=[wall.get_path_name()])]
    material_path.write_text(json.dumps(materials,indent=2))
    assert levels.save_current_level()
    assert hashlib.sha256(source_map.read_bytes()).hexdigest()==source_sha
    build_path=ROOT/'Saved/GHS_BuildReport.json';build=json.loads(build_path.read_text())
    build.update(column_outlines_added=True,actor_count=len(actors.get_all_level_actors()),instanced_count=sum(g['count'] for g in registry['groups']),groups=[dict(actor=g['actor'],count=g['count'],mesh=g['mesh']) for g in registry['groups']])
    build_path.write_text(json.dumps(build,indent=2))
    report.update(success=True,actor_count=build['actor_count'],hism_group_count=len(registry['groups']),instanced_count=build['instanced_count'],column_count=170,outline_instance_count=2040,column_outline_material=wall.get_path_name(),existing_groups_and_individuals_preserved=True,source_level_sha256=source_sha)
    report_path.write_text(json.dumps(report,indent=2))
    unreal.log('GHS_COLUMN_OUTLINES_SAVED')
except Exception:
    report['error']=traceback.format_exc();report_path.write_text(json.dumps(report,indent=2));raise
