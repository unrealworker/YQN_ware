"""Measured CAD silhouettes for four-cell frames and the V-roller merge.

XY linework is source evidence. Z, wall thickness and supports are presentation
assumptions: the supplied drawing is a plan and contains no machine elevations.
The 321321 block has four separate frames, not evidence of a continuous belt.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'SourceAssets/MPR/operations/cad_detail_geometry.json'

# Each pair is the two long edges of one physical roller in source INSERT 2E886D.
ROLLER_EDGE_PAIRS = [
    ('F4D30', 'F4D31'), ('F4D34', 'F4D35'), ('F4D38', 'F4D39'),
    ('F4D3C', 'F4D3D'), ('F4D40', 'F4D41'), ('F4D42', 'F4D43'),
    ('F4D46', 'F4D47'), ('F4D4A', 'F4D4B'), ('F4D5B', 'F4D5C'),
    ('F4D5F', 'F4D60'), ('F4D61', 'F4D62'), ('F4DC3', 'F4DC4'),
    ('F4E21', 'F4E22'), ('F4E23', 'F4E24'), ('F4E25', 'F4E26'),
    ('F4E27', 'F4E28'), ('F4E29', 'F4E2A'), ('F4E2B', 'F4E2C'),
    ('F4E2D', 'F4E2E'), ('F4E9B', 'F4E9C'), ('F4DF0', 'F4DF1'),
    ('F4DF4', 'F4DF5'), ('F4DF6', 'F4DF7'), ('F4DF8', 'F4DF9'),
]


def _local(point, placement, native):
    """Bake source reflection into vertices; instance scales remain positive."""
    theta = math.radians(-placement['rotation_deg'])
    c, s = math.cos(theta), math.sin(theta)
    x, y = [point[k] - placement['position_m'][k] for k in range(2)]
    return [(c*x-s*y)*native[0]/placement['size_m'][0],
            (s*x+c*y)*native[1]/placement['size_m'][1]]


def _bounds(points):
    return [[min(p[k] for p in points), max(p[k] for p in points)] for k in range(2)]


def extract_details(source_path, output_path=INPUT):
    """Extract selected real CAD edge handles, without importing the full scene."""
    source_path = Path(source_path)
    evidence = json.loads(source_path.read_text(encoding='utf8'))
    rows = {row['handles'][0]: row for row in evidence['representative_types']}
    source = Path(evidence['source'])
    result = dict(schema_version=1, source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  intermediate_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
                  units='metres; CAD +Y; local geometry has source mirror baked', blocks={})
    row = rows['2D41DC']
    lines = {g['h'][-1]: g for g in row['geometry']}
    native = [.415, 2.38]
    cells = []
    # Four complete independent round-corner frames. External vertical edges
    # and horizontal edges determine each measured outside rectangle.
    selectors = [
        ('27ACBF','27ACC8','27AC09','27ACC6','27ACCB','27ACCC','27AC0D','27ACCA'),
        ('27ACE4','27ACDE','27AC20','27ACDD','27ACE9','27ACEB','27AC2D','27ACEA'),
        ('27ACCE','27ACD2','27AC13','27ACD0','27ACDA','27ACDC','27AC1E','27ACDB'),
        ('27ACF3','27ACF2','27AC37','27ACF4','27ACF6','27ACFA','27AC3B','27ACF8'),
    ]
    for handles in selectors:
        groups = []
        for subset in (handles[:4], handles[4:]):
            pts = [p for handle in subset for p in lines[handle]['p']]
            groups.append(_bounds([_local(p,row['placement'],native) for p in pts]))
        cells.append(dict(outer_bounds_m=groups[0], inner_bounds_m=groups[1], source_edge_handles=list(handles),
                          outer_corner_radius_m=.04260, inner_corner_radius_m=.01716))
    result['blocks']['321321'] = dict(mesh='SM_MPR_CollectionCellsCAD', native_size_m=native,
        reference_placement=row['placement'], source_handles=row['handles'], cells=cells,
        interpretation='Four separate framed cells. Contents and process direction unconfirmed; no continuous belt.',
        height_assumptions='Frame top 0.99m and support height 0.76m retain prior display envelope; not CAD elevations.')
    row = rows['2E886D']
    lines = {g['h'][-1]: g for g in row['geometry']}
    native = row['placement']['size_m']
    rollers = []
    for handles in ROLLER_EDGE_PAIRS:
        a,b = [list(map(list, lines[h]['p'])) for h in handles]
        if math.dist(a[0], b[0])+math.dist(a[1], b[1]) > math.dist(a[0], b[1])+math.dist(a[1], b[0]):
            b.reverse()
        direction = [a[1][k]-a[0][k] for k in range(2)]
        length = math.hypot(*direction)
        diameter = abs(direction[0]*(b[0][1]-a[0][1])-direction[1]*(b[0][0]-a[0][0]))/length
        assert .053 < diameter < .055, (handles, diameter)
        axis = [[(p[k]+q[k])/2 for k in range(2)] for p,q in zip(a,b)]
        rollers.append(dict(axis_m=[_local(p,row['placement'],native) for p in axis],
                            diameter_m=diameter, source_edge_handles=list(handles)))
    # Side rails follow CAD outer-edge lines; neither of the angled transfer
    # ends nor the narrow straight outlet is closed by an above-bed crossbar.
    rails = []
    for handles in [('F4EE4','F5023'), ('F534E','F5215')]:
        points = [p for h in handles for p in lines[h]['p']]
        ends = max(((a,b) for a in points for b in points),key=lambda pair:math.dist(*pair))
        rails.append(dict(axis_m=[_local(p,row['placement'],native) for p in ends], source_edge_handles=list(handles)))
    raw = [p for g in row['geometry'] for p in g['p']]
    result['blocks']['Y型汇流机'] = dict(mesh='SM_MPR_YMergeCAD',native_size_m=native,
        reference_placement=row['placement'],source_handles=row['handles'],rollers=rollers,side_rails=rails,
        cad_local_bounds_m=_bounds([_local(p,row['placement'],native) for p in raw]),
        interpretation='Two mirrored banks of twelve diagonal rollers; exact axes derived from paired CAD edges.',
        height_assumptions='All roller tops at 1.035m to match adjacent existing conveyor surface; supports inferred, not CAD elevations.')
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result


def _rounded_rect(bounds, radius, steps=4):
    (x0,x1),(y0,y1)=bounds
    radius=min(radius,(x1-x0)/2,(y1-y0)/2)
    points=[]
    for cx,cy,start in [(x1-radius,y1-radius,0),(x0+radius,y1-radius,90),
                         (x0+radius,y0+radius,180),(x1-radius,y0+radius,270)]:
        for i in range(steps+1):
            angle=math.radians(start+90*i/steps)
            points.append((cx+radius*math.cos(angle),cy+radius*math.sin(angle)))
    return points


def _ring(g,name,outer,inner,bottom,top):
    assert len(outer)==len(inner)
    n=len(outer)
    vertices=[(x,y,z) for points,z in [(outer,bottom),(outer,top),(inner,bottom),(inner,top)] for x,y in points]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces.extend([(i,j,j+n,i+n),(i+2*n,i+3*n,j+3*n,j+2*n),
                      (i+n,j+n,j+3*n,i+3*n),(i,i+2*n,j+2*n,j)])
    g.mesh(name,'Cobalt',vertices,faces)


def _rod(g,name,points,radius,top,segments=8):
    a,b=points
    dx,dy=b[0]-a[0],b[1]-a[1]
    length=math.hypot(dx,dy)
    nx,ny=-dy/length,dx/length
    center_z=top-radius
    vertices=[(p[0]+nx*radius*math.cos(i*2*math.pi/segments),
               p[1]+ny*radius*math.cos(i*2*math.pi/segments),
               center_z+radius*math.sin(i*2*math.pi/segments)) for p in points for i in range(segments)]
    faces=[tuple(range(segments-1,-1,-1)),tuple(range(segments,2*segments))]
    faces.extend((i,(i+1)%segments,(i+1)%segments+segments,i+segments) for i in range(segments))
    g.mesh(name,'Metal',vertices,faces)


def add_cad_detail_meshes(g, evidence_path=INPUT):
    """Populate Geometry without importing bpy or modifying other mesh data."""
    data=json.loads(Path(evidence_path).read_text(encoding='utf8'))['blocks']
    row=data['321321'];name=row['mesh']
    for cell in row['cells']:
        outer=_rounded_rect(cell['outer_bounds_m'],cell['outer_corner_radius_m'])
        inner=_rounded_rect(cell['inner_bounds_m'],cell['inner_corner_radius_m'])
        _ring(g,name,outer,inner,.82,.99)
        g.prism(name,'Porcelain',inner,.805,.83)
    # Two low rails and four legs support the four frames. There is no belt,
    # motor, arrow or roller primitive whose function the drawing does not show.
    for x in (-.16,.16):
        g.box(name,'Metal',(x,0,.785),(.035,2.32,.04))
        for y in (-.96,.96):
            g.box(name,'Metal',(x,y,.38),(.045,.045,.76))
            g.box(name,'Charcoal',(x,y,.025),(.08,.08,.05))
    row=data['Y型汇流机'];name=row['mesh']
    for roller in row['rollers']:
        _rod(g,name,roller['axis_m'],roller['diameter_m']/2,1.035)
    for rail in row['side_rails']:
        a,b=rail['axis_m']
        g.segment(name,'Cobalt',a,b,.012,.95,.11)
        # Support centers inset from both rail ends, inside measured footprint.
        for t in (.12,.88):
            p=[a[k]+(b[k]-a[k])*t for k in range(2)]
            p=[p[k]*.9 for k in range(2)]
            g.box(name,'Metal',(*p,.435),(.04,.04,.87))
            g.box(name,'Charcoal',(*p,.02),(.065,.065,.04))
    # Below-bed tie connects the two side frames without obstructing transfer.
    for t in (.15,.85):
        points=[]
        for rail in row['side_rails']:
            a,b=rail['axis_m'];points.append([a[k]+(b[k]-a[k])*t for k in range(2)])
        g.segment(name,'Metal',*points,.035,.86,.04)
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--extract',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=INPUT)
    args=parser.parse_args()
    result=extract_details(args.extract,args.output)
    print(json.dumps({key:dict(mesh=row['mesh'],native_size_m=row['native_size_m'],
                              parts=len(row.get('cells',row.get('rollers',[]))))
                      for key,row in result['blocks'].items()},ensure_ascii=False))
