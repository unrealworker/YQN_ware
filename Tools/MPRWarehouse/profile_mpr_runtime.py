"""Owned MPR editor-game profiling only; never save maps, assets or settings.

Launch with -game -RenderOffscreen -MPRProfile -ForceRes -ResX=1920 -ResY=1080
and -ExecCmds="py D:/UEPro/Test/Tools/MPRWarehouse/profile_mpr_runtime.py".
Exterior/interior each warm for 15 seconds, then record 15 seconds of native
CSV. Screenshots occur only after capture has stopped and the CSV has flushed.
"""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import struct
import time
import traceback
import unreal as u

ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
OUT=ROOT/'Saved/MPR'
MAP='/Game/Maps/MPR_CAD_Warehouse'
MAP_FILE=ROOT/'Content/Maps/MPR_CAD_Warehouse.umap'
START=time.monotonic()
STAMP=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
DEADLINE_SECONDS=150
world=pc=pawn=camera=handle=None
roofs=[]
original_hidden=[]
original_cvars={}
original_pawn_tick=None
original_view_target=None
original_camera_transform=None
finished=False
capturing=False
busy=False
stage='initializing'
result={'success':False,'map':MAP,'run_id':STAMP,'assets_saved':False,'performance':{},'captures':[],
    'scope':'One local UnrealEditor -game offscreen process, static exterior/interior, no HUD; not Pixel Streaming or concurrency acceptance.',
    'warmup_seconds_per_state':15,'capture_seconds_per_state':15,
    'timing_source':'Native CSV FrameTime, GameThreadTime, RenderThreadTime, GPUTime. Python/Slate callback intervals are not used as frame/GPU timing.',
    'deadline_seconds':DEADLINE_SECONDS}


