"""Original clustered broadleaf trees and shrubs for the GHS campus context.

All geometry uses the generator's unreflected u/v metres, with outward CCW
faces. ``size`` is a uniform multiplier: size=1 gives an 8.6--10.8 m tree,
depending on variant. No Blender dependency, global random state, or scene
side effects. The caller owns placement, clearance and material merging.
"""
import math
import json
from pathlib import Path


PALETTE = {
    'Trees': (.28, .42, .24), 'TreesLight': (.36, .50, .30),
    'TreesDark': (.18, .32, .15), 'Trunk': (.205, .165, .115),
}
_style_path=Path(__file__).resolve().parents[2]/'SourceAssets/GHS/Park/reference_style.json'
if _style_path.exists():
    _palette=json.loads(_style_path.read_text(encoding='utf-8'))['palette']
    PALETTE.update({k:_palette[k] for k in PALETTE if k in _palette})

# Five unequal, overlapping foliage masses form an irregular broadleaf crown.
# Their combined radius/height matches the prior placement envelope, while
# three supporting branches can be read in the open lower crown.
TREE_PROFILES = (
    ((.25,.05,6.45,2.35,2.20,2.15),(-2.05,.15,4.65,2.05,2.30,2.15),
     (1.90,-.20,4.20,2.25,2.05,2.15),(-.15,1.60,3.70,2.55,2.05,2.10),
     (.65,-1.55,5.10,2.30,1.95,2.30)),
    ((-.25,.10,8.20,2.10,1.95,2.60),(-1.65,.15,5.80,2.00,2.10,2.60),
     (1.60,-.30,5.20,2.15,2.00,2.55),(.05,1.45,4.25,2.35,1.85,2.25),
     (-.45,-1.45,6.45,2.20,1.85,2.60)),
    ((.50,.10,6.50,2.60,2.25,2.20),(-2.30,.10,4.55,2.30,2.25,2.25),
     (2.15,-.35,4.20,2.45,2.15,2.25),(-.20,1.70,3.85,2.80,2.05,2.15),
     (.65,-1.70,5.05,2.55,1.90,2.25)),
)
TREE_BASE_HEIGHTS=(8.60,10.80,8.70)
TREE_BASE_RADII=(4.05,3.70,4.60)


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


def _make_emitter(api,u,v,size,angle,base_z=.025):
    if size <= 0:
        raise ValueError('Vegetation size must be positive')
    ca,sa = math.cos(angle),math.sin(angle)
    stats = {'triangles':0, 'parts':0, 'height_m':0, 'radius_m':0}

    def emit(role,vertices,faces):
        transformed = [(u+size*(x*ca-y*sa),v+size*(x*sa+y*ca),base_z+size*z)
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


def _leaf_lobe(center,radii,phase):
    segments,rings=16,12
    vertices=[(center[0],center[1],center[2]+radii[2])]
    for ring in range(1,rings):
        phi=math.pi*ring/rings
        for j in range(segments):
            theta=math.tau*j/segments
            irregularity=.965+.045*math.sin(theta*3+phase+phi*.8)+.025*math.sin(theta*5-phase)
            vertices.append((center[0]+radii[0]*math.sin(phi)*math.cos(theta)*irregularity,
                             center[1]+radii[1]*math.sin(phi)*math.sin(theta)*irregularity,
                             center[2]+radii[2]*math.cos(phi)))
    bottom=len(vertices);vertices.append((center[0],center[1],center[2]-radii[2]))
    faces=[(0,1+j,1+(j+1)%segments) for j in range(segments)]
    for ring in range(rings-2):
        a=1+ring*segments;b=a+segments
        faces.extend((a+j,b+j,b+(j+1)%segments,a+(j+1)%segments) for j in range(segments))
    last=1+(rings-2)*segments
    faces.extend((bottom,last+(j+1)%segments,last+j) for j in range(segments))
    return vertices,faces


def build_tree(api,u,v,size=1,variant=0,base_z=.025):
    """Emit a 1856-triangle broadleaf tree with five unequal foliage masses.

    Returns actual geometry bounds for placement safety; base_z permits
    planting on raised forest islands without buried or floating tree roots.
    """
    variant=int(variant)%3;profile=TREE_PROFILES[variant]
    angle=(variant*2.399963+u*.037+v*.023)%(math.pi*2)
    emit,stats=_make_emitter(api,u,v,size,angle,base_z)
    _branch(emit,(0,0,0),(-.12,.06,3.60),.27,.16,sides=10)
    role=('Trees','TreesLight','TreesDark')[variant]
    lobes=[_leaf_lobe(p[:3],p[3:],variant*1.17+i*.83) for i,p in enumerate(profile)]
    max_radius=max(math.hypot(x,y) for vertices,_ in lobes for x,y,z in vertices)
    radial_scale=TREE_BASE_RADII[variant]/max_radius
    for vertices,faces in lobes:
        emit(role,[(x*radial_scale,y*radial_scale,z) for x,y,z in vertices],faces)
    for i in (1,2,3):
        x,y,z,rx,ry,rz=profile[i]
        _branch(emit,(-.08,.04,1.60+i*.08),
                (x*radial_scale*.72,y*radial_scale*.72,z-rz*.60),.15,.075,sides=6)
    if 'counts' in api:
        api['counts']['low_poly_trees']+=1
        api['counts']['clustered_broadleaf_trees']+=1
    stats.update(variant=variant,size=size,base_z_m=base_z,
                 crown_start_height_m=min(p[2]-p[5] for p in profile)*size)
    return stats


def build_shrub(api,u,v,size=.65,variant=0,base_z=.025):
    """Emit a dense, low round shrub; size=.65 gives ~0.9 m tall, 1.5 m wide.

    160 triangles. Green clusters sit below tree crowns and hide trunks, so
    repeated shrubs form the clipped hedge islands seen in the reference.
    """
    variant = int(variant)
    emit,stats = _make_emitter(api,u,v,size,variant*2.399963,base_z)
    _cluster(emit,(-.22,.04,.66),(.87,.84,.69),variant,
             'TreesDark' if variant%3==0 else 'Trees')
    _cluster(emit,(.42,-.11,.60),(.66,.70,.59),variant+4,'TreesLight')
    if 'counts' in api:
        api['counts']['landscape_shrubs'] += 1
    stats.update(variant=variant%3,size=size)
    return stats
