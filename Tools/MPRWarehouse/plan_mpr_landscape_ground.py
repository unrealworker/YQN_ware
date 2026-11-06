"""Plan restrained planting beds on the existing MPR terrain, without UE calls.

The two target mesh references are the only native changes this plan requests.
Existing traffic surfaces, vehicles, wheel stops and all other actors stay put.
"""
from pathlib import Path
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Saved/ParkRefinement/python_deps'))
import numpy as np
import shapely
from shapely.geometry import Point, LineString, Polygon, box, shape
from shapely.ops import unary_union
from mpr_site_completion_geometry import Ground, from_polygons, polygons, parts

OUT = ROOT/'SourceAssets/MPR/landscape_layout_20261106/ground'
BASELINE = ROOT/'Saved/MPR/landscape_layout_20261106/before.json.gz'
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
NAMESPACE = '/Game/MPRWarehouse/LandscapeLayout20261106'

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def build():
    paths = dict(site='SourceAssets/MPR/site_completion_20261105/site_plan.json',
                 roads='SourceAssets/MPR/city_road_removal_20261106/layout.json',
                 terrain='SourceAssets/MPR/rebuild_b50b57/manifest.json',
                 source_geometry='SourceAssets/MPR/site_completion_20261105/geometry/manifest.json',
                 cad='SourceAssets/MPR/mpr_cad_layout.json')
    inputs = {p:sha(ROOT/p) for p in paths.values()}
    data = {k:read(ROOT/p) for k,p in paths.items()}
    for r in data['source_geometry']['meshes']:
        if r['name'] in ('SM_MPRSC_MPRR_CampusGreen','SM_MPRSC_MPR4_TerminalCurb'):
            assert sha(ROOT/r['fbx'])==r['sha256']
            inputs[r['fbx']]=r['sha256']
    site, layout, manifest, cad = (data[k] for k in ('site','roads','terrain','cad'))
    baseline = json.loads(gzip.decompress(BASELINE.read_bytes()))
    assert baseline['map'].split('.')[0] == MAP
    main = from_polygons(site['protected_geometry']['main'])
    old = from_polygons(next(s['polygons'] for s in site['surfaces'] if s['role']=='MPRR_CampusGreen'))
    hard = unary_union([from_polygons(s['polygons']) for s in site['surfaces'] if s['role']!='MPRR_CampusGreen'])
    roads, rail, water, buildings = (shape(layout[k]) for k in ('roads','rail_corridor','water','building_protection'))
    operation = from_polygons(site['protected_geometry']['operating_area'])
    mouths = from_polygons(site['protected_geometry']['parking_mouths'])
    doors = unary_union([Point(d['position_m']).buffer(2.1) for d in cad['pedestrian_doors']])
    # Rounding only removes sharp corners; it cannot push landscaping onto work areas.
    retained = []
    removed_small = []
    for p in parts(old, 'Polygon'):
        if p.area < 4:
            removed_small.append(p)
            continue
        q = p.buffer(-.45, quad_segs=8).buffer(.45, quad_segs=8).intersection(p)
        retained.extend(parts(q, 'Polygon'))
    base = unary_union(retained)
    blockers = unary_union([roads.buffer(.5,quad_segs=16),rail.buffer(2,quad_segs=16),
                           water.buffer(.35),buildings,main,hard.buffer(.12),mouths.buffer(.5),operation])
    extra = []
    for name, bounds in [('West',[-208,-86,-201,78]),('EastSouth',[201,-15,207.3,28]),
                         ('EastNorth',[201,38,207.3,82])]:
        # Explicit gaps at the existing east/west access roads remain unplanted.
        g = box(*bounds).buffer(-2,quad_segs=8).buffer(2,quad_segs=8).difference(blockers).difference(base)
        g = unary_union([p for p in parts(g,'Polygon') if p.area>4])
        extra.append(dict(id=name,polygons=polygons(g)))
    additions = unary_union([from_polygons(r['polygons']) for r in extra])
    green = base.union(additions)
    assert green.is_valid and additions.intersection(blockers).area < 1e-6
    assert base.difference(old).area < 1e-6
    assert green.intersection(hard).area < 1e-6
    ground = Ground(ROOT,manifest,green.buffer(3),inputs)
    surface = dict(id='CampusGreen',role='MPRR_CampusGreen',polygons=polygons(green),
                   offset_m=.045,triangles_m=ground.triangles_for(green,.045))
    # Reuse every original wheel stop feature exactly. Only landscape curbs change.
    stops = [r for r in site['linear_features'] if r['id'].startswith('WheelStop_')]
    assert len(stops)==19 and all(r['role']=='MPR4_TerminalCurb' for r in stops)
    vehicle_exclusions = []
    for row in site['vehicle_instances']:
        from mpr_site_completion_geometry import footprint
        name = row['mesh']
        length,width = (16.4,2.68) if 'Trailer' in name else (6.71,3.) if 'Tractor' in name else (4.52,1.90)
        vehicle_exclusions.append(footprint(row,length,width))
    occupied = unary_union(vehicle_exclusions)
    curb_safe = green.difference(operation.buffer(.65)).difference(mouths.buffer(.75))
    curb_safe = curb_safe.difference(occupied.buffer(.75)).difference(roads.buffer(.65))
    curb_safe = curb_safe.difference(main.buffer(1.5)).difference(doors)
    path = green.buffer(-.20,quad_segs=8).boundary.intersection(curb_safe.buffer(-.122))
    curbs = []
    for i, seg in enumerate(parts(path,'LineString')):
        if seg.length < .5:
            continue
        dense = shapely.segmentize(seg,.75)
        curbs.append(dict(id='LandscapeCurb_'+str(i),role='MPR4_TerminalCurb',
                          points_m=[[round(x,6),round(y,6),round(ground.at(x,y)+.035,6)] for x,y in dense.coords],
                          width_m=.24,height_m=.20,offset_m=.035))
    raised = unary_union([LineString(f['points_m']).buffer(f['width_m']/2,cap_style=2) for f in curbs])
    checks = dict(green_hard_overlap_m2=green.intersection(hard).area,
                  green_road_overlap_m2=green.intersection(roads).area,
                  green_rail_overlap_m2=green.intersection(rail).area,
                  new_green_blocked_overlap_m2=additions.intersection(blockers).area,
                  raised_outside_green_m2=raised.difference(green).area,
                  raised_operating_overlap_m2=raised.intersection(operation).area,
                  raised_mouth_overlap_m2=raised.intersection(mouths).area,
                  raised_vehicle_overlap_m2=raised.intersection(occupied).area)
    assert all(v<1e-5 for v in checks.values()), checks
    curb_solid=dict(role='MPR4_TerminalCurb',polygons=polygons(raised),height_m=.20,
                    bottom_triangles_m=ground.triangles_for(raised,.035),
                    boundary_loops_m=[])
    for p in parts(raised,'Polygon'):
        for ring in [p.exterior,*p.interiors]:
            dense=shapely.segmentize(LineString(ring.coords),.75)
            curb_solid['boundary_loops_m'].append([[round(x,6),round(y,6),round(ground.at(x,y)+.035,6)] for x,y in dense.coords])
    mappings = []
    for label,name,role in [('MPRSC_MPRR_CampusGreen','SM_MPRLG_CampusGreen','MPRR_CampusGreen'),
                            ('MPRSC_MPR4_TerminalCurb','SM_MPRLG_LandscapeCurb','MPR4_TerminalCurb')]:
        actors = [a for a in baseline['actors'] if a['label']==label]
        assert len(actors)==1
        a = actors[0]; components = [c for c in a['components'] if c.get('mesh')]
        assert len(components)==1
        c = components[0]
        mappings.append(dict(name=name,old_mesh=c['mesh'].split('.')[0],new_mesh=NAMESPACE+'/Meshes/'+name,
                             guid=a['guid'],actor_path=a['path'],component=c['name'],label=label,
                             materials=c['materials'],material_roles=[role]))
    result = dict(schema_version=1,map=MAP,namespace=NAMESPACE,
                  coordinate_frame='CAD_METRES_POSITIVE_Y; UE=(x,-y,z)*100',
                  source_hashes=inputs,baseline=str(BASELINE.relative_to(ROOT)),baseline_sha256=sha(BASELINE),
                  mesh_mappings=mappings,surfaces=[surface],linear_features=stops+curbs,curb_solid=curb_solid,
                  planting_z_m_offset=.045,tree_root_z_m_offset=.055,
                  additions=extra,original_green=polygons(old),
                  protected_geometry=dict(hard=polygons(hard),roads=polygons(roads),rail=polygons(rail),
                                          operating=polygons(operation),mouths=polygons(mouths)),
                  audit=dict(**checks,old_green_area_m2=old.area,new_green_area_m2=green.area,
                             additions_area_m2=additions.area,corner_rounding_removed_m2=old.difference(base).area,
                             removed_fragments_m2=sum(p.area for p in removed_small),
                             old_islands=len(parts(old,'Polygon')),new_islands=len(parts(green,'Polygon')),
                             wheel_stops_preserved=19,landscape_curb_sections=len(curbs),
                             ground_offset_m=.045,curb_base_offset_m=.035,curb_top_offset_m=.235,
                             new_actors=0,replaced_mesh_components=2))
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/'plan.json',result)
    print(json.dumps(result['audit'],ensure_ascii=False))
    return result

