"""Verify the delivered CAD layout against DXF polygon vertices and report column contacts."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from extract_cad24_layout import DEFAULT_OUTPUT, DEFAULT_SOURCE, INCH, ROOT, TARGETS, ezdxf
from shapely import MultiPoint, Polygon, STRtree
from shapely.affinity import translate


def physical_parts(doc, insert):
    matrix = insert.matrix44()
    return [
        Polygon([tuple(matrix.transform(p))[:2] for p in entity.vertices_in_wcs()])
        for entity in doc.blocks[insert.dxf.name].query('LWPOLYLINE')
    ]


def verify(source, layout_path):
    doc = ezdxf.readfile(source)
    layout = json.loads(layout_path.read_text(encoding='utf8'))
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    if layout['sha256'] != sha:
        raise ValueError('Input DXF differs from the generated layout')
    insert_by_handle = {e.dxf.handle: e for e in doc.modelspace().query('INSERT') if e.dxf.name in TARGETS}
    delivered = layout['racks'] + layout['ground']
    source_ids = [row['id'].removeprefix('CAD_24_') for row in delivered + layout['coincident_duplicates']]
    if len(set(source_ids)) != len(source_ids) or set(insert_by_handle) != set(source_ids):
        raise ValueError('Layout inventory differs from the reference plan')

    origin = layout['registration']['origin_dxf_inches']
    pillars = list(doc.modelspace().query('INSERT[name=="PILLAR"]'))
    pillar_shapes = [physical_parts(doc, pillar)[0] for pillar in pillars]
    pillar_tree = STRtree(pillar_shapes)
    contacts = []
    max_center_error = 0
    for row in delivered:
        insert = insert_by_handle[row['id'].removeprefix('CAD_24_')]
        parts = physical_parts(doc, insert)
        if 'variant' not in row:
            # Floor INSERTs also draw a five-inch clearance stripe on each side.
            # The physical pallet rectangle agrees with its WIDTH_IN/DEPTH_IN.
            nominal_area = float(row['attrs']['WIDTH_IN']) * float(row['attrs']['DEPTH_IN'])
            parts = [p for p in parts if abs(p.area - nominal_area) < .001]
        footprint = MultiPoint([p for poly in parts for p in poly.exterior.coords]).convex_hull
        plan_center = [(coord - origin[i]) * INCH for i, coord in enumerate(footprint.centroid.coords[0])]
        max_center_error = max(max_center_error, math.dist(plan_center, row['position_m']))
        local = translate(footprint, -origin[0], -origin[1])
        boundary = list(local.minimum_rotated_rectangle.exterior.coords)
        lengths = sorted(math.dist(boundary[i], boundary[i + 1]) * INCH for i in (0, 1))
        expected = sorted([row['physical_span_m'], row['physical_depth_m']])
        if max(abs(x-y) for x, y in zip(lengths, expected)) > .00001:
            raise ValueError(f'Dimensions disagree at {row["id"]}')
        if 'variant' not in row:
            continue
        for index in pillar_tree.query(footprint, predicate='intersects'):
            column = pillar_shapes[index]
            # Sub-millimeter contacts along a shared boundary are DXF roundoff.
            if footprint.intersection(column).area < 1e-5:
                continue
            structural = any(part.intersection(column).area > 1e-5 for part in parts)
            contacts.append({'rack': row['id'], 'row': row['row_code'], 'bay': row['bay_sequence'],
                             'column_handle': pillars[index].dxf.handle, 'frame_or_beam_overlap': structural})
    if max_center_error > .00001:
        raise ValueError(f'Center disagreement: {max_center_error} m')
    controls = []
    for corner in [(-225, 42), (203, 42), (-225, -40), (203, -40)]:
        target = [n / INCH + o for n, o in zip(corner, origin)]
        index = min(range(len(pillars)), key=lambda i: math.dist(pillar_shapes[i].centroid.coords[0], target))
        controls.append({'handle': pillars[index].dxf.handle,
                         'position_m': [round((n-o)*INCH, 6) for n, o in zip(pillar_shapes[index].centroid.coords[0], origin)]})

    return {
        'source_sha256': sha, 'emitted_rack_count': len(layout['racks']),
        'emitted_floor_count': len(layout['ground']), 'coincident_inserts': layout['coincident_duplicates'],
        'source_geometry_count': dict(Counter(e.dxf.name for e in insert_by_handle.values())),
        'max_center_error_m': round(max_center_error, 9),
        'pillar_count': len(pillars), 'registration_controls': controls, 'rack_footprint_pillar_pairs': len(contacts),
        'rack_structural_pillar_pairs': sum(c['frame_or_beam_overlap'] for c in contacts),
        'cad_pillar_contacts': contacts
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dxf', nargs='?', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--layout', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/GHS-CAD24/geometry_verification.json')
    args = parser.parse_args()
    report = verify(args.dxf, args.layout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'cad_pillar_contacts'}, indent=2))
