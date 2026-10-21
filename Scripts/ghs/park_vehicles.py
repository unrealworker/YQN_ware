"""Small, recognisable parked cars for the GHS campus.

Coordinates use the campus u/v metre convention.  The supplied ``api.mesh``
performs the Blender Y reflection, so faces here are outward in right-handed
u/v/z space.  There is no Blender dependency and no change to scene placement.
"""
import math


def build_car(api, u, v, angle=0, blue=False, variant=0):
    """Emit a sedan (even variant) or compact SUV (odd variant).

    Cars face local +u and fit within 4.53 x 1.854 m, including mirrors/tyres.
    The caller owns parking-clearance records and the parked-car counter.
    Required roles: Buildings, Blue, Detail, Markings, Solar, Rubber,
    VehicleLights.  Returns actual bounds and triangle count for validation.
    """
    mesh_api = api['mesh'] if isinstance(api, dict) else api.mesh
    c, s = math.cos(angle), math.sin(angle)
    suv = int(variant) % 2 == 1
    body_role = 'Blue' if blue else 'Buildings'
    vertices_emitted = []
    triangle_count = 0
    part_count = 0

    def emit(role, vertices, faces):
        nonlocal triangle_count, part_count
        world = [(u+x*c-y*s, v+x*s+y*c, z) for x, y, z in vertices]
        mesh_api(role, world, faces)
        vertices_emitted.extend(world)
        triangle_count += sum(len(face)-2 for face in faces)
        part_count += 1

    def block(role, center, size):
        x, y, z = center
        a, b, h = (d*.5 for d in size)
        emit(role, [(x-a,y-b,z-h),(x+a,y-b,z-h),
                    (x+a,y+b,z-h),(x-a,y+b,z-h),
                    (x-a,y-b,z+h),(x+a,y-b,z+h),
                    (x+a,y+b,z+h),(x-a,y+b,z+h)],
             [(3,2,1,0),(4,5,6,7),(0,1,5,4),
              (1,2,6,5),(2,3,7,6),(3,0,4,7)])

    def longitudinal_solid(role, sections):
        # A yz loop seen from +x is counter-clockwise.
        vertices = [(x,y,z) for x,w,low,top in sections
                    for y,z in ((-w,low),(w,low),(w,top),(-w,top))]
        faces = [(3,2,1,0)]
        for k in range(len(sections)-1):
            for j in range(4):
                faces.append((4*k+j,4*k+(j+1)%4,
                              4*(k+1)+(j+1)%4,4*(k+1)+j))
        start = 4*(len(sections)-1)
        faces.append(tuple(start+j for j in range(4)))
        emit(role, vertices, faces)

    # Tapered nose/tail, shoulders and separate low rocker give an automotive
    # silhouette even when viewed from high above the car park.
    belt = .98 if suv else .88
    longitudinal_solid(body_role, [(-2.25,.71,.42,.69),
        (-2.08,.86,.36,belt-.06),(-1.62,.89,.34,belt),
        (1.36,.89,.34,belt),(2.07,.84,.39,belt-.14),
        (2.25,.70,.46,.64)])
    block('Rubber',(0,0,.29),(3.72,1.46,.19))

    # Front and rear wheels have a bevelled rubber tread, visibly circular
    # outer faces, pale alloy hubs, and shallow sculpted upper arch trim.
    wheel_z, radius, sides = .36, .32, 10
    for x in (-1.40,1.42):
        for side in (-1,1):
            rings = [(.75,.285),(.88,radius),(.925,.285)]
            wheel_vertices = [(x+math.cos(i*2*math.pi/sides)*r,
                               side*y,wheel_z+math.sin(i*2*math.pi/sides)*r)
                              for y,r in rings for i in range(sides)]
            # x/z loop has normal -y; outer face is +y for side +1.
            wheel_faces = [tuple(range(sides))]
            for k in range(2):
                wheel_faces.extend((k*sides+i,(k+1)*sides+i,
                    (k+1)*sides+(i+1)%sides,k*sides+(i+1)%sides)
                    for i in range(sides))
            wheel_faces.append(tuple(reversed(range(2*sides,3*sides))))
            if side < 0:
                wheel_faces = [tuple(reversed(face)) for face in wheel_faces]
            emit('Rubber',wheel_vertices,wheel_faces)
            hub = [(x+math.cos(i*2*math.pi/sides)*.165,
                    side*.926,wheel_z+math.sin(i*2*math.pi/sides)*.165)
                   for i in range(sides)]
            hub_face = tuple(reversed(range(sides))) if side > 0 else tuple(range(sides))
            emit('Markings',hub,[hub_face])
            # A dark centre makes the wheel read as an alloy rim, not a disc.
            cap = [(x+math.cos(i*2*math.pi/6)*.055,side*.927,
                    wheel_z+math.sin(i*2*math.pi/6)*.055) for i in range(6)]
            cap_face = tuple(reversed(range(6))) if side > 0 else tuple(range(6))
            emit('Detail',cap,[cap_face])
            arch_vertices = []
            for i in range(9):
                a = math.pi*i/8
                for r in (.345,.385):
                    arch_vertices.append((x+math.cos(a)*r,side*.901,
                                          wheel_z+math.sin(a)*r))
            arch_faces = [(2*i,2*i+1,2*i+3,2*i+2) for i in range(8)]
            # Arc quads initially face -y.
            if side > 0:
                arch_faces = [tuple(reversed(face)) for face in arch_faces]
            emit('Detail',arch_vertices,arch_faces)

    # Glazing is inset inside the painted A/B/C pillars.  Roof and windscreen
    # are separate sloping planes, rather than a glass cube on the body.
    rear_base = -1.92 if suv else -1.45
    rear_roof = -1.46 if suv else -.93
    front_roof = .64 if suv else .46
    front_base = 1.29 if suv else 1.14
    roof_z = 1.72 if suv else 1.48
    bottom_w, top_w = .82, .69
    cabin = [(rear_base,-bottom_w,belt),(front_base,-bottom_w,belt),
             (front_base,bottom_w,belt),(rear_base,bottom_w,belt),
             (rear_roof,-top_w,roof_z),(front_roof,-top_w,roof_z),
             (front_roof,top_w,roof_z),(rear_roof,top_w,roof_z)]
    emit(body_role,cabin,[(3,2,1,0),(4,5,6,7),(0,1,5,4),
                          (1,2,6,5),(2,3,7,6),(3,0,4,7)])

    def inset_quad(corners, inset=.10, offset=(0,0,0)):
        center = [sum(p[k] for p in corners)/4 for k in range(3)]
        return [tuple(center[k]+(p[k]-center[k])*(1-inset)+offset[k]
                      for k in range(3)) for p in corners]

    emit('Solar',inset_quad([cabin[i] for i in (1,2,6,5)],.12,(.008,0,.004)),
         [(0,1,2,3)])
    emit('Solar',inset_quad([cabin[i] for i in (3,0,4,7)],.12,(-.008,0,.004)),
         [(0,1,2,3)])
    for side in (-1,1):
        z0, z1 = belt+.075, roof_z-.07
        y0, y1 = side*(bottom_w-.012), side*(top_w+.020)
        rear0, rear1 = rear_base+.15, rear_roof+.105
        front0, front1 = front_base-.15, front_roof-.09
        pillar = -.24 if suv else -.18
        rear_window = [(rear0,y0,z0),(pillar-.055,y0,z0),
                       (pillar-.055,y1,z1),(rear1,y1,z1)]
        front_window = [(pillar+.055,y0,z0),(front0,y0,z0),
                        (front1,y1,z1),(pillar+.055,y1,z1)]
        face = (0,1,2,3) if side < 0 else (3,2,1,0)
        emit('Solar',rear_window,[face])
        emit('Solar',front_window,[face])
        # Narrow door handles and compact mirror caps stay within body width.
        block('Detail',(-.52,side*.894,belt-.12),(.22,.012,.035))
        block('Detail',(.70,side*.894,belt-.12),(.20,.012,.035))
        block(body_role,(front_base-.19,side*.872,belt+.11),(.22,.102,.105))

    # Painted bumpers are separated by black intake strips; front lamps are
    # wide pale lenses and rear lamps are red, making direction unambiguous.
    block('Detail',(2.185,0,.49),(.10,1.22,.12))
    block('Detail',(-2.185,0,.46),(.10,1.28,.095))
    block('Rubber',(2.247,0,.59),(.008,.62,.10))
    for side in (-1,1):
        block('Markings',(2.254,side*.54,.58),(.008,.30,.10))
        block('VehicleLights',(-2.254,side*.53,.63),(.008,.25,.10))
    # Plate gives the rear a small readable centre detail at close view.
    block('Markings',(-2.231,0,.56),(.012,.35,.10))

    lo = [min(p[k] for p in vertices_emitted) for k in range(3)]
    hi = [max(p[k] for p in vertices_emitted) for k in range(3)]
    return {'variant': 'compact_suv' if suv else 'sedan',
            'triangle_count': triangle_count, 'part_count': part_count,
            'bounds_uvz_m': {'min': lo, 'max': hi},
            'parking_size_m': [4.53,1.854], 'height_m': roof_z,
            'roles': sorted({body_role,'Rubber','Markings','Detail',
                             'Solar','VehicleLights'})}
