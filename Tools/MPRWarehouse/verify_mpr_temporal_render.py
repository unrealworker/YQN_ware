"""Capture real Tick-driven MPR motion to diagnose temporal reconstruction.

Run an owned -game -RenderOffscreen -TwinDiagnostics -EnablePython process at
-ForceRes -ResX=1920 -ResY=1080 with this script in -ExecCmds="py ...".
-MPRTemporalBaseline labels the unmodified run; -MPRTemporalVelocity optionally
captures the Velocity buffer. No scene, material, or configuration is saved.
Unlike diagnostic-step videos, automatic advancement stays enabled throughout
every moving screenshot, including the frames spent completing its PNG write.
"""
import hashlib
import math
from pathlib import Path
import re
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).parent))
import verify_mpr_continuous_runtime as continuous

v = continuous.v
CENTRAL_COMPONENTS = ('CentralMovingColumns', 'CentralLiftTrays', 'CentralParcels')
ORIGINAL_CVARS = {}
VIEWMODE_CHANGED = False
ORIGINAL_FINISH = v.finish


def flag(name):
    return bool(re.search(r'(?:^|\s)-' + re.escape(name) + r'(?=\s|$)',
                          v.u.SystemLibrary.get_command_line(), re.I))


def property_or_error(obj, name):
    try:
        result = obj.get_editor_property(name)
        if result is None or isinstance(result, (str, int, float, bool)):
            return result
        return str(result)
    except Exception as error:
        return {'unavailable': str(error)}


def assets_readback():
    rows = []
    for name in CENTRAL_COMPONENTS:
        component = v.components[name]
        mesh = component.get_editor_property('static_mesh')
        row = dict(component=component.get_path_name(), instances=component.get_instance_count(),
                   mesh=mesh.get_path_name(),
                   materials=[component.get_material(i).get_path_name()
                              if component.get_material(i) else None
                              for i in range(component.get_num_materials())],
                   mobility=property_or_error(component, 'mobility'),
                   previous_instance_transform_python_api=hasattr(component, 'get_instance_prev_transform'))
        for name_ in ('disallow_nanite', 'force_disable_nanite', 'evaluate_world_position_offset',
                      'world_position_offset_disable_distance', 'cast_shadow'):
            row[name_] = property_or_error(component, name_)
        try:
            settings = mesh.get_editor_property('nanite_settings')
            row['nanite_enabled'] = settings.get_editor_property('enabled')
        except Exception as error:
            row['nanite_enabled'] = {'unavailable': str(error)}
        rows.append(row)
    return rows


def poses():
    # A cheap, direct native-component read; no full report is requested per frame.
    return {name: [v.xyz(v.instance(v.components[name], i).translation) for i in (0, 1, 10)]
            for name in ('CentralMovingColumns', 'CentralLiftTrays')}


def displacement(before, after):
    return max(math.dist(a, b) for name in before
               for a, b in zip(before[name], after[name]))


def capture(name, moving, mode):
    path = v.OUT / (name + '.png')
    before = poses()
    start = time.monotonic()
    # Render several real moving frames; NEVER diagnostic-step or pause here.
    yield
    yield
    v.console('Shot showui filename="' + path.as_posix() + '" -nosuffix')
    yield from v.wait('capture_' + name, lambda: v.timing.png_ready(path), 15, log=False)
    after = poses()
    motion = displacement(before, after)
    assert (motion > .01) if moving else (motion < .001), (name, moving, motion)
    assert v.same_pose(v.fixed_camera, v.camera()), 'Camera changed during capture'
    data = path.read_bytes()
    assert struct.unpack('>II', data[16:24]) == (1920, 1080)
    v.report['captures'].append(dict(name=name, path=str(path), mode=mode,
        automatic_tick=True, playing=moving,
        aa_method=v.u.SystemLibrary.get_console_variable_int_value('r.AntiAliasingMethod'),
        camera=v.fixed_camera[:], seconds=time.monotonic() - start,
        native_displacement_during_capture_cm=motion,
        before_poses=before, after_poses=after, sha256=hashlib.sha256(data).hexdigest()))
    v.write()


def restore_runtime():
    global VIEWMODE_CHANGED
    if not v.world:
        return
    if VIEWMODE_CHANGED:
        v.console('viewmode lit')
        VIEWMODE_CHANGED = False
    for name, value in ORIGINAL_CVARS.items():
        v.console(name + ' ' + str(value))
    if ORIGINAL_CVARS:
        v.report['restored_aa_method'] = v.u.SystemLibrary.get_console_variable_int_value('r.AntiAliasingMethod')
        v.report['runtime_cvars_restored'] = (
            v.report['restored_aa_method'] == ORIGINAL_CVARS['r.AntiAliasingMethod'])


def finish(error=None):
    try:
        restore_runtime()
    finally:
        ORIGINAL_FINISH(error)


