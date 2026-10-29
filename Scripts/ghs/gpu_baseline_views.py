"""Owned, offscreen UE GPU evidence. No assets, maps or configuration are saved.

Run -game -RenderOffscreen -TwinDiagnostics -ResX=1920 -ResY=1080
 -ExecCmds="py D:/UEPro/Test/Scripts/ghs/gpu_baseline_views.py".
See gpu_baseline_README.md for isolated launch and result interpretation.
"""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import time
import traceback
import unreal

ROOT=Path('D:/UEPro/Test')
CLI=unreal.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+flag+r'(?=\s|$)',CLI,re.I) for flag in ('game','RenderOffscreen','TwinDiagnostics'))
STAMP=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
VISUAL_QA=bool(re.search(r'(?:^|\s)-GPUVisualQA(?=\s|$)',CLI,re.I))
PROFILE_QA=bool(re.search(r'(?:^|\s)-GPUHistoryProfile(?=\s|$)',CLI,re.I))
DEPTH_QA=bool(re.search(r'(?:^|\s)-GPUDepthQA(?=\s|$)',CLI,re.I))
assert sum((VISUAL_QA,PROFILE_QA,DEPTH_QA))<=1, 'Choose at most one diagnostic mode'
OUT=ROOT/'Saved/GPUOptimization'/(('depth_' if DEPTH_QA else 'profile_' if PROFILE_QA else 'visual_' if VISUAL_QA else 'baseline_')+STAMP)
OUT.mkdir(parents=True,exist_ok=True)
MAP=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
result=dict(success=False,assets_saved=False,scope='owned editor-game 1080p100% GPU benchmark; not server capacity',
            output=str(OUT),map_sha256_before=hashlib.sha256(MAP.read_bytes()).hexdigest(),views=[])
result['runtime_project']=unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
result['pid']=os.getpid()
world=pc=hud=pawn=handle=None
START=time.monotonic()
stage='discover'
old={}
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from profile_lighting import try_completed_csv

