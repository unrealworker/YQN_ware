"""Constant-speed polyline motion with smooth, non-overshooting heading.

The supplied positions and travel time are unchanged. Only heading is sampled
from a C1 curve; the runtime can seek or reverse through the resulting keys.
Rows contain (relative_seconds, (x, y, z), unwrapped_yaw_degrees).
"""
import math
from bisect import bisect_left, bisect_right

_MIN_STEERING_SAMPLE_SECONDS = .001
_MIN_EXTRA_KNOT_SECONDS = 2*_MIN_STEERING_SAMPLE_SECONDS


def _yaw_slopes(times, angles):
    """Shape-preserving PCHIP derivatives, with rest at route endpoints."""
    intervals = [b-a for a,b in zip(times,times[1:])]
    rates = [(b-a)/dt for a,b,dt in zip(angles,angles[1:],intervals)]
    slopes = [0.]*len(angles)
    for i in range(1,len(angles)-1):
        if rates[i-1]*rates[i]>0:
            w1 = 2*intervals[i]+intervals[i-1]
            w2 = intervals[i]+2*intervals[i-1]
            slopes[i] = (w1+w2)/(w1/rates[i-1]+w2/rates[i])
    return slopes


def _cubic(a, b, ma, mb, dt):
    return 2*a-2*b+dt*(ma+mb), -3*a+3*b-dt*(2*ma+mb), dt*ma, a


def _blend_steering(times, points, angles, window):
    """Exactly average piecewise-linear yaw over a centred time window.

    Constant heading outside the route defines the boundary extension. Window
    edges become additional knots so a sparse straight cannot smear steering
    across its full length. Original position/time knots are always retained.
    """
    half = window*.5
    areas = [0.]
    for i in range(len(times)-1):
        areas.append(areas[-1]+(times[i+1]-times[i])*(angles[i]+angles[i+1])*.5)

    def integral(time):
        if time<=times[0]:
            return (time-times[0])*angles[0]
        if time>=times[-1]:
            return areas[-1]+(time-times[-1])*angles[-1]
        i = bisect_right(times,time)-1
        dt = time-times[i]
        rate = (angles[i+1]-angles[i])/(times[i+1]-times[i])
        return areas[i]+angles[i]*dt+.5*rate*dt*dt

    extras = []
    for time in times:
        for shifted in (time-half,time+half):
            if not times[0]<shifted<times[-1]:
                continue
            i = bisect_left(times,shifted)
            # Source path corners win. Near-duplicate optional knots create
            # microsecond intervals that cannot survive exported time rounding.
            if min(abs(shifted-times[i-1]),abs(times[i]-shifted))>=_MIN_EXTRA_KNOT_SECONDS:
                extras.append(shifted)
    unique_extras = []
    for time in sorted(extras):
        if not unique_extras or time-unique_extras[-1]>=_MIN_EXTRA_KNOT_SECONDS:
            unique_extras.append(time)
    knots = sorted(times+unique_extras)
    positions,headings = [],[]
    for time in knots:
        i = min(len(times)-2,bisect_right(times,time)-1)
        fraction = (time-times[i])/(times[i+1]-times[i])
        positions.append(tuple(a+(b-a)*fraction for a,b in zip(points[i],points[i+1])))
        headings.append((integral(time+half)-integral(time-half))/window)
    positions[0],positions[-1] = points[0],points[-1]
    headings[0],headings[-1] = angles[0],angles[-1]
    return knots,positions,headings


def _compact_linear_keys(rows, tolerance=1e-8):
    """Remove keys reconstructable by the runtime's time-linear sampler.

    Every removed sample is checked against the final retained span, avoiding
    accumulated error along a long straight. Keep yaw spans below 180 degrees
    because Unreal interpolates between keys using the shortest angle.
    """
    if len(rows)<3:
        return rows
    keep = {0,len(rows)-1}
    pending = [(0,len(rows)-1)]
    epsilon = tolerance*tolerance
    while pending:
        first,last = pending.pop()
        if last<=first+1:
            continue
        a,b = rows[first],rows[last]
        dt = b[0]-a[0]
        dx,dy,dz = [y-x for x,y in zip(a[1],b[1])]
        dyaw = b[2]-a[2]
        if abs(dyaw)>=180.:
            split = (first+last)//2
            keep.add(split)
            pending.extend(((first,split),(split,last)))
            continue
        maximum,split = epsilon,None
        for i in range(first+1,last):
            row = rows[i]
            q = (row[0]-a[0])/dt
            ex = row[1][0]-a[1][0]-q*dx
            ey = row[1][1]-a[1][1]-q*dy
            ez = row[1][2]-a[1][2]-q*dz
            eyaw = row[2]-a[2]-q*dyaw
            error = max(ex*ex+ey*ey+ez*ez,eyaw*eyaw)
            if error>maximum:
                maximum,split = error,i
        if split is not None:
            keep.add(split)
            pending.extend(((first,split),(split,last)))
    return [rows[i] for i in sorted(keep)]


