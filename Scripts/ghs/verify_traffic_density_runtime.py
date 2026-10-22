"""Traffic-only acceptance in an owned offscreen game; no scene asset saves."""
import hashlib,json,re,time,traceback
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/TrafficDensity';OUT.mkdir(exist_ok=True)
assert all(re.search(r'(?:^|\s)-'+f+r'(?=\s|$)',unreal.SystemLibrary.get_command_line(),re.I) for f in ('game','RenderOffscreen','TwinDiagnostics'))
MAP=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
before_hash=hashlib.sha256(MAP.read_bytes()).hexdigest()
world=pc=hud=pawn=traffic=handle=None
started=time.monotonic();stage='discover';measure=False;frames=[]
result=dict(success=False,checks=[],captures=[],assets_saved=False)
def write(): (OUT/'runtime.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
def record(name,**data): result['checks'].append(dict(name=name,passed=True,**data));write()
def wait(name,predicate,timeout=45):
    global stage
    stage=name;deadline=time.monotonic()+timeout
    while not predicate():
        assert time.monotonic()<deadline,'Timeout: '+name
        yield
def pause(seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:yield
def discover():
    global world,pc,hud,pawn,traffic
    for w in unreal.ObjectIterator(unreal.World):
        if not w.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):continue
        c=unreal.GameplayStatics.get_player_controller(w,0)
        h=getattr(c,'twin_hud_widget',None) if c else None
        if h and h.browser_ready:
            world,pc,hud,pawn,traffic=w,c,h,c.get_controlled_pawn(),c.campus_traffic
            return bool(traffic)
    return False
def stats():return json.loads(traffic.get_traffic_report_json())
def capture(name):
    path=OUT/(name+'.png');old=path.stat().st_mtime_ns if path.exists() else 0
    unreal.SystemLibrary.execute_console_command(world,'Shot showui filename="'+path.as_posix()+'" -nosuffix',pc)
    yield from wait(name,lambda:path.exists() and path.stat().st_mtime_ns!=old)
    result['captures'].append(path.name);write()
def positions(components):
    return [[str(c.get_instance_transform(i,True).translation) for i in range(c.get_instance_count())] for c in components]
def run():
    global measure
    yield from wait('discover',discover,90)
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    yield from wait('camera',lambda:not pawn.is_pose_transition_active())
    yield from pause(2)
    initial=stats();components=traffic.get_components_by_class(unreal.InstancedStaticMeshComponent)
    assert initial['ready'] and initial['capacity']==32 and initial['fixed_instances']==32
    assert initial['route_count']==6 and initial['component_count']==4 and not initial['collision']
    assert len(components)==4 and all(c.get_instance_count()==8 for c in components)
    assert len(initial['active_by_route'])==6 and all(0<r['active']<=6 for r in initial['active_by_route'])
    actor_count=len(unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor))
    scene=json.loads(hud.get_snapshot());identities=[e['id'] for e in scene['equipment']+scene['facilities']]
    assert len(scene['equipment'])==106 and len(scene['facilities'])==56
    assert pc.warehouse_roof.is_roof_closed()
    record('fixed_32_instances_six_directions',report=initial)
    p0=positions(components);samples=[];measure=True
    for i in range(12):
        yield from pause(1)
        report=stats();samples.append(report['active'])
        assert report['fixed_instances']==32 and report['component_count']==4 and report['peak_active']<=32
        assert all(0<=r['active']<=6 for r in report['active_by_route'])
    measure=False
    assert positions(components)!=p0
    assert sum(samples)/len(samples)>20,'Increased population must be visible in the actual game'
    record('motion_and_denser_population',active_samples=samples,average=sum(samples)/len(samples))
    yield from capture('01-traffic-overview')
    # Accelerate only this decorative actor to exercise endpoint retirement.
    # These frames are excluded from the ordinary-speed timing sample above.
    before=stats();traffic.set_editor_property('custom_time_dilation',8.)
    yield from wait('retire_and_reuse',lambda:stats()['completed']>before['completed'] and stats()['spawned']>before['spawned'],40)
    traffic.set_editor_property('custom_time_dilation',1.)
    after=stats()
    assert after['fixed_instances']==32 and after['component_count']==4 and after['peak_active']<=32
    assert len(unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor))==actor_count
    assert all(c.get_instance_count()==8 for c in components)
    record('endpoint_recycling_without_actor_or_instance_growth',before=before,after=after,actor_count=actor_count)
    center=pawn.get_editor_property('overview_center');rotation=unreal.Rotator(pitch=-60,yaw=pawn.get_editor_property('overview_yaw'),roll=0)
    view=hud.get_viewport_pixel_size();view=unreal.Vector2D(view.x/hud.get_hud_scale(),view.y/hud.get_hud_scale());pane=hud.get_panel_position()
    pawn.transition_to_pose(center,95000,rotation,view,unreal.Vector2D(pane.x*.5,view.y*.52),True,0.)
    yield from pause(1)
    yield from capture('02-traffic-corridors')
    current=json.loads(hud.get_snapshot())
    assert [e['id'] for e in current['equipment']+current['facilities']]==identities
    assert hashlib.sha256(MAP.read_bytes()).hexdigest()==before_hash
    record('business_identity_and_map_preserved',equipment=106,facilities=56,map_sha256=before_hash)
def finish(error=None):
    result.update(success=error is None,elapsed_seconds=time.monotonic()-started)
    if error:result.update(stage=stage,error=error)
    ordered=sorted(frames)
    if ordered:result['ordinary_speed_frame_sample_ms']=dict(count=len(ordered),median=ordered[len(ordered)//2]*1000,p95=ordered[int(len(ordered)*.95)]*1000,note='Local offscreen Slate sample, not GPU-only cost or independent-user Pixel Streaming benchmark')
    if traffic:traffic.set_editor_property('custom_time_dilation',1.)
    write();unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('GHS_TRAFFIC_DENSITY '+json.dumps(result,ensure_ascii=False))
    if world:unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)
steps=run()
def tick(delta):
    if measure and 0<delta<1:frames.append(delta)
    try:
        assert time.monotonic()-started<180,'Acceptance timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
handle=unreal.register_slate_post_tick_callback(tick)
