"""Apply the measured rack revision to both open-project maps, preserving other state."""
import copy,hashlib,json,sys,traceback
from datetime import datetime,timezone
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from ue_instancing import spawn_group
from sync_wall_heights import snapshot
MAPS=['/Game/Maps/GHS_CAD_DigitalTwin','/Game/Maps/GHS_CAD_NormalWarehouse']
REGS=['SourceAssets/GHS/ue_scene_registry.json','SourceAssets/GHS_Normal/ue_scene_registry.json','SourceAssets/GHS/Presentation/visual_layout.json']
REPORT=ROOT/'Saved/GHS_CADRackRevision.json'
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
lib=unreal.EditorAssetLibrary
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,d):Path(p).write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def transform(r):
    x,y,z=r['position_m']
    return unreal.Transform(location=unreal.Vector(x*100,-y*100,z*100),rotation=unreal.Rotator(pitch=0,yaw=-r['rotation_deg'],roll=0),scale=unreal.Vector(*r['scale']))
def labels():return {a.get_actor_label():a for a in actors.get_all_level_actors()}

def run():
    assert not REPORT.exists(),'Revision already exists; review it before reapplying'
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(),'Unsaved map edits must be preserved before changing levels'
    checkpoint=read(ROOT/'Saved/GHS_CADRackCheckpoint.json');backup=Path(checkpoint['backup_root'])
    registry=read(ROOT/'SourceAssets/GHS/RackSpecs/revised_registry.json');revision=registry['cad_rack_revision']
    imported=read(ROOT/'Saved/GHS_CADRackImport.json');assert imported['success']
    solid=read(ROOT/'Saved/GHS_CADRackSolidAudit.json');assert solid['success'],solid.get('summary')
    assert imported['model_manifest_sha256']==revision['models_sha256']
    assert solid['input_sha256']['mapping']==revision['mapping_sha256']
    assert solid['input_sha256']['models']==revision['models_sha256']
    assert solid['column_height_m']==revision['building_display_height_m'] and solid['rack_floor_offset_m']==0
    mesh_records={m['name']:m for m in imported['meshes']}
    changed=set(revision['changed_groups']);retired=set(revision['retired_groups'])
    cameras={'CAM_GHS_RackAisles'};allowed=changed|retired|cameras
    report=dict(success=False,checkpoint=str(ROOT/'Saved/GHS_CADRackCheckpoint.json'),backup_root=str(backup),
        revision=revision,maps=[],changed_files={},preserved_snapshots={},camera_adjustments={})
    for relative in [*REGS,'SourceAssets/GHS/wall_height_profile.json',*['Content/Maps/'+m.rsplit('/',1)[-1]+'.umap' for m in MAPS]]:
        entry=checkpoint['files'][relative];assert sha(ROOT/relative)==entry['sha256'],relative+' changed since checkpoint'
        report['changed_files'][relative]=dict(before_sha256=entry['sha256'],backup=entry['backup'])
    try:
        # Snapshot both saved levels before any target-level edit.
        for m in MAPS:
            assert levels.load_level(m);before=snapshot(labels())
            assert len(before)==(229 if m==MAPS[1] else 227)
            dest=backup/(m.rsplit('/',1)[-1]+'_actors_before.json');write(dest,before)
            report['preserved_snapshots'][m]=str(dest)
        write(REPORT,report)
        for m in MAPS:
            assert levels.load_level(m);by=labels();before=read(report['preserved_snapshots'][m])
            normal=m==MAPS[1]
            for name in retired:
                assert name in by and actors.destroy_actor(by[name]),name
            for g in registry['groups']:
                name=g['actor']
                if name not in changed:continue
                mesh=lib.load_asset('/Engine/BasicShapes/Cube' if g['mesh']=='Cube' else '/Game/GHSDigitalTwin/Meshes/'+g['mesh']);assert mesh
                if name in by and name not in retired:
                    actor=by[name];component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                    component.clear_instances();component.set_static_mesh(mesh)
                    component.add_instances([transform(r) for r in g['instances']],should_return_indices=True,world_space=True,update_navigation=False)
                else:
                    actor=spawn_group(name,'GHS/Storage/CADRackSpecifications' if name!='GHS_CAD_DockDoors' else 'GHS/Architecture/LoadingDoors',mesh,[transform(r) for r in g['instances']])
                    component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                if g['mesh'] in mesh_records:
                    materials=mesh_records[g['mesh']]['normal_materials' if normal else 'blue_materials']
                    for i,path in enumerate(materials):
                        mat=lib.load_asset(path);assert mat,path;component.set_material(i,mat)
                assert component.get_instance_count()==g['count']
                if name.startswith('GHS_CAD_Rack_') or name=='GHS_CAD_DockDoors':
                    actor.set_editor_property('tags',['GHSDigitalTwin','HISMGroup','CADSpecification','InstanceCount='+str(g['count'])])
                    actor.set_is_temporarily_hidden_in_editor(False)
            by=labels();camera=by['CAM_GHS_RackAisles']
            position=unreal.Vector(-18300,2800,2300);target=unreal.Vector(-19800,-400,450)
            camera.set_actor_location(position,False,False)
            camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position,target),False)
            report['camera_adjustments'][m]=dict(position_cm=[-18300,2800,2300],target_cm=[-19800,-400,450],reason='Frame the CAD-height racks at a comparable oblique view')
            actors.set_selected_level_actors([])
            after=snapshot(by)
            for name,state in before.items():
                if name not in allowed:assert after.get(name)==state,'Unrelated actor changed: '+name
            assert set(after)==(set(before)-retired)|(changed-set(before)),set(after)^((set(before)-retired)|(changed-set(before)))
            assert levels.save_current_level(),m
            report['maps'].append(dict(map=m,actor_count=len(after),hism_groups=len(registry['groups']),
                instances=sum(g['count'] for g in registry['groups']),rack_instances=1639,door_instances=87))
            write(REPORT,report)
        for relative in REGS:
            data=copy.deepcopy(registry)
            if 'GHS_Normal/' in relative:data['map']=MAPS[1]
            write(ROOT/relative,data)
        write(ROOT/'SourceAssets/GHS/wall_height_profile.json',registry['wall_height_profile'])
        for relative,entry in report['changed_files'].items():entry['after_sha256']=sha(ROOT/relative)
        changes=[p for p,h in checkpoint['content_hashes'].items() if sha(ROOT/p)!=h]
        assert set(changes)=={'Content/Maps/'+m.rsplit('/',1)[-1]+'.umap' for m in MAPS},changes
        new_assets={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Content').rglob('*.uasset') if p.relative_to(ROOT).as_posix() not in checkpoint['content_hashes']}
        assert all(p.startswith('Content/GHSDigitalTwin/Meshes/SM_GHS_CAD') for p in new_assets),new_assets
        report.update(success=True,changed_content=changes,new_assets=new_assets,
            unrelated_content_files_unchanged=len(checkpoint['content_hashes'])-len(changes),
            completed_utc=datetime.now(timezone.utc).isoformat(),model_import_report_sha256=sha(ROOT/'Saved/GHS_CADRackImport.json'))
        # End in the user's light scene at the corrected rack camera.
        current=labels()['CAM_GHS_RackAisles'];editor.set_level_viewport_camera_info(current.get_actor_location(),current.get_actor_rotation())
        unreal.log('GHS_CAD_RACK_REVISION_SAVED '+json.dumps(report['maps']))
    except Exception:
        report['error']=traceback.format_exc();raise
    finally:write(REPORT,report)

if __name__=='__main__':run()
