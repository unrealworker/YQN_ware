"""Reload MPR and capture authored exterior/interior/details without HUD."""
import json,time,traceback,hashlib,sys
from pathlib import Path
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir()));OUT=ROOT/'Saved/MPR';OUT.mkdir(parents=True,exist_ok=True)
MAP='/Game/Maps/MPR_CAD_Warehouse'
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_scene_ownership import verify_owned_scene,refresh_map_hash
ownership=verify_owned_scene(ROOT)
A=u.get_editor_subsystem(u.EditorActorSubsystem);L=u.get_editor_subsystem(u.LevelEditorSubsystem);E=u.get_editor_subsystem(u.UnrealEditorSubsystem)
assert not L.is_in_play_in_editor()
assert not u.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert L.load_level('/Engine/Maps/Entry');assert L.load_level(MAP)
actors=list(A.get_all_level_actors());by={a.get_actor_label():a for a in actors}
build_report=OUT/'scene_build.json'
if not build_report.exists():build_report=ROOT/'SourceAssets/MPR/validation/scene_build.json'
expected=json.loads(build_report.read_text(encoding='utf-8'));CAD=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf-8'))
groups={}
for a in actors:
    c=a.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
    if c:
        groups[a.get_actor_label()]=c
        for i in range(c.get_num_materials()):
            assert u.MaterialEditingLibrary.has_material_usage(c.get_material(i),u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES),(a.get_actor_label(),'missing instanced material shader',i)
assert len(groups)==len(expected['groups'])
assert sum(c.get_instance_count() for c in groups.values())==expected['instance_count']
assert sum(c.get_instance_count() for k,c in groups.items() if k.startswith('MPR_Racks_'))==len(CAD['racks'])
assert sum(c.get_instance_count() for k,c in groups.items() if k.startswith('MPR_Columns_'))==len(CAD['columns'])
assert sum(c.get_instance_count() for k,c in groups.items() if k.startswith('MPR_DockDoors_'))==74
truck_rear_errors=[]
truck_targets=[u.Vector((r['position_m'][0]+r['outward_normal_xy'][0]*.25)*100,
                       -(r['position_m'][1]+r['outward_normal_xy'][1]*.25)*100,0)
               for i,r in enumerate(CAD['dock_doors']) if i%5==0]
for label,component in groups.items():
    if not label.startswith('MPR_ParkedTruck'):continue
    bounds=component.static_mesh.get_bounds()
    for i in range(component.get_instance_count()):
        rear=u.MathLibrary.transform_location(component.get_instance_transform(i,world_space=True),u.Vector(bounds.origin.x-bounds.box_extent.x,0,0))
        error=min(((rear.x-p.x)**2+(rear.y-p.y)**2)**.5 for p in truck_targets)
        assert error<.5,('Truck rear is not aligned to its dock',label,i,error)
        truck_rear_errors.append(error)
assert len(truck_rear_errors)==len(truck_targets)
for a in actors:
    for t in a.tags:assert not str(t).startswith(('GHS_','GHSDigitalTwin','GHSStorageGroup','TwinId=GHN')),(a.get_actor_label(),t)
    for c in a.get_components_by_class(u.StaticMeshComponent):
        assert c.static_mesh,(a.get_actor_label(),'missing mesh')
        assert all(c.get_material(i) for i in range(c.get_num_materials())),(a.get_actor_label(),'missing material')
        assert str(c.get_collision_profile_name())=='NoCollision',(a.get_actor_label(),'unnecessary collision')

