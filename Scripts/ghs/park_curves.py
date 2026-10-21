"""Pure 2D path geometry for campus roads, curb strips and fence placement.

Coordinates and distances use the caller's units (metres in the park builder).
Positive offsets are to the left while following the path. Closed paths have
one repeated endpoint; closed post sampling deliberately omits that duplicate.
Only the Python standard library is used, so the same kernel runs in Blender
and in ordinary geometry validation without importing bpy.
"""
from bisect import bisect_right
import math

_EPS = 1e-9


def _distance(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _unit(a, b):
    length = _distance(a, b)
    return ((b[0] - a[0]) / length, (b[1] - a[1]) / length)


def _number(value, name, positive=False, nonnegative=False):
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0) or (nonnegative and value < 0):
        raise ValueError('%s must be finite and %s' % (
            name, 'positive' if positive else 'nonnegative' if nonnegative else 'finite'))
    return value


def _clean(points, closed=False):
    result = []
    for point in points:
        p = (float(point[0]), float(point[1]))
        if not all(math.isfinite(component) for component in p):
            raise ValueError('path coordinates must be finite')
        if not result or _distance(result[-1], p) > _EPS:
            result.append(p)
    if closed and len(result) > 1 and _distance(result[-1], result[0]) <= _EPS:
        result.pop()
    return result


def _append_point(result, point):
    if not result or _distance(result[-1], point) > _EPS:
        result.append(point)


def _append_line(result, target, max_step):
    if not result:
        result.append(target)
        return
    start = result[-1]
    length = _distance(start, target)
    if length <= _EPS:
        return
    steps = max(1, math.ceil(length / max_step))
    for step in range(1, steps):
        t = step / steps
        result.append((start[0] + (target[0] - start[0]) * t,
                       start[1] + (target[1] - start[1]) * t))
    result.append(target)


def rounded_path(points, radius=12, closed=False, max_step=1.0, return_metadata=False):
    """Replace control-polyline corners with tangent circular fillets.

    ``radius`` is the requested centreline radius. Adjacent corners share each
    edge's available length proportionally, so clamped fillets cannot overlap.
    Use ``return_metadata=True`` to receive ``(samples, metadata)`` and inspect
    ``min_radius`` before accepting truck routes. A 180-degree reversal is
    rejected because it has no finite tangent fillet. Radius zero leaves sharp
    corners. Open endpoints are preserved exactly; closed paths begin at the
    first corner's incoming tangent and repeat it once at the end.

    Curves are analytically C1 at straight/arc joins. Their polygonal samples
    are spaced at most ``max_step`` apart; reducing that value improves their
    rendering and offset approximation.
    """
    radius = _number(radius, 'radius', nonnegative=True)
    max_step = _number(max_step, 'max_step', positive=True)
    controls = _clean(points, closed)
    count = len(controls)
    corners = {}
    trims = [0.0] * count
    edges = [(i, (i + 1) % count) for i in range(count if closed else max(0, count - 1))]
    if closed and count < 3:
        raise ValueError('a closed path needs at least three distinct controls')
    indices = range(count) if closed else range(1, count - 1)
    for i in indices:
        previous, p, following = controls[i - 1], controls[i], controls[(i + 1) % count]
        incoming, outgoing = _unit(previous, p), _unit(p, following)
        dot = max(-1.0, min(1.0, incoming[0] * outgoing[0] + incoming[1] * outgoing[1]))
        turn = math.atan2(incoming[0] * outgoing[1] - incoming[1] * outgoing[0], dot)
        if radius > 0 and abs(abs(turn) - math.pi) < 1e-7:
            raise ValueError('a 180-degree reversal cannot have a tangent fillet')
        if radius <= _EPS or abs(turn) <= 1e-8:
            continue
        trim = radius * math.tan(abs(turn) * .5)
        trims[i] = trim
        corners[i] = dict(corner_index=i, control=p, incoming=incoming,
                          outgoing=outgoing, turn_angle=turn, requested_trim=trim)

    # Every shared edge gives both of its corner trims the same limiting
    # factor. Taking the minimum of the two incident factors is simultaneous,
    # deterministic and guarantees trim[i] + trim[j] <= edge length.
    scales = [1.0] * count
    for i, j in edges:
        requested = trims[i] + trims[j]
        if requested > _EPS:
            scale = min(1.0, _distance(controls[i], controls[j]) / requested)
            scales[i] = min(scales[i], scale)
            scales[j] = min(scales[j], scale)

    for i, corner in corners.items():
        trim = trims[i] * scales[i]
        actual_radius = radius * scales[i]
        p, incoming, outgoing = corner['control'], corner['incoming'], corner['outgoing']
        tangent_in = (p[0] - incoming[0] * trim, p[1] - incoming[1] * trim)
        tangent_out = (p[0] + outgoing[0] * trim, p[1] + outgoing[1] * trim)
        sign = 1 if corner['turn_angle'] > 0 else -1
        center = (tangent_in[0] - incoming[1] * actual_radius * sign,
                  tangent_in[1] + incoming[0] * actual_radius * sign)
        corner.update(trim=trim, radius=actual_radius, tangent_in=tangent_in,
                      tangent_out=tangent_out, center=center)

    result = []
    for i, p in enumerate(controls):
        corner = corners.get(i)
        if not corner:
            _append_line(result, p, max_step)
            continue
        _append_line(result, corner['tangent_in'], max_step)
        center, actual_radius = corner['center'], corner['radius']
        angle = math.atan2(corner['tangent_in'][1] - center[1],
                           corner['tangent_in'][0] - center[0])
        steps = max(1, math.ceil(actual_radius * abs(corner['turn_angle']) / max_step))
        for step in range(1, steps):
            a = angle + corner['turn_angle'] * step / steps
            _append_point(result, (center[0] + actual_radius * math.cos(a),
                                   center[1] + actual_radius * math.sin(a)))
        _append_point(result, corner['tangent_out'])
    if closed and result:
        _append_line(result, result[0], max_step)
        # Preserve one exact seam even if the last arc ends within tolerance.
        if _distance(result[-1], result[0]) <= _EPS:
            result[-1] = result[0]
    radii = [corner['radius'] for corner in corners.values()]
    metadata = dict(requested_radius=radius, min_radius=min(radii) if radii else None,
                    corners=list(corners.values()),
                    clamped_corners=sum(r < radius - _EPS for r in radii),
                    closed=bool(closed), length=path_length(result),
                    control_count=count, sample_count=len(result))
    return (result, metadata) if return_metadata else result


