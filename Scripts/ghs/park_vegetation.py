"""Original clustered broadleaf trees and shrubs for the GHS campus context.

All geometry uses the generator's unreflected u/v metres, with outward CCW
faces. ``size`` is a uniform multiplier: size=1 gives a 5.6--6.8 m tree,
depending on variant. No Blender dependency, global random state, or scene
side effects. The caller owns placement, clearance and material merging.
"""
import math


PALETTE = {
    'Trees': (.10, .22, .11),
    'TreesLight': (.14, .29, .15),
    'TreesDark': (.065, .16, .075),
    'Trunk': (.205, .165, .115),
}

# Each crown is three overlapping rounded clusters. The slight lean and
# uneven heights produce an organic silhouette without high polygon counts.
TREE_PROFILES = (
    ((-.10, .02, 4.05, 1.72, 1.60, 1.68),
     (1.03, -.23, 3.70, 1.18, 1.26, 1.20),
     (-.94, .42, 4.00, 1.17, 1.15, 1.35)),
    ((.02, -.03, 4.88, 1.28, 1.25, 1.91),
     (.65, .38, 3.88, 1.15, 1.10, 1.45),
     (-.62, -.48, 4.60, 1.10, 1.05, 1.48)),
    ((-.05, .05, 3.95, 1.78, 1.61, 1.46),
     (1.21, .39, 3.39, 1.34, 1.29, 1.28),
     (-1.19, -.38, 3.49, 1.39, 1.31, 1.28)),
)


def _normal(p):
    length = math.sqrt(sum(q*q for q in p))
    return tuple(q/length for q in p)


def _icosphere():
    t = (1 + math.sqrt(5)) / 2
    verts = [_normal(p) for p in
             [(-1,t,0),(1,t,0),(-1,-t,0),(1,-t,0),
              (0,-1,t),(0,1,t),(0,-1,-t),(0,1,-t),
              (t,0,-1),(t,0,1),(-t,0,-1),(-t,0,1)]]
    faces = [(0,11,5),(0,5,1),(0,1,7),(0,7,10),(0,10,11),
             (1,5,9),(5,11,4),(11,10,2),(10,7,6),(7,1,8),
             (3,9,4),(3,4,2),(3,2,6),(3,6,8),(3,8,9),
             (4,9,5),(2,4,11),(6,2,10),(8,6,7),(9,8,1)]
    midpoints = {}

    def middle(a,b):
        key = tuple(sorted((a,b)))
        if key not in midpoints:
            midpoints[key] = len(verts)
            verts.append(_normal(tuple((verts[a][i]+verts[b][i])/2 for i in range(3))))
        return midpoints[key]

    divided = []
    for a,b,c in faces:
        ab,bc,ca = middle(a,b),middle(b,c),middle(c,a)
        divided.extend([(a,ab,ca),(b,bc,ab),(c,ca,bc),(ab,bc,ca)])
    return verts, divided


SPHERE_VERTICES, SPHERE_FACES = _icosphere()


def _make_emitter(api,u,v,size,angle):
    if size <= 0:
        raise ValueError('Vegetation size must be positive')
    ca,sa = math.cos(angle),math.sin(angle)
    stats = {'triangles':0, 'parts':0, 'height_m':0, 'radius_m':0}

    def emit(role,vertices,faces):
        transformed = [(u+size*(x*ca-y*sa),v+size*(x*sa+y*ca),.025+size*z)
                       for x,y,z in vertices]
        api['mesh'](role,transformed,faces)
        stats['triangles'] += sum(len(face)-2 for face in faces)
        stats['parts'] += 1
        stats['height_m'] = max(stats['height_m'],max(p[2] for p in transformed))
        stats['radius_m'] = max(stats['radius_m'],max(math.hypot(x,y)*size for x,y,z in vertices))

    return emit,stats


def _cluster(emit,center,radii,phase=0,role='Trees'):
    # Tiny deterministic nonuniformities retain rounded crowns without making
    # identical spheres. All vertices remain a radial transform of a sphere.
    vertices = []
    for i,(x,y,z) in enumerate(SPHERE_VERTICES):
        irregularity = 1+.035*math.sin(i*2.399963+phase)
        vertices.append((center[0]+x*radii[0]*irregularity,
                         center[1]+y*radii[1]*irregularity,
                         center[2]+z*radii[2]*irregularity))
    emit(role,vertices,SPHERE_FACES)


def _branch(emit,start,end,radius0,radius1,sides=6):
    axis = _normal(tuple(end[i]-start[i] for i in range(3)))
    reference = (0,0,1) if abs(axis[2])<.95 else (1,0,0)
    cross = (axis[1]*reference[2]-axis[2]*reference[1],
             axis[2]*reference[0]-axis[0]*reference[2],
             axis[0]*reference[1]-axis[1]*reference[0])
    ux,uy,uz = _normal(cross)
    vx,vy,vz = axis[1]*uz-axis[2]*uy,axis[2]*ux-axis[0]*uz,axis[0]*uy-axis[1]*ux
    verts = []
    for point,radius in ((start,radius0),(end,radius1)):
        for i in range(sides):
            c,s = math.cos(i*2*math.pi/sides),math.sin(i*2*math.pi/sides)
            verts.append((point[0]+radius*(c*ux+s*vx),
                          point[1]+radius*(c*uy+s*vy),
                          point[2]+radius*(c*uz+s*vz)))
    faces = [tuple(reversed(range(sides))),tuple(range(sides,2*sides))]
    faces.extend((i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides))
    emit('Trunk',verts,faces)


def build_tree(api,u,v,size=1,variant=0):
    """Emit one 320-triangle tree and return its actual height/crown radius.

    Required api['mesh'](role,vertices,faces); optional api['counts'] mapping.
    Roles Trees/TreesLight/TreesDark/Trunk. size=1: broad tree about 5.8 m,
    narrow tree about 6.8 m, spreading tree about 5.5 m. There is no clearance
    rejection here; the caller should test returned/known canopy dimensions.
    """
    variant = int(variant)
    profile = TREE_PROFILES[variant%3]
    angle = (variant*2.399963 + u*.037 + v*.023) % (math.pi*2)
    emit,stats = _make_emitter(api,u,v,size,angle)
    _branch(emit,(0,0,0),(-.055,.03,2.85),.19,.105)
    for i,(x,y,z,rx,ry,rz) in enumerate(profile):
        _branch(emit,(-.035,.02,1.86+i*.23),(x*.72,y*.72,z-.20),.105,.045)
        _cluster(emit,(x,y,z),(rx,ry,rz),variant+i*3.1,
                 ('Trees','TreesDark','TreesLight')[i])
    if 'counts' in api:
        api['counts']['low_poly_trees'] += 1
        api['counts']['clustered_broadleaf_trees'] += 1
    stats.update(variant=variant%3,size=size)
    return stats


def build_shrub(api,u,v,size=.65,variant=0):
    """Emit a dense, low round shrub; size=.65 gives ~0.9 m tall, 1.5 m wide.

    160 triangles. Green clusters sit below tree crowns and hide trunks, so
    repeated shrubs form the clipped hedge islands seen in the reference.
    """
    variant = int(variant)
    emit,stats = _make_emitter(api,u,v,size,variant*2.399963)
    _cluster(emit,(-.22,.04,.66),(.87,.84,.69),variant,
             'TreesDark' if variant%3==0 else 'Trees')
    _cluster(emit,(.42,-.11,.60),(.66,.70,.59),variant+4,'TreesLight')
    if 'counts' in api:
        api['counts']['landscape_shrubs'] += 1
    stats.update(variant=variant%3,size=size)
    return stats