def write():
    result['stage']=stage
    (OUT/'report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    (ROOT/'Saved/GPUOptimization/latest.json').write_text(json.dumps(dict(report=str(OUT/'report.json'),stage=stage,success=result['success'],error=result.get('error')),indent=2),encoding='utf-8')

def cmd(value): unreal.SystemLibrary.execute_console_command(world,value,pc)
def action(name,**kwargs): hud.command(json.dumps(dict(action=name,**kwargs)))
def pause(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end: yield
def wait(condition,seconds=30):
    end=time.monotonic()+seconds
    while not condition():
        assert time.monotonic()<end, 'Deadline at '+stage
        yield
def discover():
    global world,pc,hud,pawn
    for candidate in unreal.ObjectIterator(unreal.World):
        if not candidate.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'): continue
        controller=unreal.GameplayStatics.get_player_controller(candidate,0)
        widget=getattr(controller,'twin_hud_widget',None) if controller else None
        if widget and widget.browser_ready:
            world,pc,hud,pawn=candidate,controller,widget,controller.get_controlled_pawn()
            return True
    return False
def pp_settings(settings):
    fields=('override_dynamic_global_illumination_method','dynamic_global_illumination_method',
            'override_reflection_method','reflection_method','override_ambient_occlusion_intensity',
            'ambient_occlusion_intensity','override_lumen_scene_lighting_quality','lumen_scene_lighting_quality')
    data={}
    for field in fields:
        try:
            value=settings.get_editor_property(field)
            data[field]=value if isinstance(value,(str,float,int,bool)) else str(value)
        except Exception: pass
    return data
def inspect_pp():
    data=[]
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.PostProcessVolume):
        entry=dict(name=actor.get_name(),settings=pp_settings(actor.settings))
        for field in ('enabled','unbound','priority','blend_weight','blend_radius'):
            try: entry[field]=actor.get_editor_property(field)
            except Exception: pass
        data.append(entry)
    camera=pawn.warehouse_camera
    return dict(volumes=data,camera_blend_weight=camera.post_process_blend_weight,
                camera_settings=pp_settings(camera.post_process_settings),
                note='World volume and camera overrides. GPU CSV passes establish actual rendered costs; not a final-view-PP native dump.')
def pose():
    camera=pawn.warehouse_camera
    p=camera.get_world_location();r=camera.get_world_rotation()
    return dict(location_cm=[p.x,p.y,p.z],rotation_deg=[r.pitch,r.yaw,r.roll],fov=camera.field_of_view,
                roof_closed=pc.warehouse_roof.is_roof_closed(),interior_available=pc.warehouse_roof.is_interior_available(),
                viewport=str(hud.get_viewport_pixel_size()))
def summarize_rhi(path):
    rows=list(csv.reader(io.StringIO(Path(path).read_text(encoding='utf-8-sig'))))
    indices=[i for i,row in enumerate(rows) if row and row[0]=='EVENTS']
    names=rows[indices[-1]]
    samples=rows[indices[0]+11:indices[-1]-10]
    output={}
    for name in ('RHI/DrawCalls','RHI/PrimitivesDrawn','GPUMem/UsedMB','GPUMem/AvailableMB','GPUMem/DemotedMB'):
        if name in names:
            index=names.index(name)
            values=[float(row[index]) for row in samples if len(row)>index and row[index]]
            output[name]=dict(mean=statistics.fmean(values),p95=sorted(values)[math.ceil(len(values)*.95)-1],unit='MiB' if name.startswith('GPUMem/') else 'count')
    output['primitive_note']='RHI PrimitivesDrawn is total submitted primitives, including non-triangle primitives; do not label as exact visible mesh triangles.'
    return output
def capture(name):
    global stage
    stage='warmup_'+name;write()
    yield from pause(10)
    entry=dict(name=name,camera=pose(),postprocess=inspect_pp(),
        observed_cvars={key:unreal.SystemLibrary.get_console_variable_string_value(key) for key in (
        'r.AntiAliasingMethod','sg.AntiAliasingQuality','r.TSR.History.ScreenPercentage','r.TSR.History.UpdateQuality',
        'r.TSR.History.R11G11B10','r.TSR.ShadingRejection.Flickering','r.ScreenPercentage','r.TSR.AsyncCompute')})
    entry['storage']=json.loads(pc.storage_capacity.get_report_json())
    filename='GPUOptimization_'+STAMP+'_'+name+'.csv'
    source=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()))/'Profiling/CSV'/filename
    cmd('CsvProfile STARTFILE='+filename)
    cmd('CsvProfile FRAMES=600')
    stage='capture_'+name;write()
    deadline=time.monotonic()+100
    sample=None
    while sample is None:
        assert time.monotonic()<deadline, 'CSV not complete: '+str(source)
        yield from pause(.5)
        sample=try_completed_csv(source,expected_frames=600)
    target=OUT/(name+'.csv')
    target.write_bytes(source.read_bytes())
    source.unlink()
    sample['csv']=str(target)
    entry.update(sample)
    control=re.search(r'(?:^|\s)-GHSStreamControlDir=(?:"([^"]+)"|(\S+))',CLI,re.I)
    if control:
        metrics_path=Path(control.group(1) or control.group(2))/'metrics.json'
        if metrics_path.exists():
            metrics=json.loads(metrics_path.read_text(encoding='utf-8-sig'))
            if metrics.get('pid')==os.getpid(): entry['native_runtime_metrics']=metrics
    entry['rhi']=summarize_rhi(target)
    entry['gpu_passes_descending']=sorted([dict(name=k,**v) for k,v in sample['metrics'].items()
        if k.startswith('GPU/') and k!='GPU/Total'],key=lambda x:x['mean_ms'],reverse=True)
    result['views'].append(entry)
    stage='screenshot_'+name;write()
    path=OUT/(name+'.png')
    cmd('Shot showui filename="'+str(path).replace('\\','/')+'" -nosuffix')
    yield from wait(lambda:path.exists(),15)
    entry['screenshot']=str(path)
    # Overlay captures happen after measured frames.
    cmd('stat RHI')
    yield from pause(1)
    statpath=OUT/(name+'_RHI.png')
    cmd('Shot showui filename="'+str(statpath).replace('\\','/')+'" -nosuffix')
    yield from wait(lambda:statpath.exists(),15)
    cmd('stat RHI')
    entry['rhi_screenshot']=str(statpath)
    write()
