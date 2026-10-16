"""Fresh-UE saved scene validation using actual instance transforms/mesh bounds.

Does not save assets or levels. Keeps the pre-clearance verification report.
"""
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
import traceback

import unreal

ROOT = Path(r'D:\UEPro\Test')
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
import audit_intersections as geometry
import verify_ue_scene as common

REPORT_PATH = ROOT / 'Saved/GHS_ClearanceVerification.json'
SOURCE_SHA = 'd3a69810c3eb35e55bf518a2503a0a988cd8e82957703250b6b480a403cc2e30'
EXPECTED_COUNTS = {
    'GHS_CAD_Columns': 170, 'GHS_ColumnBases': 170,
    'GHS_CAD_PalletCargo': 7408, 'GHS_CAD_Racks': 1617,
    'GHS_CAD_DockRacks': 87, 'GHS_ColumnOccupiedStorageOutlines': 488,
}
LAYOUT_KEYS = {'GHS_CAD_Columns': 'columns', 'GHS_CAD_PalletCargo': 'storage',
               'GHS_CAD_Racks': 'racks', 'GHS_CAD_DockRacks': 'equipment'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def actual_box(transform, bounds):
    """Rotate actual local bounds origin and scale extents, then mirror to CAD."""
    rotation = transform.rotation.rotator()
    assert abs(rotation.pitch) < .02 and abs(rotation.roll) < .02
    sx, sy, sz = common.xyz(transform.scale3d)
    assert min(sx, sy, sz) > 0
    theta = math.radians(float(rotation.yaw))
    co, si = math.cos(theta), math.sin(theta)
    ox, oy, oz = bounds.origin.x*sx, bounds.origin.y*sy, bounds.origin.z*sz
    x = (transform.translation.x+co*ox-si*oy)/100
    y = -(transform.translation.y+si*ox+co*oy)/100
    z = (transform.translation.z+oz)/100
    hz = bounds.box_extent.z*sz/100
    return geometry.Box(x, y, bounds.box_extent.x*sx/100,
                        bounds.box_extent.y*sy/100, co, -si, z-hz, z+hz)


def lineage_checks(layout, registry, cad):
    ids = lambda rows: {row['id'] for row in rows}
    for key in ['columns', 'storage', 'racks', 'equipment', 'blocked_storage', 'excluded_candidates']:
        assert len(ids(layout[key])) == len(layout[key]), key + ' duplicate IDs'
    active, blocked = ids(layout['storage']), ids(layout['blocked_storage'])
    assert len(active) == 7408 and len(blocked) == 122 and not active & blocked
    assert active | blocked == ids(cad['storage']), 'Original 7530 storage locations lost'
    columns, excluded = ids(layout['columns']), ids(layout['excluded_candidates'])
    assert len(columns) == 170 and len(excluded) == 36 and not columns & excluded
    assert columns | excluded == ids(cad['columns']), 'Original column candidates lost'
    assert all(row['block'] == 'PILLAR' and row.get('exclusion_reason')
               for row in layout['excluded_candidates'])
    assert registry['blocked_storage'] == layout['blocked_storage']
    assert registry['excluded_column_candidates'] == layout['excluded_candidates']
    assert all(row.get('reason') and row.get('blocking_column_ids')
               for row in layout['blocked_storage'])
    rack_parents = {row.get('parent_cad_id', row['id'])
                    for row in layout['racks'] + layout['removed_rack_segments']}
    assert rack_parents == ids(cad['racks']), 'Rack parent CAD IDs lost'
    assert ids(layout['equipment']) == ids(cad['equipment'])
    return dict(original_storage_locations=7530, active_cargo=7408,
                blocked_storage=122, all_original_storage_ids_accounted_for=True,
                original_column_candidates=206, active_columns=170,
                excluded_pillar_candidates=36, all_original_column_ids_accounted_for=True,
                original_rack_parent_count=len(rack_parents), active_rack_segments=1617,
                removed_short_segments=len(layout['removed_rack_segments']),
                all_original_rack_parent_ids_accounted_for=True,
                blocked_storage_ids=sorted(blocked), excluded_column_ids=sorted(excluded))


def check_intersections(objects):
    grid, seen = defaultdict(list), set()
    size = 4.0
    for index, obj in enumerate(objects):
        x0, y0, x1, y1 = obj['box'].aabb
        for x in range(math.floor(x0/size), math.floor(x1/size)+1):
            for y in range(math.floor(y0/size), math.floor(y1/size)+1):
                grid[x, y].append(index)
    stats, overlaps = {}, []
    kinds = sorted(set(geometry.GROUPS.values()))
    storage = {'cargo', 'rack', 'dock_rack'}
    for offset, a in enumerate(kinds):
        for b in kinds[offset:]:
            if {a, b} & storage:
                stats[a+'_vs_'+b] = dict(candidate_pairs=0, overlaps=0)
    for candidates in grid.values():
        for offset, i in enumerate(candidates):
            for j in candidates[offset+1:]:
                pair = min(i, j), max(i, j)
                if pair in seen:
                    continue
                seen.add(pair)
                a, b = objects[pair[0]], objects[pair[1]]
                if not ({a['kind'], b['kind']} & storage):
                    continue
                category = '_vs_'.join(sorted([a['kind'], b['kind']]))
                stats[category]['candidate_pairs'] += 1
                overlap = geometry.sat(a['box'], b['box'])
                if overlap:
                    stats[category]['overlaps'] += 1
                    overlaps.append(dict(category=category, a=a['id'], b=b['id'],
                                         a_group=a['actor'], b_group=b['actor'],
                                         xy_penetration_m=overlap[0], z_overlap_m=overlap[1]))
    return dict(method='Saved HISM world transform + actual StaticMesh bounds -> CAD-frame OBB SAT',
                tolerance_m=geometry.EPS, object_count=len(objects),
                summary=stats, overlap_count=len(overlaps), overlaps=overlaps,
                mesh_bounds_are_conservative=True)


def main(report):
    registry_path = ROOT/'SourceAssets/GHS/ue_scene_registry.json'
    level_path = ROOT/'Content/Maps/GHS_CAD_DigitalTwin.umap'
    original = ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap'
    historical = ROOT/'Saved/GHS_Verification.json'
    before = dict(map=sha(level_path), registry=sha(registry_path), historical=sha(historical))
    assert sha(original) == SOURCE_SHA
    layout = common.read_json(ROOT/'SourceAssets/GHS/clearance_layout.json')
    cad = common.read_json(ROOT/'SourceAssets/GHS/cad_layout.json')
    registry = common.read_json(registry_path)
    build = common.read_json(ROOT/'Saved/GHS_BuildReport.json')
    applied = common.read_json(ROOT/'Saved/GHS_ClearanceApplied.json')
    assert build['clearance_corrected'] and applied['success']
    assert applied['source_level_sha256'] == SOURCE_SHA
    report['lineage'] = lineage_checks(layout, registry, cad)

    # Retain all previous material, transform, FX, camera, floor and LOD checks,
    # replacing only original display counts with the corrected layout counts.
    common.report = report
    common.main(clearance_layout=layout)
    report['success'] = False  # Collision checks below are still pending.
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    by_label = {actor.get_actor_label(): actor for actor in actors}
    outlines_added = bool(build.get('column_outlines_added'))
    assert len(actors) == (225 if build.get('lighting_optimized') else (248 if outlines_added else 247))
    assert len(registry['groups']) == (16 if outlines_added else 15)
    expected_instances = 12076 if build.get('wall_joined_corrected') else 14383
    if outlines_added:
        expected_instances += 2040
    assert sum(g['count'] for g in registry['groups']) == expected_instances
    components = {g['actor']: by_label[g['actor']].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
                  for g in registry['groups']}
    groups = {g['actor']: g for g in registry['groups']}
    for label, count in EXPECTED_COUNTS.items():
        assert components[label].get_instance_count() == groups[label]['count'] == count, label
    wall_material = components['GHS_CAD_WallFaces'].get_material(0)
    column_material = components['GHS_CAD_Columns'].get_material(0)
    assert wall_material == column_material
    assert column_material.get_path_name() == '/Game/GHSDigitalTwin/Materials/Instanced/M_GHS_WallVolume.M_GHS_WallVolume'
    report['column_wall_material_identical'] = True
    report['column_material'] = column_material.get_path_name()
    blocked = {row['id'] for row in layout['blocked_storage']}
    outline_counts = Counter(row['parent_cad_id'] for row in groups['GHS_ColumnOccupiedStorageOutlines']['instances'])
    assert set(outline_counts) == blocked and set(outline_counts.values()) == {4}
    assert all(row.get('status') == 'ColumnClearanceNoCargo'
               for row in groups['GHS_ColumnOccupiedStorageOutlines']['instances'])
    report['blocked_storage_boundary_instances'] = sum(outline_counts.values())

    objects, actual_bounds, maximum_error = [], {}, 0.0
    for label, kind in geometry.GROUPS.items():
        component = components[label]
        mesh = component.get_editor_property('static_mesh')
        bounds = mesh.get_bounds()
        actual_bounds[mesh.get_path_name()] = dict(origin_cm=common.xyz(bounds.origin),
                                                  extent_cm=common.xyz(bounds.box_extent))
        expected_rows = {row['id']: row for row in layout[LAYOUT_KEYS[label]]} if label in LAYOUT_KEYS else {}
        for index, row in enumerate(groups[label]['instances']):
            transform = component.get_instance_transform(index, world_space=True)
            box = actual_box(transform, bounds)
            objects.append(dict(actor=label, kind=kind, id=row['id'], box=box))
            if label in LAYOUT_KEYS:
                expected = expected_rows[row['id']]
                size = list(expected['size_m'])
                yaw = expected['rotation_deg']
                if kind == 'rack':
                    size = size[::-1]
                    yaw += 90
                err = common.compare([box.x, box.y, box.hx*2, box.hy*2],
                                     list(expected['position_m']) + size, .001,
                                     label + '[' + str(index) + '] actual mesh footprint')
                maximum_error = max(maximum_error, err)
                actual_yaw = math.degrees(math.atan2(box.si, box.co))
                assert abs((actual_yaw-yaw+180)%360-180) < .02
    report['actual_mesh_bounds'] = actual_bounds
    report['actual_mesh_footprint_max_error_m'] = maximum_error
    report['intersections'] = check_intersections(objects)
    assert report['intersections']['overlap_count'] == 0, 'Saved mesh OBB overlaps: ' + str(report['intersections']['overlaps'][:10])
    assert sha(original) == SOURCE_SHA
    assert sha(level_path) == before['map'], 'Verification modified the saved map'
    assert sha(registry_path) == before['registry'], 'Registry changed during verification'
    assert sha(historical) == before['historical'], 'Historical verification report changed'
    report.update(success=True, saved_map_sha256=before['map'], registry_sha256=before['registry'],
                  historical_report_preserved=True, historical_report_sha256=before['historical'],
                  source_level_sha256=SOURCE_SHA, production_assets_saved=False,
                  all_actual_mesh_footprints_match_clearance_layout=True,
                  clearance_actual_obb_overlap_count=0)


def run():
    if common.read_json(ROOT/'Saved/GHS_BuildReport.json').get('column_outlines_added'):
        import verify_column_outlines
        return verify_column_outlines.run()
    if common.read_json(ROOT/'Saved/GHS_BuildReport.json').get('wall_joined_corrected'):
        import verify_joined_walls
        return verify_joined_walls.run()
    report = dict(success=False, map=common.MAP, created_utc=datetime.now(timezone.utc).isoformat(),
                  verification_mode='Fresh UE process; saved mesh bounds/world transforms; no saves',
                  groups=[], individuals=[], effects=[], meshes=[])
    try:
        main(report)
    except Exception:
        report['success'] = False
        report['error'] = traceback.format_exc()
        raise
    finally:
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding='utf-8')
    unreal.log('GHS_CLEARANCE_VERIFIED ' + json.dumps({key:report[key] for key in
               ['success', 'actor_count', 'instanced_count', 'rack_count', 'pallet_count',
                'column_count', 'clearance_actual_obb_overlap_count']}))


if __name__ == '__main__':
    run()