def offset_path(path, distance, closed=False, miter_limit=4.0):
    """Offset a sampled path using intersecting adjacent segment normals.

    Positive distance means left. Dense circular samples retain a consistent
    strip width, including the closed seam. ``miter_limit`` bounds spikes on
    unsmoothed corners. Offset magnitude must stay below the inner curve
    radius to avoid the geometric cusp of an excessively wide strip.
    """
    distance = _number(distance, 'distance')
    miter_limit = _number(miter_limit, 'miter_limit', positive=True)
    if miter_limit < 1:
        raise ValueError('miter_limit must be at least one')
    points = _clean(path, closed)
    count = len(points)
    if count < 2:
        return points
    result = []
    for i, p in enumerate(points):
        if not closed and i == 0:
            tangent = _unit(p, points[1])
            normal, scale = (-tangent[1], tangent[0]), 1.0
        elif not closed and i == count - 1:
            tangent = _unit(points[i - 1], p)
            normal, scale = (-tangent[1], tangent[0]), 1.0
        else:
            before = _unit(points[i - 1], p)
            after = _unit(p, points[(i + 1) % count])
            n0, n1 = (-before[1], before[0]), (-after[1], after[0])
            nx, ny = n0[0] + n1[0], n0[1] + n1[1]
            length = math.hypot(nx, ny)
            if length <= _EPS:
                raise ValueError('cannot offset a 180-degree reversal')
            normal = (nx / length, ny / length)
            denominator = max(_EPS, normal[0] * n0[0] + normal[1] * n0[1])
            scale = min(miter_limit, 1.0 / denominator)
        result.append((p[0] + normal[0] * distance * scale,
                       p[1] + normal[1] * distance * scale))
    if closed:
        result.append(result[0])
    return result


def _prepare(path, closed=False):
    points = _clean(path, closed)
    if closed and len(points) > 1:
        points.append(points[0])
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + _distance(a, b))
    return points, cumulative


def path_length(path, closed=False):
    """Length along the sampled polyline, counting a closed seam once."""
    return _prepare(path, closed)[1][-1]


