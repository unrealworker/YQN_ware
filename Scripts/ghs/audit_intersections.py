"""Pure-Python overlap audit; reads registry/source geometry and never writes UE assets.

All calculations use the source CAD metre frame. Mirroring Y for UE is an
isometry and does not change intersections. A whole rack OBB is conservative:
the narrow phase uses inset solid boxes from the actual storage mesh recipe,
excluding transparent envelope planes and decorative seams/diagonal beams.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EPS = .001  # Ignore surface contact / penetration of at most 1 mm.
GROUPS = {
    'GHS_CAD_Columns': 'column', 'GHS_ColumnBases': 'column_base',
    'GHS_CAD_PalletCargo': 'cargo', 'GHS_CAD_Racks': 'rack',
    'GHS_CAD_DockRacks': 'dock_rack',
}


@dataclass
class Box:
    x: float
    y: float
    hx: float
    hy: float
    co: float
    si: float
    zmin: float
    zmax: float
    name: str = ''

    @property
    def axes(self):
        return ((self.co, self.si), (-self.si, self.co))

    @property
    def aabb(self):
        ex = abs(self.co) * self.hx + abs(self.si) * self.hy
        ey = abs(self.si) * self.hx + abs(self.co) * self.hy
        return self.x-ex, self.y-ey, self.x+ex, self.y+ey

    @property
    def corners(self):
        return [(self.x+self.co*x-self.si*y, self.y+self.si*x+self.co*y)
                for x, y in [(-self.hx, -self.hy), (self.hx, -self.hy),
                             (self.hx, self.hy), (-self.hx, self.hy)]]


def sat(a, b):
    """Exact OBB SAT for vertical prisms; returns minimum separation distance."""
    dz = min(a.zmax, b.zmax) - max(a.zmin, b.zmin)
    if dz <= EPS:
        return None
    minimum = float('inf')
    for x, y in a.axes + b.axes:
        ra = a.hx*abs(x*a.co+y*a.si) + a.hy*abs(-x*a.si+y*a.co)
        rb = b.hx*abs(x*b.co+y*b.si) + b.hy*abs(-x*b.si+y*b.co)
        penetration = ra+rb-abs((b.x-a.x)*x+(b.y-a.y)*y)
        if penetration <= EPS:
            return None
        minimum = min(minimum, penetration)
    return minimum, dz


def intersection_polygon(a, b):
    poly = a.corners
    corners = b.corners
    for start, end in zip(corners, corners[1:] + corners[:1]):
        def distance(p):
            return (end[0]-start[0])*(p[1]-start[1])-(end[1]-start[1])*(p[0]-start[0])
        out = []
        for p, q in zip(poly, poly[1:] + poly[:1]):
            dp, dq = distance(p), distance(q)
            if dp >= -1e-10:
                out.append(p)
            if (dp >= 0) != (dq >= 0):
                t = dp/(dp-dq)
                out.append((p[0]+t*(q[0]-p[0]), p[1]+t*(q[1]-p[1])))
        poly = out
        if not poly:
            break
    return poly


def polygon_area(poly):
    return abs(sum(p[0]*q[1]-q[0]*p[1]
                   for p, q in zip(poly, poly[1:]+poly[:1]))) / 2 if poly else 0


def source_solids():
    """Execute only the local primitive recipe with pure-data collector stubs."""
    source = (ROOT/'Scripts/video_reference/build_storage.py').read_text(encoding='utf-8')
    recipe = source[source.index("begin_asset('SM_VR_PalletCargo')"):
                    source.index("begin_asset('SM_VR_LM_Pad')")]
    result, active = {}, [None]

    def begin_asset(name):
        active[0] = name.replace('SM_VR_', 'SM_GHS_Shared_')
        result[active[0]] = []

    def box(name, location, size, material, edge=.006):
        # Uniformly inset by the bevel width. Every retained box is inside the
        # original beveled solid, so its intersection is a positive witness.
        inset = min(edge, min(size)*.2)
        core_size = [max(0, value-2*inset) for value in size]
        result[active[0]].append((name, tuple(location), tuple(core_size)))

    noop = lambda *args, **kwargs: None
    namespace = dict(begin_asset=begin_asset, box=box, beam=noop, curve=noop,
                     stripe=noop, mesh=noop, math=math)
    for name in ['blue', 'cargo', 'cyan', 'steel', 'steel_light', 'dark',
                 'bin_blue', 'bin_inner', 'ghost']:
        namespace[name] = name
    exec(compile(recipe, '<storage-solid-data-recipe>', 'exec'), namespace)
    return result


def transformed_box(record, center, size, name=''):
    sx, sy, sz = record.get('scale', [1, 1, 1])
    angle = math.radians(record.get('rotation_deg', 0))
    co, si = math.cos(angle), math.sin(angle)
    px, py, pz = record['position_m']
    x, y, z = center[0]*sx, center[1]*sy, center[2]*sz
    return Box(px+co*x-si*y, py+si*x+co*y,
               abs(size[0]*sx)/2, abs(size[1]*sy)/2, co, si,
               pz+z-abs(size[2]*sz)/2, pz+z+abs(size[2]*sz)/2, name)


def bounds_box(record, bounds):
    return transformed_box(record, [(a+b)/2 for a, b in bounds],
                           [b-a for a, b in bounds])


def audit(registry_path, output_path):
    registry_bytes = registry_path.read_bytes()
    registry = json.loads(registry_bytes)
    storage = json.loads((ROOT/'SourceAssets/VideoReference/storage.json').read_text())
    bounds = {m['name'].replace('SM_VR_', 'SM_GHS_Shared_'): m['bounds_m']
              for m in storage['meshes']}
    bounds['Cube'] = [[-.5, .5]]*3
    source_parts = source_solids()
    objects, grid = [], defaultdict(list)
    cell_size = 4.0
    for group in registry['groups']:
        if group['actor'] not in GROUPS:
            continue
        for index, record in enumerate(group['instances']):
            outer = bounds_box(record, bounds[group['mesh']])
            obj = dict(kind=GROUPS[group['actor']], actor=group['actor'], index=index,
                       id=record['id'], mesh=group['mesh'], record=record, box=outer)
            objects.append(obj)
            x0, y0, x1, y1 = outer.aabb
            for x in range(math.floor(x0/cell_size), math.floor(x1/cell_size)+1):
                for y in range(math.floor(y0/cell_size), math.floor(y1/cell_size)+1):
                    grid[(x, y)].append(len(objects)-1)

    cores = {}

    def core_boxes(i):
        if i not in cores:
            obj = objects[i]
            if obj['mesh'] == 'Cube':
                cores[i] = [obj['box']]
            else:
                cores[i] = [transformed_box(obj['record'], center, size, name)
                            for name, center, size in source_parts[obj['mesh']]]
        return cores[i]

    def witness(i, j):
        a_outer, b_outer = objects[i]['box'], objects[j]['box']
        # Prune each object's primitives against the other's full bounds first.
        aa = [p for p in core_boxes(i) if sat(p, b_outer)]
        bb = [p for p in core_boxes(j) if sat(p, a_outer)]
        for a in aa:
            for b in bb:
                overlap = sat(a, b)
                if overlap:
                    poly = intersection_polygon(a, b)
                    return dict(a_part=a.name or 'solid column cube',
                                b_part=b.name or 'solid column cube',
                                xy_penetration_m=overlap[0], z_overlap_m=overlap[1],
                                xy_area_m2=polygon_area(poly),
                                point_m=[sum(p[0] for p in poly)/len(poly),
                                         sum(p[1] for p in poly)/len(poly),
                                         (max(a.zmin,b.zmin)+min(a.zmax,b.zmax))/2])
        return None

    seen, results, stats = set(), [], defaultdict(Counter)
    storage_kinds = {'cargo', 'rack', 'dock_rack'}
    all_kinds = sorted(set(GROUPS.values()))
    for offset, a_kind in enumerate(all_kinds):
        for b_kind in all_kinds[offset:]:
            if {a_kind, b_kind} & storage_kinds:
                stats['_vs_'.join([a_kind, b_kind])].update(
                    candidate_pairs=0, obb_overlaps=0,
                    confirmed_solid_core_intersection=0, bounds_only_unresolved=0)
    for candidates in grid.values():
        for offset, i in enumerate(candidates):
            for j in candidates[offset+1:]:
                pair = (min(i,j), max(i,j))
                if pair in seen:
                    continue
                seen.add(pair)
                a, b = objects[pair[0]], objects[pair[1]]
                if not ({a['kind'], b['kind']} & storage_kinds):
                    continue
                category = '_vs_'.join(sorted([a['kind'], b['kind']]))
                stats[category]['candidate_pairs'] += 1
                overlap = sat(a['box'], b['box'])
                if not overlap:
                    continue
                stats[category]['obb_overlaps'] += 1
                solid = witness(*pair)
                status = 'confirmed_solid_core_intersection' if solid else 'bounds_only_unresolved'
                stats[category][status] += 1
                row = dict(category=category, status=status,
                           a={k:a[k] for k in ['kind','actor','index','id']},
                           b={k:b[k] for k in ['kind','actor','index','id']},
                           a_position_m=a['record']['position_m'], b_position_m=b['record']['position_m'],
                           xy_penetration_m=overlap[0], z_overlap_m=overlap[1],
                           xy_overlap_area_m2=polygon_area(intersection_polygon(a['box'],b['box'])))
                if solid:
                    row['solid_witness'] = solid
                results.append(row)
    results.sort(key=lambda r:(r['status']!='confirmed_solid_core_intersection',
                               -r['xy_overlap_area_m2'], r['category']))
    counts = Counter(obj['kind'] for obj in objects)
    confirmed = [r for r in results if r['status']=='confirmed_solid_core_intersection']
    affected = defaultdict(set)
    for row in confirmed:
        for key in ['a','b']:
            affected[row[key]['kind']].add(row[key]['id'])
    map_path = ROOT/'Content/Maps/GHS_CAD_DigitalTwin.umap'
    verification_path = ROOT/'Saved/GHS_Verification.json'
    verification = json.loads(verification_path.read_text()) if verification_path.exists() else {}
    report = dict(success=True, audit_completed=True, production_assets_modified=False,
                  created_utc=datetime.now(timezone.utc).isoformat(),
                  input_registry=str(registry_path), registry_sha256=hashlib.sha256(registry_bytes).hexdigest(),
                  saved_map_sha256=hashlib.sha256(map_path.read_bytes()).hexdigest(),
                  previously_verified_saved_level_matches_registry=bool(verification.get('success') and
                      verification.get('all_hism_world_transforms_verified')),
                  coordinate_frame='CAD metres; equivalent to UE (x,-y)*100 centimetres',
                  tolerance_m=EPS, counts=dict(counts),
                  method='Spatial grid -> exact XY OBB SAT with Z overlap -> source beveled-box inset cores',
                  bounds_source='SourceAssets/VideoReference/storage.json exported source FBX geometry bounds; Engine Cube 1m',
                  limitations=[
                      'CAD symbol size_m is a conservative annotation-inclusive bbox, not an independently measured physical footprint.',
                      'Whole-rack bounds include empty space and transparent ghost envelope; bounds-only results do not prove solid collision.',
                      'Confirmed results intersect inset core boxes fully inside the opaque source mesh parts; bevel-edge-only hits are excluded.',
                      'Decorative seams, handles represented by non-box primitives, diagonal beams, and LOD deformation are excluded from narrow phase; unresolved does not prove clearance.',
                      'This is a source geometry/registry audit, not a new UE render-mesh extraction; the prior fresh-UE verification established matching saved world transforms.',
                  ],
                  summary={key:dict(value) for key,value in sorted(stats.items())},
                  confirmed_pair_count=len(confirmed), bounds_only_pair_count=len(results)-len(confirmed),
                  affected_confirmed={key:dict(count=len(value),ids=sorted(value)) for key,value in affected.items()},
                  overlaps=results)
    output_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(output=str(output_path), counts=report['counts'],
                          confirmed_pair_count=len(confirmed), summary=report['summary']),indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,default=ROOT/'SourceAssets/GHS/ue_scene_registry.json')
    parser.add_argument('--output',type=Path,default=ROOT/'Saved/GHS_OverlapBefore.json')
    args=parser.parse_args()
    audit(args.registry,args.output)
