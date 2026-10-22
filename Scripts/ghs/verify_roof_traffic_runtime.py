"""Integration acceptance in an owned offscreen game; never save assets."""
import hashlib
import json
import math
from pathlib import Path
import re
import time
import traceback
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/RoofTraffic'
assert all(re.search(r'(?:^|\s)-'+f+r'(?=\s|$)',unreal.SystemLibrary.get_command_line(),re.I) for f in ('game','RenderOffscreen','TwinDiagnostics'))
OUT.mkdir(parents=True,exist_ok=True)
world=pc=hud=pawn=roof=traffic=None
started=time.monotonic();handle=None;stage='discover';finished=False
result=dict(success=False,checks=[],captures=[],performance_benchmark=False)
frames=[]
map_path=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
map_hash=hashlib.sha256(map_path.read_bytes()).hexdigest()

def write():
    (OUT/'runtime.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
def record(name,**values):
    result['checks'].append(dict(name=name,**values));write()
def state():return json.loads(hud.get_poi_report())
def command(action,**values):hud.command(json.dumps(dict(action=action,**values)))
def ids():return [x['id'] for x in state()['labels']]
def xyz(v):return [v.x,v.y,v.z]
def wait(name,condition,seconds=30,stable=1):
    global stage
    stage=name;until=time.monotonic()+seconds;n=0
    while True:
        assert time.monotonic()<until,'Timed out: '+name
        n=n+1 if condition() else 0
        if n>=stable:return
        yield
def pause(seconds):
    until=time.monotonic()+seconds
    while time.monotonic()<until:yield
def discover():
    global world,pc,hud,pawn,roof,traffic
    for w in unreal.ObjectIterator(unreal.World):
        if not w.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):continue
        c=unreal.GameplayStatics.get_player_controller(w,0)
        h=getattr(c,'twin_hud_widget',None) if c else None
        if not h or not h.browser_ready:continue
        world,pc,hud=w,c,h;pawn=pc.get_controlled_pawn();roof=pc.warehouse_roof;traffic=pc.campus_traffic
        return bool(roof and traffic and pawn)
    return False
def capture(name):
    path=OUT/(name+'.png');old=path.stat().st_mtime_ns if path.exists() else 0
    unreal.SystemLibrary.execute_console_command(world,'Shot showui filename="'+path.as_posix()+'" -nosuffix',pc)
    yield from wait('capture_'+name,lambda:path.exists() and path.stat().st_mtime_ns!=old)
    result['captures'].append(dict(name=name,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()));write()
def roof_source():
    actor=next(a for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor) if a.actor_has_tag('GHS_WarehouseRoof'))
    component=actor.get_component_by_class(unreal.StaticMeshComponent)
    return actor,component,[component.get_material(i).get_path_name() for i in range(component.get_num_materials())]
def restore():
    command('overview')
    assert roof.is_roof_closed() and not roof.is_component_tick_enabled()
    assert not hud.selected_id and not state()['pendingNavigation']
    assert all(i=='WAREHOUSE:GHS' for i in ids()),'Reset must suppress cached interior labels immediately'
    yield from wait('restored_camera',lambda:not pawn.is_pose_transition_active(),stable=4)
    yield from wait('restored_poi',lambda:ids()==['WAREHOUSE:GHS'])

