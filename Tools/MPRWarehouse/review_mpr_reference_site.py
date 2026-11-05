"""Run the site's pure geometry functions without Blender or file mutation.

Requires NumPy and Shapely. Run with Blender's bundled Python and the project's
existing Shapely vendor path. This audit does not execute the builder's export.
"""
import ast
import json
import math
from pathlib import Path
import random
import sys
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'Tools/MPRWarehouse'), str(ROOT/'Saved/ParkRefinement/python_deps'), str(ROOT/'Scripts/ghs')]
import numpy as np
import shapely
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union
from shapely.affinity import rotate, translate
from mpr_site_roads import build_site_roads
from mpr_railway_detail import build_railways
from park_curves import dash_segments, offset_path, sample_along

SOURCE = json.loads((ROOT/'SourceAssets/MPR/environment/environment_local.json').read_text(encoding='utf-8'))
CAD = json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf-8'))
MAIN, G = Polygon(CAD['footprint_outline_m']), -1.2
COUNTS, REJECT, INSTANCES, RNG = Counter(), Counter(), defaultdict(list), random.Random(11021001)
SHAPES = {}


def noop(*args, **kwargs):
    pass


def shape(name, role, geometry, z):
    SHAPES[name] = geometry


lines = raised_edge = block = noop
source = ast.parse((ROOT/'Tools/MPRWarehouse/build_mpr_reference_site.py').read_text(encoding='utf-8'))
selected = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in
            ('zone', 'build_surfaces', 'footprint', 'add', 'place_vehicles', 'plant')]
exec(compile(ast.Module(body=selected, type_ignores=[]), '<read-only site geometry audit>', 'exec'))
API = dict(mesh=noop, poly=noop, box=noop, strip=noop, zone=zone,
           footprint=CAD['footprint_outline_m'], include_freight=False)


def run():
    site = build_surfaces()
    rail = build_railways(API, SOURCE['polylines'], G)
    occupied = place_vehicles(site, rail)
    context = {'footprints': [[m['vertices'][i][:2] for i in m['footprintLoops'][0]]
               for m in SOURCE['meshes'] if m['layer'] == 'buildings' and m['id'] != '1583' and m.get('footprintLoops')]}
    plant(site, rail, context, occupied)
    road, court = site['roads'], site['courts']
    paved = site['paved'].union(court)
    issues = []
    train_polygons = []
    building_union = unary_union([Polygon(p) for p in context['footprints']] + [MAIN])
    shrub_obstacles = unary_union([paved, rail['exclusion'], site['pond'].buffer(3.2), building_union.buffer(.5), *occupied])
    for name, rows in INSTANCES.items():
        for i, row in enumerate(rows):
            p, yaw = row['position_m'], row['rotation_deg']
            if 'Trailer' in name:
                f = footprint(p, 16.15, 2.6, yaw)
                if f.intersection(road).area > .1:
                    issues.append(('trailer in road', name, i, p[:2], round(f.intersection(road).area, 2)))
                if f.difference(paved).area > .1:
                    issues.append(('trailer outside paved', name, i, p[:2], round(f.difference(paved).area, 2)))
            if 'Tree' in name:
                f = Point(*p[:2]).buffer(3.9 * row['scale'][0])
                if f.intersection(court).area > .1:
                    issues.append(('tree in court', name, i, p[:2], round(f.intersection(court).area, 2)))
            if '_Car_' in name:
                f = footprint(p, 4.7, 1.9, yaw)
                if f.difference(paved).area > .1:
                    issues.append(('car outside paved', name, i, p[:2], round(f.difference(paved).area, 2)))
            if 'FreightBoxcar' in name:
                train_polygons.append((name, i, footprint(p, 20.8, 3.296, yaw)))
            if '_Bush_' in name:
                radius = (1.1 if name.endswith('_0') else 1.65) * row['scale'][0]
                intersection = Point(*p[:2]).buffer(radius).intersection(shrub_obstacles).area
                if intersection > .05:
                    issues.append(('shrub touches excluded surface', name, i, p[:2], round(intersection, 3)))
    for index, (name, instance, polygon) in enumerate(train_polygons):
        for other_name, other_instance, other_polygon in train_polygons[index+1:]:
            area = polygon.intersection(other_polygon).area
            if area > .1:
                issues.append(('boxcars overlap', instance, other_instance, round(area, 2)))
    return {'counts': dict(COUNTS), 'court_outside_previous_pavement_m2': court.difference(site['paved']).area,
            'court_road_overlap_m2': court.intersection(road).area,
            'pond_road_gap_m': site['pond'].distance(road), 'pond_walk_road_gap_m': site['pond_path'].distance(road),
            'issues': issues}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
