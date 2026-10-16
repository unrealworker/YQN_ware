"""Read-only 16:9 render verification of the saved CAD rack revision.

Launch in a separate full UE Editor with -RenderOffscreen and optionally
-RefinementV2Style=blue or -RefinementV2Style=normal. Without the style flag the currently
loaded GHS map determines the style. Temporary inspection cameras are destroyed,
both map files are hash checked, and the process exits without saving assets.
"""
import hashlib
import json
import re
import struct
import time
import traceback
from pathlib import Path

import unreal


ROOT = Path(r'D:\UEPro\Test')
MAPS = {'Blue': '/Game/Maps/GHS_CAD_DigitalTwin',
        'Normal': '/Game/Maps/GHS_CAD_NormalWarehouse'}
RESOLUTION = (1920, 1080)
WARMUP_SECONDS = 20.0
CAPTURE_DELAY_SECONDS = 4.0
TIMEOUT_SECONDS = 480.0
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
settings = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.EditorPerformanceSettings'))
original_throttle = settings.get_editor_property('bThrottleCPUWhenNotForeground')
started = time.monotonic()
done = False
busy = False
callback = None
task = None
task_finished_at = None
pending = None
index = 0
views = []
temporary_cameras = []
saved_cameras = {}
original_viewport = None
report_path = ROOT / 'Saved/GHS_RefinementV2_CaptureReport.json'
report = dict(success=False, status='initializing', resolution=list(RESOLUTION), screenshots=[])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


map_hashes = {name: sha(ROOT / ('Content/Maps/' + path.rsplit('/',1)[-1] + '.umap'))
              for name,path in MAPS.items()}


def vector_values(vector):
    return [float(vector.x),float(vector.y),float(vector.z)]


def camera_state(camera):
    component = camera.get_component_by_class(unreal.CameraComponent)
    rotation = camera.get_actor_rotation()
    return dict(position_cm=vector_values(camera.get_actor_location()),
                rotation_degrees=[float(rotation.pitch),float(rotation.yaw),float(rotation.roll)],
                fov=float(component.get_editor_property('field_of_view')),
                aspect_ratio=float(component.get_editor_property('aspect_ratio')),
                constrain_aspect_ratio=bool(component.get_editor_property('constrain_aspect_ratio')))


def write_report():
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')


def png_resolution(path):
    with path.open('rb') as stream:
        header = stream.read(24)
    assert len(header)==24 and header[:8]==b'\x89PNG\r\n\x1a\n', 'Not a PNG: '+str(path)
    return struct.unpack('>II',header[16:24])