def write():
    OUT.mkdir(parents=True,exist_ok=True)
    result.update(stage=stage,elapsed_seconds=time.monotonic()-START)
    (OUT/'performance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


def console(command):u.SystemLibrary.execute_console_command(world,command,pc)
def xyz(v):return [float(v.x),float(v.y),float(v.z)]


def view():
    mgr=pc.player_camera_manager;r=mgr.get_camera_rotation()
    return {'position_cm':xyz(mgr.get_camera_location()),'rotation_deg':[r.pitch,r.yaw,r.roll],
        'viewport':list(pc.get_viewport_size()),'view_target':pc.get_view_target().get_path_name() if pc.get_view_target() else None}


def camera_matches(expected):
    actual=view()
    return actual['viewport']==[1920,1080] and pc.get_view_target()==camera and all(abs(a-b)<.03
        for field in ('position_cm','rotation_deg') for a,b in zip(actual[field],expected[field]))


def business_state():
    # Strict reflection access deliberately raises if a Python property name is
    # wrong: getattr(..., None) could otherwise silently conceal a live HUD.
    twin=pc.get_editor_property('twin_hud_widget')
    trucks=pc.get_editor_property('truck_hud_widget')
    traffic=pc.get_editor_property('campus_traffic')
    roof=pc.get_editor_property('warehouse_roof')
    storage=pc.get_editor_property('storage_capacity')
    replay=pc.get_editor_property('order_replay')
    assert twin is None and trucks is None,'Unexpected live GHS HUD widget'
    assert traffic is None,'Unexpected live GHS campus traffic actor'
    assert roof and storage and replay,'Shared controller components missing'
    storage_report=json.loads(storage.get_report_json())
    state={'controller_tick_enabled':pc.is_actor_tick_enabled(),'pawn_tick_enabled':pawn.is_actor_tick_enabled(),
        'hud_properties_checked':['twin_hud_widget','truck_hud_widget'],'both_hud_references_null':True,
        'campus_traffic_null':True,'roof_component_tick_enabled':roof.is_component_tick_enabled(),
        'roof_component_has_ghs_roof':roof.has_roof(),'storage_component_tick_enabled':storage.is_component_tick_enabled(),
        'storage_initialized':bool(storage_report.get('initialized')),
        'replay_component_tick_enabled':replay.is_component_tick_enabled(),'replay_active':replay.is_replaying()}
    assert not state['roof_component_has_ghs_roof'] and not state['storage_initialized'] and not state['replay_active'],'Unexpected initialized GHS business state'
    assert not any(state[key] for key in ('roof_component_tick_enabled','storage_component_tick_enabled','replay_component_tick_enabled')),'Unexpected active GHS business component tick'
    return state


def finite_view(state):
    assert state['viewport']==[1920,1080],'Viewport changed during camera validation'
    assert all(math.isfinite(v) for key in ('position_cm','rotation_deg') for v in state[key]),'Camera produced NaN or Inf'
    assert state['position_cm'][2]>0,'Camera moved below the warehouse ground'
    return state


def validate_camera_controls():
    # Exercise the existing pawn with its original tick enabled before sampling.
    # Calls test its production camera API, not OS mouse/keyboard delivery.
    assert pawn.is_actor_tick_enabled(),'Original shared camera pawn tick was disabled'
    pc.cancel_camera_drag();pc.set_view_target_with_blend(pawn,0.)
    pawn.reset_overview(True)
    yield from pause(.5)
    assert pc.get_view_target()==pawn,'Shared pawn did not become the rendered view target'
    baseline=finite_view(view());pivot=xyz(pawn.get_actor_location())
    baseline_distance=math.dist(baseline['position_cm'],pivot)
    assert baseline_distance>1000,'Invalid overview orbit distance'
    pawn.zoom_steps(1.)
    def zoom_changed():
        current=finite_view(view())
        return pc.get_view_target()==pawn and math.dist(current['position_cm'],pivot)<baseline_distance*.99
    yield from wait('camera_zoom_changes_rendered_distance',zoom_changed,seconds=6,stable=3)
    zoomed=finite_view(view());zoom_distance=math.dist(zoomed['position_cm'],pivot)
    pawn.orbit_pixels(u.Vector2D(100,25))
    def orbit_changed():
        current=finite_view(view())
        return pc.get_view_target()==pawn and abs((current['rotation_deg'][1]-zoomed['rotation_deg'][1]+180)%360-180)>5
    yield from wait('camera_orbit_changes_rendered_rotation',orbit_changed,seconds=6,stable=3)
    orbited=finite_view(view())
    pawn.reset_overview(True)
    def reset_matches():
        current=finite_view(view())
        return pc.get_view_target()==pawn and math.dist(current['position_cm'],baseline['position_cm'])<2 and all(
            abs((a-b+180)%360-180)<.1 for a,b in zip(current['rotation_deg'],baseline['rotation_deg']))
    yield from wait('camera_reset_restores_overview',reset_matches,seconds=6,stable=5)
    reset=finite_view(view())
    assert pawn.is_actor_tick_enabled(),'Camera test unexpectedly disabled the pawn tick'
    result['camera_controls']={'success':True,'api_sequence':['reset_overview(True)','zoom_steps(1)','orbit_pixels(100,25)','reset_overview(True)'],
        'scope':'Actual player-camera readback via shared production pawn APIs; not OS input delivery.',
        'pawn_tick_enabled_throughout':True,'baseline':baseline,'after_zoom':zoomed,'after_orbit':orbited,'after_reset':reset,
        'baseline_distance_cm':baseline_distance,'zoom_distance_cm':zoom_distance,
        'orbit_yaw_delta_deg':abs((orbited['rotation_deg'][1]-zoomed['rotation_deg'][1]+180)%360-180),
        'reset_position_error_cm':math.dist(reset['position_cm'],baseline['position_cm'])}
    write()


def wait(name,predicate,seconds=20,stable=1):
    global stage
    stage=name;until=time.monotonic()+seconds;count=0
    while True:
        assert time.monotonic()<until,'Timed out: '+name
        count=count+1 if predicate() else 0
        if count>=stable:return
        yield


def pause(seconds,expected=None):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        if expected:assert camera_matches(expected),'Camera/viewport changed while warming or sampling'
        yield


def discover():
    global world,pc,pawn,camera,roofs
    for candidate in u.ObjectIterator(u.World):
        if not candidate.get_path_name().startswith(MAP+'.'):continue
        controller=u.GameplayStatics.get_player_controller(candidate,0)
        if not controller:continue
        controlled=controller.get_controlled_pawn()
        if not controlled:continue
        world,pc,pawn=candidate,controller,controlled
        actors=list(u.GameplayStatics.get_all_actors_of_class(world,u.Actor))
        cameras=[a for a in actors if isinstance(a,u.CameraActor) and a.get_actor_label()=='MPR_ReviewCamera']
        if len(cameras)!=1:return False
        camera=cameras[0];roofs=[a for a in actors if a.actor_has_tag('MPR_Roof')]
        assert len(roofs)>=4,'MPR roof fixture is missing'
        shared_camera_class=getattr(u,'GHSWarehouseCameraPawn',None)
        assert shared_camera_class and isinstance(pawn,shared_camera_class),'Shared GHS camera pawn is missing'
        shared_controller_class=getattr(u,'GHSWarehousePlayerController',None)
        assert shared_controller_class and isinstance(pc,shared_controller_class),'Shared warehouse controller missing'
        state=business_state()
        forbidden=[]
        for actor in actors:
            cls=actor.get_class().get_name()
            tags=[str(t) for t in actor.tags]
            if cls in ('GHSCampusTrafficActor','GHSOrderReplayActor') or any(t.startswith(('GHS_','GHSDigitalTwin','GHSStorageGroup','TwinId=GHN')) for t in tags):
                forbidden.append({'name':actor.get_actor_label(),'class':cls,'tags':tags})
        assert not forbidden,('Unexpected GHS business actors',forbidden)
        result['runtime_fixture']={'world':world.get_path_name(),'controller_class':pc.get_class().get_path_name(),
            'pawn':pawn.get_path_name(),'pawn_class':pawn.get_class().get_path_name(),'camera':camera.get_path_name(),
            'roof_actor_count':len(roofs),'actor_count':len(actors),'ghs_hud_absent':True,'ghs_business_actors_absent':True,
            'business_state_before_camera_changes':state}
        return True
    return False


def stats(values):
    ordered=sorted(values);count=len(ordered)
    assert count>=50 and all(math.isfinite(v) and v>=0 for v in ordered),'Invalid/too few native samples'
    return {'count':count,'mean_ms':statistics.fmean(ordered),'median_ms':statistics.median(ordered),
        'p95_ms':ordered[math.ceil(count*.95)-1],'p99_ms':ordered[math.ceil(count*.99)-1],'max_ms':ordered[-1],
        'over_16_67ms_count':sum(v>1000/60 for v in ordered),'over_33_33ms_count':sum(v>1000/30 for v in ordered),
        'over_50ms_count':sum(v>50 for v in ordered)}


def csv_complete(path):
    try:
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-32768))
            return b'[HasHeaderRowAtEnd],1' in stream.read()
    except OSError:return False