def validate():
    """Independent binary-FBX readback with terrain and protected area checks."""
    from validate_mpr_rebuild_surface_clearance import fbx_nodes
    plan,manifest = read(OUT/'plan.json'),read(OUT/'manifest.json')
    assert manifest['plan_sha256']==sha(OUT/'plan.json')
    for p,h in plan['source_hashes'].items(): assert sha(ROOT/p)==h,p
    terrain_manifest=read(ROOT/'SourceAssets/MPR/rebuild_b50b57/manifest.json')
    green=from_polygons(plan['surfaces'][0]['polygons'])
    ground=Ground(ROOT,terrain_manifest,green.buffer(3),{})
    reports=[]
    stop_features=[r for r in plan['linear_features'] if r['id'].startswith('WheelStop_')]
    source_site=read(ROOT/'SourceAssets/MPR/site_completion_20261105/site_plan.json')
    assert stop_features==[r for r in source_site['linear_features'] if r['id'].startswith('WheelStop_')]
    for row in manifest['meshes']:
        p=ROOT/row['fbx'];assert sha(p)==row['sha256']
        objects=next(n for n in fbx_nodes(p) if n[0]==b'Objects')
        geos=[n for n in objects[2] if n[0]==b'Geometry'];assert len(geos)==1
        f={n[0]:n for n in geos[0][2]}
        vertices=np.asarray(f[b'Vertices'][1][0]).reshape(-1,3)
        faces=[];current=[]
        for i in f[b'PolygonVertexIndex'][1][0]:
            current.append(i if i>=0 else -i-1)
            if i<0:
                faces.extend(vertices[[current[0],current[j],current[j+1]]] for j in range(1,len(current)-1));current=[]
        bounds=np.stack((vertices.min(0),vertices.max(0)),axis=1)
        assert len(faces)==row['triangles'] and np.max(abs(bounds-np.asarray(row['bounds_m'])))<.0001
        mats=[n[1][1].decode().split('\x00')[0] for n in objects[2] if n[0]==b'Material']
        assert mats==row['material_roles'],mats
        top=[t for t in faces if np.cross(t[1]-t[0],t[2]-t[0])[2]>0]
        footprint=unary_union([Polygon(t[:,:2]) for t in top])
        if row['name']=='SM_MPRLG_CampusGreen':
            difference=footprint.symmetric_difference(green).area
            # Blender meshes use float32 before FBX doubles are serialized.
            # Bound that roundoff spatially, rather than demanding zero area.
            hausdorff=footprint.hausdorff_distance(green)
            assert difference<.01 and hausdorff<.001,(difference,hausdorff)
            errors=[]
            for t in top:
                for point in [t.mean(0),(t[0]+t[1])/2,(t[1]+t[2])/2,(t[0]+t[2])/2]:
                    errors.append(abs(point[2]-ground.at(*point[:2])-.045))
            assert max(errors)<.00001,max(errors)
        else:
            expected=unary_union([LineString(r['points_m']).buffer(r['width_m']/2,cap_style=2)
                                  for r in plan['linear_features']])
            difference=footprint.symmetric_difference(expected).area
            assert difference<.03,difference
            count=sum(sum(math.dist(a[:2],b[:2])>=.001 for a,b in zip(r['points_m'],r['points_m'][1:]))*12 for r in stop_features)
            previous_path=ROOT/'SourceAssets/MPR/site_completion_20261105/geometry/SM_MPRSC_MPR4_TerminalCurb.fbx'
            obj=next(n for n in fbx_nodes(previous_path) if n[0]==b'Objects')
            geo=next(n for n in obj[2] if n[0]==b'Geometry');fields={n[0]:n for n in geo[2]}
            vv=np.asarray(fields[b'Vertices'][1][0]).reshape(-1,3);ff=[];current=[]
            for index in fields[b'PolygonVertexIndex'][1][0]:
                current.append(index if index>=0 else -index-1)
                if index<0:
                    ff.extend(vv[[current[0],current[j],current[j+1]]] for j in range(1,len(current)-1));current=[]
            key=lambda tri:tuple(sorted(tuple(float(c) for c in p) for p in tri))
            old_faces=Counter(key(t) for t in ff)
            preserved=Counter(key(t) for t in faces[:count])
            assert not (preserved-old_faces),'Existing wheel stop triangles changed'
            errors=[]
            for t in faces[count:]:
                if np.cross(t[1]-t[0],t[2]-t[0])[2]<=0:continue
                for point in [t.mean(0),(t[0]+t[1])/2,(t[1]+t[2])/2,(t[0]+t[2])/2]:
                    errors.append(abs(point[2]-ground.at(*point[:2])-.235))
            assert max(errors)<.00001,max(errors)
        reports.append(dict(name=row['name'],triangles=len(faces),material_roles=mats,
                            footprint_error_m2=difference,max_terrain_offset_error_m=max(errors)if errors else None,
                            preserved_wheel_stop_triangles=count if row['name']=='SM_MPRLG_LandscapeCurb' else 0))
    result=dict(success=True,plan_sha256=sha(OUT/'plan.json'),manifest_sha256=sha(OUT/'manifest.json'),
                checks=plan['audit'],native_binary_fbx=reports)
    write(OUT/'geometry_validation.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--validate',action='store_true');args=p.parse_args()
    validate() if args.validate else build()