def _point_at(points, cumulative, distance, closed=False):
    if not points:
        raise ValueError('cannot sample an empty path')
    total = cumulative[-1]
    if len(points) == 1 or total <= _EPS:
        return points[0], (1.0, 0.0)
    distance = distance % total if closed else max(0.0, min(total, distance))
    segment = min(len(points) - 2, bisect_right(cumulative, distance) - 1)
    a, b = points[segment], points[segment + 1]
    length = cumulative[segment + 1] - cumulative[segment]
    fraction = (distance - cumulative[segment]) / length
    point = (a[0] + (b[0] - a[0]) * fraction,
             a[1] + (b[1] - a[1]) * fraction)
    return point, _unit(a, b)


def point_at_distance(path, distance, closed=False):
    """Return ``(point, unit_tangent)`` at a polyline arc distance.

    Open distances clamp to endpoints. Closed distances wrap around the loop.
    At a polygon vertex the outgoing segment supplies the tangent.
    """
    distance = _number(distance, 'distance')
    points, cumulative = _prepare(path, closed)
    return _point_at(points, cumulative, distance, closed)


def sample_along(path, spacing, start=0, closed=False):
    """Return ``(point, unit_tangent, arc_distance)`` samples along a path.

    Open paths use exactly ``spacing`` and include an end only when it falls
    on that spacing. Closed paths use ceil(length / spacing) equally spaced
    samples so the seam gap matches every other gap and never exceeds the
    requested spacing. ``start`` shifts the first closed sample; reported
    distances are monotonic and may extend beyond one loop before wrapping.
    """
    spacing = _number(spacing, 'spacing', positive=True)
    start = _number(start, 'start', nonnegative=True)
    points, cumulative = _prepare(path, closed)
    total = cumulative[-1]
    if not points or total <= _EPS:
        return []
    if closed:
        count = max(1, math.ceil(total / spacing))
        spacing = total / count
        start %= total
    else:
        count = max(0, math.floor((total - start + _EPS) / spacing) + 1)
    result = []
    for i in range(count):
        distance = start + i * spacing
        point, tangent = _point_at(points, cumulative, distance, closed)
        result.append((point, tangent, distance))
    return result


def _slice(points, cumulative, start, end, closed):
    if not points:
        return []
    total = cumulative[-1]
    if closed and total > _EPS:
        if end < start:
            end += math.ceil((start - end) / total) * total
    else:
        start, end = max(0.0, min(total, start)), max(0.0, min(total, end))
    if end < start - _EPS:
        raise ValueError('slice end must not precede start on an open path')
    result = [_point_at(points, cumulative, start, closed)[0]]
    if total > _EPS and closed:
        for loop in range(math.floor(start / total), math.floor(end / total) + 1):
            for p, distance in zip(points[1:], cumulative[1:]):
                distance += loop * total
                if start + _EPS < distance < end - _EPS:
                    _append_point(result, p)
    else:
        for p, distance in zip(points[1:-1], cumulative[1:-1]):
            if start + _EPS < distance < end - _EPS:
                _append_point(result, p)
    _append_point(result, _point_at(points, cumulative, end, closed)[0])
    return result


def slice_path(path, start, end, closed=False):
    """Extract an arc-length interval, retaining interior sampled vertices.

    Closed intervals may cross the seam, e.g. ``length-2, length+3``; when end
    is less than start it is advanced to the next appropriate loop.
    """
    start, end = _number(start, 'start'), _number(end, 'end')
    points, cumulative = _prepare(path, closed)
    return _slice(points, cumulative, start, end, closed)


def dash_segments(path, dash_length=3, gap_length=5, phase=0, closed=False):
    """Return dash polylines using continuous distance across every vertex.

    ``phase`` is the nonnegative distance before the first dash. The final
    dash is clipped at the path end. Each dash keeps the curved source's
    interior samples, so it can be rendered with the same ribbon builder.
    """
    dash_length = _number(dash_length, 'dash_length', positive=True)
    gap_length = _number(gap_length, 'gap_length', nonnegative=True)
    phase = _number(phase, 'phase', nonnegative=True)
    points, cumulative = _prepare(path, closed)
    total = cumulative[-1]
    period = dash_length + gap_length
    count = max(0, math.ceil((total - phase) / period))
    result = []
    for i in range(count):
        start = phase + i * period
        end = min(total, start + dash_length)
        if end - start > _EPS:
            result.append(_slice(points, cumulative, start, end, closed))
    return result