def parse_csv(path):
    raw=path.read_bytes();rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    headers=[i for i,row in enumerate(rows) if row and row[0]=='EVENTS']
    assert 1<=len(headers)<=2,'CSV lacks finalized header or contains unexpected headers'
    names=rows[headers[-1]];first=headers[0]+1 if len(headers)>1 else 0
    initial_names=rows[headers[0]]
    assert initial_names==names[:len(initial_names)],'CSV final header does not extend its initial header'
    frames=rows[first:headers[-1]]
    required=('FrameTime','GameThreadTime','RenderThreadTime','GPUTime')
    assert all(initial_names.count(name)==1 for name in required),(path,'Missing/ambiguous initial native timing columns',initial_names)
    # UE5.8 FCsvStreamWriter appends VisibleSeries as they are registered and
    # writes only the current series for each row. Its final header may therefore
    # be wider than earlier rows. Accept only that append-only shape; truncation
    # after a column has appeared, or loss of any initial column, remains invalid.
    previous_width=len(initial_names)
    for index,row in enumerate(frames):
        assert previous_width<=len(row)<=len(names),('CSV row width is invalid',index,previous_width,len(row),len(names))
        previous_width=len(row)
    def column(name,allow_unregistered=False):
        index=names.index(name)
        assert allow_unregistered or all(index<len(row) for row in frames),'Missing native timing '+name
        values=[float(row[index]) if index<len(row) else 0.0 for row in frames]
        assert all(math.isfinite(v) and v>=0 for v in values),'Invalid timing '+name
        return values
    values={name:column(name) for name in required}
    positive=sum(v>0 for v in values['GPUTime'])/max(1,len(frames))
    passes=[n for n in names if n.startswith('GPU/') and n not in ('GPU/Total','GPU/Unaccounted')]
    assert passes,'No native GPU pass timestamps; GPU/Unaccounted is not total GPU time'
    pass_values=[column(n,allow_unregistered=True) for n in passes]
    late_pass_zero_fill={n:sum(names.index(n)>=len(row) for row in frames)
                        for n in passes if names.index(n)>=len(initial_names)}
    late_pass_zero_fill={n:count for n,count in late_pass_zero_fill.items() if count}
    pass_positive=sum(any(v>0 for v in frame) for frame in zip(*pass_values))/max(1,len(frames))
    assert positive>=.95 and pass_positive>=.95,('Insufficient positive GPU timestamps',positive,pass_positive)
    native_seconds=sum(values['FrameTime'])/1000
    assert native_seconds>=10,('Native CSV duration too short',native_seconds)
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'timing_unit':'ms','frame_count':len(frames),
        'native_frame_time_seconds':native_seconds,'metrics':{n:stats(v) for n,v in values.items()},
        'gpu_verified':True,'gpu_evidence':{'mode':'UE5.8 RHI','primary_metric':'GPUTime','positive_frame_ratio':positive,
            'gpu_pass_positive_frame_ratio':pass_positive,'pass_columns':passes,
            'unregistered_tail_pass_zero_fill_counts':late_pass_zero_fill},
        'window':'All finalized native CSV frames between start and stop, including boundary frames; no spikes removed.',
        'percentile_method':'nearest-rank'}


