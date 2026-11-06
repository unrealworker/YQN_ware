"""Extend the two user-marked planting surfaces, retaining every old triangle."""
from pathlib import Path
import argparse
from collections import Counter
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Saved/ParkRefinement/python_deps'))
import numpy as np
from shapely.geometry import Point, Polygon, box, shape
from shapely.ops import unary_union
from mpr_site_completion_geometry import Ground, from_polygons, polygons, parts, footprint

OUT = ROOT/'SourceAssets/MPR/green_extension_20261106'
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
NAMESPACE = '/Game/MPRWarehouse/GreenExtension20261106'
NAME = 'SM_MPRGE_CampusGreen'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def build():
    paths = dict(site='SourceAssets/MPR/site_completion_20261105/site_plan.json',
                 roads='SourceAssets/MPR/city_road_removal_20261106/layout.json',
                 terrain='SourceAssets/MPR/rebuild_b50b57/manifest.json',
                 old='SourceAssets/MPR/landscape_layout_20261106/ground/plan.json',
                 old_manifest='SourceAssets/MPR/landscape_layout_20261106/ground/manifest.json',
                 cad='SourceAssets/MPR/mpr_cad_layout.json')
    hashes = {p: sha(ROOT/p) for p in paths.values()}
    data = {k: read(ROOT/p) for k, p in paths.items()}
    site, layout, old = data['site'], data['roads'], data['old']
    previous = next(r for r in data['old_manifest']['meshes'] if r['name']=='SM_MPRLG_CampusGreen')
    assert sha(ROOT/previous['fbx']) == previous['sha256']
    hashes[previous['fbx']] = previous['sha256']
    green = from_polygons(old['surfaces'][0]['polygons'])
    hard = unary_union([from_polygons(r['polygons']) for r in site['surfaces'] if r['role']!='MPRR_CampusGreen'])
    roads, rail = (shape(layout[k]) for k in ('roads','rail_corridor'))
    main = from_polygons(site['protected_geometry']['main'])
    operations = from_polygons(site['protected_geometry']['operating_area'])
    mouths = from_polygons(site['protected_geometry']['parking_mouths'])
    doors = unary_union([Point(r['position_m']).buffer(2.1) for r in data['cad']['pedestrian_doors']])
    vehicles = []
    for row in site['vehicle_instances']:
        name = row['mesh']
        length, width = (16.4,2.68) if 'Trailer' in name else (6.71,3.) if 'Tractor' in name else (4.52,1.90)
        vehicles.append(footprint(row,length,width))
    occupied = unary_union(vehicles)
    # A bounded flood fill selects only the existing main warehouse road loop.
    enclosure = [p for p in parts(box(-220,-230,220,110).difference(roads.buffer(.4)), 'Polygon')
                 if p.contains(Point(-100,-170))]
    assert len(enclosure)==1
    south_limit = box(-180,-200,45.902207,-138.21362)
    south = enclosure[0].intersection(south_limit).difference(hard.buffer(.12)).difference(green)
    south = max(parts(south, 'Polygon'), key=lambda p:p.area)
    # Retain the grey pedestrian strip beside the stepped facade and door mouths.
    east_limit = box(136.4,-117,205,-20.50042)
    east = enclosure[0].intersection(east_limit).difference(main.buffer(1.0,join_style=2))
    east = east.difference(green).difference(operations).difference(mouths).difference(doors)
    east = east.difference(occupied.buffer(.25)).difference(rail.buffer(1))
    east = unary_union([p for p in parts(east,'Polygon') if p.area>1.])
    assert south.is_valid and east.is_valid
    added = south.union(east)
    blockers = dict(existing_green=green, roads=roads, rail=rail, main_building=main,
                    operating_area=operations, parking_mouths=mouths, vehicles=occupied)
    checks = {k+'_overlap_m2':added.intersection(v).area for k,v in blockers.items()}
    checks['south_hard_overlap_m2'] = south.intersection(hard).area
    assert all(v<1e-6 for v in checks.values()), checks
    ground = Ground(ROOT,data['terrain'],added.buffer(3),hashes)
    additions = []
    for id, geom, offset in [('SouthWedge',south,.045),('EastSteps',east,.10)]:
        triangles = ground.triangles_for(geom,offset)
        triangles = [t for t in triangles if Polygon([p[:2] for p in t]).area>1e-9]
        additions.append(dict(id=id,role='MPRR_CampusGreen',polygons=polygons(geom),
                              offset_m=offset,triangles_m=triangles))
    result = dict(schema_version=1,map=MAP,namespace=NAMESPACE,
                  coordinate_frame='CAD_METRES_POSITIVE_Y; UE=(x,-y,z)*100',
                  source_hashes=hashes,source_green_fbx=previous['fbx'],
                  name=NAME,material_roles=['MPRR_CampusGreen'],
                  material='/Game/MPRWarehouse/Hierarchy/Materials/MI_MPRH_CampusGreen',
                  old_mesh='/Game/MPRWarehouse/LandscapeLayout20261106/Meshes/SM_MPRLG_CampusGreen',
                  new_mesh=NAMESPACE+'/Meshes/'+NAME,
                  actor_guid='8AACBD08462839D9FDF1A79A307C9952',
                  surfaces=[old['surfaces'][0],*additions],
                  protected_geometry={k:polygons(v)for k,v in blockers.items()},
                  audit=dict(**checks,original_green_area_m2=green.area,
                             south_addition_area_m2=south.area,east_addition_area_m2=east.area,
                             new_green_area_m2=green.area+added.area,
                             old_triangles_preserved=len(old['surfaces'][0]['triangles_m']),
                             east_concrete_overlap_m2=east.intersection(hard).area,
                             east_min_concrete_clearance_m=.025,
                             south_offset_m=.045,east_offset_m=.10,road_setback_m=.4,
                             facade_setback_m=1.,new_actors=0,replaced_mesh_components=1))
    write(OUT/'plan.json',result)
    # Plot input is separate from the geometry plan so it can use any Pillow runtime.
    plot=[]
    def add(g,color,label=None):
        plot.append(dict(polygons=polygons(g),color=color,label=label))
    add(roads,'#929dac');add(rail,'#a7aaad')
    add(hard,'#dddedd');add(green,'#b3c995');add(main,'#f5f5f5')
    add(south,'#629342','South extension');add(east,'#629342','East extension')
    write(ROOT/'Saved/MPR/green_extension_20261106/plot_data.json',plot)
    print(json.dumps(result['audit'],ensure_ascii=False))


