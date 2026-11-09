"""Four fixed native views of all-CAD personnel; no repeated motion benchmark.

Use existing MPR map with -own -game -RenderOffscreen -TwinDiagnostics
-EnablePython -ForceRes -ResX=1920 -ResY=1080 and
-ExecCmds="py D:/UEPro/Test/Tools/MPRWarehouse/capture_mpr_cad_workers.py".
No map, asset or editor-camera saves. See report for exact CAD handles/views.
"""
import hashlib
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
import verify_mpr_continuous_runtime as check
v = check.v


def mean_pivot(workers):
    return [sum(w['feet_ue_cm'][i] for w in workers) / len(workers) for i in range(2)] + [85.]


def survey_views():
    workers = check.CAD_WORKERS['workers']
    lo = [min(w['feet_ue_cm'][i] for w in workers) for i in range(2)]
    hi = [max(w['feet_ue_cm'][i] for w in workers) for i in range(2)]
    center = [(a + b) / 2 for a, b in zip(lo, hi)] + [100.]
    # Center each local survey on original CAD points, not an inferred room.
    top = [w for w in workers if w['blocks'] == ['terwrq434'] and not w['central_feed']]
    top.sort(key=lambda w: math.dist(w['feet_ue_cm'][:2], [-15100., -5900.]))
    top = top[:6]
    nested = [w for w in workers if w['blocks'] == ['GIE2', 'terwrq434']]
    seed = next(w for w in nested if w['source_handle'] == '2CB2B5/10A50B')
    nested.sort(key=lambda w: math.dist(w['feet_ue_cm'][:2], seed['feet_ue_cm'][:2]))
    nested = nested[:6]
    anonymous = [w for w in workers if '*U1348' in w['blocks']]
    assert len(anonymous) == 6
    return [
        dict(name='01_full_warehouse', workers=workers, pivot=center, distance=34000, pitch=-68, yaw=-90, fov=60),
        dict(name='02_top_level_workers', workers=top, pivot=mean_pivot(top), distance=2500, pitch=-48, yaw=-90, fov=45),
        dict(name='03_gie2_nested_workers', workers=nested, pivot=mean_pivot(nested), distance=2500, pitch=-48, yaw=-65, fov=45),
        dict(name='04_anonymous_nested_workers', workers=anonymous, pivot=mean_pivot(anonymous), distance=2300, pitch=-48, yaw=-65, fov=45),
    ]


def rectangle(center, size, yaw):
    angle = math.radians(yaw)
    c, s = math.cos(angle), math.sin(angle)
    return [[center[0] + c * x - s * y, center[1] + s * x + c * y]
            for x, y in [(-size[0]/2, -size[1]/2), (size[0]/2, -size[1]/2),
                         (size[0]/2, size[1]/2), (-size[0]/2, size[1]/2)]]


def edge_distance(point, a, b):
    ab = [b[i] - a[i] for i in range(2)]
    t = max(0., min(1., sum((point[i]-a[i]) * ab[i] for i in range(2)) / sum(x*x for x in ab)))
    return math.dist(point[:2], [a[i] + t * ab[i] for i in range(2)])


def outside_distance(point, corners):
    signs = [(b[0]-a[0]) * (point[1]-a[1]) - (b[1]-a[1]) * (point[0]-a[0])
             for a, b in zip(corners, corners[1:] + corners[:1])]
    distance = min(edge_distance(point, a, b) for a, b in zip(corners, corners[1:] + corners[:1]))
    return -distance if all(x >= 0 for x in signs) or all(x <= 0 for x in signs) else distance


def native_point(transform, point):
    """Independent quaternion transform of the mesh's physical desk footprint."""
    q = transform.rotation
    scale = v.xyz(transform.scale3d)
    x, y, z = [point[i] * scale[i] for i in range(3)]
    tx, ty, tz = 2*(q.y*z-q.z*y), 2*(q.z*x-q.x*z), 2*(q.x*y-q.y*x)
    result = [x+q.w*tx+q.y*tz-q.z*ty, y+q.w*ty+q.z*tx-q.x*tz, z+q.w*tz+q.x*ty-q.y*tx]
    origin = v.xyz(transform.translation)
    return [result[i] + origin[i] for i in range(3)]


