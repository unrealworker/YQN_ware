"""GHS carton/pallet detail rules adapted to the MPR bulk Geometry interface.

No bpy, Unreal, global scene state, file writes, or imports of executable GHS
builders. The source is Scripts/ghs/build_refined_rack_cargo.py::carton/pallet.
Use each measured MPR cargo envelope as one carton; never copy the GHS rack's
four-cartons-per-layer or stack-count rules into MPR dense small-item shelves.
"""
from itertools import combinations, product
import math

ROLES = ('Cargo', 'CargoSeam', 'Charcoal', 'Cobalt')
PREVIEW_PALETTE = {
    'Cargo': [.76, .80, .85],
    'CargoSeam': [.51, .57, .64],
    'Charcoal': [.055, .075, .11],
    'Cobalt': [.018, .075, .51],
}
MATERIAL_PATHS = {role: '/Game/GHSZcoolSmartFactory/Materials/M_Zcool_' + role for role in ROLES}
PROVENANCE = {
    'geometry_source': 'Scripts/ghs/build_refined_rack_cargo.py::carton/pallet',
    'style_source': 'Scripts/ghs/build_zcool_smart_factory.py::STYLE',
    'edge_radius_m': .004,
    'packing_tape_width_m': .024,
    'label_dimensions_m': [.078, .052],
    'adaptation': 'The GHS detail vocabulary is fitted inside each existing MPR envelope. No GHS pallet-stack counts or rack geometry are imported.',
}


def _outward(points, center):
    a, b, c = points[:3]
    u = [b[i]-a[i] for i in range(3)]
    v = [c[i]-a[i] for i in range(3)]
    normal = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
    offset = [sum(p[i] for p in points)/len(points)-center[i] for i in range(3)]
    return list(reversed(points)) if sum(normal[i]*offset[i] for i in range(3)) < 0 else points


def _face(g, name, role, points, center):
    points = _outward(points, center)
    g.mesh(name, role, points, [tuple(range(len(points)))])


def _beveled_box(g, name, role, center, size, radius):
    """Single-segment 4 mm chamfer matching GHS without thousands of Blender objects."""
    half = [s/2 for s in size]
    r = min(radius, min(size)*.2)
    inner = [h-r for h in half]
    vertices, faces, lookup = [], [], {}

    def add_face(local):
        points = [[center[i]+p[i] for i in range(3)] for p in local]
        indices = []
        for point in _outward(points, center):
            key = tuple(round(v, 12) for v in point)
            if key not in lookup:
                lookup[key] = len(vertices)
                vertices.append(tuple(point))
            indices.append(lookup[key])
        faces.append(tuple(indices))

    for axis in range(3):
        b, c = [i for i in range(3) if i != axis]
        for sign in (-1, 1):
            points = []
            for sb, sc in ((-1,-1),(1,-1),(1,1),(-1,1)):
                p = [0., 0., 0.]
                p[axis], p[b], p[c] = sign*half[axis], sb*inner[b], sc*inner[c]
                points.append(p)
            add_face(points)
    for a, b in combinations(range(3), 2):
        c = next(i for i in range(3) if i not in (a, b))
        for sa, sb in product((-1,1), repeat=2):
            points = []
            for axis, sc in ((a,-1),(a,1),(b,1),(b,-1)):
                p = [0., 0., 0.]
                p[a] = sa*(half[a] if axis == a else inner[a])
                p[b] = sb*(half[b] if axis == b else inner[b])
                p[c] = sc*inner[c]
                points.append(p)
            add_face(points)
    for signs in product((-1,1), repeat=3):
        add_face([[signs[i]*(half[i] if i == axis else inner[i]) for i in range(3)] for axis in range(3)])
    assert len(vertices) == 24 and len(faces) == 26
    g.mesh(name, role, vertices, faces)


def add_carton(g, mesh_name, center, size, lod=0, *, facing=None,
               body_role='Cargo', seam_role='CargoSeam', label_role='Charcoal'):
    """Add exactly one GHS-style carton inside the caller's existing MPR envelope.

    Arguments match Geometry.box: center=(x,y,z), size=(width,depth,height),
    metres. Caller must apply the existing F7 beam-clearance fit before calling.
    LOD0 uses the GHS bevel plus front/top packing tape and a shipping label.
    LOD1 keeps tape/label without bevel; LOD2 keeps only the bounded carton.
    facing=-1/+1 selects aisle-facing Y. By default select the outside rack face.
    No pallet is added here, even when the carton is tall.
    """
    x, y, z = map(float, center)
    w, d, h = map(float, size)
    assert min(w,d,h) > .001 and lod in (0,1,2)
    facing = (-1 if y <= 0 else 1) if facing is None else facing
    assert facing in (-1,1)
    if lod == 2:
        g.box(mesh_name, body_role, (x,y,z), (w,d,h))
        return {'carton_count':1, 'pallet_count':0, 'detail_planes':0, 'bounded_size_m':[w,d,h]}
    # GHS decals normally project 0.4 mm outside the carton. Recess only the
    # underlying front/top body by 0.5 mm so details retain the exact CAD bounds.
    inset = min(.0005, min(w,d,h)*.001)
    body_center = (x, y-facing*inset/2, z-inset/2)
    body_size = (w, d-inset, h-inset)
    if lod == 0:
        _beveled_box(g, mesh_name, body_role, body_center, body_size, .004)
    else:
        g.box(mesh_name, body_role, body_center, body_size)
    front, top = y+facing*d/2, z+h/2
    tape = min(.024, w*.12)
    margin = min(.006, h*.08, d*.08)
    _face(g,mesh_name,seam_role,
          [(x-tape/2,front,z-h/2+margin),(x+tape/2,front,z-h/2+margin),
           (x+tape/2,front,z+h/2-margin),(x-tape/2,front,z+h/2-margin)],(x,y,z))
    _face(g,mesh_name,seam_role,
          [(x-tape/2,y-d/2+margin,top),(x+tape/2,y-d/2+margin,top),
           (x+tape/2,y+d/2-margin,top),(x-tape/2,y+d/2-margin,top)],(x,y,z))
    lw, lh = min(.078,w*.22), min(.052,h*.18)
    lx, lz = x+w*.25, z+h*.15
    _face(g,mesh_name,label_role,
          [(lx-lw/2,front,lz-lh/2),(lx+lw/2,front,lz-lh/2),
           (lx+lw/2,front,lz+lh/2),(lx-lw/2,front,lz+lh/2)],(x,y,z))
    return {'carton_count':1,'pallet_count':0,'detail_planes':3,'bounded_size_m':[w,d,h],
            'source':'GHS refined carton: bevel + packing tape + shipping label'}