def png_ready(path):
    try:
        with path.open('rb') as stream:
            if stream.read(8)!=b'\x89PNG\r\n\x1a\n':return False
            stream.seek(16);size=struct.unpack('>II',stream.read(8))
            stream.seek(-12,2);ended=stream.read()==b'\x00\x00\x00\x00IEND\xaeB\x60\x82'
        assert size==(1920,1080),('Screenshot resolution mismatch',size)
        return ended
    except (OSError,struct.error):return False


def sample(name,target_m,distance,pitch,yaw,hidden):
    global capturing,stage
    before_business=business_state()
    assert before_business['pawn_tick_enabled']==original_pawn_tick,'Shared pawn tick changed during profiling'
    for actor in roofs:actor.set_actor_hidden_in_game(hidden)
    assert all(bool(a.get_editor_property('hidden'))==hidden for a in roofs)
    rot=u.Rotator(pitch=pitch,yaw=yaw);target=u.Vector(target_m[0]*100,-target_m[1]*100,target_m[2]*100)
    eye=target-u.MathLibrary.get_forward_vector(rot)*distance
    camera.set_actor_location_and_rotation(eye,rot,False,True)
    pc.set_view_target_with_blend(camera,0.)
    expected={'position_cm':xyz(eye),'rotation_deg':[pitch,yaw,0.]}
    yield from wait(name+'_fixed_camera',lambda:camera_matches(expected),stable=5)
    stage=name+'_warmup';write();yield from pause(15,expected)
    filename='MPR_'+STAMP+'_'+name+'.csv';path=ROOT/'Saved/Profiling/CSV'/filename
    assert not path.exists(),'Fresh capture filename already exists'
    console('CsvProfile STARTFILE='+filename);console('CsvProfile START');capturing=True
    stage=name+'_capture';t0=time.monotonic();yield from pause(15,expected)
    wall_seconds=time.monotonic()-t0;console('CsvProfile STOP');capturing=False
    yield from wait(name+'_csv_flush',lambda:csv_complete(path),seconds=20)
    after_business=business_state()
    assert before_business==after_business,'Business/pawn tick state changed during sample'
    result['performance'][name]={'camera':view(),'roof_hidden':hidden,'warmup_seconds':15,'sample_wall_seconds':wall_seconds,'native_csv':parse_csv(path),
        'runtime_state_before':before_business,'runtime_state_after':after_business,'pawn_tick_suppressed':False}
    write()
    # Allow GPU CSV drain to finish before requesting a screenshot.
    yield from pause(.5,expected)
    png=OUT/('performance_'+STAMP+'_'+name+'.png');assert not png.exists()
    console('Shot showui filename="'+png.as_posix()+'" -nosuffix')
    yield from wait(name+'_screenshot',lambda:png_ready(png),seconds=15)
    assert camera_matches(expected),'Camera changed for screenshot'
    result['captures'].append({'state':name,'path':str(png),'sha256':hashlib.sha256(png.read_bytes()).hexdigest(),
        'size':[1920,1080],'camera':view(),'roof_hidden':hidden,'outside_performance_window':True});write()


