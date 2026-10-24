"""Rendered acceptance for active remaining routes, replay POIs and camera controls."""
from pathlib import Path
exec(Path('D:/UEPro/Test/Scripts/ghs/verify_order_replay_runtime.py').read_text(encoding='utf8').split('steps=run()')[0])
OUT=ROOT/'Saved/OrderReplay/RemainingRoutes';OUT.mkdir(parents=True,exist_ok=True)
report=dict(success=False,checks=[],captures=[],states={})
EXPECTED=['#67DDEB']*5

def replay_actor():
    return next(a for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
                if a.get_class().get_name()=='GHSOrderReplayActor')

def visible(component):return bool(component.get_editor_property('visible'))
def distance(a,b):return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))
def rotation():return numeric(pawn.get_actor_rotation(),('pitch','yaw','roll'))
def vector(v):return numeric(v,'xyz')
def forks():return [d for d in state()['devices'] if d['id'].startswith('REPLAY-FORK')]
def poi_report(name):
    value=json.loads(hud.get_poi_report())
    (OUT/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
    return value

def scene_capture(name):
    path=OUT/(name+'.png');stamp=path.stat().st_mtime_ns if path.exists() else 0
    unreal.SystemLibrary.execute_console_command(world,'Shot filename="'+path.as_posix()+'" -nosuffix',pc)
    yield from wait(name,lambda:path.exists() and path.stat().st_mtime_ns!=stamp)
    report['captures'].append(str(path));write()

def run():
    yield from wait('discover',discover,100)
    yield from wait('initial camera',lambda:not pawn.is_pose_transition_active())
    data_file=ROOT/'Content/GHSTwinUI/data/order-replay.json'
    data_sha=hashlib.sha256(data_file.read_bytes()).hexdigest()
    baseline_actors=unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
    assert not any(a.get_class().get_name()=='GHSOrderReplayActor' for a in baseline_actors)
    camera_before=pose()
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    command('navigate',page='trace');hud.navigate('trace')
    command('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-23T12:00:00.000Z',endUtc='2026-10-23T13:00:00.000Z')
    yield from wait('prepared',lambda:not state()['preparing'] and not pawn.is_pose_transition_active())
    command('replayPause');command('replaySeek',time=0);command('replayOverview')
    yield from wait('floor overview',lambda:not pawn.is_pose_transition_active());yield from pause(.8)
    assert pawn.spring_arm_component.target_arm_length<50000, pawn.spring_arm_component.target_arm_length
    record('floor_overview_closer',pivot=vector(pawn.get_actor_location()),distance_cm=pawn.spring_arm_component.target_arm_length)
    actor=replay_actor()
    trails=sorted(actor.get_components_by_class(unreal.InstancedStaticMeshComponent),key=lambda c:c.get_name())
    ripples=sorted(actor.get_components_by_class(unreal.DecalComponent),key=lambda c:c.get_name())
    assert len(trails)==5,(len(trails),[c.get_name() for c in trails])
    assert len(ripples)==5,(len(ripples),[c.get_name() for c in ripples])
    assert not any(visible(t) for t in trails+ripples),'Idle forks must not display routes/ripples'
    assert not any(d['trailVisible'] for d in forks())
    record('idle_forklifts_have_no_routes')
    command('replaySeek',time=230);yield from pause(.8)
    devices=state()['devices'];fork_rows=forks()
    trucks=[d for d in devices if d['id'].startswith('REPLAY-TRUCK')]
    assert [d.get('trailColor') for d in fork_rows]==EXPECTED
    assert all(not d.get('trailColor') for d in trucks)
    total_instances=sum(t.get_instance_count() for t in trails)
    expected_moving=[True,False,True,True,False]
    assert [visible(t) for t in trails]==expected_moving
    assert [visible(t) for t in ripples]==expected_moving
    assert [d['trailVisible'] for d in fork_rows]==expected_moving
    assert [d['trailHeightCm'] for d in fork_rows]==[3,3.8,4.6,5.4,6.2]
    for i,(t,d) in enumerate(zip(trails,fork_rows)):
        assert abs(d['trailWidthCm']-18)<.001
        tr=t.get_instance_transform(0,False)
        assert abs(tr.translation.z-(3+i*.8))<.001
        assert abs(tr.scale3d.y-.18)<.001
        assert abs(t.get_material(0).get_scalar_parameter_value('ActiveLegId')-d['trailLegId'])<.01
    labels=poi_report('poi-moving')['labels'];ids={d['id'] for d in labels}
    assert 'REPLAY-FORK-02' in ids and 'REPLAY-FORK-05' in ids,ids
    assert all(x.startswith('REPLAY-') for x in ids)
    assert any(x.startswith('REPLAY-TRUCK') for x in ids)
    for n,a in enumerate(labels):
        assert a['y']+a['height']<=888 and a['x']+a['width']<=1440,a
        for b in labels[n+1:]:
            assert not(a['x']<b['x']+b['width'] and a['x']+a['width']>b['x'] and a['y']<b['y']+b['height'] and a['y']+a['height']>b['y']),(a,b)
    record('thin_cyan_moving_routes_and_height_separation',colours=EXPECTED,trail_components=len(trails),ripple_components=len(ripples),instances=total_instances)
    record('replay_pois_include_idle_and_trucks',visible_ids=sorted(ids))
    yield from capture('01-floor-overview');yield from scene_capture('scene-floor-overview')
    initial=forks()[0];command('replaySeek',time=240);later=forks()[0]
    assert initial['trailLegId']==later['trailLegId']
    assert later['trailProgressMeters']>initial['trailProgressMeters']+1
    assert later['trailRemainingMeters']<initial['trailRemainingMeters']-1
    assert abs(trails[0].get_material(0).get_scalar_parameter_value('RemainingFromMeters')-later['trailProgressMeters'])<.001
    yield from pause(.5);yield from capture('01b-progress-240')
    command('replaySeek',time=230);restored=forks()[0]
    assert abs(restored['trailProgressMeters']-initial['trailProgressMeters'])<.0001
    assert abs(restored['trailRemainingMeters']-initial['trailRemainingMeters'])<.0001
    record('traversed_route_clips_and_reverse_seek_restores',before=initial,after=later)
    idle_label=next(x for x in labels if x['id']=='REPLAY-FORK-02')
    hud.handle_scene_click(unreal.Vector2D(idle_label['x']+idle_label['width']/2,idle_label['y']+idle_label['height']/2))
    assert state()['selectedId']=='REPLAY-FORK-02' and not state()['exitPending']
    record('poi_click_selects_without_exiting')
    command('replayTrails',mode='selected');command('replaySelect',id='REPLAY-TRUCK-A')
    assert not any(visible(t) for t in trails+list(ripples))
    command('replaySelect',id='REPLAY-FORK-03');assert sum(visible(t) for t in trails)==1
    assert sum(visible(t) for t in ripples)==1
    command('replayTrails',mode='off');assert not any(visible(t) for t in trails+list(ripples))
    yield from pause(.2);assert len(json.loads(hud.get_poi_report())['labels'])>0
    command('replayTrails',mode='all');assert [visible(t) for t in trails]==expected_moving
    record('selected_truck_has_no_route')
    for i in (1,3):
        device='REPLAY-FORK-%02d'%i
        command('replayFollow',id=device)
        yield from wait('follow '+device,lambda:not pawn.is_pose_transition_active());yield from pause(.7)
        yield from capture('02-cyan-fork-%02d'%i)
        if i==3: yield from scene_capture('scene-followed')
    followed=poi_report('poi-followed')['labels']
    assert any(x['id']=='REPLAY-FORK-03' and x['following'] for x in followed)
    command('replayFollow',id='REPLAY-FORK-01')
    yield from wait('orbit start',lambda:not pawn.is_pose_transition_active());yield from pause(.8)
    before_rotation=rotation();pawn.orbit_pixels(unreal.Vector2D(135,65));yield from pause(1)
    rotated=rotation()
    assert state()['followId']=='REPLAY-FORK-01',state()
    assert abs(math.remainder(rotated[1]-before_rotation[1],360))>15,(before_rotation,rotated)
    before_zoom=float(pawn.spring_arm_component.target_arm_length);pawn.zoom_steps(1);yield from pause(1)
    after_zoom=float(pawn.spring_arm_component.target_arm_length)
    assert after_zoom<before_zoom-20,(before_zoom,after_zoom)
    old_position=vector(pawn.get_actor_location());command('replayRate',rate=8);command('replayPlay');yield from pause(2)
    command('replayPause');yield from pause(1)
    assert state()['followId']=='REPLAY-FORK-01'
    assert distance(vector(pawn.get_actor_location()),old_position)>100
    assert abs(math.remainder(rotation()[1]-rotated[1],360))<.2,(rotated,rotation())
    assert abs(float(pawn.spring_arm_component.target_arm_length)-after_zoom)<1
    yield from wait('follow settles after pause',lambda:distance(vector(pawn.get_actor_location()),vector(pawn.get_focus_target()))<.05)
    focus_before=vector(pawn.get_focus_target());pan_before=pose()
    pawn.pan_pixels(unreal.Vector2D(240,120),1920)
    assert pc.begin_map_drag() is False
    yield from pause(.5)
    assert vector(pawn.get_focus_target())==focus_before
    assert distance(vector(pawn.get_actor_location()),pan_before[0])<1,(pan_before,pose())
    assert state()['followId']=='REPLAY-FORK-01'
    record('follow_keeps_orbit_zoom_and_ignores_pan',before_rotation=before_rotation,after_rotation=rotated,zoom_cm=after_zoom)
    yield from capture('03-follow-orbit')
    command('replaySeek',time=230);yield from pause(.3)
    material_times=[]
    for component in trails:
        material=component.get_material(0);material_times.append(material.get_scalar_parameter_value('ReplayTime'))
    for component in ripples:
        material=component.get_decal_material();material_times.append(material.get_scalar_parameter_value('ReplayTime'))
    assert all(abs(t-230)<.001 for t in material_times),material_times
    yield from pause(.5)
    assert state()['time']==230
    assert all(abs(t.get_material(0).get_scalar_parameter_value('ReplayTime')-230)<.001 for t in trails)
    assert all(abs(t.get_decal_material().get_scalar_parameter_value('ReplayTime')-230)<.001 for t in ripples)
    record('flow_and_ripples_use_paused_replay_clock')
    command('replayFollow',id='');command('replaySeek',time=90);command('replayFollow',id='REPLAY-FORK-03')
    yield from wait('fault camera',lambda:not pawn.is_pose_transition_active());yield from pause(.5)
    fault=next(d for d in forks() if d['id']=='REPLAY-FORK-03')
    assert '故障' in fault['status'] and not fault['trailVisible'],fault
    fault_labels=poi_report('poi-fault')['labels']
    assert any(x['id']==fault['id'] and x['status']=='故障停机' for x in fault_labels),fault_labels
    yield from capture('04-fault-no-route');yield from scene_capture('scene-fault');record('fault_stops_route_but_preserves_poi')
    command('replayFollow',id='');command('replaySeek',time=state()['duration'])
    command('replayOverview');yield from wait('completed overview',lambda:not pawn.is_pose_transition_active());yield from pause(.6)
    assert state()['completed'] and not any(d['trailVisible'] for d in forks())
    poi_report('poi-completed');yield from capture('05-completed');yield from scene_capture('scene-completed')
    command('replaySeek',time=230)
    command('replayOverview');yield from wait('benchmark overview',lambda:not pawn.is_pose_transition_active())
    command('replayRate',rate=1);command('replayPlay');yield from pause(2)
    frames=[];last=time.monotonic()
    for _ in range(300):
        yield
        now=time.monotonic();frames.append((now-last)*1000);last=now
    assert sum(t.get_instance_count() for t in trails)==total_instances
    report['performance']=dict(frames=300,mean_ms=statistics.mean(frames),median_ms=statistics.median(frames),p95_ms=sorted(frames)[285],max_ms=max(frames))
    command('replayEndRequest');command('replayExitConfirm');yield from pause(.3)
    assert not state()['active'] and pose()==camera_before
    assert not any(a.get_class().get_name()=='GHSOrderReplayActor' for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor))
    assert json.loads(session.get_restoration_report())['verified']
    assert not any(x['id'].startswith('REPLAY-') for x in json.loads(hud.get_poi_report())['labels'])
    assert hashlib.sha256(MAP.read_bytes()).hexdigest()==map_hash
    assert hashlib.sha256(data_file.read_bytes()).hexdigest()==data_sha
    record('normal_scene_no_replay_fx_and_sources_unchanged',map_sha256=map_hash,data_sha256=data_sha)

steps=run()
def tick(delta):
    try:
        assert time.monotonic()-started<360,'Runtime visual verification timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
write();handle=unreal.register_slate_post_tick_callback(tick)
