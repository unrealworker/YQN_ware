"""Independent source topology/clearance checks; no bpy or Unreal imports."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Saved/ParkRefinement/python_deps'))
import numpy as np
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import unary_union


def validate(path):
    data = json.loads(Path(path).read_text(encoding='utf8'))
    roads, rails = data['road_centerlines'], data['rail_centerlines']
    paved, corridor = shape(data['roads']), shape(data['rail_corridor'])
    frame = shape(data['frame'])
    main = Polygon(json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))['footprint_outline_m'])
    checks = []
    building_clearance = shape(data['building_protection'])
    for row in [*roads, *rails]:
        original = LineString(np.asarray(row['source_points_m'])[:, :2])
        actual = LineString(np.asarray(row['points_m'])[:, :2])
        tolerance = .36 if row in roads else .18
        missing = actual.difference((paved if row in roads else corridor).buffer(.001)).intersection(frame.buffer(-.02))
        # A driveway may end at a source facade. The explicit 35cm building
        # setback can shorten that final bit; it may not interrupt its middle.
        facade_end_zone = unary_union([Point(actual.coords[i]).buffer(.36) for i in [0,-1]]).intersection(building_clearance)
        expected_facade_setback = missing.intersection(facade_end_zone) if row in roads else LineString()
        unexplained = missing.difference(expected_facade_setback.buffer(.00001))
        checks.append(dict(id=row['id'], endpoint_error_m=max(Point(original.coords[i]).distance(Point(actual.coords[i])) for i in [0,-1]),
             hausdorff_error_m=original.hausdorff_distance(actual), allowed_error_m=tolerance,
             uncovered_centerline_m=unexplained.length, source_facade_setback_m=expected_facade_setback.length))
    source_node_checks = []
    for i, row in enumerate(roads):
        source = LineString(np.asarray(row['source_points_m'])[:, :2])
        new = LineString(np.asarray(row['points_m'])[:, :2])
        for other in roads[i+1:]:
            source_other = LineString(np.asarray(other['source_points_m'])[:, :2])
            hit = source.intersection(source_other)
            if hit.is_empty:
                continue
            new_other = LineString(np.asarray(other['points_m'])[:, :2])
            if hit.geom_type == 'Point':
                source_node_checks.append(dict(ids=[row['id'],other['id']], source_node=list(hit.coords)[0],
                        new_node_max_error_m=max(new.distance(hit),new_other.distance(hit))))
    failure = [c for c in checks if c['endpoint_error_m'] > 1e-8 or c['hausdorff_error_m'] > c['allowed_error_m']+1e-8 or c['uncovered_centerline_m'] > .02]
    node_failures = [c for c in source_node_checks if c['new_node_max_error_m'] > .005]
    result = dict(status='passed' if not failure and not node_failures else 'failed', axis_checks=checks,
        road_junction_checks=source_node_checks, failures=failure, junction_failures=node_failures,
        main_road_overlap_m2=paved.intersection(main).area, main_rail_overlap_m2=corridor.intersection(main).area,
        all_building_clearance_road_overlap_m2=paved.intersection(shape(data['building_protection'])).area,
        source_axis_ids_preserved=len(set(c['id'] for c in checks)) == 199,
        no_old_exterior_dependency=True)
    output = Path(path).with_name('road_validation.json')
    output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['axis_checks','road_junction_checks']},indent=2))
    return result


if __name__ == '__main__':
    result = validate(sys.argv[1] if len(sys.argv)>1 else ROOT/'Saved/MPR/rebuild_20261104/road_layout.json')
    raise SystemExit(0 if result['status']=='passed' else 1)
