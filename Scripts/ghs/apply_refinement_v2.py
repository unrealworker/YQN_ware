"""Apply the checkpointed V2 scene refinement in the user's live UE editor."""
import copy,hashlib,json,sys,traceback
from pathlib import Path
from datetime import datetime,timezone
import unreal
ROOT=Path(r'D:\UEPro\Test');SRC=ROOT/'SourceAssets/GHS/RefinementV2';sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from ue_instancing import spawn_group
from sync_wall_heights import snapshot
MAPS=['/Game/Maps/GHS_CAD_DigitalTwin','/Game/Maps/GHS_CAD_NormalWarehouse']
REGS=['SourceAssets/GHS/ue_scene_registry.json','SourceAssets/GHS_Normal/ue_scene_registry.json','SourceAssets/GHS/Presentation/visual_layout.json']
REPORT=ROOT/'Saved/GHS_RefinementV2.json'
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);lib=unreal.EditorAssetLibrary
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,d):Path(p).write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def transform(r):
    x,y,z=r['position_m'];return unreal.Transform(location=unreal.Vector(x*100,-y*100,z*100),rotation=unreal.Rotator(pitch=0,yaw=-r['rotation_deg'],roll=0),scale=unreal.Vector(*r['scale']))
def labels():return {a.get_actor_label():a for a in actors.get_all_level_actors()}
def run():
    assert not REPORT.exists(),'Revision already exists: inspect before reapplication'
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(),'Preserve unsaved user map edits first'
    checkpoint=read(ROOT/'Saved/GHS_RefinementV2Checkpoint.json');backup=Path(checkpoint['backup_root'])
    registry=read(SRC/'revised_registry.json');revision=registry['refinement_v2']
    imported=read(ROOT/'Saved/GHS_RefinementV2Import.json');assert imported['success']
    geometry=read(SRC/'Envelope/scene_geometry_audit.json');assert geometry['status']=='passed'
    assert geometry['summary']['final_v2_rack_asset_binding_verified'] and not geometry['summary']['rack_mesh_manifest_fallback_used']
    for source in geometry['source_files'].values():assert sha(source['path'])==source['sha256'],source['path']+' changed since geometry audit'
    for relative,digest in imported['manifests'].items():assert sha(SRC/relative)==digest
    for relative,digest in revision['source_sha256'].items():assert sha(SRC/relative)==digest
    mesh_records={m['name']:m for m in imported['meshes']}
    changed=set(revision['changed_groups']);retired=set(revision['retired_groups']);allowed=changed|retired
    report=dict(success=False,checkpoint=str(ROOT/'Saved/GHS_RefinementV2Checkpoint.json'),backup_root=str(backup),
        revision=revision,maps=[],changed_files={},preserved_snapshots={},import_sha256=sha(ROOT/'Saved/GHS_RefinementV2Import.json'),
        geometry_audit_sha256=sha(SRC/'Envelope/scene_geometry_audit.json'))
    for relative in [*REGS,'SourceAssets/GHS/wall_height_profile.json',*['Content/Maps/'+m.rsplit('/',1)[-1]+'.umap' for m in MAPS]]:
        entry=checkpoint['files'][relative];assert sha(ROOT/relative)==entry['sha256'],relative+' changed since checkpoint'
        report['changed_files'][relative]=dict(before_sha256=entry['sha256'],backup=entry['backup'])
    try:
        for m in MAPS:
            assert levels.load_level(m);before=snapshot(labels());assert len(before)==(252 if m==MAPS[0] else 254)
            dest=backup/(m.rsplit('/',1)[-1]+'_v2_actors_before.json');write(dest,before);report['preserved_snapshots'][m]=str(dest)
        write(REPORT,report)
        for m in MAPS:
            assert levels.load_level(m);by=labels();before=read(report['preserved_snapshots'][m]);style='Blue' if m==MAPS[0] else 'Normal'
            for name in retired:assert name in by and actors.destroy_actor(by[name]),name
            for g in registry['groups']:
                name=g['actor']
                if name not in changed:continue
                if g['mesh'] in mesh_records:mesh=lib.load_asset(mesh_records[g['mesh']]['path'])
                else:mesh=lib.load_asset('/Engine/BasicShapes/Cube' if g['mesh']=='Cube' else '/Game/GHSDigitalTwin/Meshes/'+g['mesh'])
                assert mesh,g['mesh']
                if name in by and name not in retired:
                    actor=by[name];component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                    component.clear_instances();component.set_static_mesh(mesh)
                    component.add_instances([transform(r) for r in g['instances']],should_return_indices=True,world_space=True,update_navigation=False)
                else:
                    actor=spawn_group(name,'GHS/RefinementV2',mesh,[transform(r) for r in g['instances']]);component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                if g['mesh'] in mesh_records:
                    for i,path in enumerate(mesh_records[g['mesh']]['palettes'][style]):
                        mat=lib.load_asset(path);assert mat,path;component.set_material(i,mat)
                # Editing actor tags reconstructs Blueprint components; re-fetch the live HISM.
                actor.set_editor_property('tags',['GHSDigitalTwin','HISMGroup','RefinementV2','InstanceCount='+str(g['count'])])
                component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                assert component.get_instance_count()==g['count'],(name,component.get_instance_count(),g['count'])
            actors.set_selected_level_actors([]);after=snapshot(labels())
            for name,state in before.items():
                if name not in allowed:assert after.get(name)==state,'Unrelated actor changed: '+name
            assert set(after)==((set(before)-retired)|(changed-set(before)))
            assert levels.save_current_level(),m
            report['maps'].append(dict(map=m,actor_count=len(after),hism_groups=len(registry['groups']),instances=sum(g['count'] for g in registry['groups']),
                racks=revision['rack_count'],groundcargo=revision['cargo_count'],doors=87,trucks=87))
            write(REPORT,report)
        for relative in REGS:
            data=copy.deepcopy(registry)
            if 'GHS_Normal/' in relative:
                data['map']=MAPS[1]
                data['presentation']['expected_actor_count']=registry['presentation']['expected_actor_count']+2
            write(ROOT/relative,data)
        write(ROOT/'SourceAssets/GHS/wall_height_profile.json',registry['wall_height_profile'])
        for relative,entry in report['changed_files'].items():entry['after_sha256']=sha(ROOT/relative)
        content_changes=[p for p,h in checkpoint['content_hashes'].items() if sha(ROOT/p)!=h]
        assert set(content_changes)=={'Content/Maps/'+m.rsplit('/',1)[-1]+'.umap' for m in MAPS},content_changes
        new_assets={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Content').rglob('*.uasset') if p.relative_to(ROOT).as_posix() not in checkpoint['content_hashes']}
        assert len(new_assets)==52 and all(p.startswith('Content/GHSRefinementV2/') for p in new_assets),list(new_assets)
        report.update(success=True,changed_content=content_changes,new_assets=new_assets,unrelated_content_unchanged=len(checkpoint['content_hashes'])-2,
            completed_utc=datetime.now(timezone.utc).isoformat())
        # Display the repaired southern docks and their waiting trucks in the current scene.
        pos=unreal.Vector(-15600,8050,1250);target=unreal.Vector(-16700,5850,430)
        editor.set_level_viewport_camera_info(pos,unreal.MathLibrary.find_look_at_rotation(pos,target))
        unreal.log('GHS_REFINEMENT_V2_SAVED '+json.dumps(report['maps']))
    except Exception:report['error']=traceback.format_exc();raise
    finally:write(REPORT,report)
if __name__=='__main__':run()
