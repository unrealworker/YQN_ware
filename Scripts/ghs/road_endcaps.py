"""Local openings in the original Glen sidewalk/curb at its two extensions.

All coordinates are site UV metres. The opening stops at the carriageway
boundary; the parallel side curbs and sidewalks lie outside this mask.
"""
import math

from shapely.geometry import Polygon
from shapely.ops import unary_union


def glen_endcap_masks(roads):
    glen = [road for road in roads if road['id'] == 'glen']
    if len(glen) != 1:
        raise ValueError('Exactly one Glen centreline is required')
    road = glen[0]
    result = []
    for side in ('start', 'end'):
        if not road['extend_' + side]:
            continue
        path = road['path_uv_m']
        index, neighbor = (0, 1) if side == 'start' else (-1, -2)
        p, q = path[index], path[neighbor]
        length = math.dist(p, q)
        tx, ty = (p[0] - q[0]) / length, (p[1] - q[1]) / length
        half = road['width_m'] / 2 + .00001
        # Public sidewalk projects 1.75m past the old flat end. The small
        # inward overlap tolerates source float32 vertices without affecting
        # the curb parallel to the carriageway.
        polygon = Polygon([(p[0]+tx*d-ty*s, p[1]+ty*d+tx*s)
                           for d, s in [(-.12,-half),(2.,-half),(2.,half),(-.12,half)]])
        result.append(dict(road_id='glen', side=side, old_end_uv_m=p,
                           tangent_uv=[tx,ty], width_m=road['width_m'], polygon=polygon))
    if len(result) != 2:
        raise ValueError('This scoped repair requires both Glen extensions')
    return result


def open_glen_endcaps(geometry, roads):
    """Remove only the two approved transverse caps from a planar band."""
    return geometry.difference(unary_union([row['polygon'] for row in glen_endcap_masks(roads)]))
