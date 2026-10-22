"""Capture exterior, roof details and the intact interior with roof hidden."""
import json
import copy
import importlib
import sys
from pathlib import Path
import time
import traceback
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/ParkReferenceStyle'
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import reference_style_materials
importlib.reload(reference_style_materials)
base=json.loads((ROOT/'SourceAssets/GHS/Park/reference_style.json').read_text(encoding='utf-8'))
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
controls=['r.HighResScreenshotDelay','ShowFlag.PostProcessing','ShowFlag.AntiAliasing','ShowFlag.TemporalAA','r.Shadow.Virtual.NormalBias','r.Shadow.Virtual.ScreenRayLength']
old_controls={key:unreal.SystemLibrary.get_console_variable_float_value(key) for key in controls}
for key,value in [('r.HighResScreenshotDelay',32),('ShowFlag.PostProcessing',1),('ShowFlag.AntiAliasing',1),('ShowFlag.TemporalAA',1)]:unreal.SystemLibrary.execute_console_command(world,key+' '+str(value))
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor()
by={a.get_actor_label():a for a in actors.get_all_level_actors()}
roof=by['GHS_MainWarehouseRoof'];camera=by['GHSPark_Yard']
key=by['GHS_CoolOverheadKey'].get_component_by_class(unreal.DirectionalLightComponent)
old_contact=key.get_editor_property('contact_shadow_length')
original_transform=camera.get_actor_transform()
original_view=editor.get_level_viewport_camera_info()
original_selection=actors.get_selected_level_actors()
original_game_view=levels.editor_get_game_view()
original_hidden=roof.get_editor_property('hidden')
original_editor_hidden=roof.is_temporarily_hidden_in_editor()
levels.editor_set_game_view(True);actors.set_selected_level_actors([])
performance=unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings'))
throttle=performance.get_editor_property('bThrottleCPUWhenNotForeground')
performance.set_editor_property('bThrottleCPUWhenNotForeground',False)
views=[('Render_AA',(-59.59298,-264.43257,4.5),2200,-25,-110,False),
       ('Render_ContactOff',(-59.59298,-264.43257,4.5),2200,-25,-110,False),
       ('Render_TraceOff',(-59.59298,-264.43257,4.5),2200,-25,-110,False)]
started=time.monotonic();task=pending=handle=None;index=0;done=busy=False
report=dict(success=False,captures=[])
def write(): (OUT/'shadow_probe_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
def finish(error=None):
    global done
    if done:return
    done=True
    report['saved']=False
    try:
        if handle:unreal.unregister_slate_post_tick_callback(handle)
        roof.set_actor_hidden_in_game(original_hidden);roof.set_is_temporarily_hidden_in_editor(original_editor_hidden)
        camera.set_actor_transform(original_transform,False,True)
        editor.set_level_viewport_camera_info(*original_view)
        actors.set_selected_level_actors(original_selection)
        levels.editor_set_game_view(original_game_view)
        performance.set_editor_property('bThrottleCPUWhenNotForeground',throttle)
        report['roof_visibility_restored']=(roof.get_editor_property('hidden')==original_hidden and
                                            roof.is_temporarily_hidden_in_editor()==original_editor_hidden)
        reference_style_materials.apply(base,save_assets=False)
        key.set_editor_property('contact_shadow_length',old_contact)
        for render_name,render_value in old_controls.items():unreal.SystemLibrary.execute_console_command(world,render_name+' '+str(render_value))
    except Exception:
        error=(error+'\n' if error else '')+traceback.format_exc()
    finally:
        report.update(success=error is None,error=error,elapsed=time.monotonic()-started)
        write()
def tick(dt):
    global busy,task,pending,index
    if busy or done:return
    busy=True
    try:
        assert time.monotonic()-started<150
        if task:
            if not task.is_task_done():return
            path=pending['path']
            if not path.exists() or path.stat().st_mtime_ns==pending['old']:return
            report['captures'].append(dict(view=pending['name'],path=str(path),roof_hidden=pending['hidden'],bytes=path.stat().st_size))
            task=pending=None;write()
        if index==len(views):finish();return
        name,uv,distance,pitch,yaw,hidden=views[index];index+=1
        if name in ('Render_ContactOff','Render_Fill'):unreal.SystemLibrary.execute_console_command(world,'r.Shadow.Virtual.NormalBias 1.5')
        if name=='UnusedFillVariant':
            fill=copy.deepcopy(base);fill['lighting']['skylight_intensity']=.42;fill['lighting']['lower_hemisphere_color']=[.14,.18,.22]
            reference_style_materials.apply(fill,save_assets=False)
        roof.set_actor_hidden_in_game(hidden);roof.set_is_temporarily_hidden_in_editor(hidden)
        target=unreal.Vector((uv[0]-239.33385)*100,(uv[1]-60.24019)*100,uv[2]*100)
        rotation=unreal.Rotator(pitch=pitch,yaw=yaw)
        eye=target-unreal.MathLibrary.get_forward_vector(rotation)*distance
        camera.set_actor_location_and_rotation(eye,rotation,False,True)
        editor.set_level_viewport_camera_info(eye,rotation)
        path=OUT/(name+'.png')
        pending=dict(name=name,path=path,hidden=hidden,old=path.stat().st_mtime_ns if path.exists() else 0)
        task=unreal.AutomationLibrary.take_high_res_screenshot(1920,1080,str(path),camera=camera,delay=2.)
        assert task
    except Exception:finish(traceback.format_exc())
    finally:busy=False
write();handle=unreal.register_slate_post_tick_callback(tick)
