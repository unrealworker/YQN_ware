"""Render the same paused blue route and its background over multiple real frames."""
from pathlib import Path
exec(Path(__file__).with_name('verify_order_replay_runtime.py').read_text(encoding='utf8').split('steps=run()')[0])

material_file=ROOT/'Content/GHSOrderReplay/Materials/M_ReplayTrail.uasset'
material_hash=hashlib.sha256(material_file.read_bytes()).hexdigest()
OUT=ROOT/'Saved/OrderReplay/TrailStability'/material_hash[:12]
OUT.mkdir(parents=True,exist_ok=True)
report=dict(success=False,checks=[],captures=[],states={},trail_sha256=material_hash)

def frame(name):
    path=OUT/(name+'.png'); old=path.stat().st_mtime_ns if path.exists() else 0
    unreal.SystemLibrary.execute_console_command(world,'Shot filename="'+path.as_posix()+'" -nosuffix',pc)
    yield from wait(name,lambda:path.exists() and path.stat().st_mtime_ns!=old)
    report['captures'].append(str(path))

def run():
    yield from wait('discover',discover,100)
    yield from wait('camera',lambda:not pawn.is_pose_transition_active())
    camera_before=pose()
    command('navigate',page='trace')
    hud.navigate('trace')
    command('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-23T12:00:00.000Z',endUtc='2026-10-23T13:00:00.000Z')
    yield from wait('prepared',lambda:state()['active'] and not state()['preparing'] and not pawn.is_pose_transition_active())
    command('replayPause')
    track=json.loads((ROOT/'Content/GHSTwinUI/data/order-replay.json').read_bytes())['tracks'][0]
    a,b=max(((a,b) for a,b in zip(track['keys'],track['keys'][1:]) if a[7]=='运送托盘' and b[7]==a[7]),
            key=lambda row:math.dist(row[0][1][:2],row[1][1][:2]))
    assert math.dist(a[1][:2],b[1][:2])>800
    t=a[0]+.08*(b[0]-a[0])
    command('replaySeek',time=t);command('replaySelect',id=track['id']);command('replayTrails',mode='selected')
    actor=next(x for x in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
               if x.get_class().get_name()=='GHSOrderReplayActor')
    trail=next(x for x in actor.get_components_by_class(unreal.InstancedStaticMeshComponent) if x.get_name()=='Trail0')
    assert trail.get_editor_property('visible')
    create=next(x for x in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.CameraActor)
                if x.get_actor_label()=='CAM_GHS_Overview')
    previous_target=pc.get_view_target()
    rot=unreal.Rotator(pitch=-82,yaw=math.degrees(math.atan2(b[1][1]-a[1][1],b[1][0]-a[1][0]))-90.)
    center=unreal.Vector(*(x+.63*(y-x) for x,y in zip(a[1],b[1])))
    create.camera_component.set_editor_property('field_of_view',60.)
    hud.set_visibility(unreal.SlateVisibility.COLLAPSED)
    pc.set_view_target_with_blend(create,0.)
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    for name,distance in [('near',1900),('far',6500)]:
        create.set_actor_location_and_rotation(center-unreal.MathLibrary.get_forward_vector(rot)*distance,rot,False,True)
        command('replayTrails',mode='off')
        yield from pause(1.5)
        yield from frame(name+'-off')
        command('replayTrails',mode='selected')
        yield from pause(1.5)
        for i in range(10):
            yield from frame(name+'-'+str(i))
        assert abs(state()['time']-t)<.001 and trail.get_editor_property('visible')
    if '-ghstrailpan' in CLI.lower():
        base=center-unreal.MathLibrary.get_forward_vector(rot)*1900.
        step=unreal.MathLibrary.get_right_vector(rot)*4.5
        for enabled in (False,True):
            create.set_actor_location_and_rotation(base,rot,False,True)
            command('replayTrails',mode='selected' if enabled else 'off')
            yield from pause(1.5)
            anchors=[]
            for i in range(10):
                create.set_actor_location_and_rotation(base+step*i,rot,False,True)
                yield
                yield from frame(('pan-' if enabled else 'pan-off-')+str(i))
                anchors.append(pc.project_world_location_to_screen(center,False).x)
            if enabled:report['states']['pan_anchor_pixels']=anchors
    # The HUD's NativeTick advances the production session clock.
    hud.set_visibility(unreal.SlateVisibility.VISIBLE)
    material=trail.get_material(0)
    clock_comparison={}
    for rate in (1,64):
        command('replaySeek',time=t);command('replayRate',rate=rate)
        start_time=state()['time'];start_flow=material.get_scalar_parameter_value('ReplayTime')
        command('replayPlay')
        yield from wait('running '+str(rate),lambda:state()['time']>start_time+.25*rate)
        command('replayPause')
        delta=state()['time']-start_time
        flow=material.get_scalar_parameter_value('ReplayTime')-start_flow
        clock_comparison[str(rate)]=dict(replay_seconds=delta,flow_seconds=flow,
                                          flow_seconds_per_display_second=flow/(delta/rate))
    report['states']['transport']=clock_comparison
    pc.set_view_target_with_blend(previous_target,0.)
    command('replayEndRequest');command('replayExitConfirm')
    yield from wait('restored',lambda:not state()['active'])
    assert pose()==camera_before
    record('two_frozen_views_with_matching_route_off_background',replay_time=t,device=track['id'])

steps=run()
def tick(delta):
    try:
        assert time.monotonic()-started<240
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
write();handle=unreal.register_slate_post_tick_callback(tick)
