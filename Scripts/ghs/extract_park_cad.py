"""Read the supplied CADmapper DXF and register it to the existing warehouse.

No source DXF or license file is modified. Run extraction with Blender's
Python 3.13 and rendering with the bundled Codex Python (Pillow available):
  python -B Scripts/ghs/extract_park_cad.py --extract-only
  python -B Scripts/ghs/extract_park_cad.py --render-only
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'CADGis/cadmapper-muscoy-california-us/cadmapper-muscoy-california-us/cadmapper-muscoy-california-us.dxf'
OUTPUT = ROOT / 'SourceAssets/GHS/Park/cad_layout.json'
REPORT = ROOT / 'Saved/ParkRefinement/CAD'
ROAD_LAYERS = {'highways', 'major_roads', 'minor_roads'}
TARGET_WAREHOUSE = [(0, 0), (465.7344, 0), (465.7344, 111.98368),
                    (440.88196, 118.872), (45.8724, 118.872),
                    (45.8724, 137.16), (0, 137.16)]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(point, matrix):
    x, y = point[:2]
    return [matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
            matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]]


def bbox_points(points):
    points = list(points)
    return [[min(p[i] for p in points) for i in range(len(points[0]))],
            [max(p[i] for p in points) for i in range(len(points[0]))]] if points else None


def polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Polygon':
        return [geometry]
    return [p for part in getattr(geometry, 'geoms', []) for p in polygons(part)]


def polygon_records(geometry, matrix=None):
    def ring(coordinates):
        return [transform(p, matrix) if matrix else list(p[:2]) for p in coordinates]
    return [dict(exterior=ring(p.exterior.coords),
                 holes=[ring(h.coords) for h in p.interiors])
            for p in sorted(polygons(geometry), key=lambda p: p.area, reverse=True)]


def registration_for(warehouse):
    ring = warehouse['footprints_raw'][0]['exterior'][:-1]
    a, b = max(zip(ring, ring[1:] + ring[:1]), key=lambda edge: math.dist(*edge))
    back_sw, back_ne = (a, b) if a[0] < b[0] else (b, a)
    index = ring.index(back_sw)
    neighbors = [ring[index - 1], ring[(index + 1) % len(ring)]]
    front_sw = next(p for p in neighbors if p != back_ne)
    ux, uy = back_ne[0] - back_sw[0], back_ne[1] - back_sw[1]
    vx, vy = front_sw[0] - back_sw[0], front_sw[1] - back_sw[1]
    determinant = ux * vy - vx * uy
    width, depth = 465.7344, 137.16
    matrix = [[width * vy / determinant, -width * vx / determinant, 0],
              [-depth * uy / determinant, depth * ux / determinant, 0]]
    for row in matrix:
        row[2] = -row[0] * back_sw[0] - row[1] * back_sw[1]
    length = math.hypot(ux, uy)
    rigid = [[ux / length, uy / length, 0], [uy / length, -ux / length, 0]]
    for row in rigid:
        row[2] = -row[0] * back_sw[0] - row[1] * back_sw[1]
    inverse = [[ux / width, vx / depth, back_sw[0]],
               [uy / width, vy / depth, back_sw[1]]]
    anchors = [dict(name='backSW', raw=back_sw, uv_m=[0, 0]),
               dict(name='backNE', raw=back_ne, uv_m=[width, 0]),
               dict(name='frontSW', raw=front_sw, uv_m=[0, depth])]
    return dict(method='three_anchor_affine', warehouse_handle=warehouse['handle'],
                matrix_2x3=matrix, inverse_matrix_2x3=inverse,
                rigid_metre_preserving_matrix_2x3=rigid,
                anchors=anchors, u_axis_raw_degrees=math.degrees(math.atan2(uy, ux)),
                handedness='u follows northeast warehouse rear edge; v points southeast toward docks',
                determinant=matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0],
                raw_back_edge_length=length, raw_west_edge_length=math.hypot(vx, vy),
                back_edge_scale=width / length, west_edge_scale=depth / math.hypot(vx, vy),
                target_warehouse_uv_m=TARGET_WAREHOUSE,
                note='Fits three selected outer corners exactly. OSM outline is approximate; residual differences at remaining corners are reported, not corrected locally.')


def extract(source=SOURCE, output=OUTPUT):
    sys.path.insert(0, str(ROOT / 'Scripts/_vendor/cad'))
    sys.path.insert(0, str(ROOT / 'Saved/ParkRefinement/python_deps'))
    import ezdxf
    from ezdxf import bbox
    import shapely
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    source = Path(source)
    source_hash = sha256(source)
    doc = ezdxf.readfile(source)
    modelspace = doc.modelspace()
    bounds = bbox.extents(modelspace, fast=True)
    layers, layer_points = defaultdict(Counter), defaultdict(list)
    buildings, linework, other_meshes, warnings = [], [], [], []
    for entity in modelspace:
        kind, layer, handle = entity.dxftype(), entity.dxf.layer, entity.dxf.handle
        layers[layer][kind] += 1
        if kind == 'MESH':
            vertices = [list(v) for v in entity.vertices]
            faces = [list(f) for f in entity.faces]
            layer_points[layer].extend(vertices)
            if layer != 'buildings':
                other_meshes.append(dict(handle=handle, layer=layer, vertex_count=len(vertices),
                                         face_count=len(faces), bbox_raw=bbox_points(vertices)))
                continue
            projected_faces = []
            for face in faces:
                if len(face) < 3:
                    continue
                polygon = Polygon([(vertices[i][0], vertices[i][1]) for i in face])
                if not polygon.is_valid:
                    polygon = shapely.make_valid(polygon)
                projected_faces.extend(p for p in polygons(polygon) if p.area > 1e-8)
            footprint = unary_union(projected_faces)
            if footprint.is_empty:
                warnings.append('building %s has no projectable horizontal face' % handle)
                continue
            rectangle = list(footprint.minimum_rotated_rectangle.exterior.coords)
            lengths = [math.dist(a, b) for a, b in zip(rectangle, rectangle[1:])]
            zmin, zmax = min(v[2] for v in vertices), max(v[2] for v in vertices)
            buildings.append(dict(id='CAD_' + handle, handle=handle, layer=layer,
                                  footprints_raw=polygon_records(footprint),
                                  mesh_vertices_xyz_raw=vertices, mesh_faces=faces,
                                  area_raw=footprint.area, bbox_raw=list(footprint.bounds),
                                  centroid_raw=list(footprint.centroid.coords)[0],
                                  oriented_size_raw=[max(lengths), min(lengths)],
                                  base_elevation_raw=zmin, top_elevation_raw=zmax,
                                  height_m=zmax - zmin,
                                  height_status='source_extrusion_unverified',
                                  height_note='CADmapper extrusion is retained as a source hint; it is not a surveyed building height.'))
        elif kind in ('POLYLINE', 'LWPOLYLINE'):
            points = [list(p) for p in (entity.points() if kind == 'POLYLINE' else entity.vertices_in_wcs())]
            closed = bool(entity.is_closed if kind == 'POLYLINE' else entity.closed)
            if points and math.dist(points[0], points[-1]) < 1e-7:
                closed = True
            layer_points[layer].extend(points)
            record = dict(id='CAD_' + handle, handle=handle, layer=layer, entity_type=kind,
                          points_xyz_raw=points, closed=closed)
            if kind == 'LWPOLYLINE':
                record['bulges_raw'] = [float(p[4]) for p in entity.get_points('xyseb')]
                if any(record['bulges_raw']):
                    warnings.append('LWPOLYLINE %s contains bulges retained as raw values' % handle)
            linework.append(record)
        else:
            warnings.append('unexported entity %s type %s' % (handle, kind))
    buildings.sort(key=lambda record: record['area_raw'], reverse=True)
    warehouse = buildings[0]
    registration = registration_for(warehouse)
    matrix = registration['matrix_2x3']
    scale_area = abs(registration['determinant'])
    for record in linework:
        record['points_uv_m'] = [transform(p, matrix) for p in record['points_xyz_raw']]
        record['length_m'] = sum(math.dist(a, b) for a, b in zip(record['points_uv_m'], record['points_uv_m'][1:]))
        record['elevation_range_raw'] = [min(p[2] for p in record['points_xyz_raw']), max(p[2] for p in record['points_xyz_raw'])]
        record['width_status'] = 'not_encoded_in_source_centerline'
    for record in buildings:
        record['footprints_uv_m'] = [dict(exterior=[transform(p, matrix) for p in polygon['exterior']],
                                        holes=[[transform(p, matrix) for p in hole] for hole in polygon['holes']])
                                     for polygon in record['footprints_raw']]
        record['footprint_uv_m'] = record['footprints_uv_m'][0]['exterior']
        record['centroid_uv_m'] = transform(record['centroid_raw'], matrix)
        record['bbox_uv_m'] = bbox_points(p for polygon in record['footprints_uv_m'] for p in polygon['exterior'])
        record['area_m2'] = record['area_raw'] * scale_area
        projected = Polygon(record['footprint_uv_m'])
        rectangle = list(projected.minimum_rotated_rectangle.exterior.coords)
        lengths = [math.dist(a, b) for a, b in zip(rectangle, rectangle[1:])]
        record['oriented_size_m'] = [max(lengths), min(lengths)]
    aligned_vertices = warehouse['footprint_uv_m'][:-1]
    residuals = []
    for target in TARGET_WAREHOUSE:
        actual = min(aligned_vertices, key=lambda p: math.dist(p, target))
        residuals.append(dict(target_uv_m=target, cad_uv_m=actual, distance_m=math.dist(actual, target)))
    registration['remaining_outline_vertex_residuals'] = residuals
    registration['outline_vertex_residual_max_m'] = max(r['distance_m'] for r in residuals)
    registration['outline_vertex_residual_rms_m'] = math.sqrt(sum(r['distance_m'] ** 2 for r in residuals) / len(residuals))
    license_path = source.parent / 'LICENSE.txt'
    license_text = license_path.read_text(encoding='utf8') if license_path.exists() else None
    roads = [record for record in linework if record['layer'] in ROAD_LAYERS]
    all_uv = [p for road in linework for p in road['points_uv_m']]
    all_uv.extend(p for building in buildings for p in building['footprint_uv_m'])
    result = dict(schema_version=1,
                  created_utc=datetime.now(timezone.utc).isoformat(),
                  source=dict(path=str(source), sha256=source_hash, size_bytes=source.stat().st_size,
                              dxf_version=doc.dxfversion, header_units_code=doc.units,
                              header_units_name='millimetres', interpreted_coordinate_units='metres',
                              raw_coordinate_to_metre_scale=1.0,
                              unit_warning='INSUNITS=4 says millimetres, but the matched warehouse measures 465.14 x 137.66 raw units and typical dwellings 10-21 units. Raw coordinates are therefore interpreted as metres; no 0.001 conversion is applied.',
                              header_extmin=list(doc.header.get('$EXTMIN')),
                              header_extmax=list(doc.header.get('$EXTMAX')),
                              header_extent_status='invalid sentinel values; calculated extents used',
                              source_modified=False),
                  attribution=dict(provider='CADmapper', license_path=str(license_path),
                                   license_text=license_text,
                                   map_data='Map data (c) OpenStreetMap contributors.',
                                   map_license_url='http://www.openstreetmap.org/copyright',
                                   elevation_sources=['USGS National Elevation Dataset (public domain)',
                                                      'NASA Shuttle Radar Topography Mission (public domain)'],
                                   distribution_requirement='The downloaded file must be distributed with the accompanying LICENSE.txt. Full source license text is preserved here.'),
                  statistics=dict(entity_count=len(modelspace),
                                  entity_types=dict(Counter(e.dxftype() for e in modelspace)),
                                  layers={layer:dict(entity_types=dict(counts),
                                                     bbox_raw=bbox_points(layer_points[layer]))
                                          for layer, counts in sorted(layers.items())},
                                  bbox_xyz_raw=[list(bounds.extmin), list(bounds.extmax)],
                                  bbox_uv_m=bbox_points(all_uv),
                                  road_count=len(roads), linework_count=len(linework),
                                  building_count=len(buildings)),
                  warehouse_handle=warehouse['handle'], registration=registration,
                  warehouse_candidates=[{key:record[key] for key in
                                         ('handle', 'area_raw', 'oriented_size_raw', 'bbox_raw', 'centroid_raw')}
                                        for record in buildings[:10]],
                  roads=roads, linework=linework, buildings=buildings,
                  other_meshes=other_meshes,
                  warnings=warnings + ['All building heights are source extrusion hints, not verified measurements.',
                                       'Road centreline classes are authoritative to this source; carriageway widths are not encoded.'])
    if sha256(source) != source_hash:
        raise RuntimeError('source DXF changed during read-only extraction')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / 'source_LICENSE.txt').write_text(license_text or 'No adjacent license file found.', encoding='utf8')
    summary = {key:result[key] for key in ('source', 'attribution', 'statistics', 'registration', 'warehouse_candidates', 'warnings')}
    (REPORT / 'cad_analysis.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(output=str(output), roads=len(roads), buildings=len(buildings),
                         warehouse_handle=warehouse['handle'],
                         affine_matrix=matrix,
                         residual_max_m=registration['outline_vertex_residual_max_m'],
                         unchanged_source_sha256=source_hash), indent=2))
    return result


def render(data, report=REPORT):
    from PIL import Image, ImageDraw, ImageFont
    report.mkdir(parents=True, exist_ok=True)
    font_path = 'C:/Windows/Fonts/arial.ttf'
    font = ImageFont.truetype(font_path, 20)
    small = ImageFont.truetype(font_path, 16)
    title_font = ImageFont.truetype(font_path, 30)
    colors = {'highways':'#de804a', 'major_roads':'#435f91', 'minor_roads':'#6d90ab',
              'paths':'#a9b5be', 'parks':'#83a490', 'railways':'#8e7199', 'water':'#65a6bd',
              'contours':'#ded9cb'}
    def drawing(bounds, title, subtitle, filename, uv):
        width, height = 2400, 1650
        margin, top, bottom = 70, 145, 100
        xmin, ymin, xmax, ymax = bounds
        scale = min((width - 2 * margin) / (xmax - xmin), (height - top - bottom) / (ymax - ymin))
        xoff = (width - (xmax - xmin) * scale) * .5
        yoff = top + ((height - top - bottom) - (ymax - ymin) * scale) * .5
        def point(p):
            return xoff + (p[0] - xmin) * scale, yoff + (ymax - p[1]) * scale
        image = Image.new('RGB', (width, height), '#f3f2ed')
        draw = ImageDraw.Draw(image)
        draw.text((50, 28), title, font=title_font, fill='#233546')
        draw.text((50, 76), subtitle, font=font, fill='#566472')
        for record in data['linework']:
            if record['layer'] not in ('contours', 'parks', 'water'):
                continue
            points = record['points_uv_m'] if uv else record['points_xyz_raw']
            draw.line([point(p) for p in points], fill=colors.get(record['layer'], '#b5b9ba'), width=1)
        for building in reversed(data['buildings']):
            selected = building['handle'] == data['warehouse_handle']
            polygons_data = building['footprints_uv_m'] if uv else building['footprints_raw']
            for polygon in polygons_data:
                draw.polygon([point(p) for p in polygon['exterior']],
                             fill='#efbd7b' if selected else '#bbc4cc',
                             outline='#b66527' if selected else '#7e8b95', width=3 if selected else 1)
                for hole in polygon['holes']:
                    draw.polygon([point(p) for p in hole], fill='#f3f2ed')
        for record in data['linework']:
            if record['layer'] in ('contours', 'parks', 'water'):
                continue
            points = record['points_uv_m'] if uv else record['points_xyz_raw']
            draw.line([point(p) for p in points], fill=colors.get(record['layer'], '#abb4be'),
                      width={'highways':6, 'major_roads':4, 'minor_roads':3}.get(record['layer'], 1))
        if uv:
            target = TARGET_WAREHOUSE + [TARGET_WAREHOUSE[0]]
            draw.line([point(p) for p in target], fill='#007f9a', width=4)
        for anchor in data['registration']['anchors']:
            p = point(anchor['uv_m'] if uv else anchor['raw'])
            draw.ellipse((p[0]-6, p[1]-6, p[0]+6, p[1]+6), fill='#a22e32')
            draw.text((p[0]+10, p[1]-26), anchor['name'], font=font, fill='#86252a')
        # The detail crop contains geometry outside its bounds. Clear the
        # annotation bands after drawing so it cannot paint over the report.
        draw.rectangle((0, 0, width, top - 20), fill='#f3f2ed')
        draw.rectangle((0, height - 100, width, height), fill='#f3f2ed')
        draw.text((50, 28), title, font=title_font, fill='#233546')
        draw.text((50, 76), subtitle, font=font, fill='#566472')
        legend = [('highways', 'Highways'), ('major_roads', 'Major roads'), ('minor_roads', 'Minor roads'),
                  ('paths', 'Paths'), ('railways', 'Railways')]
        x = 60
        for key, label in legend:
            draw.line((x, height-70, x+35, height-70), fill=colors[key], width=5)
            draw.text((x+45, height-83), label, font=font, fill='#374754')
            x += 270
        draw.text((60, height-35), 'Map data (c) OpenStreetMap contributors | CADmapper | Source coordinates interpreted as metres', font=small, fill='#62717c')
        image.save(report / filename)
    raw = data['statistics']['bbox_xyz_raw']
    drawing((raw[0][0]-20, raw[0][1]-20, raw[1][0]+20, raw[1][1]+20),
            'CADmapper source geometry - raw CAD XY',
            '419 building footprints | 79 vehicle-road centrelines | warehouse handle 1eb6 highlighted',
            'CAD_raw_context.png', False)
    uv_bounds = data['statistics']['bbox_uv_m']
    drawing((uv_bounds[0][0]-20, uv_bounds[0][1]-20, uv_bounds[1][0]+20, uv_bounds[1][1]+20),
            'Registered CAD geometry - existing warehouse UV',
            'Three-anchor affine registration | orange: source warehouse | cyan: existing warehouse footprint',
            'CAD_registered_uv.png', True)
    drawing((-65, -75, 555, 240), 'Warehouse alignment and surrounding roads',
            'Exact backSW / backNE / frontSW anchors; remaining outline differences are reported in cad_analysis.json',
            'CAD_warehouse_alignment.png', True)
    print(json.dumps({'renders':[str(report / name) for name in
                                ('CAD_raw_context.png', 'CAD_registered_uv.png', 'CAD_warehouse_alignment.png')]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--extract-only', action='store_true')
    parser.add_argument('--render-only', action='store_true')
    args = parser.parse_args()
    if args.extract_only and args.render_only:
        parser.error('choose either --extract-only or --render-only')
    data = json.loads(args.output.read_text(encoding='utf8')) if args.render_only else extract(args.source, args.output)
    if not args.extract_only:
        render(data)


if __name__ == '__main__':
    main()
