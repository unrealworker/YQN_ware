"""Small, material-grouped California tract houses for the GHS campus context.

No bpy dependency or scene side effects. ``api['mesh']`` receives counter-
clockwise polygons in the generator's unreflected u/v metres. A house faces
local -v; angle rotates its complete geometry and returned world anchors.
Widths/depths include roof overhangs. Lots, fences and driveways belong to the
caller so they can follow its actual street/parcel boundaries.
"""
import math


VARIANT_NAMES = (
    'Cross-hip left wing',
    'Recessed porch right wing',
    'Twin-height courtyard',
    'Broad hip with entry pavilion',
)


def build_house(api, u, v, w, d, angle, variant=0):
    """Append one two-storey house; return placement anchors and mesh statistics.

    Required: api['mesh'](role, vertices, faces).
    Optional: api['counts'] mapping; api['record_footprint'](role, points).
    Optional: api['solar_role'] material role (default Solar).
    Roles: Buildings, Roofs, Curbs, Glass, Detail, Solar. The caller should use
    linear RGB (.045,.075,.13) for Solar to retain the slate-blue roof accents.
    The returned ``driveway_local`` is a suggestion extending 5.4 m in front
    of the garage, outside the building bounds; it is NOT emitted as geometry.
    """
    if w < 4 or d < 5:
        raise ValueError('Two-storey context houses require w >= 4 and d >= 5 m')
    variant = int(variant) % 4
    sx, sy = w / 12.0, d / 13.0
    sz = min(1.08, max(.86, math.sqrt(sx * sy)))
    ca, sa = math.cos(angle), math.sin(angle)
    stats = {'triangles': 0, 'parts': 0, 'windows': 0, 'solar_panels': 0}
    bounds = [[float('inf'), float('-inf')] for _ in range(3)]

    def local_point(x, y, z=0):
        return x * sx, y * sy, z * sz

    def world_point(x, y, z=0):
        x, y, z = local_point(x, y, z)
        return u + x * ca - y * sa, v + x * sa + y * ca, z

    def emit(role, vertices, faces):
        for vertex in vertices:
            for axis, value in enumerate(local_point(*vertex)):
                bounds[axis][0] = min(bounds[axis][0], value)
                bounds[axis][1] = max(bounds[axis][1], value)
        api['mesh'](role, [world_point(*p) for p in vertices], faces)
        stats['triangles'] += sum(len(face) - 2 for face in faces)
        stats['parts'] += 1

    def cuboid(role, x, y, z, width, depth, height):
        hx, hy, hz = width / 2, depth / 2, height / 2
        vertices = [(x + dx, y + dy, z + dz) for dz in (-hz, hz)
                    for dx, dy in ((-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy))]
        emit(role, vertices, [(3,2,1,0),(4,5,6,7),(0,1,5,4),
                              (1,2,6,5),(2,3,7,6),(3,0,4,7)])

    def wall_quad(role, side, plane, center, z, width, height, offset=0):
        """Outward-facing quad on one axis-aligned wall."""
        t0, t1, z0, z1 = center-width/2, center+width/2, z-height/2, z+height/2
        if side == 'front':
            points = [(t0,plane-offset,z0),(t1,plane-offset,z0),
                      (t1,plane-offset,z1),(t0,plane-offset,z1)]
        elif side == 'back':
            points = [(t1,plane+offset,z0),(t0,plane+offset,z0),
                      (t0,plane+offset,z1),(t1,plane+offset,z1)]
        elif side == 'left':
            points = [(plane-offset,t1,z0),(plane-offset,t0,z0),
                      (plane-offset,t0,z1),(plane-offset,t1,z1)]
        else:
            points = [(plane+offset,t0,z0),(plane+offset,t1,z0),
                      (plane+offset,t1,z1),(plane+offset,t0,z1)]
        emit(role, points, [(0,1,2,3)])

    def window(side, plane, t, z, width=1.15, height=1.28):
        # Layered quads retain crisp frames at the campus viewing scale while
        # avoiding dozens of tiny trim boxes per opening.
        wall_quad('Curbs', side, plane, t, z, width+.18, height+.18, .025)
        wall_quad('Glass', side, plane, t, z, width, height, .037)
        wall_quad('Curbs', side, plane, t, z, .055, height, .041)
        wall_quad('Curbs', side, plane, t, z-height/2-.055, width+.27, .10, .052)
        stats['windows'] += 1

    def hip_roof(x, y, width, depth, eave, rise, solar=False):
        hx, hy = width/2, depth/2
        vertices = [(x-hx,y-hy,eave),(x+hx,y-hy,eave),
                    (x+hx,y+hy,eave),(x-hx,y+hy,eave)]
        if width >= depth:
            ridge = (width-depth)/2
            vertices += [(x-ridge,y,eave+rise),(x+ridge,y,eave+rise)]
            faces = [(0,1,5,4),(1,2,5),(2,3,4,5),(3,0,4)]
        else:
            ridge = (depth-width)/2
            vertices += [(x,y-ridge,eave+rise),(x,y+ridge,eave+rise)]
            faces = [(0,1,4),(1,2,5,4),(2,3,5),(3,0,4,5)]
        emit('Roofs', vertices, faces)
        # Eave edge has physical depth, unlike a paper-thin roof plane.
        lower = [(px,py,pz-.13) for px,py,pz in vertices[:4]]
        emit('Curbs', lower+vertices[:4],
             [(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
        if not solar:
            return
        # A 3x2 array lies on one real hip slope; no floating level panels.
        # Its horizontal extent is constrained by the diagonal hip boundaries.
        front_run = min(width,depth)/2
        top_run = front_run*.66
        low_run = front_run*.25
        array_width = min(4.30, width-2*top_run-.45)
        x0 = x-array_width/2
        y0, y1 = y-hy+low_run, y-hy+top_run

        def panel_quad(role, xa, xb, ya, yb, lift):
            vertices = [(xa,ya,eave+(ya-(y-hy))*rise/front_run+lift),
                        (xb,ya,eave+(ya-(y-hy))*rise/front_run+lift),
                        (xb,yb,eave+(yb-(y-hy))*rise/front_run+lift),
                        (xa,yb,eave+(yb-(y-hy))*rise/front_run+lift)]
            emit(role, vertices, [(0,1,2,3)])

        panel_quad('Detail',x0-.055,x0+array_width+.055,y0-.045,y1+.045,.045)
        for row in range(2):
            for column in range(3):
                xa = x0 + column*array_width/3 + .035
                xb = x0 + (column+1)*array_width/3 - .035
                ya = y0 + row*(y1-y0)/2 + .035
                yb = y0 + (row+1)*(y1-y0)/2 - .035
                panel_quad(api.get('solar_role','Solar'),xa,xb,ya,yb,.060)
                stats['solar_panels'] += 1

    # (x,y,width,depth,height). Every base footprint has a different setback
    # and roof arrangement while preserving a consistent two-storey scale.
    configurations = (
        ((0,1.35,10.2,8.1,6.05), (-2.71,-3.35,4.9,3.0,6.05),
         (2.65,-3.85,4.8,4.0,3.02), (-.20,-3.35), 'front'),
        ((-.15,1.35,10.0,8.2,6.15), (2.61,-3.35,4.6,3.15,6.15),
         (-2.75,-3.85,4.6,4.0,3.02), (.10,-3.35), 'front'),
        ((-1.10,1.35,8.1,8.2,6.18), (3.25,.40,3.5,7.6,5.82),
         (-2.55,-3.85,4.8,4.0,3.05), (1.0,-3.25), 'front'),
        ((0,1.45,10.3,7.9,6.12), (-2.75,-3.30,4.6,3.3,5.84),
         (2.60,-3.90,4.8,3.9,3.0), (-.05,-3.55), 'front'),
    )
    main, wing, garage, entry, entry_side = configurations[variant]
    mx,my,mw,md,mh = main
    wx,wy,ww,wd,wh = wing
    gx,gy,gw,gd,gh = garage

    for x,y,width,depth,height in (main,wing,garage):
        cuboid('Buildings',x,y,height/2+.12,width,depth,height)
        cuboid('Curbs',x,y,.15,width+.12,depth+.12,.30)
    hip_roof(mx,my,mw+.50,md+.50,mh+.12,1.90,solar=True)
    hip_roof(wx,wy,ww+.46,wd+.46,wh+.12,1.04 if variant != 2 else 1.20)
    hip_roof(gx,gy,gw+.46,gd+.46,gh+.12,.91,solar=(variant == 2))

    # Side and rear windows make rows legible from the warehouse as well as
    # the street. Upper/lower levels use the same alignments.
    front, rear = my-md/2, my+md/2
    left, right = mx-mw/2, mx+mw/2
    for level in (1.72,4.63):
        for t in (my-2.55,my+.05,my+2.65):
            # Variant 2's east wing covers the main's side; avoid buried panes.
            window('left',left,t,level)
            if variant != 2:
                window('right',right,t,level)
        for x in (mx-mw*.32,mx,mx+mw*.32):
            window('back',rear,x,level,1.26)
    for x in (mx-mw*.32,mx,mx+mw*.32):
        if not (wx-ww/2-.15 < x < wx+ww/2+.15 and wy-wd/2 < front):
            window('front',front,x,4.63,1.30)

    wing_front = wy-wd/2
    window('front',wing_front,wx-.95 if ww>4 else wx,4.57,1.25)
    if ww > 4:
        window('front',wing_front,wx+.95,4.57,1.25)
    if not (gx-gw/2 < wx < gx+gw/2):
        window('front',wing_front,wx,1.72,1.65)
    if variant == 2:
        for level in (1.72,4.52):
            for t in (wy-2.35,wy+.1,wy+2.55):
                window('right',wx+ww/2,t,level,1.10)

    # Double garage with horizontal sectional seams and a glazed top row.
    garage_front = gy-gd/2
    wall_quad('Curbs','front',garage_front,gx,1.43,gw-.40,2.58,.026)
    wall_quad('Roofs','front',garage_front,gx,1.42,gw-.66,2.34,.041)
    for z in (.75,1.27,1.79):
        wall_quad('Detail','front',garage_front,gx,z,gw-.70,.030,.049)
    for dx in (-.94,0,.94):
        wall_quad('Glass','front',garage_front,gx+dx,2.23,.72,.24,.052)
    wall_quad('Detail','front',garage_front,gx,1.13,.28,.055,.055)

    # Entry reads as a sheltered recess: shallow projecting portico, dark
    # door, sidelight and two slender posts. No random facade texture.
    ex,ey = entry
    entrance_y = min(front-.035,ey)
    cuboid('Buildings',ex,entrance_y+.34,1.49,1.52,.76,2.74)
    wall_quad('Detail','front',entrance_y-.04,ex,1.40,1.08,2.38,.028)
    wall_quad('Glass','front',entrance_y-.04,ex+.38,1.58,.20,1.83,.045)
    wall_quad('Curbs','front',entrance_y-.04,ex-.29,1.41,.045,.26,.047)
    cuboid('Curbs',ex,entrance_y-.22,.16,1.85,1.25,.26)
    canopy_y = entrance_y-.14
    cuboid('Curbs',ex,canopy_y,2.94,2.05,1.52,.18)
    for dx in (-.82,.82):
        cuboid('Buildings',ex+dx,canopy_y-.55,1.57,.14,.14,2.73)

    # A few alternate details produce variation without changing materials.
    if variant == 1:
        cuboid('Buildings',mx+3.3,my+2.1,mh+1.15,.66,.76,1.55)
        cuboid('Curbs',mx+3.3,my+2.1,mh+1.95,.82,.92,.13)
    if variant == 3:
        cuboid('Curbs',wx,wing_front-.06,3.22,ww+.03,.18,.16)

    record = api.get('record_footprint')
    if record:
        for x,y,width,depth,height in (main,wing,garage):
            record('Buildings',[world_point(x+dx,y+dy)[:2] for dx,dy in
                                ((-width/2,-depth/2),(width/2,-depth/2),
                                 (width/2,depth/2),(-width/2,depth/2))])
    counts = api.get('counts')
    if counts is not None:
        for key, value in (('detailed_context_houses',1),
                           ('house_variant_'+str(variant),1),
                           ('house_windows',stats['windows']),
                           ('house_solar_panels',stats['solar_panels'])):
            counts[key] = counts.get(key,0)+value

    garage_anchor = local_point(gx,garage_front,0)[:2]
    driveway_width = (gw-.30)*sx
    driveway = [(garage_anchor[0]-driveway_width/2,garage_anchor[1]-.08),
                (garage_anchor[0]+driveway_width/2,garage_anchor[1]-.08),
                (garage_anchor[0]+driveway_width/2,garage_anchor[1]-5.4),
                (garage_anchor[0]-driveway_width/2,garage_anchor[1]-5.4)]
    return {'variant':variant,'name':VARIANT_NAMES[variant],
            'bounds_local':bounds,'height':bounds[2][1],
            'garage_front_local':garage_anchor,'garage_width':driveway_width,
            'entrance_local':local_point(ex,entrance_y-.85,0)[:2],
            'driveway_local':driveway,
            'garage_front_world':world_point(gx,garage_front,0)[:2],
            'entrance_world':world_point(ex,entrance_y-.85,0)[:2],
            'triangle_count':stats['triangles'],'window_count':stats['windows'],
            'solar_panel_count':stats['solar_panels']}