def add_pallet(g, mesh_name, center, size, lod=0, *, role='Cobalt'):
    """Add GHS runners/blocks/deck boards within an EXISTING pallet envelope.

    center/size use Geometry.box convention. Use only for CAD floor pallets and
    F5/F7 pallet loads; the helper never decides to add a pallet to small cartons.
    """
    x,y,z = map(float,center)
    w,d,ph = map(float,size)
    assert min(w,d,ph) > .001 and lod in (0,1,2)
    base = z-ph/2
    if lod == 2:
        g.box(mesh_name,role,(x,y,z),(w,d,ph))
        return {'pallet_count':1,'parts':1}
    deck = min(.018,ph*.22)
    rw = min(.10,w*.13)
    board_depth = min(.13,d/6)
    spacer = ph-2*deck
    for sx in (-1,0,1):
        xx=x+sx*(w/2-rw/2)
        if lod == 0:
            g.box(mesh_name,role,(xx,y,base+deck/2),(rw,d,deck))
            block_depth=min(.12,d/6)
            for sy in (-1,0,1):
                g.box(mesh_name,role,(xx,y+sy*(d/2-block_depth/2),base+deck+spacer/2),
                      (rw,block_depth,spacer))
        else:
            g.box(mesh_name,role,(xx,y,base+(ph-deck)/2),(rw,d,ph-deck))
    for i in range(5):
        yy=y-(d-board_depth)/2+i*(d-board_depth)/4
        g.box(mesh_name,role,(x,yy,base+ph-deck/2),(w,board_depth,deck))
    return {'pallet_count':1,'parts':17 if lod == 0 else 8,
            'source':'GHS refined pallet: three runners, nine blocks, five deck boards'}


def add_pallet_load(g, mesh_name, center, size, lod=0, *, pallet_height=.14,
                    max_carton_height=.35, facing=None,
                    body_role='Cargo', seam_role='CargoSeam',
                    label_role='Charcoal', pallet_role='Cobalt'):
    """Place a GHS-style 2x2 carton stack inside ONE MPR CAD load envelope.

    center/size describe the whole CAD envelope, including an existing pallet.
    Use for F5/F7 and F17 floor loads. Pass pallet_height=0 for F9, whose CAD
    does not specify a pallet. Apply any measured beam-clearance fit to size[2]
    before calling. This is visual packing inside one CAD position: individual
    rendered carton count must never replace the CAD position/envelope count.

    GHS carton width/depth caps are 0.45/0.55 m with 20 mm horizontal gaps.
    Carton height is at most 0.35 m; layer count is chosen to fit the given load
    height. Cartons touch vertically; 4 mm bevels provide the fine visual seams.
    """
    x,y,z = map(float,center)
    w,d,h = map(float,size)
    ph = float(pallet_height)
    assert lod in (0,1,2) and min(w,d,h) > .02
    assert 0 <= ph < h-.01 and 0 < max_carton_height <= .35
    base = z-h/2
    if ph:
        add_pallet(g,mesh_name,(x,y,base+ph/2),(w,d,ph),lod,role=pallet_role)
    gap = min(.020, min(w,d)*.06)
    cw,cd = min(.45,(w-gap)/2), min(.55,(d-gap)/2)
    available = h-ph
    layers = max(1,math.ceil(available/max_carton_height-1e-9))
    ch = available/layers
    margin_x = max(0., w/2-cw-gap/2)
    margin_y = max(0., d/2-cd-gap/2)
    shifts = []
    for layer in range(layers):
        dx = min(.012,margin_x)*(-1 if layer%2 == 0 else 1)
        dy = min(.008,margin_y)*(1 if layer%2 == 0 else -1)
        shifts.append([dx,dy])
        bottom = base+ph+layer*ch
        for ix,iy in product((-1,1),repeat=2):
            cx=x+ix*(cw+gap)/2+dx
            cy=y+iy*(cd+gap)/2+dy
            assert abs(cx-x)+cw/2 <= w/2+1e-9
            assert abs(cy-y)+cd/2 <= d/2+1e-9
            add_carton(g,mesh_name,(cx,cy,bottom+ch/2),(cw,cd,ch),lod,
                       facing=facing,body_role=body_role,seam_role=seam_role,label_role=label_role)
    return {'cad_envelope_count':1, 'carton_count':layers*4,
            'pallet_count':int(ph>0), 'layers':layers, 'cartons_per_layer':4,
            'carton_size_m':[cw,cd,ch], 'horizontal_gap_m':gap,
            'vertical_gap_m':0., 'layer_shifts_m':shifts,
            'bounded_size_m':[w,d,h], 'pallet_height_m':ph,
            'inferred_visual_loading':True,
            'basis':'GHS individual-carton presentation packed within the unchanged MPR CAD cargo-position envelope; carton count is illustrative, not a new CAD storage-position count.'}
