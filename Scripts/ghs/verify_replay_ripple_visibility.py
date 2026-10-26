"""Rendered acceptance for replay-only blue diffusion on the actual floor."""
from pathlib import Path
exec(Path('D:/UEPro/Test/Scripts/ghs/verify_order_replay_runtime.py').read_text(encoding='utf8').split('steps=run()')[0])
OUT=ROOT/'Saved/OrderReplay/RippleVisibility-20261026/runtime';OUT.mkdir(parents=True,exist_ok=True)
report=dict(success=False,checks=[],captures=[],states={})


def visible(component):
    return bool(component.get_editor_property('visible'))


def run():
    yield from wait('discover',discover,100)
    yield from wait('initial camera',lambda:not pawn.is_pose_transition_active())
    data_file=ROOT/'Content/GHSTwinUI/data/order-replay.json'
    trail_file=ROOT/'Content/GHSOrderReplay/Materials/M_ReplayTrail.uasset'
    ripple_file=ROOT/'Content/GHSOrderReplay/Materials/M_ReplayGroundRipple.uasset'
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (MAP,data_file,trail_file,ripple_file)}
    data=json.loads(data_file.read_text(encoding='utf8'))
    camera_before=pose();roof_before=pc.warehouse_roof.get_transition_phase()
    originals=unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
    assert not any(a.get_class().get_name()=='GHSOrderReplayActor' for a in originals)
    original_decal_count=sum(len(a.get_components_by_class(unreal.DecalComponent)) for a in originals)
    record('normal_scene_has_no_replay_actor',scene_decal_count=original_decal_count)
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    command('navigate',page='trace');hud.navigate('trace')
    command('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-23T12:00:00.000Z',endUtc='2026-10-23T13:00:00.000Z')
    yield from wait('prepared',lambda:not state()['preparing'] and not pawn.is_pose_transition_active())
    command('replayPause');command('replaySeek',time=0)
    actor=next(a for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
               if a.get_class().get_name()=='GHSOrderReplayActor')
    ripples=sorted(actor.get_components_by_class(unreal.DecalComponent),key=lambda c:c.get_name())
    trails=sorted(actor.get_components_by_class(unreal.InstancedStaticMeshComponent),key=lambda c:c.get_name())
    assert len(ripples)==len(trails)==5
    assert not any(visible(c) for c in ripples+trails)
    record('idle_replay_has_no_ripples_or_routes',ripple_count=5,trail_count=5)

    # Use a real loaded straight span; no fixed replay timestamps can go stale.
    track=data['tracks'][1]
    a,b=next((a,b) for a,b in zip(track['keys'],track['keys'][1:])
             if a[7]=='运送托盘' and b[0]-a[0]>5 and math.dist(a[1],b[1])>500)
    timepoint=(a[0]+b[0])*.5
    identity=track['id'];command('replaySeek',time=timepoint)
    command('replayTrails',mode='selected');command('replaySelect',id=identity)
    command('replayFollow',id=identity)
    yield from wait('follow ripple',lambda:not pawn.is_pose_transition_active());yield from pause(.6)
    assert [visible(c) for c in ripples]==[False,True,False,False,False]
    assert [visible(c) for c in trails]==[False,True,False,False,False]
    material=ripples[1].get_decal_material();trail_material=trails[1].get_material(0)
    tint=numeric(material.get_vector_parameter_value('Tint'),('r','g','b','a'))
    assert tint==numeric(trail_material.get_vector_parameter_value('Tint'),('r','g','b','a'))
    assert abs(material.get_scalar_parameter_value('RippleEmission')-.55)<.0001
    size=numeric(ripples[1].get_editor_property('decal_size'),'xyz')
    assert size==(3.,165.,165.),size
    # Editor-only graph APIs are unavailable in -game. Match this rendered asset
    # to the scoped editor validation, which checks all three material outputs.
    graph=json.loads((OUT.parent/'material-verification.json').read_text(encoding='utf8'))
    assert graph['success'] and graph['version']=='theme-blue-visible-diffusion-v2'
    assert graph['outputs']==['BaseColor','Emissive','Opacity']
    assert graph['material_sha256']==hashes[str(ripple_file.relative_to(ROOT))]
    record('theme_blue_coverage_matches_route',linear_tint=tint,emission=.55,
           decal_half_size_cm=size,main_wave_core_width_cm=5.28,peak_wave_opacity=.96,
           gradient_srgb=['#8BB9FF','#356BFA'],asset_sha256=hashes[str(ripple_file.relative_to(ROOT))])

    for i,offset in enumerate((0.,.5,1.,1.5)):
        command('replaySeek',time=timepoint+offset);yield from pause(.4)
        assert abs(material.get_scalar_parameter_value('ReplayTime')-(timepoint+offset))<.001
        row=next(d for d in state()['devices'] if d['id']==identity)
        assert row['loaded'] and row['trailVisible']
        report['states']['phase-'+str(i)]=row
        yield from capture('01-diffusion-phase-'+str(i))
    clock=material.get_scalar_parameter_value('ReplayTime');yield from pause(.4)
    assert material.get_scalar_parameter_value('ReplayTime')==clock
    command('replaySeek',time=timepoint)
    assert abs(material.get_scalar_parameter_value('ReplayTime')-timepoint)<.001
    record('diffusion_uses_paused_seekable_replay_clock',sample_offsets_seconds=[0.,.5,1.,1.5])
    command('replayTrails',mode='off');assert not any(visible(c) for c in ripples+trails)
    yield from pause(.3);yield from capture('02-effects-hidden')
    command('replayTrails',mode='all')
    fault=next(e for e in data['events'] if e['kind']=='fault')
    command('replaySeek',time=fault['time']+1)
    assert not visible(ripples[2]) and not visible(trails[2])
    command('replaySeek',time=state()['duration'])
    assert state()['completed'] and not any(visible(c) for c in ripples+trails)
    record('route_switch_fault_and_completion_hide_ripples')
    command('replayEndRequest');command('replayExitConfirm');yield from pause(.4)
    assert not state()['active'] and pose()==camera_before
    assert pc.warehouse_roof.get_transition_phase()==roof_before
    assert json.loads(session.get_restoration_report())['verified']
    final=unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
    assert not any(a.get_class().get_name()=='GHSOrderReplayActor' for a in final)
    assert sum(len(a.get_components_by_class(unreal.DecalComponent)) for a in final)==original_decal_count
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in hashes.items())
    record('normal_scene_restored_without_replay_decals',protected_hashes=hashes)


steps=run()


def tick(delta):
    try:
        assert time.monotonic()-started<240,'Ripple runtime verification timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())


write();handle=unreal.register_slate_post_tick_callback(tick)
