"""Finish an interrupted save in the editor owning the normal-map file lock."""
import sys
sys.path.insert(0,r'D:\UEPro\Test\Scripts\ghs')
import sync_wall_heights as s
import importlib
importlib.reload(s)
import unreal

report=s.read(s.REPORT)
assert not report['success'] and len(report['maps'])==1
backup=s.Path(report['backup_root'])
s.write(backup/'interrupted_save.json',report)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
current=editor.get_editor_world().get_path_name().split('.')[0]
assert current==s.PROFILE['maps'][1],current
labels={a.get_actor_label():a for a in s.ACTORS.get_all_level_actors()}
before=s.normalized(s.read(backup/(current.rsplit('/',1)[-1]+'_before.json')))
actual=s.snapshot(labels)
s.write(s.ROOT/'Saved/GHS_WallHeightLiveInspection.json',dict(snapshot=actual,
        dirty_maps=[p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]))
assert actual==before,'Live scene has other unsaved changes; review them before synchronization'
for label in s.WALLS:
    c=labels[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    row=s.row_for(label)
    t=unreal.Transform(location=unreal.Vector(*[x*100 for x in row['position_m']]),rotation=unreal.Rotator(),scale=unreal.Vector(*row['scale']))
    assert c.update_instance_transform(0,t,world_space=True,mark_render_state_dirty=True,teleport=True)
assert s.LEVELS.save_current_level()
report['maps'].append(dict(map=current,heights=s.extents(labels)))
for relative in s.REGISTRIES:
    assert s.sha(s.ROOT/relative)==report['file_changes'][relative]['before_sha256'],relative
    s.write(s.ROOT/relative,s.synchronize_registry(s.read(s.ROOT/relative)))
for relative,item in report['file_changes'].items():item['after_sha256']=s.sha(s.ROOT/relative)
content=s.read(backup/'content_hashes.json')
changed=[r for r,digest in content.items() if s.sha(s.ROOT/r)!=digest]
assert set(changed)==set(s.MAP_FILES),changed
report.pop('error',None)
report.update(success=True,changed_content=changed,unchanged_content_count=len(content)-len(changed),
              source_meshes_and_materials_unchanged=True,completed_utc=s.datetime.now(s.timezone.utc).isoformat(),
              completed_in_live_editor=True)
s.write(s.REPORT,report)
unreal.log('WALL_HEIGHT_SYNC_LIVE_SAVED: both maps, 5.6m walls')