def cad_table_readback(value):
    tables = check.CAD_WORKERS['work_tables']
    assert len(tables) == value['refitted_cad_worktables'] == 42
    expected = [{**surface, 'corners': rectangle(surface['center_ue_cm'], surface['size_cm'], surface['yaw_deg'])}
                for table in tables for surface in table['surfaces']]
    assert len(expected) == 84
    actual = []
    for actor in v.u.GameplayStatics.get_all_actors_of_class(v.world, v.u.Actor):
        for component in actor.get_components_by_class(v.u.InstancedStaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if not mesh or mesh.get_name() != 'SM_MPR_WorkTable':
                continue
            for index in range(component.get_instance_count()):
                transform = v.instance(component, index)
                if not v.visible(transform):
                    continue
                # Existing mesh desk is x=±50,y=±60,z=93 cm. Its monitor raises
                # the complete bounds to148 cm, so use surveyed tabletop, not
                # the enclosing bounds height or the original bloated CAD block.
                corners = [native_point(transform, [x, y, 93])[:2]
                           for x, y in [(-50, -60), (50, -60), (50, 60), (-50, 60)]]
                actual.append(dict(component=component.get_path_name(), instance=index, corners=corners))
    used, matches = set(), []
    for source in expected:
        candidates = []
        for i, item in enumerate(actual):
            if i in used:
                continue
            error = max(min(math.dist(p, q) for q in item['corners']) for p in source['corners'])
            if error < .05:
                candidates.append((i, error))
        assert len(candidates) == 1, ('Missing/duplicate native exact CAD table', source['source_handle'], candidates)
        index, error = candidates[0]
        used.add(index)
        matches.append(dict(source_handle=source['source_handle'], max_corner_error_cm=error,
                            **actual[index]))
    roots = {r['source_handle']: r for r in value['cad_workers']}
    clearances = []
    for source in check.CAD_WORKERS['workers']:
        if source['blocks'] != ['GIE2', 'terwrq434']:
            continue
        feet = roots[source['source_handle']]['feet_cm']
        distance = min(outside_distance(feet, table['corners']) for table in matches)
        # The source head/torso projection gives ~22.75 cm, sufficient for a
        # conservative15 cm body radius. All84 rendered tabletops are checked.
        assert distance >= 15, ('CAD worker intersects tabletop', source['source_handle'], distance)
        clearances.append(dict(source_handle=source['source_handle'], clearance_cm=distance))
    assert len(clearances) == 84
    result = dict(replaced_legacy_instances=42, native_tabletops=84, native_matches=matches,
        max_corner_error_cm=max(row['max_corner_error_cm'] for row in matches),
        body_radius_cm=15, minimum_root_to_edge_cm=min(row['clearance_cm'] for row in clearances),
        worker_clearances=clearances)
    v.record('gie2_exact_tabletops_and_worker_body_clearance', **result)
    return result


def run():
    v.report.update(scope='Four fixed native views of 256 personnel reconstructed from all source CAD blocks.',
        cad_workers_sha256=hashlib.sha256(check.CAD_WORKERS_FILE.read_bytes()).hexdigest(),
        limitations=['Static visual survey; continuous motion and performance are validated separately.'])
    yield from v.wait('discover', v.discover, 40)
    yield from v.wait('viewport', lambda: list(v.pc.get_viewport_size()) == [1920, 1080], 10)
    for command in ('DisableAllScreenMessages', 't.MaxFPS 0', 'r.VSync 0', 't.IdleWhenNotForeground 0'):
        v.console(command)
    v.sim.set_automatic_advance_for_diagnostics(False)
    check.reset()
    v.step(140)
    v.sim.set_simulation_playing(False)
    v.sim.set_panel_visible(False)
    current = check.verify_state(v.state())
    check.cad_native_readback(current)
    cad_table_readback(current)
    initial_instances = {name: c.get_instance_count() for name, c in v.components.items()}
    v.report['cad_personnel'] = current['cad_workers']
    for view in survey_views():
        yield from check.central.focus_view(view['name'], view['pivot'], view['distance'],
                                           view['pitch'], view['yaw'], fov=view['fov'])
        current = check.verify_state(v.state())
        # Every shot retains the source-defined feet and body headings. The
        # skeletal native getter accounts for the mannequin mesh-axis offset.
        native = check.cad_native_readback(current)
        yield from v.pause(.5)
        path = v.OUT / (view['name'] + '.png')
        yield from check.capture_frame(path)
        placements = {w['source_handle']: w for w in current['cad_workers']}
        skeletal = {w['index']: w for w in current['skeletal_workers']}
        subjects = []
        for source in view['workers']:
            row = placements[source['source_handle']]
            actual = skeletal[row['worker_index']]
            subjects.append(dict(source_handle=source['source_handle'], worker_index=row['worker_index'],
                feet_cm=source['feet_ue_cm'], yaw_deg=source['facing_ue_yaw_deg'],
                visible=actual['visible'], native_translation_cm=actual['transform']['translation_cm']))
        v.report['captures'].append(dict(name=view['name'], path=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), camera=v.fixed_camera[:],
            resolution=[1920, 1080], subjects=subjects, native_readback=native))
        v.write()
    assert initial_instances == {name: c.get_instance_count() for name, c in v.components.items()}
    assert len(v.report['captures']) == 4
    v.record('four_fixed_native_views_all_cad_worker_categories', source_count=256,
             central_feed_subset=6, total_runtime_slots=current['worker_slots'])
    v.report.update(success=True, stage='complete')


v.BASE = v.ROOT / 'Saved/MPR/cad_workers_20261109/native'
v.DEADLINE_SECONDS = 180
v.verify_state = check.verify_state
v.run = run
if __name__ == '__main__':
    v.main()