def run():
    yield from wait('discover',discover,60)
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    yield from wait('initial_camera',lambda:not pawn.is_pose_transition_active(),stable=10)
    yield from pause(2)
    assert roof.is_roof_closed() and not roof.is_interior_available()
    assert ids()==['WAREHOUSE:GHS'],ids()
    actor,mesh,materials=roof_source()
    assert 'M_GHSFacade_Glass' in materials[3],materials
    data=json.loads(hud.get_snapshot());assert len(data['equipment'])==106 and len(data['facilities'])==56
    record('initial_closed_single_poi',materials=materials,equipment=106,facilities=56)
    yield from capture('01_Closed_Overview')
    poi=state()['labels'][0];scale=hud.get_hud_scale()
    assert hud.handle_scene_click(unreal.Vector2D((poi['x']+134)*scale,(poi['y']+32)*scale))
    assert roof.is_opening() and not hud.selected_id
    start=unreal.GameplayStatics.get_time_seconds(world)
    while not roof.is_interior_available():
        assert not hud.selected_id
        assert not ids(),ids()
        assert hud.handle_scene_click(unreal.Vector2D(600*scale,450*scale))
        yield
    elapsed=unreal.GameplayStatics.get_time_seconds(world)-start
    assert .5-1e-4<=elapsed<.75,elapsed
    assert not roof.is_component_tick_enabled()
    yield from wait('internal_labels',lambda:len(ids())>0 and 'WAREHOUSE:GHS' not in ids())
    record('poi_click_half_second_and_interaction_lock',game_seconds=elapsed)
    yield from capture('03_Open_Interior')
    yield from restore()
    assert roof_source()[2]==materials
    # Direct roof click uses its projected geometric anchor, not a label hit box.
    point=unreal.GameplayStatics.project_world_to_screen(pc,roof.get_poi_world_location(),False)
    assert point is not None
    assert hud.handle_scene_click(point) and roof.is_opening()
    yield from wait('direct_roof_open',roof.is_interior_available)
    record('direct_roof_click')
    yield from restore()
    before=xyz(pawn.get_actor_location())
    assert hud.select_object('AGV-07',True)
    assert not hud.selected_id and state()['pendingNavigation']=='select'
    while not roof.is_interior_available():
        assert not hud.selected_id and not pawn.is_pose_transition_active()
        assert math.dist(before,xyz(pawn.get_actor_location()))<1
        yield
    yield from wait('selected_after_open',lambda:hud.selected_id=='AGV-07')
    yield from wait('focused_after_open',lambda:not pawn.is_pose_transition_active(),stable=8)
    record('page_select_opens_before_camera_and_selection')
    yield from capture('04_AGV_Located')
    yield from restore()
    assert hud.select_object('AGV-07',True)
    assert hud.select_object('FORK-07',True)
    yield from wait('latest_selection',lambda:hud.selected_id=='FORK-07')
    record('latest_navigation_wins')
    yield from restore()
    assert hud.select_object('AGV-07',True)
    command('overview')
    yield from pause(.8)
    assert roof.is_roof_closed() and not hud.selected_id and not state()['pendingNavigation']
    record('reset_cancels_pending_navigation')
    yield from restore()
    command('focus',id='AGV-07')
    assert roof.is_opening() and not pawn.is_pose_transition_active()
    yield from wait('focus_command_opened',roof.is_interior_available)
    yield from wait('focus_command_flight',lambda:pawn.is_pose_transition_active())
    yield from wait('focus_command_finished',lambda:not pawn.is_pose_transition_active())
    record('page_focus_command_opens_before_flight')
    yield from restore()
    command('preset',value='racks')
    assert roof.is_opening()
    yield from wait('region_command_opened',roof.is_interior_available)
    yield from wait('region_command_flight',lambda:pawn.is_pose_transition_active())
    yield from wait('region_command_finished',lambda:not pawn.is_pose_transition_active())
    record('region_preset_opens_before_flight')
    yield from restore()
    # Slow only this visual capture, after normal 0.5-second timing was verified.
    unreal.GameplayStatics.set_global_time_dilation(world,.12)
    assert hud.open_warehouse()
    yield from wait('mid_dissolve',lambda:roof.get_open_progress()>=.44)
    yield from capture('02_Dissolve_Midpoint')
    unreal.GameplayStatics.set_global_time_dilation(world,1.)
    yield from wait('finish_visual_dissolve',roof.is_interior_available)
    yield from restore()
    t0=json.loads(traffic.get_traffic_report_json());assert t0['ready'] and t0['capacity']==16 and t0['fixed_instances']==16 and not t0['collision']
    components=traffic.get_components_by_class(unreal.InstancedStaticMeshComponent)
    assert len(components)==4
    transforms0=[[xyz(c.get_instance_transform(i,True).translation) for i in range(c.get_instance_count())] for c in components]
    yield from pause(3)
    transforms1=[[xyz(c.get_instance_transform(i,True).translation) for i in range(c.get_instance_count())] for c in components]
    assert transforms0!=transforms1,'Vehicles did not move'
    def recycled():
        now=json.loads(traffic.get_traffic_report_json())
        return now['completed']>t0['completed'] and now['spawned']>t0['spawned']
    yield from wait('traffic_end_recycling',recycled,seconds=70)
    t1=json.loads(traffic.get_traffic_report_json())
    assert t1['completed']>t0['completed'] and t1['spawned']>t0['spawned']
    assert t1['fixed_instances']==16 and t1['peak_active']<=16
    record('traffic_motion_and_bounded_recycling',before=t0,after=t1)
    unreal.SystemLibrary.execute_console_command(world,'r.SetRes 2560x1600w',pc)
    yield from wait('2560_viewport',lambda:tuple(pc.get_viewport_size())==(2560,1600))
    yield from pause(1)
    assert ids()==['WAREHOUSE:GHS']
    yield from capture('05_Closed_2560x1600')
    # Inspect context tails and green islands beyond the normal campus framing.
    center=pawn.get_editor_property('overview_center')
    rotation=unreal.Rotator();rotation.pitch=-60;rotation.yaw=pawn.get_editor_property('overview_yaw');rotation.roll=0
    view=hud.get_viewport_pixel_size();view=unreal.Vector2D(view.x/hud.get_hud_scale(),view.y/hud.get_hud_scale())
    pane=hud.get_panel_position()
    pawn.transition_to_pose(center,95000,rotation,view,unreal.Vector2D(pane.x*.5,view.y*.52),True,0.)
    yield from pause(.3)
    yield from capture('06_Context_Edges')
    assert roof_source()[2]==materials
    data2=json.loads(hud.get_snapshot());assert [r['id'] for r in data2['equipment']+data2['facilities']]==[r['id'] for r in data['equipment']+data['facilities']]
    assert hashlib.sha256(map_path.read_bytes()).hexdigest()==map_hash
    record('materials_business_ids_and_saved_map_preserved')

def finish(error=None):
    global finished
    if finished:return
    finished=True;result.update(success=error is None,elapsed_seconds=time.monotonic()-started)
    if error:result.update(error=error,stage=stage)
    valid=sorted(v for v in frames if 0<v<1)
    if valid:result['frame_sample_ms']=dict(median=valid[len(valid)//2]*1000,p95=valid[int(len(valid)*.95)]*1000,count=len(valid),note='Shared-machine editor/offscreen sample; not independent-session streaming benchmark')
    write()
    if handle is not None:unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('GHS_ROOF_TRAFFIC_RUNTIME '+json.dumps(result,ensure_ascii=False))
    unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)
steps=run()
def tick(delta):
    frames.append(delta)
    try:
        assert time.monotonic()-started<240,'Acceptance timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
handle=unreal.register_slate_post_tick_callback(tick)
