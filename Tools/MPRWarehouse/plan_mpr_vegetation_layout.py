"""Deterministic ordered vegetation plan for the existing MPR HISM actors.

CPU-only: writes only SourceAssets/MPR/landscape_layout_20261106 vegetation
plan and analysis figures. Does not connect to Unreal or edit source assets.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import gzip, hashlib, json, math, random, struct, sys, zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Saved/ParkRefinement/python_deps'))
import numpy as np
import shapely
from shapely.geometry import Point, LineString, Polygon, box, shape
from shapely.ops import unary_union
from mpr_site_completion_geometry import Ground, from_polygons, polygons, parts, footprint

OUT = ROOT/'SourceAssets/MPR/landscape_layout_20261106'
BASELINE = 'Saved/MPR/landscape_layout_20261106/before.json.gz'
TREE = '/Game/MPRWarehouse/SiteComplete/Meshes/SM_MPRSC_Tree_Canopy'
RADIUS = 6.4180411992666615
SEED = 11062026


def read(path):
    raw = (ROOT/path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith('.gz') else raw)


def sha(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def png(path, pixels):
    h, w, _ = pixels.shape
    def chunk(name, data):
        return struct.pack('!I',len(data))+name+data+struct.pack('!I',zlib.crc32(name+data)&0xffffffff)
    stream = b''.join(b'\0'+row.tobytes() for row in pixels)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,2,0,0,0))+
                     chunk(b'IDAT',zlib.compress(stream,6))+chunk(b'IEND',b''))


def build():
    paths = dict(baseline=BASELINE, transport='SourceAssets/MPR/city_road_removal_20261106/layout.json',
                 manifest='SourceAssets/MPR/rebuild_b50b57/manifest.json',
                 site='SourceAssets/MPR/site_completion_20261105/site_plan.json',
                 ground='SourceAssets/MPR/landscape_layout_20261106/ground/plan.json',
                 tree='SourceAssets/MPR/site_completion_20261105/tree/geometry_audit.json')
    values = {k:read(p) for k,p in paths.items()}
    hashes = {p:sha(p) for p in paths.values()}
    scene, layout, manifest, site, gp = [values[k] for k in ('baseline','transport','manifest','site','ground')]
    assert scene['map'].split('.')[0] == '/Game/Maps/MPR_CAD_Warehouse_B50B57'
    assert abs(values['tree']['radial_extent_m']-RADIUS) < 1e-8
    groups, before = [], []
    for actor in scene['actors']:
        for component in actor['components']:
            if str(component.get('mesh','')).split('.')[0] != TREE:
                continue
            assert actor['transform']['translation_cm'] == [0,0,0]
            assert component['transform']['translation_cm'] == [0,0,0]
            old = component['instance_transforms']
            groups.append(dict(actor_guid=actor['guid'], actor_name=actor['name'], label=actor['label'],
                               component_name=component['name'], original_count=len(old),
                               original_instance_transforms=old, instance_transforms=[], custom_data=[],
                               original_materials=component['materials']))
            for tr in old:
                x,y,z=tr['translation_cm']
                before.append(dict(position_m=[x/100,-y/100,z/100],crown_radius_m=RADIUS*max(tr['scale'])))
    assert len(groups)==64 and len(before)==1302
    frame=shape(layout['frame']).buffer(-5)
    roads=shape(layout['roads']);rail=shape(layout['rail_corridor']);water=shape(layout['water'])
    buildings=shape(layout['building_protection'])
    operating=from_polygons(site['protected_geometry']['operating_area'])
    mouths=from_polygons(site['protected_geometry']['parking_mouths'])
    # Site paving is retained by the ground plan. Crown clearance is deliberately
    # conservative around all current operational/parking geometry.
    paving=unary_union([from_polygons(s['polygons']) for s in site['surfaces'] if s['role']!='MPRR_CampusGreen'])
    vehicles=[]
    for v in site['vehicle_instances']:
        name=v['mesh']
        length,width=(16.4,2.68)if 'Trailer'in name else(6.71,3.)if 'Tractor'in name else(4.52,1.9)
        vehicles.append(footprint(v,length,width))
    vehicle_mask=unary_union(vehicles).buffer(.4)
    # Ground source exposes the final green polygons in a stable semantic field.
    green=from_polygons(gp['surfaces'][0]['polygons'])
    transport_block=unary_union([roads.buffer(.60),rail.buffer(1.2),water.buffer(.8)])
    critical=unary_union([transport_block,buildings.buffer(.8),operating.buffer(.4),mouths.buffer(.4),vehicle_mask])
    hard_block=unary_union([critical,paving.buffer(.12)])
    hero_block=unary_union([critical,paving.buffer(-.65)])
    shapely.prepare(hero_block)
    shapely.prepare(hard_block);shapely.prepare(frame)
    ground=Ground(ROOT,manifest,frame,hashes)
    rows=[];buckets=defaultdict(list);rng=random.Random(SEED);rejected=Counter()

    def add(x,y,r,category,mask,source,require_green=False):
        disc=Point(x,y).buffer(r+.15,quad_segs=24)
        if not frame.covers(disc):rejected['frame']+=1;return False
        if disc.intersects(hero_block if mask else hard_block):rejected['hard_clearance']+=1;return False
        # Only hero-tree canopy edges may overhang non-operational paving by
        # <= 0.65 m. Every trunk/root disc stays clear of all hard surfaces.
        if Point(x,y).buffer(.65,quad_segs=24).intersects(paving.buffer(.02)):
            rejected['root_paving']+=1;return False
        if require_green and not green.buffer(.08).covers(Point(x,y).buffer(.65)):
            rejected['green_root']+=1;return False
        key=(math.floor(x/12),math.floor(y/12))
        for bx in range(key[0]-1,key[0]+2):
            for by in range(key[1]-1,key[1]+2):
                for j in buckets[(bx,by)]:
                    other=rows[j]
                    if math.hypot(x-other['position_m'][0],y-other['position_m'][1]) < r+other['crown_radius_m']+.65:
                        rejected['crown_spacing']+=1;return False
        try:z=ground.at(x,y)+(.055 if green.covers(Point(x,y)) else .01)
        except ValueError:rejected['terrain']+=1;return False
        yaw=rng.uniform(0,360)
        rows.append(dict(position_m=[round(x,6),round(y,6),round(z,6)], crown_radius_m=round(r,6),
                         rotation_deg=round(yaw,6), mask=mask, category=category, source=source))
        buckets[key].append(len(rows)-1)
        return True

    def line_rows(line,spacing,radius,category,mask,source,offset=0,require_green=False):
        if offset:line=line.offset_curve(offset,quad_segs=12,join_style=1)
        accepted=0
        for segment in parts(line,'LineString'):
            if segment.length<spacing*.6:continue
            n=max(1,math.floor(segment.length/spacing))
            for i in range(n):
                p=segment.interpolate((i+.5)*segment.length/n)
                r=radius*(.98+.04*((i*7)%9)/8)
                accepted+=add(p.x,p.y,r,category,mask,source,require_green)
        return accepted

    # Hero perimeter: deliberately same family of crowns; only narrow northern
    # and southern green strips use smaller versions of this same mesh.
    line_rows(LineString([(-204.5,-81),(-204.5,73)]),10.2,2.85,'campus_west',1,'west_green',require_green=True)
    line_rows(LineString([(-193,99.35),(193,99.35)]),9.4,2.28,'campus_north',1,'north_green',require_green=True)
    line_rows(LineString([(204.15,-10),(204.15,23)]),10.5,2.75,'campus_east',1,'east_green_south',require_green=True)
    line_rows(LineString([(204.15,43),(204.15,77)]),10.5,2.75,'campus_east',1,'east_green_north',require_green=True)
    rd={v['id']:v for v in layout['road_centerlines']}
    south=LineString(rd['TPX_ROADS_AXES_B19']['points_m']).intersection(box(-198,-180,195,-30))
    for segment in parts(south,'LineString'):
        # The retained truck yard leaves a narrow inside strip. Its outer verge
        # has continuous existing lawn: use the larger row there without placing
        # crowns in the truck manoeuvring apron or forcing trees into thin slivers.
        line_rows(segment,9.8,2.1,'campus_south_inner',1,'B19_inner_green',-7.8,True)
        line_rows(segment,10.8,2.85,'campus_south',1,'B19_outer_lawn',8.8,False)
    # Rounded corner islands have a small, intentional two/three-tree family.
    for k,(x,y,r) in enumerate([(-196.7,-104,2.3),(-196.7,-114,2.3),(-190,93,2.65),(194,94,2.65),
                               (198,-27,2.2),(190,-34,2.4),(182.25,-44,2.2),
                               (182.25,-54,2.2),(174,-64,2.4),(166.4,-74,2.2)]):
        add(x,y,r,'campus_corner',1,'corner_'+str(k),True)

    campus_zone=box(-210,-180,211,103)
    # The side-road frame is stronger than the background park clusters.
    priority=['TPX_ROADS_AXES_9A5','TPX_ROADS_AXES_B19','TPX_ROADS_AXES_A50','TPX_ROADS_AXES_9CB']
    for identity in priority:
        v=rd[identity];line=LineString(v['points_m'])
        for offset in (v['width_m']/2+4.1,-v['width_m']/2-4.1):
            edge=line.offset_curve(offset,quad_segs=12,join_style=1).difference(campus_zone.buffer(1))
            line_rows(edge,12.5,3.0,'primary_avenue',0,identity)
    # Remaining streets: one single row in each selected verge, with a looser
    # interval and intersection gaps; never populate short access stubs.
    road_specs=sorted([v for v in layout['road_centerlines'] if v['id'] not in priority and
                       v['road_class']!='access' and v['length_m']>90],key=lambda v:(-v['length_m'],v['id']))
    for k,v in enumerate(road_specs):
        if len(rows)>=820:break
        line=LineString(v['points_m'])
        sides=(1,-1)if v['road_class']=='primary' else ((1,)if k%2==0 else(-1,))
        for sign in sides:
            edge=line.offset_curve(sign*(v['width_m']/2+3.65),quad_segs=12,join_style=1).difference(campus_zone.buffer(3))
            line_rows(edge,15.0,2.75,'secondary_avenue',0,v['id'])

    # Compact groves in open parcels. Each cluster is 3--7 trees around a centre,
    # separated from the next cluster by a broad lawn; never a connected chain.
    old_support=unary_union([Point(r['position_m'][:2]).buffer(50,quad_segs=8)for r in before])
    open_mask=frame.difference(hard_block.buffer(13)).difference(campus_zone.buffer(15))
    open_mask=open_mask.intersection(old_support)
    anchors=[]
    for gy in range(-620,801,65):
        for gx in range(-730,731,65):
            x=gx+rng.uniform(-16,16);y=gy+rng.uniform(-16,16)
            if open_mask.covers(Point(x,y).buffer(12)):
                anchors.append((x,y))
    # Prioritize open land near the main campus and railway before remote edges.
    anchors.sort(key=lambda p:(max(0,math.hypot(p[0]-50,p[1]+20)-450),p[1],p[0]))
    accepted_clusters=0
    for i,(cx,cy)in enumerate(anchors):
        if len(rows)>=1220:break
        n=3+(i%5);angle=rng.uniform(0,math.tau)
        template=[(0,0),(-8,-1),(4,7),(5,-6),(-4,7),(-2,-8),(9,2)]
        candidates=[]
        for j,(px,py)in enumerate(template[:n]):
            px+=rng.uniform(-.25,.25);py+=rng.uniform(-.25,.25)
            candidates.append((cx+px*math.cos(angle)-py*math.sin(angle),
                               cy+px*math.sin(angle)+py*math.cos(angle),2.75+.35*((j*3+i)%7)/6))
        # All cluster trees must have room: reject the whole grove, not a
        # clipped one or two tree remnant that would become visual noise.
        initial=len(rows)
        for x,y,r in candidates:add(x,y,r,'natural_grove',0,'grove_'+str(i))
        if len(rows)-initial<3:
            for key in buckets:buckets[key]=[j for j in buckets[key]if j<initial]
            del rows[initial:]
        else:accepted_clusters+=1
    assert len(rows)<=1302 and len(rows)>500

    # Keep all original HISM Actor identities. Assign to nearest original tile
    # centre; every group may change instance count but nothing is respawned.
    centers=[]
    for g in groups:
        points=g['original_instance_transforms']
        centers.append((sum(t['translation_cm'][0]for t in points)/len(points)/100,
                        -sum(t['translation_cm'][1]for t in points)/len(points)/100))
    for row in rows:
        x,y,z=row['position_m'];idx=min(range(len(groups)),key=lambda i:(x-centers[i][0])**2+(y-centers[i][1])**2)
        a=-math.radians(row['rotation_deg'])/2;s=row['crown_radius_m']/RADIUS
        groups[idx]['instance_transforms'].append(dict(translation_cm=[x*100,-y*100,z*100],rotation_xyzw=[0.,0.,math.sin(a),math.cos(a)],scale=[s,s,s]))
        groups[idx]['custom_data'].append(row['mask'])
    # Independent full-pair check uses analytic radii, not tessellated buffer.
    min_gap=min(math.dist(a['position_m'][:2],b['position_m'][:2])-a['crown_radius_m']-b['crown_radius_m']
                for i,a in enumerate(rows)for b in rows[i+1:])
    assert min_gap>=.64,min_gap
    circles=[Point(r['position_m'][:2]).buffer(r['crown_radius_m']+.15,quad_segs=24)for r in rows]
    overlap=sum(c.intersection(critical).area for c in circles)
    assert overlap<.0001,overlap
    deep_overlap=sum(c.intersection(paving.buffer(-.65)if r['mask']else paving.buffer(.12)).area for c,r in zip(circles,rows))
    assert deep_overlap<.0001,deep_overlap
    root_overlap=sum(Point(r['position_m'][:2]).buffer(.65,quad_segs=24).intersection(paving.buffer(.02)).area for r in rows)
    assert root_overlap<.0001,root_overlap
    overhang=[]
    for i,(c,r)in enumerate(zip(circles,rows)):
        area=c.intersection(paving).area
        if area>.00001:
            assert r['mask']==1
            overhang.append(dict(tree_index=i,category=r['category'],source=r['source'],position_m=r['position_m'],
                                 area_m2=area,max_allowed_depth_m=.65))
    result=dict(schema_version=1,map=scene['map'].split('.')[0],baseline_sha256=sha(BASELINE),source_hashes=hashes,
                coordinate_frame='CAD metres; UE=(x,-y,z)*100',tree_mesh=TREE,radial_extent_m=RADIUS,
                groups=groups,trees=rows,counts=dict(before=1302,after=len(rows),groups=64,
                    hero=sum(r['mask']for r in rows),background=sum(not r['mask']for r in rows),
                    by_category=dict(Counter(r['category']for r in rows)),groves=accepted_clusters),
                validation=dict(success=True,min_canopy_gap_m=min_gap,protected_overlap_m2=overlap,
                    nonpermitted_paving_overlap_m2=deep_overlap,root_paving_overlap_m2=root_overlap,
                    limited_hero_canopy_overhang=overhang,max_overhang_depth_m=.65,
                    terrain_sampled=True,all_64_actor_identities_retained=True,source_tree_mesh_unchanged=True,
                    primary_spacing_m=12.5,secondary_spacing_m=15.0,natural_cluster_size=[3,7]),
                policy=dict(campus='Regular dark-green boundary rows, cut at actual access roads',
                    background='Pale single roadside rows and compact 3-7-tree groves with open lawn',
                    material='Use existing hierarchy leaf family, mask 1 campus and mask 0 background',
                    terrain='Tree roots sample actual terrain, plus green-surface elevation'),rejected=dict(rejected))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'vegetation_plan.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    plot(layout,site,green,before,rows,OUT/'vegetation_analysis.png')
    print(json.dumps(result['counts'],ensure_ascii=False))
    return result


def plot(layout,site,green,before,after,path):
    # Original analytical plot, not an edit of a supplied/rendered image.
    ext=(-320,-380,480,420);w=h=1200;xx=np.linspace(ext[0],ext[2],w);yy=np.linspace(ext[3],ext[1],h)
    def paint(canvas,g,color):
        if g.is_empty:return
        minx,miny,maxx,maxy=g.bounds
        ix0=max(0,int((minx-ext[0])/(ext[2]-ext[0])*w));ix1=min(w,int((maxx-ext[0])/(ext[2]-ext[0])*w)+2)
        iy0=max(0,int((ext[3]-maxy)/(ext[3]-ext[1])*h));iy1=min(h,int((ext[3]-miny)/(ext[3]-ext[1])*h)+2)
        if ix1<=ix0 or iy1<=iy0:return
        X,Y=np.meshgrid(xx[ix0:ix1],yy[iy0:iy1]);shapely.prepare(g)
        mask=shapely.contains_xy(g,X,Y);canvas[iy0:iy1,ix0:ix1][mask]=color
    imgs=[]
    for trees in (before,after):
        image=np.full((h,w,3),(221,225,211),dtype=np.uint8)
        paint(image,shape(layout['roads']),(161,169,180));paint(image,shape(layout['rail_corridor']),(174,177,178))
        for s in site['surfaces']:
            if s['role']!='MPRR_CampusGreen':paint(image,from_polygons(s['polygons']),(203,203,199))
        paint(image,green,(165,188,143));paint(image,shape(layout['building_protection']),(242,243,241));paint(image,shape(layout['water']),(70,129,143))
        for t in trees:
            color=(105,136,82)if t.get('mask')else(158,174,144)
            paint(image,Point(t['position_m'][:2]).buffer(t['crown_radius_m'],quad_segs=16),color)
        imgs.append(image)
    png(path,np.concatenate([imgs[0],np.full((h,16,3),255,np.uint8),imgs[1]],axis=1))


if __name__=='__main__':build()