def fbx_faces(path):
    from validate_mpr_rebuild_surface_clearance import fbx_nodes
    objects=next(n for n in fbx_nodes(path) if n[0]==b'Objects')
    geos=[n for n in objects[2] if n[0]==b'Geometry'];assert len(geos)==1
    fields={n[0]:n for n in geos[0][2]}
    vertices=np.asarray(fields[b'Vertices'][1][0]).reshape(-1,3)
    faces=[];indices=[]
    for index in fields[b'PolygonVertexIndex'][1][0]:
        indices.append(index if index>=0 else -index-1)
        if index<0:
            faces.extend(vertices[[indices[0],indices[j],indices[j+1]]] for j in range(1,len(indices)-1));indices=[]
    mats=[n[1][1].decode().split('\x00')[0] for n in objects[2] if n[0]==b'Material']
    return faces,vertices,mats


def validate():
    plan,manifest=read(OUT/'plan.json'),read(OUT/'manifest.json')
    assert manifest['plan_sha256']==sha(OUT/'plan.json')
    for path,h in plan['source_hashes'].items():assert sha(ROOT/path)==h,path
    row=manifest['meshes'][0];assert len(manifest['meshes'])==1
    assert sha(ROOT/row['fbx'])==row['sha256']
    faces,vertices,mats=fbx_faces(ROOT/row['fbx'])
    old_faces,_,_=fbx_faces(ROOT/plan['source_green_fbx'])
    key=lambda t:tuple(sorted(tuple(float(v)for v in p)for p in t))
    assert Counter(map(key,faces[:len(old_faces)]))==Counter(map(key,old_faces)), 'Old green triangles changed'
    assert mats==['MPRR_CampusGreen'] and len(faces)==row['triangles']
    assert np.max(abs(np.stack((vertices.min(0),vertices.max(0)),axis=1)-np.asarray(row['bounds_m'])))<.0001
    additions=plan['surfaces'][1:]
    extent=unary_union([from_polygons(r['polygons'])for r in additions])
    ground=Ground(ROOT,read(ROOT/'SourceAssets/MPR/rebuild_b50b57/manifest.json'),extent.buffer(3),{})
    cursor=len(old_faces); reports=[]
    for s in additions:
        count=len(s['triangles_m']);ts=faces[cursor:cursor+count];cursor+=count
        expected=from_polygons(s['polygons'])
        actual=unary_union([Polygon(t[:,:2])for t in ts])
        difference=actual.symmetric_difference(expected).area
        # Float32 triangle seams may form microscopic interior holes. GEOS's
        # boundary Hausdorff distance then measures to those interior seams;
        # mutual 0.1 mm containment bounds the actual surface error instead.
        outside=actual.difference(expected.buffer(.0001)).area
        missing=expected.difference(actual.buffer(.0001)).area
        assert difference<.01 and outside<1e-9 and missing<1e-9,(difference,outside,missing,s['id'])
        errors=[]
        for t in ts:
            for p in [t.mean(0),(t[0]+t[1])/2,(t[1]+t[2])/2,(t[2]+t[0])/2]:
                errors.append(abs(p[2]-ground.at(*p[:2])-s['offset_m']))
        assert max(errors)<.00001,max(errors)
        reports.append(dict(id=s['id'],triangles=count,footprint_error_m2=difference,
                            outside_tolerance_m2=outside,missing_outside_tolerance_m2=missing,
                            terrain_offset_error_m=max(errors)))
    assert cursor==len(faces)
    report=dict(success=True,plan_sha256=sha(OUT/'plan.json'),manifest_sha256=sha(OUT/'manifest.json'),
                original_fbx_triangles_preserved=len(old_faces),checks=plan['audit'],additions=reports)
    write(OUT/'geometry_validation.json',report)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--validate',action='store_true');args=p.parse_args()
    validate() if args.validate else build()
