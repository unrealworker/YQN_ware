"""Plan local campus colour hierarchy without touching UE or existing sources.

Coordinates are CAD metres (+Y).  This writes only the hierarchy landscape
source directory. Existing tree locations and HISM order are recorded verbatim.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Saved/ParkRefinement/python_deps'))
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union
from mpr_site_completion_geometry import Ground, from_polygons, polygons

OUTPUT = 'SourceAssets/MPR/hierarchy_20261105/landscape/selection.json'
TREE = '/Game/MPRWarehouse/SiteComplete/Meshes/SM_MPRSC_Tree_Canopy'
IDENTITY = dict(translation_cm=[0., 0., 0.], rotation_xyzw=[0., 0., 0., 1.], scale=[1., 1., 1.])


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(root=ROOT, scene='Saved/MPR/transport_cleanup_20261105/before_scene.json'):
    root = Path(root)
    paths = dict(manifest='SourceAssets/MPR/rebuild_b50b57/manifest.json',
                 site='SourceAssets/MPR/site_completion_20261105/site_plan.json',
                 layout='SourceAssets/MPR/rebuild_b50b57/transport_revision_20261105/layout.json',
                 tree_audit='SourceAssets/MPR/site_completion_20261105/tree/geometry_audit.json')
    sources = {path: digest(root / path) for path in paths.values()}
    values = {key: json.loads((root / path).read_text(encoding='utf-8')) for key, path in paths.items()}
    manifest, site, layout = (values[k] for k in ('manifest', 'site', 'layout'))
    snapshot = json.loads((root / scene).read_text(encoding='utf-8'))
    original = manifest['instances']['SM_MPR4_Tree_Oak']
    moves = {r['source_id']: r['to_position_m'] for r in site['tree_relocations']}
    trees = [dict(r, position_m=moves.get(r['source_id'], r['position_m'])) for r in original]
    campus = unary_union([from_polygons(s['polygons']) for s in site['surfaces']]).convex_hull
    selection = campus.buffer(15)
    by_source = {r['source_id']: r for r in trees}
    seen, groups, chosen = set(), [], []
    for actor in snapshot['actors']:
        for component in actor['components']:
            if str(component.get('mesh', '')).split('.')[0] != TREE:
                continue
            assert actor['transform'] == IDENTITY and component['transform'] == IDENTITY
            assert component['num_custom_data_floats'] == 0 and component['custom_data'] == []
            rows = []
            indices = []
            for i, transform in enumerate(component['instance_transforms']):
                xyz = transform['translation_cm']
                point = [xyz[0]/100, -xyz[1]/100, xyz[2]/100]
                hits = [r for r in trees if max(abs(a-b) for a, b in zip(point, r['position_m'])) < .05]
                assert len(hits) == 1, (actor['name'], i, point, len(hits))
                row = hits[0]
                assert row['source_id'] not in seen
                seen.add(row['source_id'])
                rows.append(row['source_id'])
                if selection.covers(Point(point[:2])):
                    indices.append(i)
                    chosen.append(dict(source_id=row['source_id'], position_m=row['position_m'],
                                       provenance=row['provenance']))
            groups.append(dict(actor_name=actor['name'], actor_guid=actor['guid'], label=actor['label'],
                               actor_transform=actor['transform'], component_transform=component['transform'],
                               component_name=component['name'], mesh=component['mesh'],
                               materials=component['materials'], instance_count=component['instance_count'],
                               instance_transforms=component['instance_transforms'], source_ids=rows,
                               selected_indices=indices))
    assert len(groups) == 63 and len(seen) == len(trees) == 1282
    assert seen == set(by_source)
    assert len(chosen) == 111
    green = [a for a in snapshot['actors'] if a['label'] == 'MPRSC_MPRR_CampusGreen']
    assert len(green) == 1
    green_actor = green[0]
    green_components = [c for c in green_actor['components'] if c.get('mesh')]
    assert len(green_components) == 1
    green_component = green_components[0]

    blocked = unary_union([shape(layout[k]).buffer(.35) for k in
                           ('roads', 'rail_corridor', 'water', 'building_protection')]
                          + [from_polygons(s['polygons']) for s in site['surfaces']
                             if s['role'] != 'MPRR_CampusGreen'])
    tree_discs = [Point(r['position_m'][:2]).buffer(r['crown_radius_m']+.25) for r in trees]
    ground = Ground(root, manifest, box(-220, -180, 220, 120), sources)
    coordinates = [('West', -205., float(y)) for y in range(-84, 73, 12)]
    coordinates += [('East', 205., float(y)) for y in (-12, 0, 12)]
    coordinates += [('East', 204., float(y)) for y in (48, 60, 72)]
    added = []
    for i, (side, x, y) in enumerate(coordinates):
        disc = Point(x, y).buffer(2.65)
        assert not disc.intersects(blocked), ('Infill touches protected route/paving', side, x, y)
        assert all(not disc.intersects(other) for other in tree_discs), ('Infill touches crown', side, x, y)
        tree_discs.append(disc)
        scale = 2.4 / values['tree_audit']['radial_extent_m']
        added.append(dict(source_id=f'CampusHierarchy_{side}_{i:02}',
                          provenance='hierarchy_perimeter_infill', position_m=[x, y, round(ground.at(x, y)+.01, 6)],
                          rotation_deg=float((i*137) % 360), scale=[scale]*3, crown_radius_m=2.4,
                          safety_crown_radius_m=2.65, blocked_surface_clearance_m=round(disc.distance(blocked), 6)))
    assert len(added) == 20
    return dict(schema_version=1, map=snapshot['map'], coordinate_frame='CAD metres; UE=(x,-y,z)*100',
                source_hashes=sources, scene_evidence=dict(path=scene, sha256=digest(root/scene)),
                palette_srgb=dict(campus_grass='8EAA72', leaf_mid='819965', leaf_light='9AAF82', leaf_shade='687F53'),
                policy=dict(existing_instance_transforms_and_order='preserve verbatim',
                            background_color='preserve original shader at mask=0',
                            selection='current campus surface convex hull, buffered 15 metres; centres inside',
                            infill='existing green roadside gaps; never move old trees',
                            new_crown_radius_m=2.4, crown_margin_m=.25, transport_building_buffer_m=.35),
                selection_region=polygons(selection),
                counts=dict(existing=1282, existing_selected=111, existing_background=1171, new=20, final=1302,
                            original_groups=63, changed_groups=sum(bool(g['selected_indices']) for g in groups),
                            selected_by_provenance=dict(Counter(r['provenance'] for r in chosen))),
                groups=groups, selected_sources=sorted(chosen, key=lambda r:r['source_id']), infill=added,
                campus_green=dict(actor_name=green_actor['name'], actor_guid=green_actor['guid'],
                                  label=green_actor['label'], component_name=green_component['name'],
                                  actor_transform=green_actor['transform'], component_transform=green_component['transform'],
                                  mesh=green_component['mesh'], materials=green_component['materials']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', default='Saved/MPR/transport_cleanup_20261105/before_scene.json')
    parser.add_argument('--output', default=OUTPUT)
    args = parser.parse_args()
    destination = (ROOT / args.output).resolve()
    allowed = (ROOT/'SourceAssets/MPR/hierarchy_20261105/landscape').resolve()
    assert destination.is_relative_to(allowed)
    result = build(scene=args.scene)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(output=str(destination), **result['counts']), ensure_ascii=False))
