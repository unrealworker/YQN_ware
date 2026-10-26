"""Render and sample the production forklift motion in an isolated game world."""
from pathlib import Path
exec(Path('D:/UEPro/Test/Scripts/ghs/verify_order_replay_runtime.py').read_text(encoding='utf8').split('steps=run()')[0])
OUT=ROOT/'Saved/OrderReplay/SmoothTurning-20261026/runtime';OUT.mkdir(parents=True,exist_ok=True)
report=dict(success=False,checks=[],captures=[],states={})


def device(identity):
    return next(row for row in state()['devices'] if row['id']==identity)


def run():
    yield from wait('discover',discover,100)
    yield from wait('initial camera',lambda:not pawn.is_pose_transition_active())
    data_file=ROOT/'Content/GHSTwinUI/data/order-replay.json'
    data_sha=hashlib.sha256(data_file.read_bytes()).hexdigest()
    data=json.loads(data_file.read_text(encoding='utf8'));events=data['events']
    assert len(data['tracks'])==18 and len(events)==48
    assert max(len(t['keys']) for t in data['tracks'])<100000
    camera_before=pose();roof_before=pc.warehouse_roof.get_transition_phase()
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    command('navigate',page='trace');hud.navigate('trace')
    began=time.monotonic()
    command('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-23T12:00:00.000Z',endUtc='2026-10-23T14:00:00.000Z')
    call_ms=(time.monotonic()-began)*1000
    assert state()['active'],state()
    yield from wait('prepared',lambda:not state()['preparing'] and not pawn.is_pose_transition_active())
    prepare_ms=(time.monotonic()-began)*1000
    command('replayPause')
    actor=next(a for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
               if a.get_class().get_name()=='GHSOrderReplayActor')
    trails=actor.get_components_by_class(unreal.InstancedStaticMeshComponent)
    assert len(trails)==5
    instances=sum(c.get_instance_count() for c in trails)
    record('production_data_loaded',data_sha256=data_sha,cycle_seconds=data['cycleDuration'],
           maximum_track_keys=max(len(t['keys']) for t in data['tracks']),
           start_command_ms=call_ms,prepared_including_roof_camera_ms=prepare_ms,
           trail_components=len(trails),trail_instances=instances)

    # Find an actual loaded bend instead of relying on a stale hardcoded time.
    track=data['tracks'][0];candidate=[]
    for a,b in zip(track['keys'],track['keys'][1:]):
        dt=b[0]-a[0]
        if a[7]=='运送托盘' and dt>0 and math.dist(a[1],b[1])>.01:
            rate=abs(math.remainder(b[2]-a[2],360))/dt
            candidate.append((rate,(a[0]+b[0])/2))
    center=max(candidate)[1];identity=track['id']
    # Dense seeks exercise the real C++ shortest-angle sampler and attached load.
    samples=[]
    for n in range(121):
        t=center-2+n/30
        command('replaySeek',time=t);row=device(identity)
        assert row['loaded'] and row['cargoCount']==1,row
        samples.append(dict(time=state()['time'],position=row['position'],yaw=row['yaw']))
    rates=[abs(math.remainder(b['yaw']-a['yaw'],360))/(b['time']-a['time']) for a,b in zip(samples,samples[1:])]
    assert max(abs(math.remainder(b['yaw']-a['yaw'],360)) for a,b in zip(samples,samples[1:]))<15
    # Exact source speed remains unchanged through the bend.
    speeds=[math.dist(a['position'],b['position'])/(100*(b['time']-a['time'])) for a,b in zip(samples,samples[1:])]
    assert all(2.56<=v<=2.61 for v in speeds),[min(speeds),max(speeds)]
    target=center+.25;command('replaySeek',time=target);expected=state()['devices']
    yield from pause(.35);assert state()['devices']==expected
    command('replaySeek',time=center+8);command('replaySeek',time=target)
    assert state()['devices']==expected
    report['states']['turn_samples']=samples
    record('constant_speed_loaded_turn_and_deterministic_seek',device=identity,center_time=center,
           sample_count=len(samples),maximum_yaw_rate_deg_s=max(rates),speed_range_m_s=[min(speeds),max(speeds)])

    command('replaySeek',time=center);command('replayFollow',id=identity)
    yield from wait('follow turn',lambda:not pawn.is_pose_transition_active());yield from pause(.5)
    for name,offset in [('before',-1.),('middle',0.),('after',1.)]:
        command('replaySeek',time=center+offset);yield from pause(.5)
        report['states']['turn_'+name]=device(identity)
        yield from capture('01-turn-'+name)
    command('replaySeek',time=center-2);command('replayRate',rate=1);command('replayPlay')
    moving=[]
    while state()['time']<center+2:
        row=device(identity);moving.append((state()['time'],row['yaw']));yield
    command('replayPause')
    moving_rates=[abs(math.remainder(b[1]-a[1],360))/(b[0]-a[0]) for a,b in zip(moving,moving[1:]) if b[0]>a[0]]
    assert moving_rates and all(math.isfinite(v) for v in moving_rates)
    assert state()['followId']==identity
    record('realtime_turn_keeps_follow',samples=len(moving),maximum_yaw_rate_deg_s=max(moving_rates))

    pickup=next(e for e in events if e['kind']=='pickup' and e['deviceId']==identity)
    drop=next(e for e in events if e['kind']=='dropoff' and e['deviceId']==identity)
    fault=next(e for e in events if e['kind']=='fault')
    recovery=next(e for e in events if e['kind']=='recovery')
    assert abs(recovery['time']-fault['time']-45)<.00001
    for name,event,loaded in [('pickup',pickup,True),('dropoff',drop,False)]:
        command('replaySeek',time=event['time']+.1)
        assert device(identity)['loaded']==loaded
        yield from pause(.5);yield from capture('02-'+name)
    command('replaySeek',time=fault['time']+1)
    broken=device(fault['deviceId']);assert '故障' in broken['status'] and not broken['trailVisible']
    command('replaySeek',time=recovery['time']+.2)
    assert '故障' not in device(fault['deviceId'])['status']
    record('cargo_events_and_fault_stop_stay_aligned',fault_pause_seconds=45)
    command('replaySeek',time=0)
    first=[{k:v for k,v in row.items() if k!='trip'} for row in state()['devices']]
    command('replaySeek',time=data['cycleDuration'])
    assert [{k:v for k,v in row.items() if k!='trip'} for row in state()['devices']]==first
    assert sum(c.get_instance_count() for c in trails)==instances
    command('replaySeek',time=state()['duration'])
    assert state()['completed'] and not state()['playing']
    record('continuous_cycle_and_fixed_route_pool',trail_instances=instances)
    command('replayEndRequest');command('replayExitConfirm');yield from pause(.4)
    assert not state()['active'] and pose()==camera_before
    assert pc.warehouse_roof.get_transition_phase()==roof_before
    assert json.loads(session.get_restoration_report())['verified']
    assert hashlib.sha256(MAP.read_bytes()).hexdigest()==map_hash
    assert hashlib.sha256(data_file.read_bytes()).hexdigest()==data_sha
    record('original_scene_restored',map_sha256=map_hash,data_sha256=data_sha)


steps=run()


def tick(delta):
    try:
        assert time.monotonic()-started<240,'Turning runtime verification timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())


write();handle=unreal.register_slate_post_tick_callback(tick)
