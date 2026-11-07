"""Native Manny acceptance in the original MPR map; never saves scene assets.

Uses the full workflow validator for cargo/cart conservation, real mesh readback,
shared GHS camera controls, and a native CSV performance window. Adds close-up
24-fps sorting footage and bone-pose invariance across diagnostic step sizes.
"""
from pathlib import Path
import hashlib
import math
import sys

sys.path.insert(0, str(Path(__file__).parent))
import verify_mpr_full_sorter_runtime as v

v.BASE = v.ROOT / 'Saved/MPR/worker_mannequin_20261107/runtime'


def worker_bones():
    return {c.get_name(): [v.transform_values(c.get_bone_transform_by_name(
        c.get_bone_name(i), v.u.BoneSpaces.WORLD_SPACE)) for i in range(c.get_num_bones())]
        for c in v.sim.get_components_by_class(v.u.MPRWorkerPoseComponent) if c.is_visible()}


def close_camera(mi, yaw=-120, distance=300, pitch=-20):
    yield from v.focus(mi, 0)
    pickup = v.state()['machines'][mi]['pickup_world_cm']
    side = v.LAYOUT['machines'][mi]['infeed_side_local_x']
    pivot = [pickup[0]-side*56, pickup[1]-25, 108]
    v.pawn.focus_on_target(v.u.Vector(*pivot), distance, v.u.Rotator(pitch=pitch, yaw=yaw),
                          v.u.Vector2D(1920, 1080), v.u.Vector2D(960, 540), 0)
    yield from v.pause(2.)
    v.pawn.freeze_current_pose()
    v.fixed_camera = v.camera()


def close_sorting(mi):
    v.sim.reset_simulation()
    v.sim.set_simulation_playing(True)
    v.sim.set_panel_visible(False)
    yield from close_camera(mi)
    v.step(3.)
    folder = v.OUT/'sorting_close';folder.mkdir(parents=True)
    frames = []
    for frame in range(168):
        state = v.verify_state(v.state())
        v.verify_rendered(state, [mi])
        path = folder/f'frame_{frame:04d}.png'
        yield
        yield
        v.console('Shot filename="'+path.as_posix()+'" -nosuffix')
        yield from v.wait('close_shot', lambda: v.timing.png_ready(path), 8, False)
        assert v.same_pose(v.fixed_camera, v.camera())
        frames.append(dict(frame=frame, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           sim_time=state['machines'][mi]['sim_time'], worker=state['skeletal_workers'][mi*2],
                           carriers=state['machines'][mi]['carriers']))
        v.step(1/24)
        if frame % 24 == 0:
            v.report['stage']='close_sorting_'+str(frame)
            v.write()
    v.report['worker_clip'] = dict(frames=frames, fps=24, seconds=7, camera=v.fixed_camera,
                                  resolution=[1920,1080], machine_index=mi)
    v.record('fixed_1080p_official_manny_close_sorting', frames=168, fps=24)


def run():
    yield from v.wait('discover_manny_mpr', v.discover, 45)
    yield from v.wait('viewport_1920x1080', lambda: list(v.pc.get_viewport_size())==[1920,1080], 10)
    for command in ('DisableAllScreenMessages','t.MaxFPS 0','r.VSync 0','t.IdleWhenNotForeground 0',
                    'Slate.bAllowThrottling 0','csv.CompressionMode 0','r.GPUCsvStatsEnabled 1'):
        v.console(command)
    v.sim.set_automatic_advance_for_diagnostics(False)
    v.sim.reset_simulation()
    initial = v.verify_state(v.state())
    v.bind_instances(initial)
    v.report['engine_version'] = v.u.SystemLibrary.get_engine_version()
    v.report['actor_count_before'] = len(v.u.GameplayStatics.get_all_actors_of_class(v.world,v.u.Actor))
    v.record('44_official_manny_slots_and_no_primitive_workers', readback=v.verify_rendered(initial,range(22)))
    yield from v.control_tests()

    # True event time, not the last rendered Induct frame, drives the release.
    v.sim.reset_simulation();v.sim.set_simulation_playing(True);v.step(6.)
    coarse = worker_bones()
    v.sim.reset_simulation();v.sim.set_simulation_playing(True)
    for _ in range(60):v.step(.1)
    assert v.equivalent(coarse,worker_bones(),.01), 'Release pose depends on render sampling'
    v.record('all_worker_bones_at_6s_equal_single_and_60_steps')

    # Include approach, gripping, transfer, release and return for all 22 stations.
    v.sim.reset_simulation();v.sim.set_simulation_playing(True)
    worst_hand=worst_length=0.
    for _ in range(180):
        state=v.step(.05)
        for worker in state['skeletal_workers']:
            if worker['visible']:
                worst_hand=max(worst_hand,worker['left_error_cm'],worker['right_error_cm'])
                worst_length=max(worst_length,worker['limb_length_error_cm'])
    v.record('all_22_approach_transfer_release_poses', samples=180, max_hand_error_cm=worst_hand,
             max_limb_length_error_cm=worst_length)

    first64=next(i for i,m in enumerate(v.LAYOUT['machines']) if m['profile']=='cad64')
    first120=next(i for i,m in enumerate(v.LAYOUT['machines']) if m['profile']=='cad120')
    yield from close_sorting(first64)
    v.sim.set_panel_visible(True)
    yield from v.workflow(first64,0,sequence=True,record_infeed=False)
    yield from v.workflow(first120,1)
    yield from v.automatic_exchange_test()
    yield from v.performance_sample()
    assert len(v.u.GameplayStatics.get_all_actors_of_class(v.world,v.u.Actor))==v.report['actor_count_before']
    assert len(v.sim.get_components_by_class(v.u.MPRWorkerPoseComponent))==44
    assert len(v.report['sequence'])==132
    v.record('stable_actor_and_44_skeletal_component_pool')
    v.report.update(success=True,stage='complete')


if __name__=='__main__':
    v.run=run
    v.main()
    v.report["capture_sequence"]=True
    for asset in sorted((v.ROOT/'Content/Characters/Mannequins').rglob('*.uasset')):
        v.ASSETS.append(asset);v.HASHES[str(asset)]=hashlib.sha256(asset.read_bytes()).hexdigest()
