"""Read-only endpoint classification shared by context builders and repairs.

Traffic route boundaries are not necessarily the physical end of a road.
An endpoint shared by source roads is an internal junction, even when the
traffic manifest historically requests a visual continuation there.
"""
import math


def classify_context_road_ends(roads, cad_roads=(), tolerance_m=.05):
    if tolerance_m <= 0:
        raise ValueError('Endpoint tolerance must be positive')
    result = {'external': [], 'internal': []}
    for road in roads:
        for side, index in (('start', 0), ('end', -1)):
            if not road.get('extend_'+side):
                continue
            point = road['path_uv_m'][index]
            route_incidents = sorted({other['id'] for other in roads
                if any(math.dist(point, p) <= tolerance_m
                       for p in (other['path_uv_m'][0], other['path_uv_m'][-1]))})
            cad_incidents = sorted({str(other.get('handle', other.get('id'))) for other in cad_roads
                if other.get('points_uv_m') and any(math.dist(point, p) <= tolerance_m
                    for p in (other['points_uv_m'][0], other['points_uv_m'][-1]))})
            internal = len(route_incidents) > 1 or len(cad_incidents) > 1
            result['internal' if internal else 'external'].append(dict(
                road_id=road['id'], side=side, endpoint_uv_m=list(point),
                route_incidents=route_incidents, cad_incidents=cad_incidents))
    return result