def run():
    global stage
    yield from wait(discover,120)
    result['postprocess_at_start']=inspect_pp()
    temporary={'r.GPUStatsEnabled':'1','r.GPUCsvStatsEnabled':'1','csv.CompressionMode':'0','t.MaxFPS':'0','r.VSync':'0',
               'r.VSyncEditor':'0','t.IdleWhenNotForeground':'0','Slate.bAllowThrottling':'0','r.DynamicRes.OperationMode':'0','r.ScreenPercentage':'100'}
    for key,value in temporary.items():
        old[key]=unreal.SystemLibrary.get_console_variable_string_value(key)
        cmd(key+' '+value)
    result['original_cvars']=old
    result['effective_cvars']={key:unreal.SystemLibrary.get_console_variable_string_value(key) for key in list(temporary)+[
        'r.AntiAliasingMethod','r.Shadow.Virtual.Enable','r.DynamicGlobalIlluminationMethod','r.ReflectionMethod','sg.ShadowQuality','sg.PostProcessQuality','sg.EffectsQuality',
        'sg.AntiAliasingQuality','r.TSR.History.ScreenPercentage','r.TSR.History.UpdateQuality','r.TSR.History.R11G11B10','r.TSR.ShadingRejection.Flickering','r.TSR.AsyncCompute',
        'r.EarlyZPass','r.EarlyZPassMovable','r.EarlyZPassOnlyMaterialMasking','r.TSR.16BitVALU','r.TSR.16BitVALU.Nvidia','r.TSR.WaveOps']}
    action('overview');hud.navigate('overview')
    yield from pause(20)
    if VISUAL_QA or PROFILE_QA or DEPTH_QA:
        yield from (run_depth_qa() if DEPTH_QA else run_history_profile() if PROFILE_QA else run_visual_qa())
        result['map_sha256_after']=hashlib.sha256(MAP.read_bytes()).hexdigest()
        assert result['map_sha256_after']==result['map_sha256_before']
        result['success']=True;stage='complete';write()
        return
    yield from capture('01_roof_closed')
    hud.open_warehouse()
    yield from wait(lambda:pc.warehouse_roof.is_interior_available(),10)
    yield from capture('02_roof_open')
    action('preset',value='floor')
    yield from pause(3)
    yield from capture('03_floor')
    action('preset',value='racks')
    yield from pause(3)
    yield from capture('04_racks')
    hud.navigate('trace')
    action('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-29T01:00:00Z',endUtc='2026-10-29T02:00:00Z')
    yield from pause(4)
    assert json.loads(hud.get_replay_state()).get('active'),hud.get_replay_state()
    action('replaySeek',time=230)
    action('replayPlay')
    yield from capture('05_replay')
    result['replay_state']=json.loads(hud.get_replay_state())
    result['map_sha256_after']=hashlib.sha256(MAP.read_bytes()).hexdigest()
    assert result['map_sha256_after']==result['map_sha256_before']
    result['success']=True
    stage='complete';write()

def screenshot(name):
    path=OUT/(name+'.png')
    cmd('Shot showui filename="'+str(path).replace('\\','/')+'" -nosuffix')
    yield from wait(lambda:path.exists(),15)
    return str(path)

def focus(uv,distance,pitch,yaw):
    target=unreal.Vector((uv[0]-239.33385)*100,(uv[1]-60.24019)*100,uv[2]*100)
    viewport=hud.get_viewport_pixel_size()
    center=unreal.Vector2D(hud.get_panel_position().x*.5,viewport.y*.5+28)
    pawn.transition_to_pose(target,distance,unreal.Rotator(pitch=pitch,yaw=yaw),viewport,center,True,0.)

def run_visual_qa():
    global stage
    old['r.TSR.History.ScreenPercentage']=unreal.SystemLibrary.get_console_variable_string_value('r.TSR.History.ScreenPercentage')
    for key,value in {'r.ProfileGPU.ShowUI':'0','r.ProfileGPU.ShowLeafEvents':'1'}.items():
        old[key]=unreal.SystemLibrary.get_console_variable_string_value(key);cmd(key+' '+value)
    result['visual_qa']=[]
    for history in (200,150,100):
        cmd('r.TSR.History.ScreenPercentage '+str(history))
        action('overview')
        yield from capture('Q_overview_history'+str(history))
        unreal.log('GPU_VISUAL_PROFILE_HISTORY_'+str(history))
        cmd('ProfileGPU')
        yield from pause(4)
        focus((25,121,9.6),7500,-30,-45)
        yield from pause(4)
        path=yield from screenshot('Q_glass_history'+str(history))
        result['visual_qa'].append(dict(history=history,view='glass',screenshot=path,camera=pose()))
        focus((170,56,9.8),18000,-45,-115)
        yield from pause(4)
        path=yield from screenshot('Q_roof_detail_history'+str(history))
        result['visual_qa'].append(dict(history=history,view='roof',screenshot=path,camera=pose()))
        stage='motion_roof_'+str(history);write()
        for frame in range(24):
            focus((170,56,9.8),18000,-45,-115+.35*(frame+1))
            yield
            path=yield from screenshot('Q_motion_roof_'+str(history)+'_%02d'%frame)
        hud.open_warehouse()
        yield from wait(lambda:pc.warehouse_roof.is_interior_available(),10)
        action('preset',value='racks')
        yield from pause(4)
        # Fixed screen-pixel input increments, same camera flight start per variant.
        stage='motion_racks_'+str(history);write()
        for frame in range(24):
            pawn.orbit_pixels(unreal.Vector2D(1.5,0))
            yield
            path=yield from screenshot('Q_motion_racks_'+str(history)+'_%02d'%frame)
        write()
    result['visual_qa_note']='Motion QA is deterministic stepped camera screenshots, not a real-time FPS or 60fps video proof.'
    cmd('r.TSR.History.ScreenPercentage '+old['r.TSR.History.ScreenPercentage'])