def build_route_profile(path, cruise_speed, *, sample_hz=60., steering_blend_seconds=.30):
    """Travel the exact input polyline at the supplied constant speed.

    Total duration is exactly polyline length / cruise_speed. No braking,
    speed limit, inserted wait or time stretching is applied. A fourth column
    overrides inferred heading, including the headings used for load offsets.
    Heading is symmetrically averaged over steering_blend_seconds (0 disables)
    before shape-preserving C1 interpolation, sampled only where it changes.
    The original endpoint headings stay exact. Duplicate poses add no time;
    stationary heading changes belong to the caller's explicit turn action.
    """
    if any(not math.isfinite(v) or v<=0 for v in (cruise_speed,sample_hz)):
        raise ValueError('Cruise speed and sample frequency must be finite and positive')
    if not math.isfinite(steering_blend_seconds) or steering_blend_seconds<0:
        raise ValueError('Steering blend duration must be finite and non-negative')
    points,explicit = [],[]
    for row in path:
        if len(row)<3 or not all(math.isfinite(v) for v in row[:4]):
            raise ValueError('Route points require finite xyz and optional yaw')
        point = tuple(float(v) for v in row[:3])
        yaw = float(row[3]) if len(row)>3 else None
        if points and point==points[-1]:
            previous = explicit[-1]
            if yaw is not None and previous is not None and abs(math.remainder(yaw-previous,360))>1e-10:
                raise ValueError('Stationary heading changes require a separate caller turn action')
            if yaw is not None and previous is None:
                explicit[-1] = yaw
            continue
        points.append(point)
        explicit.append(yaw)
    if not points:
        raise ValueError('Route must contain a point')

    angles = []
    for i,point in enumerate(points):
        yaw = explicit[i]
        if yaw is None:
            directions = []
            for sign in (-1,1):
                j = i+sign
                if 0<=j<len(points):
                    dx = (points[j][0]-point[0])*sign
                    dy = (points[j][1]-point[1])*sign
                    length = math.hypot(dx,dy)
                    if length>0.:
                        directions.append((dx/length,dy/length))
            if directions:
                x = sum(direction[0] for direction in directions)
                y = sum(direction[1] for direction in directions)
                if math.hypot(x,y)<1e-10:
                    x,y = directions[-1]
                yaw = math.degrees(math.atan2(y,x))
            else:
                yaw = angles[-1] if angles else 0.
        angles.append(angles[-1]+math.remainder(yaw-angles[-1],360) if angles else yaw)
    if len(points)==1:
        return [(0.,points[0],angles[0])]

    times,total_length = [0.],0.
    for a,b in zip(points,points[1:]):
        total_length += math.dist(a,b)
        times.append(total_length/cruise_speed)
    if any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Route contains a segment too small for representable time')
    if steering_blend_seconds>0.:
        times,points,angles = _blend_steering(times,points,angles,steering_blend_seconds)
    slopes = _yaw_slopes(times,angles)
    result = [(0.,points[0],angles[0])]
    for i,(a,b) in enumerate(zip(points,points[1:])):
        dt = times[i+1]-times[i]
        turn = abs(angles[i+1]-angles[i])
        # Keep curve samples fine enough for rendering, but not so close that
        # the timeline's microsecond rounding/merge creates speed artefacts.
        # Original short path spans keep both corners, without subdividing
        # them further unless shortest-angle yaw sampling requires a split.
        count = max(2,math.ceil(dt*sample_hz),math.ceil(turn/3.)) if turn>1e-10 else 1
        count = max(math.floor(turn/180.)+1,min(count,max(1,math.floor(dt/_MIN_STEERING_SAMPLE_SECONDS))))
        coeff = _cubic(angles[i],angles[i+1],slopes[i],slopes[i+1],dt)
        for j in range(1,count+1):
            if j==count:
                result.append((times[i+1],b,angles[i+1]))
                continue
            q = j/count
            position = tuple(x+(y-x)*q for x,y in zip(a,b))
            ca,cb,cc,cd = coeff
            yaw = ((ca*q+cb)*q+cc)*q+cd
            result.append((times[i]+dt*q,position,yaw))
    return _compact_linear_keys(result)
