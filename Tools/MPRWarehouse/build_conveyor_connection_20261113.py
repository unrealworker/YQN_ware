"""Build only the source 2D457E wheel-sorter connection in a private Blender process.

XY comes from the source DXF boundaries in cad_evidence.json. Z follows the
adjacent existing conveyor, as the source plan has no elevation dimensions.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from mpr_blender_common import Geometry

OUT = ROOT / 'SourceAssets/MPR/conveyor_connection_20261113'
NAME = 'SM_MPR_CAD_2D457E_Connected'
g = Geometry()
evidence = json.loads((OUT / 'cad_evidence.json').read_text(encoding='utf8'))
spine = evidence['spine']
cx, width = spine['center_x'], spine['width']
y0, y1 = spine['y_range']
surfaces = []


def box(role, p, size):
    g.box(NAME, role, p, size)


def cylinder(role, center, radius, length, axis='x', sides=8):
    vertices = []
    for end in (-1, 1):
        for i in range(sides):
            a = 2 * math.pi * i / sides
            p = [end * length / 2, radius * math.cos(a), radius * math.sin(a)]
            if axis == 'y':
                p = [-p[1], p[0], p[2]]
            vertices.append(tuple(center[j] + p[j] for j in range(3)))
    faces = [tuple(range(sides - 1, -1, -1)), tuple(range(sides, 2 * sides))]
    faces += [(i, (i + 1) % sides, (i + 1) % sides + sides, i + sides) for i in range(sides)]
    g.mesh(NAME, role, vertices, faces)


def surface(points, kind):
    g.prism(NAME, 'Metal', points, .92, .955)
    surfaces.append(dict(kind=kind, points=points))


def leg(x, y):
    box('Metal', (x, y, .46), (.055, .055, .9))
    box('Rubber', (x, y, .025), (.13, .13, .05))


surface([[cx-width/2,y0], [cx+width/2,y0], [cx+width/2,y1], [cx-width/2,y1]], 'continuous_spine')
modules = [(-60.64666168 + i*1.28042647, -59.98644178 + i*1.28042647) for i in range(5)]
count = math.ceil((y1-y0)/.12)
for i in range(count):
    y = y0 + .06 + i*(y1-y0-.12)/(count-1)
    if not any(a-.04 < y < b+.04 for a,b in modules):
        cylinder('Metal', (cx,y,1), .035, width-.11)
for a,b in modules:
    # The CAD wheel modules use small discrete wheels, not a transverse bar.
    for row in range(6):
        for col in range(5):
            cylinder('Rubber', (cx+(col-2)*.145,a+.065+row*(b-a-.13)/5,1), .035,.095)

for branch in evidence['branches']:
    points = branch['points']
    surface(points, 'branch_%s_%s' % (branch['side'], branch['index']))
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    count = math.ceil((xmax-xmin)/branch['roller_pitch_m'])
    for i in range(count):
        x = xmin + .045 + i*(xmax-xmin-.09)/(count-1)
        hits = []
        for p,q in zip(points,points[1:]+points[:1]):
            if abs(q[0]-p[0]) > 1e-8 and min(p[0],q[0]) <= x <= max(p[0],q[0]):
                hits.append(p[1] + (x-p[0])*(q[1]-p[1])/(q[0]-p[0]))
        lo, hi = min(hits),max(hits)
        cylinder('Metal', (x,(lo+hi)/2,1),.035,hi-lo-.10,'y')
    # Leave the spine throat and outfeed face open for transfers.
    for i,j in ((0,1),(1,2),(3,4)):
        g.segment(NAME,'Cobalt',points[i],points[j],.04,.96,.14)
    outx = points[2][0]
    endx = branch['extension_end_x']
    lo, hi = points[2][1],points[3][1]
    deck = [[outx,lo],[endx,lo],[endx,hi],[outx,hi]]
    surface(deck, 'outfeed_%s_%s' % (branch['side'], branch['index']))
    # Plain transfer decks in the CAD are retained at roller top elevation.
    g.prism(NAME,'Metal',deck,.955,1.035)
    for y in (lo,hi):
        g.segment(NAME,'Cobalt',(outx,y),(endx,y),.04,.96,.14)
    for y in (lo+.10,hi-.10):
        leg(endx-branch['side']*.10,y)

# Side frame rails are interrupted only at the ten CAD branching throats.
for side in (-1,1):
    cursor=y0
    throats=sorted((b['points'][0][1],b['points'][4][1]) for b in evidence['branches'] if b['side']==side)
    x=cx+side*width/2
    for lo,hi in throats+[(y1,y1)]:
        if lo>cursor:
            g.segment(NAME,'Cobalt',(x,cursor),(x,lo),.045,.94,.14)
        cursor=max(cursor,hi)
for y in [y0+.25,y0+2.1,y0+4.1,y0+6.1,y0+8.1,y0+10.1,y1-.25]:
    for side in (-1,1):
        leg(cx+side*.34,y)
    box('Metal',(cx,y,.36),(.74,.05,.05))

# Original receiving frame footprint: an OPEN frame, not four filled beds.
fx0,fy0,fx1,fy1=evidence['receiving_frame']['bounds_m']
for x in (fx0,fx1):
    for y in (fy0,fy1):
        leg(x,y)
    g.segment(NAME,'Metal',(x,fy0),(x,fy1),.05,.90,.07)
for y in (fy0,fy1):
    g.segment(NAME,'Metal',(fx0,y),(fx1,y),.05,.90,.07)

manifest=g.export(OUT,'MPR_ConveyorConnection_20261113',dict(source_handle='2D457E',
    source_block=evidence['source_block'],height_basis=evidence['height_basis'],
    roller_center_z_m=1.,roller_top_z_m=1.035,branch_count=10,wheel_modules=5,
    surface_polygons=surfaces,layout_scope='Only 2D457E; no bridges to 2D4587 or 2D45D9'))
assert len(manifest['meshes'])==1 and manifest['meshes'][0]['triangles']<25000