def run_history_profile():
    old['r.TSR.History.ScreenPercentage']=unreal.SystemLibrary.get_console_variable_string_value('r.TSR.History.ScreenPercentage')
    for key,value in {'r.ProfileGPU.ShowUI':'0','r.ProfileGPU.ShowLeafEvents':'1'}.items():
        old[key]=unreal.SystemLibrary.get_console_variable_string_value(key);cmd(key+' '+value)
    for history in (200,150):
        cmd('r.TSR.History.ScreenPercentage '+str(history))
        action('overview')
        yield from capture('P_closed_history'+str(history))
        unreal.log('GPU_FINAL_PROFILE_HISTORY_'+str(history))
        cmd('ProfileGPU')
        yield from pause(4)
    hud.open_warehouse()
    yield from wait(lambda:pc.warehouse_roof.is_interior_available(),10)
    action('preset',value='floor')
    yield from capture('P_floor_history150')
    unreal.log('GPU_FINAL_PROFILE_FLOOR_HISTORY150')
    cmd('ProfileGPU')
    yield from pause(4)
    cmd('r.TSR.History.ScreenPercentage '+old['r.TSR.History.ScreenPercentage'])

def run_depth_qa():
    """Read-only validation shared by externally configured mask0 / mask1 runs."""
    assert float(unreal.SystemLibrary.get_console_variable_string_value('r.TSR.History.ScreenPercentage'))==150
    yield from capture('D01_closed')
    focus((25,121,9.6),7500,-30,-45)
    yield from pause(4)
    result['glass_screenshot']=yield from screenshot('D_glass_vehicles_trees')
    action('overview')
    yield from pause(4)
    hud.open_warehouse()
    result['roof_transition_screenshots']=[]
    for frame in range(20):
        yield
        result['roof_transition_screenshots'].append((yield from screenshot('D_roof_open_%02d'%frame)))
    yield from wait(lambda:pc.warehouse_roof.is_interior_available(),10)
    yield from capture('D02_open')
    action('preset',value='floor')
    yield from pause(3)
    yield from capture('D03_floor_preset')
    action('preset',value='racks')
    yield from pause(3)
    yield from capture('D04_racks_preset')
    fixtures={}
    metadata=json.loads((ROOT/'Content/GHSTwinUI/data/storage-capacity.json').read_text())
    kinds={'GHSStorageGroup:'+g['actor']:g['kind'] for g in metadata['groups']}
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor):
        for comp in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            for tag in comp.component_tags:
                kind=kinds.get(str(tag))
                if kind and kind not in fixtures:
                    transform=comp.get_instance_transform(0,True)
                    target=unreal.MathLibrary.transform_location(transform,comp.static_mesh.get_bounds().origin)
                    fixtures[kind]=(comp,target)
    assert set(fixtures)=={'rack','floor'}
    result['capacity_closeups']=[]
    action('layers',pois=False)
    for capacity in (0.,.8,1.):
        action('capacity',rack=capacity,floor=capacity)
        yield from pause(3)
        for kind,(comp,target) in fixtures.items():
            viewport=hud.get_viewport_pixel_size()
            center=unreal.Vector2D(hud.get_panel_position().x*.5,viewport.y*.5+28)
            pawn.focus_on_target(target,3200 if kind=='rack' else 2400,unreal.Rotator(pitch=-40,yaw=-60),viewport,center,0.)
            yield from pause(3)
            path=yield from screenshot('D_capacity_'+kind+'_'+str(int(capacity*100)))
            result['capacity_closeups'].append(dict(capacity=capacity,kind=kind,camera=pose(),screenshot=path,storage=json.loads(pc.storage_capacity.get_report_json())))
            write()
    action('capacity',rack=.8,floor=1.)
    action('layers',pois=True)
    hud.navigate('trace')
    action('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-29T01:00:00Z',endUtc='2026-10-29T02:00:00Z')
    yield from pause(4)
    assert json.loads(hud.get_replay_state()).get('active')
    action('replaySeek',time=230)
    action('replayPlay')
    yield from capture('D05_replay')
    for key,value in {'r.ProfileGPU.ShowUI':'0','r.ProfileGPU.ShowLeafEvents':'1'}.items():
        old[key]=unreal.SystemLibrary.get_console_variable_string_value(key);cmd(key+' '+value)
    cmd('ProfileGPU')
    yield from pause(4)


generator=run()
def tick(delta):
    global handle,stage
    try:
        assert time.monotonic()-START<960,'Overall deadline exceeded'
        next(generator)
        return
    except StopIteration: pass
    except Exception:
        result['error']=traceback.format_exc();stage='failed';write();unreal.log_error(result['error'])
    try:
        for key,value in old.items(): cmd(key+' '+value)
        if handle: unreal.unregister_slate_post_tick_callback(handle);handle=None
        if world: unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)
    except Exception: unreal.log_error(traceback.format_exc())
write()
handle=unreal.register_slate_post_tick_callback(tick)