def finish(error=None):
    global done
    if done:
        return
    done = True
    if callback is not None:
        unreal.unregister_slate_post_tick_callback(callback)
    try:
        for camera in temporary_cameras:
            assert actors.destroy_actor(camera), 'Could not remove temporary capture camera'
        by_label = {actor.get_actor_label():actor for actor in actors.get_all_level_actors()}
        for label,state in saved_cameras.items():
            assert camera_state(by_label[label])==state, 'Saved camera changed: '+label
        if original_viewport:
            editor.set_level_viewport_camera_info(*original_viewport)
        for name,path in MAPS.items():
            current = sha(ROOT / ('Content/Maps/'+path.rsplit('/',1)[-1]+'.umap'))
            assert current==map_hashes[name], 'Capture changed saved map: '+name
        report.update(saved_cameras_unchanged=True,temporary_cameras_removed=True,
                      map_files_unchanged=True,map_file_sha256=map_hashes)
    except Exception:
        cleanup = traceback.format_exc()
        error = error+'\nCleanup error:\n'+cleanup if error else cleanup
    finally:
        settings.set_editor_property('bThrottleCPUWhenNotForeground',original_throttle)
    complete = error is None and len(report['screenshots'])==len(views) and len(views)>0
    report.update(success=complete,status='complete' if complete else 'failed',
                  screenshots_complete=complete,elapsed_seconds=round(time.monotonic()-started,2))
    if error:
        report['error']=error
        unreal.log_error('GHS_REFINEMENT_V2_CAPTURE_FAILED '+error)
    else:
        unreal.log('GHS_REFINEMENT_V2_CAPTURE_COMPLETE '+report['style'])
    write_report()
    # Deliberately no save_current_level, save_all_dirty_packages or config save.
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    global busy,index,task,pending,task_finished_at
    if busy or done:
        return
    busy=True
    try:
        now=time.monotonic()
        assert now-started<TIMEOUT_SECONDS, 'Timed out waiting for UE screenshots'
        if now-started<WARMUP_SECONDS:
            return
        if task is not None:
            if not task.is_task_done():
                return
            if task_finished_at is None:
                task_finished_at=now
            path=pending['path']
            valid=path.is_file() and path.stat().st_size>0
            if valid and pending['previous_mtime_ns'] is not None:
                valid=path.stat().st_mtime_ns!=pending['previous_mtime_ns']
            if not valid and now-task_finished_at<10:
                return
            assert valid, 'Screenshot was not refreshed: '+str(path)
            resolution=png_resolution(path)
            assert resolution==RESOLUTION, ('Wrong capture resolution',resolution)
            report['screenshots'].append(dict(view=pending['view'],path=str(path),
                bytes=path.stat().st_size,resolution=list(resolution),camera=pending['camera'],
                cad_anchor=pending.get('cad_anchor')))
            task=None
            pending=None
            task_finished_at=None
            write_report()
        if index>=len(views):
            finish()
            return
        view=views[index]
        index+=1
        camera=view['camera']
        path=view['path']
        editor.set_level_viewport_camera_info(camera.get_actor_location(),camera.get_actor_rotation())
        pending=dict(view=view['view'],path=path,camera=camera_state(camera),
                     previous_mtime_ns=path.stat().st_mtime_ns if path.exists() else None,
                     cad_anchor=view.get('cad_anchor'))
        report['status']='capturing_'+view['view']
        write_report()
        task=unreal.AutomationLibrary.take_high_res_screenshot(
            RESOLUTION[0],RESOLUTION[1],str(path),camera=camera,delay=CAPTURE_DELAY_SECONDS)
        assert task is not None, 'UE did not create a screenshot task'
    except Exception:
        finish(traceback.format_exc())
    finally:
        busy=False


def add_temporary(view,position_cm,target_cm,fov,anchor=None):
    position=unreal.Vector(*position_cm)
    rotation=unreal.MathLibrary.find_look_at_rotation(position,unreal.Vector(*target_cm))
    camera=actors.spawn_actor_from_class(unreal.CameraActor,position,rotation)
    assert camera, 'Could not create temporary capture camera'
    temporary_cameras.append(camera)
    camera.set_actor_label('TEMP_REFINEMENT_V2_CAPTURE_'+view)
    component=camera.get_component_by_class(unreal.CameraComponent)
    component.set_field_of_view(fov)
    component.set_aspect_ratio(16/9)
    component.set_editor_property('constrain_aspect_ratio',True)
    views.append(dict(view=view,camera=camera,
        path=ROOT/'Saved'/('GHS_RefinementV2_'+style+'_UE_'+view+'.png'),cad_anchor=anchor))


