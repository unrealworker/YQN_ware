"""Render follow-camera composition while the real panel opens and closes."""
from pathlib import Path
exec(Path('D:/UEPro/Test/Scripts/ghs/verify_order_replay_runtime.py').read_text(encoding='utf8').split('steps=run()')[0])
OUT=ROOT/'Saved/OrderReplay/FollowPanel-20261026/runtime';OUT.mkdir(parents=True,exist_ok=True)
report=dict(success=False,checks=[],captures=[],states={},motions=[])


def sample():
    rect=hud.get_replay_scene_rect();camera=pawn.get_component_by_class(unreal.CameraComponent)
    offset=pawn.spring_arm_component.socket_offset;distance=pawn.spring_arm_component.target_arm_length
    focal=1920/(2*math.tan(math.radians(camera.field_of_view*.5)))
    projected=pc.project_world_location_to_screen(pawn.get_actor_location(),False)
    return dict(progress=hud.get_panel_transition_progress(),panel_x=hud.get_panel_visual_position().x,
                center_x=rect.x+rect.z*.5,offset_center_x=960-offset.y/distance*focal,
                rendered_x=projected.x,rotation=numeric(pawn.get_actor_rotation(),('pitch','yaw','roll')),
                distance=distance,follow=state()['followId'],playing=state()['playing'],time=state()['time'])


def toggle():
    pixels=hud.get_viewport_pixel_size()
    assert hud.handle_chrome_click(unreal.Vector2D(pixels.x-30,25))


def motion(name,opening,reverse=False):
    before=sample();rows=[before];toggle()
    assert sample()==before,'Click must not reset the follow pose before animation advances'
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        yield
        row=sample();rows.append(row)
        assert row['follow']==before['follow'] and pawn.is_replay_following()
        assert row['rotation']==before['rotation'] and abs(row['distance']-before['distance'])<.01
        assert row['playing']==before['playing']
        if not before['playing']:assert row['time']==before['time']
        if reverse and .35<row['progress']<.65:break
        if not reverse and abs(row['progress']-(1 if opening else 0))<.0001:break
    # Let the actual camera component consume its final spring-arm transform.
    for _ in range(3):yield;rows.append(sample())
    max_rect_error=max(abs(row['center_x']-row['panel_x']*.5) for row in rows)
    max_offset_error=max(abs(row['offset_center_x']-row['panel_x']*.5) for row in rows)
    render_steps=[abs(b['rendered_x']-a['rendered_x']) for a,b in zip(rows,rows[1:])]
    native_steps=[abs(b['panel_x']-a['panel_x'])*.5 for a,b in zip(rows,rows[1:])]
    # Projection observes the previous camera-component tick. At a reversal,
    # its first step still consumes the last offset from the preceding motion.
    pending_render_step=abs(before['offset_center_x']-before['rendered_x'])
    report['motions'].append(dict(name=name,samples=rows,max_rect_error_px=max_rect_error,
        max_offset_error_px=max_offset_error,max_render_step_px=max(render_steps),max_panel_center_step_px=max(native_steps)))
    write()
    assert any(.01<r['progress']<.99 for r in rows),'Missing intermediate panel frames'
    assert max_rect_error<.1,('Follow composition snaps instead of tracking panel',max_rect_error)
    assert max_offset_error<.1,('Camera framing is not synchronized',max_offset_error)
    assert max(render_steps)<=max(max(native_steps),pending_render_step)+3,('Rendered camera jumped',max(render_steps),max(native_steps),pending_render_step)
    if not reverse:assert abs(rows[-1]['progress']-(1 if opening else 0))<.0001
    record(name,frames=len(rows),maximum_render_step_px=max(render_steps))


def run():
    yield from wait('discover',discover,100)
    yield from wait('initial camera',lambda:not pawn.is_pose_transition_active())
    before=pose()
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    command('navigate',page='trace');hud.navigate('trace')
    command('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-23T12:00:00.000Z',endUtc='2026-10-23T13:00:00.000Z')
    yield from wait('prepared',lambda:not state()['preparing'] and not pawn.is_pose_transition_active())
    command('replayPause');command('replaySeek',time=670)
    command('replayFollow',id='REPLAY-FORK-02')
    yield from wait('forklift follow',lambda:not pawn.is_pose_transition_active())
    pawn.orbit_pixels(unreal.Vector2D(90,-18));pawn.zoom_steps(-1)
    yield from pause(1.5)
    start=sample();pawn.pan_pixels(unreal.Vector2D(150,75),1920)
    assert sample()==start,'Manual pan must remain blocked while following'
    yield from capture('01-follow-expanded')
    yield from motion('paused-forklift-collapse',False)
    yield from capture('02-follow-collapsed')
    yield from motion('paused-forklift-expand',True)
    yield from motion('paused-forklift-partial-collapse',False,True)
    yield from motion('paused-forklift-reverse-expand',True)
    command('replayPlay')
    yield from motion('moving-forklift-collapse',False)
    yield from motion('moving-forklift-expand',True)
    command('replayPause')
    assert state()['time']>670
    command('replayFollow',id='REPLAY-TRUCK-A')
    yield from wait('truck follow',lambda:not pawn.is_pose_transition_active());yield from pause(.5)
    yield from motion('truck-collapse',False)
    yield from motion('truck-expand',True)
    # Free view must not be moved by a panel toggle.
    command('replayFollow',id='');yield from pause(.3)
    free_pose=pose();toggle();yield from pause(.6);assert pose()==free_pose
    toggle();yield from pause(.6);assert pose()==free_pose
    record('free_view_unchanged')
    command('replayEndRequest');command('replayExitConfirm')
    assert json.loads(session.get_restoration_report())['verified'] and pose()==before
    assert hashlib.sha256(MAP.read_bytes()).hexdigest()==map_hash
    record('scene_and_original_camera_restored',map_sha256=map_hash)


steps=run()


def tick(delta):
    try:
        assert time.monotonic()-started<180,'Follow panel verification timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())


write();handle=unreal.register_slate_post_tick_callback(tick)