camera=by['MPR_ReviewCamera'];roofs=[a for a in actors if a.actor_has_tag('MPR_Roof')]
assert len(roofs)>=4
old_transform=camera.get_actor_transform();old_view=E.get_level_viewport_camera_info()
old_hidden=[(a,a.get_editor_property('hidden'),a.is_temporarily_hidden_in_editor()) for a in roofs]
perf=u.get_default_object(u.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings'))
old_throttle=perf.get_editor_property('bThrottleCPUWhenNotForeground');perf.set_editor_property('bThrottleCPUWhenNotForeground',False)
old_delay=u.SystemLibrary.get_console_variable_int_value('r.HighResScreenshotDelay')
u.SystemLibrary.execute_console_command(E.get_editor_world(),'r.HighResScreenshotDelay 16')
A.set_selected_level_actors([]);L.editor_set_game_view(True)
views=[('01-exterior',[0,0,12],58000,-42,-75,False),
       ('02-context',[0,0,0],105000,-65,-70,False),
       ('03-interior',[0,0,0],56000,-65,-90,True),
       ('04-racks',[-35,-18,4],9500,-30,-55,True),
       ('05-sorting',[-112,-10,1.8],14000,-50,-80,True),
       ('06-docks',[-70,-84,2],12000,-24,-90,False),
       ('07-sorter-detail',[-108.78,-28.76,1.2],2300,-28,-55,True),
       ('08-rack-detail',[-35,-18,4],2700,-20,-55,True),
       ('09-site-roads',[65,-145,0],24000,-50,-80,False),
       ('10-railway',[210,-125,0],23000,-48,-65,False),
       ('11-roof',[30,-5,14],36500,-72,-90,False)]
report=dict(success=False,map=MAP,reload_verified=True,actors=len(actors),hism_groups=len(groups),instances=expected['instance_count'],
            no_ghs_business_tags=True,truck_rear_alignment_max_error_cm=max(truck_rear_errors),captures=[])
handle=None;index=0;task=None;pending=None;done=False;busy=False;start=time.monotonic()

def write():(OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def finish(error=None):
    global done
    if done:return
    done=True
    if handle:u.unregister_slate_post_tick_callback(handle)
    for a,h,eh in old_hidden:a.set_actor_hidden_in_game(h);a.set_is_temporarily_hidden_in_editor(eh)
    camera.set_actor_transform(old_transform,False,True);E.set_level_viewport_camera_info(*old_view)
    perf.set_editor_property('bThrottleCPUWhenNotForeground',old_throttle)
    u.SystemLibrary.execute_console_command(E.get_editor_world(),'r.HighResScreenshotDelay '+str(old_delay))
    report.update(success=error is None,error=error,elapsed=time.monotonic()-start)
    assert L.save_current_level()
    refresh_map_hash(ROOT,ownership)
    write()
    if '-MPRCaptureQuit' in u.SystemLibrary.get_command_line():u.SystemLibrary.quit_editor()
def tick(dt):
    global busy,index,task,pending
    if busy or done:return
    busy=True
    try:
        assert time.monotonic()-start<240,'capture deadline'
        if time.monotonic()-start<15:return
        if task:
            if not task.is_task_done():return
            if not pending['path'].exists() or pending['path'].stat().st_mtime_ns==pending['old']:return
            report['captures'].append(dict(name=pending['name'],path=str(pending['path']),bytes=pending['path'].stat().st_size));task=None;pending=None;write()
        if index==len(views):finish();return
        name,p,d,pitch,yaw,hidden=views[index];index+=1
        for a in roofs:a.set_actor_hidden_in_game(hidden);a.set_is_temporarily_hidden_in_editor(hidden)
        target=u.Vector(p[0]*100,-p[1]*100,p[2]*100);rot=u.Rotator(pitch=pitch,yaw=yaw);eye=target-u.MathLibrary.get_forward_vector(rot)*d
        camera.set_actor_location_and_rotation(eye,rot,False,True);E.set_level_viewport_camera_info(eye,rot)
        path=OUT/(name+'.png');pending=dict(name=name,path=path,old=path.stat().st_mtime_ns if path.exists() else 0)
        task=u.AutomationLibrary.take_high_res_screenshot(1920,1080,str(path),camera=camera,delay=2.)
        assert task
    except Exception:finish(traceback.format_exc())
    finally:busy=False
write();handle=u.register_slate_post_tick_callback(tick)
print('MPR_CAPTURE_STARTED',len(views),'views')