try:
    command_line=unreal.SystemLibrary.get_command_line()
    assert '-renderoffscreen' in command_line.lower(), 'Run this capture only in a separate -RenderOffscreen editor'
    requested=re.search(r'-RefinementV2Style=(blue|normal)\b',command_line,re.IGNORECASE)
    world=editor.get_editor_world()
    current=world.get_path_name().split('.')[0] if world else None
    if requested:
        style=requested.group(1).title()
    else:
        matching=[name for name,path in MAPS.items() if path==current]
        assert len(matching)==1, 'Load a revised GHS map or pass -RefinementV2Style=blue/normal'
        style=matching[0]
    map_path=MAPS[style]
    report_path=ROOT/'Saved'/('GHS_RefinementV2_'+style+'_CaptureReport.json')
    requested_view=re.search(r'-RefinementV2View=(\w+)\b',command_line)
    if requested_view:
        report_path=ROOT/'Saved'/('GHS_RefinementV2_'+style+'_'+requested_view.group(1)+'_CaptureReport.json')
    if current!=map_path:
        assert levels.load_level(map_path), 'Could not load '+map_path
    settings.set_editor_property('bThrottleCPUWhenNotForeground',False)
    original_viewport=editor.get_level_viewport_camera_info()
    existing={actor.get_actor_label():actor for actor in actors.get_all_level_actors()}
    for label,actor in existing.items():
        if actor.get_component_by_class(unreal.CameraComponent):
            saved_cameras[label]=camera_state(actor)
    for view in ['Overview','RackAisles']:
        saved=existing['CAM_GHS_'+view]
        state=camera_state(saved)
        position=saved.get_actor_location()
        camera=actors.spawn_actor_from_class(unreal.CameraActor,position,saved.get_actor_rotation())
        assert camera
        temporary_cameras.append(camera)
        camera.set_actor_label('TEMP_REFINEMENT_V2_CAPTURE_'+view)
        component=camera.get_component_by_class(unreal.CameraComponent)
        component.set_field_of_view(state['fov'])
        component.set_aspect_ratio(16/9)
        component.set_editor_property('constrain_aspect_ratio',True)
        views.append(dict(view=view,camera=camera,path=ROOT/'Saved'/('GHS_RefinementV2_'+style+'_UE_'+view+'.png')))
    mapping=json.loads((ROOT/'SourceAssets/GHS/RefinementV2/Layout/rack_spacing.json').read_text(encoding='utf-8'))
    rows={row['instance_id']:row for row in mapping['racks']}
    # Cameras stay in the open southern cross aisle or eastern main aisle.
    # The two level-count views look toward the unobstructed end bay fronts;
    # the pass view faces the eastmost B pass without intermediate rack rows.
    details=[
        ('TypeA_4Levels','CAD_33B72D',(11,-13,9.8),(0,0,4.5),60),
        ('TypeB_12Levels','CAD_35ED2D_36DD2F',(14,-11,9.2),(0,0,4.5),60),
        ('Pass_Clearance','CAD_35ED2D_36C4E2',(17,-3,7.8),(0,0,4.5),60),
        ('DockD1_2UpperLevels','CAD_35ED2D_36CA5D',(0,10,6.2),(0,0,4.5),70),
    ]
    for view,identifier,offset,target_offset,fov in details:
        row=rows[identifier]
        x,y=row['position_m']
        ox,oy,oz=offset
        tx,ty,tz=target_offset
        position=[(x+ox)*100,-(y+oy)*100,oz*100]
        target=[(x+tx)*100,-(y+ty)*100,tz*100]
        add_temporary(view,position,target,fov,
            dict(instance_id=identifier,spec_type=row['spec_type'],pass_variant=row['pass_variant'],
                 position_m=row['position_m'],target_cm=target))
    add_temporary('DockExterior',[-15500,8300,1600],[-16650,5900,460],56)
    add_temporary('HalfOpenDoor',[-17270,5370,190],[-17270,5900,210],62)
    add_temporary('RecoveredStorage',[-2800,-1500,1400],[-3500,-2350,100],62)
    add_temporary('RecoveredRack',[-21700,4900,1100],[-22620,3907,430],60)
    add_temporary('ClosedCorner',[23700,6600,1600],[22000,5100,430],58)
    if requested_view:
        views=[v for v in views if v['view']==requested_view.group(1)]
        assert len(views)==1,'Unknown inspection view'
    actors.set_selected_level_actors([])
    report.update(style=style,map=map_path,status='waiting_for_shaders',
                  warmup_seconds=WARMUP_SECONDS,capture_delay_seconds=CAPTURE_DELAY_SECONDS,
                  camera_count=len(views),saved_camera_count=len(saved_cameras),
                  initial_map_file_sha256=map_hashes,
                  view_plan=[dict(view=v['view'],camera=camera_state(v['camera']),cad_anchor=v.get('cad_anchor')) for v in views])
    write_report()
    started=time.monotonic()
    callback=unreal.register_slate_post_tick_callback(tick)
    unreal.log('GHS_REFINEMENT_V2_CAPTURE_QUEUED '+style+': eleven 1920x1080 read-only captures')
except Exception:
    finish(traceback.format_exc())
    raise