def run():
    global VIEWMODE_CHANGED
    v.report.update(baseline=flag('MPRTemporalBaseline'),
        scope='Native Tick-driven MPR temporal rendering comparison; same fixed camera and resolution.',
        visual_verification_required=True,
        limitations=['Capture success proves continuous native motion, fixed framing and completed images; '
                     'it does not by itself prove absence of visible temporal artifacts.',
                     'FXAA is a temporary diagnostic comparison, not a production configuration change.',
                     'GetInstancePrevTransform is not exposed by the UE 5.8 Python API; '
                     'native position movement is measured, not inferred GPU velocity.'])
    yield from v.wait('discover', v.discover, 40)
    yield from v.wait('viewport', lambda: list(v.pc.get_viewport_size()) == [1920, 1080], 10)
    for name in ('r.AntiAliasingMethod', 'r.VSync', 't.IdleWhenNotForeground', 'Slate.bAllowThrottling'):
        ORIGINAL_CVARS[name] = v.u.SystemLibrary.get_console_variable_int_value(name)
    ORIGINAL_CVARS['t.MaxFPS'] = v.u.SystemLibrary.get_console_variable_float_value('t.MaxFPS')
    v.report['original_runtime_cvars'] = dict(ORIGINAL_CVARS)
    for command in ('DisableAllScreenMessages', 't.MaxFPS 60', 'r.VSync 0',
                    't.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0'):
        v.console(command)
    v.sim.set_panel_visible(False)
    v.sim.set_automatic_advance_for_diagnostics(False)
    continuous.reset()
    v.step(140)  # Populate the equipment before the rendering experiment begins.
    yield from continuous.central.focus_view('temporal_close', [-10530, -150, 130],
                                             1350, -28, 30, fov=25)
    v.report['render_assets'] = assets_readback()
    v.report['initial_instance_pool'] = {n: c.get_instance_count() for n, c in v.components.items()}
    v.sim.set_automatic_advance_for_diagnostics(True)
    v.sim.set_simulation_playing(True)
    yield from v.pause(2, True)
    initial = continuous.verify_state(v.state())
    v.report['initial_central_generated'] = initial['central_generated']
    for i in range(3):
        yield from capture('moving_default_aa_' + str(i), True, 'default_aa')
        yield from v.pause(.2, True)
    v.sim.set_simulation_playing(False)
    yield from v.pause(2, True)
    yield from capture('paused_settled_default_aa', False, 'default_aa')

    v.console('r.AntiAliasingMethod 1')
    v.sim.set_simulation_playing(True)
    yield from v.pause(2, True)
    for i in range(2):
        yield from capture('moving_fxaa_' + str(i), True, 'fxaa_diagnostic')
        yield from v.pause(.2, True)

    if flag('MPRTemporalVelocity'):
        v.console('r.AntiAliasingMethod ' + str(ORIGINAL_CVARS['r.AntiAliasingMethod']))
        v.console('r.BufferVisualizationTarget Velocity')
        v.console('viewmode visualizebuffer')
        VIEWMODE_CHANGED = True
        yield from v.pause(2, True)
        yield from capture('moving_velocity', True, 'velocity_buffer_diagnostic')
        v.console('viewmode lit')
        VIEWMODE_CHANGED = False

    # Keep the common 60 fps cap for the final comparison; restore all process
    # overrides only in finish, after the last screenshot has completed.
    v.console('r.AntiAliasingMethod ' + str(ORIGINAL_CVARS['r.AntiAliasingMethod']))
    yield from v.pause(2, True)
    yield from capture('moving_restored_aa', True, 'restored_default_aa')
    final = continuous.verify_state(v.state())
    assert final['central_generated'] > initial['central_generated']
    assert v.report['initial_instance_pool'] == {n: c.get_instance_count() for n, c in v.components.items()}
    v.record('native_continuous_motion_rendered',
             central_generated_before=initial['central_generated'],
             central_generated_after=final['central_generated'],
             screenshot_count=len(v.report['captures']))
    # Measure real frames separately from PNG capture overhead, at the same
    # fixed view and restored production AA. This is a capped local sample.
    v.console('csv.CompressionMode 0')
    v.console('r.GPUCsvStatsEnabled 1')
    filename = 'MPR_TEMPORAL_' + v.report['run_id'] + '.csv'
    path = v.ROOT / 'Saved/Profiling/CSV' / filename
    v.console('CsvProfile STARTFILE=' + filename)
    v.console('CsvProfile START')
    yield from v.pause(15, True)
    v.console('CsvProfile STOP')
    yield from v.wait('native_csv_flush', lambda: v.timing.csv_complete(path), 10)
    timing = v.timing.parse_csv(path)
    timing['fps'] = timing['frame_count'] / timing['native_frame_time_seconds']
    v.report['performance'] = dict(native_csv=timing, resolution=[1920, 1080],
        fps_cap=60, automatic_tick=True, screenshots_during_sample=0,
        aa_method=ORIGINAL_CVARS['r.AntiAliasingMethod'])
    v.report.update(success=True, stage='complete')


v.BASE = v.ROOT / 'Saved/MPR/temporal_render_20261112/runtime'
v.DEADLINE_SECONDS = 240
v.verify_state = continuous.verify_state
v.run = run
v.finish = finish
if __name__ == '__main__':
    v.main()
