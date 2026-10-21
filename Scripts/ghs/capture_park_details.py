"""Capture saved park detail views in UE; restore the existing review camera."""
import json
import time
import traceback
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/ParkRefinement'
EDITOR=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert not LEVELS.is_in_play_in_editor()
assert 'ZcoolSmartFactory' in EDITOR.get_editor_world().get_name()
camera=next(a for a in ACTORS.get_all_level_actors() if a.get_actor_label()=='GHSPark_Yard')
original_transform=camera.get_actor_transform()
original_view=EDITOR.get_level_viewport_camera_info()
original_selection=ACTORS.get_selected_level_actors()
original_game_view=LEVELS.editor_get_game_view()
LEVELS.editor_set_game_view(True);ACTORS.set_selected_level_actors([])
performance=unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings'))
throttle=performance.get_editor_property('bThrottleCPUWhenNotForeground')
performance.set_editor_property('bThrottleCPUWhenNotForeground',False)
views=[('SW_Gate',(4,185,1),12500,-38,-30),
       ('NE_Gate',(523,29,1),13500,-42,135),
       ('Housing',(302,343,3),8500,-43,-95),
       ('TruckCourt',(190,177,0),25000,-57,-90),
       ('ParkingUpper',(21,157,0),8500,-72,-90),
       ('ParkingLower',(20,218,0),8500,-72,-90),
       ('TreeDetail',(14.3,152.15,2),1400,-25,-125),
       ('WestForest',(-115,90,0),34000,-53,-110),
       ('NortheastForest',(555,-135,0),29000,-52,-110),
       ('NE_Parking',(486,20,0),10500,-78,-90)]
site=json.loads((ROOT/'SourceAssets/GHS/Park/site_geometry_report.json').read_text(encoding='utf-8'))
selected=next(s for s in site['parking']['stalls'] if s['row']=='upper_center_north' and s['occupied'])
views.append(('VehicleDetail',(*selected['center'],.8),1100,-32,-110))
manifest=json.loads((ROOT/'SourceAssets/GHS/Park/park_manifest.json').read_text(encoding='utf-8'))
truck=next(row for row in manifest['meshes'] if row['name']=='SM_GHSPark_ClosedTruck')['instances'][0]
views += [('DisplayTruckFront',(*truck['bay_center_uv_m'],1.8),2500,-25,truck['rotation_deg']+145),
          ('DisplayTruckRear',(*truck['bay_center_uv_m'],1.8),2500,-25,truck['rotation_deg']-35)]
started=time.monotonic();task=pending=handle=None;index=0;done=busy=False
report=dict(success=False,captures=[])

def write(): (OUT/'detail_capture_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

def finish(error=None):
    global done
    if done:return
    done=True
    if handle:unreal.unregister_slate_post_tick_callback(handle)
    camera.set_actor_transform(original_transform,False,True)
    EDITOR.set_level_viewport_camera_info(*original_view)
    ACTORS.set_selected_level_actors(original_selection)
    LEVELS.editor_set_game_view(original_game_view)
    performance.set_editor_property('bThrottleCPUWhenNotForeground',throttle)
    # Restore and persist only after the capture camera is back at its exact
    # saved transform. This leaves no test-only actor or lens in the scene.
    assert LEVELS.save_current_level()
    report.update(success=error is None,error=error,elapsed=time.monotonic()-started)
    write()

def tick(dt):
    global busy,task,pending,index
    if busy or done:return
    busy=True
    try:
        assert time.monotonic()-started<240,'Detail capture timed out'
        if task:
            if not task.is_task_done():return
            path=pending['path']
            if not path.exists() or path.stat().st_mtime_ns==pending['old']:return
            report['captures'].append(dict(view=pending['name'],path=str(path),bytes=path.stat().st_size))
            task=pending=None;write()
        if index==len(views):finish();return
        name,uv,distance,pitch,yaw=views[index];index+=1
        target=unreal.Vector((uv[0]-239.33385)*100,(uv[1]-60.24019)*100,uv[2]*100)
        rotation=unreal.Rotator(pitch=pitch,yaw=yaw)
        eye=target-unreal.MathLibrary.get_forward_vector(rotation)*distance
        camera.set_actor_location_and_rotation(eye,rotation,False,True)
        EDITOR.set_level_viewport_camera_info(eye,rotation)
        path=OUT/(name+'.png');pending=dict(name=name,path=path,old=path.stat().st_mtime_ns if path.exists() else 0)
        task=unreal.AutomationLibrary.take_high_res_screenshot(1920,1080,str(path),camera=camera,delay=2.)
        assert task
    except Exception:finish(traceback.format_exc())
    finally:busy=False

write();handle=unreal.register_slate_post_tick_callback(tick)