def run():
    global original_pawn_tick,original_view_target,original_camera_transform,stage
    cli=u.SystemLibrary.get_command_line()
    assert all(re.search(r'(?:^|\s)-'+f+r'(?=\s|$)',cli,re.I) for f in ('game','RenderOffscreen','MPRProfile')),'Only owned -game -RenderOffscreen -MPRProfile allowed'
    assert not re.search(r'(?:^|\s)-(TwinPerf=|UseFixedTimeStep\b)',cli,re.I),'Do not combine benchmark drivers/fixed timesteps'
    result['command_line']=cli;result['engine_version']=u.SystemLibrary.get_engine_version()
    assert re.match(r'5\.8\.',result['engine_version']),'This GPU evidence check is for UE 5.8'
    result['map_sha256_before']=hashlib.sha256(MAP_FILE.read_bytes()).hexdigest()
    result['render_quality']={key:u.SystemLibrary.get_console_variable_string_value(key) for key in
        ('r.Nanite.MaxPixelsPerEdge','r.Nanite.AllowVoxels','r.Shadow.Virtual.Enable')}
    yield from wait('discover',discover,seconds=30)
    yield from wait('viewport_1920x1080',lambda:list(pc.get_viewport_size())==[1920,1080],seconds=10,stable=4)
    original_pawn_tick=pawn.is_actor_tick_enabled();original_view_target=pc.get_view_target();original_camera_transform=camera.get_actor_transform()
    original_hidden.extend((a,bool(a.get_editor_property('hidden'))) for a in roofs)
    yield from validate_camera_controls()
    pawn.cancel_pose_transition();pawn.freeze_current_pose()
    assert pawn.is_actor_tick_enabled()==original_pawn_tick,'Production pawn tick must be preserved'
    result['profiling_camera_policy']='Static MPR_ReviewCamera is the view target; shared pawn retains its original enabled tick. No business/controller/component tick is suppressed.'
    cvars={'r.GPUCsvStatsEnabled':1,'csv.CompressionMode':0,'t.MaxFPS':0,'r.VSync':0,'t.IdleWhenNotForeground':0,
        'Slate.bAllowThrottling':0,'r.DynamicRes.OperationMode':0,'r.ScreenPercentage':100}
    for key,value in cvars.items():
        previous=u.SystemLibrary.get_console_variable_string_value(key);assert previous!='','Missing cvar '+key
        original_cvars[key]=previous;console(key+' '+str(value))
    console('DisableAllScreenMessages')
    result['capture_cvars']=cvars;result['original_cvars']=dict(original_cvars);write()
    yield from sample('exterior',[0,0,12],58000,-42,-75,False)
    yield from sample('interior',[0,0,0],56000,-65,-90,True)
    assert set(result['performance'])=={'exterior','interior'} and len(result['captures'])==2
    result['map_sha256_after']=hashlib.sha256(MAP_FILE.read_bytes()).hexdigest()
    assert result['map_sha256_before']==result['map_sha256_after'],'Map file unexpectedly changed'
    result['map_unchanged']=True


def finish(error=None):
    global finished,handle,capturing,stage
    if finished:return
    finished=True;stage='failed' if error else 'complete';result['error']=error
    restore_errors=[]
    try:
        if capturing:console('CsvProfile STOP');capturing=False
        for actor,hidden in original_hidden:actor.set_actor_hidden_in_game(hidden)
        if camera and original_camera_transform:camera.set_actor_transform(original_camera_transform,False,True)
        if pc and original_view_target:pc.set_view_target_with_blend(original_view_target,0.)
        if pawn and original_pawn_tick is not None:pawn.set_actor_tick_enabled(original_pawn_tick)
        for key,value in original_cvars.items():console(key+' '+value)
    except Exception:restore_errors.append(traceback.format_exc())
    result['restore_errors']=restore_errors;result['success']=error is None and not restore_errors
    if restore_errors:stage='failed'
    try:write()
    finally:
        if handle is not None:
            u.unregister_slate_post_tick_callback(handle);handle=None
        (u.log if result['success'] else u.log_error)('MPR_PERFORMANCE '+json.dumps({'success':result['success'],'report':str(OUT/'performance.json'),'error':result['error']}))
        if world and pc:u.SystemLibrary.quit_game(world,pc,u.QuitPreference.QUIT,False)
        else:u.SystemLibrary.execute_console_command(None,'quit')


steps=run()


def tick(delta):
    global busy
    if finished or busy:return
    busy=True
    try:
        assert time.monotonic()-START<DEADLINE_SECONDS,'MPR profiling deadline exceeded (150s)'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
    finally:busy=False


if __name__=='__main__':
    write()
    handle=u.register_slate_post_tick_callback(tick)
    u.log('MPR_PERFORMANCE_STARTED '+str(OUT/'performance.json'))
