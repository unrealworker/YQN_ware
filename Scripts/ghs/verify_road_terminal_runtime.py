"""Render saved road ends and sample traffic in an isolated offscreen game."""
import hashlib,json,re,time,traceback
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/RoadTerminalFade/Runtime'
OUT.mkdir(parents=True,exist_ok=True)
CLI=unreal.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+f+r'(?=\s|$)',CLI,re.I) for f in ('game','RenderOffscreen','TwinDiagnostics'))
MAP=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
before_hash=hashlib.sha256(MAP.read_bytes()).hexdigest()
manifest=json.loads((ROOT/'SourceAssets/GHS/ContextTransition/context_transition.json').read_text(encoding='utf-8'))
world=pc=pawn=traffic=hud=handle=None
stage='discover';started=time.monotonic()
report={'success':False,'captures':[],'checks':[]}

def write(): (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def wait(name,predicate,timeout=45):
    global stage
    stage=name;deadline=time.monotonic()+timeout
    while not predicate():
        assert time.monotonic()<deadline,'Timeout: '+name
        yield
def pause(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end: yield
def discover():
    global world,pc,pawn,traffic,hud
    for w in unreal.ObjectIterator(unreal.World):
        if not w.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):continue
        c=unreal.GameplayStatics.get_player_controller(w,0)
        h=getattr(c,'twin_hud_widget',None) if c else None
        if h and h.browser_ready:
            world,pc,hud,pawn,traffic=w,c,h,c.get_controlled_pawn(),c.campus_traffic
            return bool(traffic)
    return False
def stats(): return json.loads(traffic.get_traffic_report_json())
def capture(name):
    path=OUT/(name+'.png');old=path.stat().st_mtime_ns if path.exists() else 0
    unreal.SystemLibrary.execute_console_command(world,'Shot filename="'+path.as_posix()+'" -nosuffix',pc)
    yield from wait(name,lambda:path.exists() and path.stat().st_mtime_ns!=old)
    report['captures'].append(str(path));write()
def record(name,**data):report['checks'].append(dict(name=name,passed=True,**data));write()
def run():
    yield from wait('discover',discover,90)
    yield from wait('camera',lambda:not pawn.is_pose_transition_active())
    all_actors=unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
    targets={a.get_actor_label():a for a in all_actors}
    for role in ('ContextRoads','Curbs','Markings','Landscape'):
        a=targets['GHSContextTransition_'+role]
        c=a.get_component_by_class(unreal.StaticMeshComponent)
        assert c.is_visible() and not a.get_editor_property('hidden') and not c.get_editor_property('hidden_in_game')
        assert '/RoadTerminalFade/Meshes/SM_GHSRoadTerminal_' in c.static_mesh.get_path_name()
        if role!='Landscape':assert '/RoadTerminalFade/' in c.get_material(0).get_path_name()
    record('saved_extension_actors_visible_with_corrected_junction_meshes')
    initial=stats();assert initial['ready'] and initial['fixed_instances']==32
    camera=next(a for a in all_actors if a.get_actor_label()=='CAM_GHS_Overview')
    camera.camera_component.set_editor_property('field_of_view',60.)
    pc.set_view_target_with_blend(camera,0.)
    hud.set_visibility(unreal.SlateVisibility.COLLAPSED)
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    # Exterior terminals only. Sycamore's shared internal junction is a
    # separate regression view, never an allowed context extension.
    for end in manifest['roads']:
        if end['road_id'].startswith('sycamore'):continue
        old,new=end['old_end_uv_m'],end['new_end_uv_m']
        u,v=(old[0]+new[0])*.5,(old[1]+new[1])*.5
        target=unreal.Vector((u-239.33385)*100,(v-60.24019)*100,end['height_m']*100)
        rot=unreal.Rotator(pitch=-58,yaw=-90)
        eye=target-unreal.MathLibrary.get_forward_vector(rot)*14000
        camera.set_actor_location_and_rotation(eye,rot,False,True)
        yield from pause(2.5)
        yield from capture(end['road_id']+'-'+end['side'])
    target=unreal.Vector((92.9018770782-239.33385)*100,(473.357670515-60.24019)*100,0)
    rot=unreal.Rotator(pitch=-65,yaw=-90)
    camera.set_actor_location_and_rotation(target-unreal.MathLibrary.get_forward_vector(rot)*14500,rot,False,True)
    yield from pause(2.5)
    yield from capture('sycamore-junction')
    before=stats();count=len(unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor))
    traffic.set_editor_property('custom_time_dilation',8.)
    yield from wait('vehicle_retirement_and_reuse',lambda:stats()['completed']>before['completed'] and stats()['spawned']>before['spawned'],45)
    traffic.set_editor_property('custom_time_dilation',1.)
    after=stats()
    assert after['fixed_instances']==32 and after['component_count']==4
    assert len(unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor))==count
    assert hashlib.sha256(MAP.read_bytes()).hexdigest()==before_hash
    record('traffic_retirement_without_growth',before=before,after=after,map_unchanged=True)

def finish(error=None):
    report.update(success=error is None,elapsed_seconds=time.monotonic()-started,map_sha256=before_hash,stage=stage)
    if error: report['error']=error
    write();unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('GHS_ROAD_TERMINAL_RUNTIME '+json.dumps(report,ensure_ascii=False))
    if world: unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)
steps=run()
def tick(delta):
    try:
        assert time.monotonic()-started<180,'Runtime check timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
write();handle=unreal.register_slate_post_tick_callback(tick)
