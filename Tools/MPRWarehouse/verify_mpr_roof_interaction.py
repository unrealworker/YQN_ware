"""Exercise the real MPR HUD, roof group and shared GHS camera in an owned game."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import struct
import sys
import time
import traceback
import unreal as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import profile_mpr_runtime as timing
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE = ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
OUT = ROOT/'Saved/MPR/roof_interaction_20261106/runtime'
OUT.mkdir(parents=True, exist_ok=True)
CLI = u.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+v+r'(?=\s|$)', CLI, re.I)
           for v in ('own', 'game', 'RenderOffscreen', 'TwinDiagnostics'))
assert not re.search(r'(?:^|\s)-MPRProfile(?=\s|$)', CLI, re.I)
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
START = time.monotonic()
world = pc = hud = pawn = roof = handle = None
parts = []
assets = {str(MAP_FILE):hashlib.sha256(MAP_FILE.read_bytes()).hexdigest()}
done = busy = False
report = dict(success=False, run_id=STAMP, checks=[], captures=[], performance={}, assets_saved=False)


def write():
    (OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')


def record(name, **data):
    report['checks'].append(dict(name=name, passed=True, **data))
    write()


def console(command):
    u.SystemLibrary.execute_console_command(world, command, pc)


def command(action):
    hud.command(json.dumps(dict(action=action)))


def poi():
    return json.loads(hud.get_poi_report())


def camera():
    m = pc.player_camera_manager
    p, r = m.get_camera_location(), m.get_camera_rotation()
    return [p.x,p.y,p.z,r.pitch,r.yaw,r.roll]


def equal_pose(a, b):
    return max(abs(x-y) for x,y in zip(a,b)) < .05


def wait(name, predicate, seconds=25):
    report['stage'] = name
    end = time.monotonic()+seconds
    while not predicate():
        assert time.monotonic() < end, 'Timed out: '+name
        yield


def pause(seconds):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        yield


def discover():
    global world, pc, hud, pawn, roof
    for w in u.ObjectIterator(u.World):
        if not w.get_path_name().startswith(MAP+'.'):
            continue
        c = u.GameplayStatics.get_player_controller(w, 0)
        h = c.get_editor_property('twin_hud_widget') if c else None
        if h:
            world, pc, hud = w, c, h
            pawn, roof = c.get_controlled_pawn(), c.warehouse_roof
            return bool(pawn and roof and roof.has_roof())
    return False


def idle(opened):
    assert not roof.is_transitioning() and not roof.is_component_tick_enabled()
    assert roof.is_interior_available() == opened
    for actor, mesh, originals, hidden in parts:
        assert actor.get_editor_property('hidden') == (opened or hidden)
        assert [mesh.get_material(i) for i in range(mesh.get_num_materials())] == originals


def transition(name, opening, expected_seconds, fixed):
    start = u.GameplayStatics.get_time_seconds(world)
    samples = []
    previous = None
    end = time.monotonic()+15
    while True:
        assert time.monotonic() < end, name
        phase, progress = roof.get_transition_phase(), roof.get_open_progress()
        now = u.GameplayStatics.get_time_seconds(world)
        samples.append([now-start, phase, progress])
        assert abs(progress-phase*phase*(3-2*phase)) < 2e-5
        assert equal_pose(fixed, camera()), 'Roof click changed the camera'
        if previous is not None:
            assert progress >= previous-1e-6 if opening else progress <= previous+1e-6
        if (roof.is_interior_available() if opening else roof.is_roof_closed()):
            break
        assert roof.is_component_tick_enabled()
        centers, axes = [], []
        for actor, mesh, originals, hidden in parts:
            for slot in range(mesh.get_num_materials()):
                material = mesh.get_material(slot)
                assert isinstance(material, u.MaterialInstanceDynamic), mesh.get_path_name()
                assert abs(material.get_scalar_parameter_value('RoofOpenProgress')-progress) < 1e-5
                center=material.get_vector_parameter_value('RoofCenter')
                axis=material.get_vector_parameter_value('RoofAxisInvExtent')
                centers.append((center.r,center.g,center.b,center.a))
                axes.append((axis.r,axis.g,axis.b,axis.a))
        assert len(set(centers)) == len(set(axes)) == 1, 'Roof parts do not share a scan'
        previous = progress
        yield
    slack = max((b[0]-a[0] for a,b in zip(samples,samples[1:])), default=.02)
    assert expected_seconds-.035 <= samples[-1][0] <= expected_seconds+slack+.035
    idle(opening)
    record(name, seconds=samples[-1][0], samples=samples)


def capture(name):
    path = OUT/(name+'_'+STAMP+'.png')
    state = dict(progress=roof.get_open_progress(), camera=camera(), poi=poi())
    console('Shot showui filename="'+path.as_posix()+'" -nosuffix')
    yield from wait('screenshot_'+name, lambda:timing.png_ready(path))
    raw = path.read_bytes()
    assert struct.unpack('>II', raw[16:24]) == (1920,1080)
    report['captures'].append(dict(name=name, path=str(path), sha256=hashlib.sha256(raw).hexdigest(), **state))
    write()


def sample(name):
    yield from pause(10)
    filename = 'MPR_INTERACTION_'+name+'_'+STAMP+'.csv'
    path = ROOT/'Saved/Profiling/CSV'/filename
    console('CsvProfile STARTFILE='+filename)
    console('CsvProfile START')
    yield from pause(15)
    console('csvprofile stop')
    yield from wait('native_csv_'+name, lambda:timing.csv_complete(path))
    native = timing.parse_csv(path)
    native['fps'] = native['frame_count']/native['native_frame_time_seconds']
    report['performance'][name] = native
    write()


def restore(fixed):
    command('overview')
    yield from wait('overview_restored', lambda:roof.is_roof_closed() and not pawn.is_pose_transition_active())
    yield from wait('warehouse_label_restored', lambda:len(poi()['labels']) == 1 and poi()['labels'][0]['opacity'] > .99)
    assert equal_pose(fixed, camera()), 'Reset did not restore the MPR entry view'
    idle(False)


def run():
    yield from wait('discover_mpr_interaction', discover, 60)
    yield from wait('initial_label', lambda:len(poi()['labels']) == 1 and not pawn.is_pose_transition_active())
    for value in ('DisableAllScreenMessages','t.MaxFPS 0','r.VSync 0','t.IdleWhenNotForeground 0',
                  'Slate.bAllowThrottling 0','csv.CompressionMode 0','r.GPUCsvStatsEnabled 1'):
        console(value)
    yield from pause(8)
    fixed = camera()
    actors = list(u.GameplayStatics.get_all_actors_of_class(world, u.Actor))
    targets = [a for a in actors if 'MPR_Roof' in [str(t) for t in a.tags]]
    assert len(targets) == 30
    for a in targets:
        for m in a.get_components_by_class(u.StaticMeshComponent):
            if not m.static_mesh:
                continue
            originals = [m.get_material(i) for i in range(m.get_num_materials())]
            parts.append((a,m,originals,a.get_editor_property('hidden')))
            for material in originals:
                p=ROOT/'Content'/(material.get_path_name().split('.')[0].removeprefix('/Game/')+'.uasset')
                assets[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    assert len(parts) == 30
    assert pc.get_editor_property('campus_traffic') is None
    assert not hud.browser_ready and not hud.is_scene_search_visible()
    labels = poi()['labels']
    assert labels[0]['id'] == 'WAREHOUSE:MPR' and 'MPR' in labels[0]['title']
    assert [labels[0]['width'], labels[0]['height']] == [228,56]
    idle(False)
    record('direct_entry_ghs_camera_and_single_mpr_warehouse_label', actor_count=len(actors), roof_parts=len(parts),
           camera_class=pawn.get_class().get_path_name(), controller_class=pc.get_class().get_path_name(),
           label=labels[0], scene=poi())
    yield from capture('01_closed')
    yield from sample('closed')
    label=poi()['labels'][0]
    scale=hud.get_hud_scale()
    point=u.Vector2D((label['x']+label['width']/2)*scale, (label['y']+label['height']/2)*scale)
    assert hud.handle_scene_click(point) and roof.is_opening()
    yield from transition('poi_click_opens_all_roof_parts', True, .8, fixed)
    yield from pause(.2)
    assert not poi()['labels'], 'MPR showed unrelated interior business labels'
    yield from capture('03_open')
    yield from sample('open')
    command('overview')
    yield from transition('overview_restores_roof', False, .55, fixed)
    yield from restore(fixed)
    # Camera input calls are the same GHS Pawn APIs used by the shared Controller.
    pawn.orbit_pixels(u.Vector2D(90,-30));yield from pause(1)
    assert not equal_pose(fixed,camera())
    before=pawn.get_actor_location()
    pawn.pan_pixels(u.Vector2D(45,35),1920);yield from pause(1)
    assert (pawn.get_actor_location()-before).length() > 10
    before=pawn.get_editor_property('spring_arm_component').target_arm_length
    command('zoomIn');yield from pause(1)
    assert pawn.get_editor_property('spring_arm_component').target_arm_length < before-100
    yield from restore(fixed)
    record('shared_orbit_pan_zoom_and_overview_reset', final_camera=camera())
    # Same camera, slow game clock only for the midpoint illustration.
    u.GameplayStatics.set_global_time_dilation(world,.08)
    assert hud.open_warehouse()
    yield from wait('scan_midpoint', lambda:roof.get_open_progress() >= .48)
    u.GameplayStatics.set_global_time_dilation(world,.0001)
    yield from capture('02_mid_scan')
    u.GameplayStatics.set_global_time_dilation(world,1)
    command('overview')
    yield from restore(fixed)
    yield from capture('04_restored')
    assert len(u.GameplayStatics.get_all_actors_of_class(world,u.Actor)) == len(actors)
    assert {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in assets} == assets
    record('all_materials_and_saved_assets_preserved', saved_assets=len(assets))
    report.update(success=True, stage='complete', map_sha256=assets[str(MAP_FILE)])
    write()


def finish(error=None):
    global done
    done=True
    if error:
        report.update(success=False,error=error)
    if world:
        u.GameplayStatics.set_global_time_dilation(world,1)
        if roof:roof.restore_roof(False)
        console('csvprofile stop')
    write()
    if handle is not None:u.unregister_slate_post_tick_callback(handle)
    if world:u.SystemLibrary.quit_game(world,pc,u.QuitPreference.QUIT,False)


steps=run()
def tick(delta):
    global busy
    if done or busy:return
    busy=True
    try:
        assert time.monotonic()-START < 210, 'Interaction verification deadline'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
    finally:busy=False


handle=u.register_slate_post_tick_callback(tick)
