"""Build the complete B50B57 surroundings in Blender; existing warehouse read-only."""
import copy, gzip, hashlib, json, math, shutil, sys
from pathlib import Path
from collections import defaultdict, Counter
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps'),str(ROOT/'Scripts/ghs')]
import bpy, shapely
from shapely.geometry import Point,Polygon,LineString,GeometryCollection,box,mapping
from shapely.ops import unary_union
from shapely.affinity import rotate,translate
from mpr_blender_common import Geometry
from mpr_rebuild_roads import build_layout,dump_layout
from mpr_rebuild_context import build_rebuild_context,source_footprint
from mpr_rebuild_style import apply_style
from mpr_railway_detail import build_railways
import mpr_railway_detail as rail_detail
import build_mpr_reference_site as exporter

OUT=ROOT/'SourceAssets/MPR/rebuild_b50b57'
CACHE=ROOT/'Saved/MPR/rebuild_20261104'
V4=ROOT/'SourceAssets/MPR/reference_v4'
G=-1.2; TILE=150.
GEO=Geometry(); INST=defaultdict(list); REUSED={}; TRI_AUDIT=[]
GROUND_TRIANGLES=[]; GROUND_INDEX=None

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,j):Path(p).write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding='utf8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def polygons(g):
    if g.is_empty:return []
    if g.geom_type=='Polygon':return [g]
    return [p for c in getattr(g,'geoms',[]) for p in polygons(c)]
def tile(g):
    if g.is_empty:return
    x0,y0,x1,y1=g.bounds
    for x in range(math.floor(x0/TILE),math.floor(x1/TILE)+1):
        for y in range(math.floor(y0/TILE),math.floor(y1/TILE)+1):
            part=g.intersection(box(x*TILE,y*TILE,(x+1)*TILE,(y+1)*TILE))
            if not part.is_empty:yield x,y,part
def triangles(p,name,step=3):
    clean=shapely.make_valid(p)
    for precision in (.0001,.001):
        try:
            q=shapely.set_precision(clean,precision).simplify(precision*.5,preserve_topology=True)
            if step:q=shapely.set_precision(shapely.segmentize(q,step),precision)
            ts=[t for part in polygons(q) for t in shapely.constrained_delaunay_triangles(part).geoms if t.area>1e-9]
            area=sum(t.area for t in ts)
            assert abs(area-p.area)<max(.001,p.length*precision*2),(name,'area loss')
            TRI_AUDIT.append(dict(name=name,precision_m=precision,area_change_m2=abs(area-p.area)))
            return ts
        except shapely.errors.GEOSException:pass
    raise RuntimeError('Triangulation failed: '+name)
def surface(name,role,geometry,z,step=3,tiled=True,conform=True):
    for x,y,g in (tile(geometry) if tiled else [(None,None,geometry)]):
        n=f'{name}_{x}_{y}' if tiled else name
        for p in polygons(g):
            pieces=[p]
            # All pavement layers share the rendered terrain's triangle planes.
            # Sampling the same nonlinear height function at different polygon
            # vertices is insufficient: large independent triangles intersect.
            if conform and GROUND_INDEX is not None and callable(z):
                pieces=[]
                for index in GROUND_INDEX.query(p,predicate='intersects'):
                    pieces.extend(polygons(p.intersection(GROUND_TRIANGLES[int(index)])))
                covered=unary_union(pieces) if pieces else GeometryCollection()
                pieces.extend(polygons(p.difference(covered)))
            for t in (t for piece in pieces for t in triangles(piece,n,step)):
                xy=list(t.exterior.coords)[:3]
                verts=[(a,b,z(a,b) if callable(z) else z) for a,b in xy]
                d=(xy[1][0]-xy[0][0])*(xy[2][1]-xy[0][1])-(xy[1][1]-xy[0][1])*(xy[2][0]-xy[0][0])
                GEO.mesh(n,role,verts,[(0,1,2) if d>0 else (0,2,1)])
def pose_footprint(p,length,width,yaw):return translate(rotate(box(-length/2,-width/2,length/2,width/2),yaw,origin=(0,0)),p[0],p[1])
def instance(name,x,y,z,yaw=0,scale=(1,1,1),**extra):
    INST[name].append(dict(position_m=[x,y,z],rotation_deg=yaw,scale=list(scale),tile=[math.floor(x/TILE),math.floor(y/TILE)],**extra))
    REUSED[name]='/Game/MPRWarehouse/ReferenceV4/Props/Meshes/'+name

class TriangleHeights:
    """Double-precision plane samples with a small uniform spatial index."""
    def __init__(self,vertices,faces):
        self.cells=defaultdict(list);self.step=32.
        for face in faces:
            a,b,c=[vertices[i]for i in face]
            dx1,dy1,dz1=[b[j]-a[j]for j in range(3)];dx2,dy2,dz2=[c[j]-a[j]for j in range(3)]
            det=dx1*dy2-dx2*dy1
            if abs(det)<1e-9:continue
            row=(a[0],a[1],a[2],dy2/det,-dx2/det,-dy1/det,dx1/det,dz1,dz2)
            lo=[min(a[i],b[i],c[i]) for i in (0,1)];hi=[max(a[i],b[i],c[i]) for i in (0,1)]
            for ix in range(math.floor((lo[0]-.001)/self.step),math.floor((hi[0]+.001)/self.step)+1):
                for iy in range(math.floor((lo[1]-.001)/self.step),math.floor((hi[1]+.001)/self.step)+1):self.cells[ix,iy].append(row)
    def at(self,x,y):
        found=None
        for ax,ay,az,ua,ub,va,vb,dz1,dz2 in self.cells.get((math.floor(x/self.step),math.floor(y/self.step)),()):
            dx,dy=x-ax,y-ay;u=ua*dx+ub*dy;v=va*dx+vb*dy
            if u>=-1e-5 and v>=-1e-5 and u+v<=1.00001:
                z=az+u*dz1+v*dz2
                if found is None or z>found:found=z
        return found

def inputs():
    (OUT/'inputs').mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    paths={
      'topoexport-B50B57.blend':Path('D:/CodexTemp/2026-11-04/topoexport-B50B57/topoexport-B50B57.blend'),
      'source_geometry.json':ROOT/'Saved/MPR/extension_20261104/source_geometry.json',
      'registration.json':ROOT/'Saved/MPR/extension_20261104/registration_proposal.json',
      'LICENSE-topoexport.txt':Path('D:/CodexTemp/2026-11-04/topoexport-B50B57/source/LICENSE.txt'),
      'visual_reference.png':Path('C:/Users/28109/AppData/Local/Temp/codex-clipboard-ef2608f2-6958-461c-90e5-a489fdf7c4d3.png')}
    for name,source in paths.items():
        dest=OUT/'inputs'/name
        if not dest.exists():shutil.copy2(source,dest)
        elif source.exists():assert sha(source)==sha(dest),name
    source=read(OUT/'inputs/source_geometry.json');reg=read(OUT/'inputs/registration.json')
    assert source['sha256']==reg['source_sha256']==sha(OUT/'inputs/topoexport-B50B57.blend')
    return source,reg,{n:sha(OUT/'inputs'/n) for n in paths}

def terrain(source,tx,main,frame,water):
    global GROUND_TRIANGLES,GROUND_INDEX
    row=next(r for r in source['objects'] if r.get('layer')=='TPX_TERRAIN_TERRAIN_MESH')
    vertices=[(*tx(v),v[2]) for v in row['vertices']]
    source_sampler=TriangleHeights(vertices,row['faces'])
    cache={}
    def height(x,y):
        key=(round(x,4),round(y,4))
        if key in cache:return cache[key]
        p=Point(x,y);distance=main.distance(p)
        if distance<=50:z=G
        else:
            source_z=source_sampler.at(x,y)
            if source_z is None:source_z=4.05327558517456
            base=source_z-4.05327558517456+G
            t=min(1,max(0,(distance-50)/40));t=t*t*(3-2*t)
            # The outer 30m is genuinely level, so vertex fade never buries roads.
            edge=max(0,min(1,(frame.boundary.distance(p)-30)/40)) if frame.covers(p) else 0
            edge=edge*edge*(3-2*edge)
            z=G+(base-G)*t*edge
        cache[key]=z;return z
    for face in row['faces']:
        xy=[vertices[i][:2] for i in face]
        if len(xy)<3:continue
        p=Polygon(xy).intersection(frame).difference(water.buffer(.7))
        surface('SM_MPRR_Terrain','MPR3_Grass',p,height,step=12)
    # Broad background has no large empty holes or a floating terrain edge.
    surface('SM_MPRR_Background','MPR3_Grass',box(-2400,-2000,2400,2400).difference(frame),G,step=90,tiled=False)
    rendered_vertices=[];rendered_faces=[]
    for name,model in GEO.data.items():
        if not name.startswith('SM_MPRR_Terrain_'):continue
        for verts,faces in model.values():
            offset=len(rendered_vertices);rendered_vertices.extend(verts)
            for face in faces:
                ids=tuple(offset+i for i in face)
                rendered_faces.append(ids)
                p=Polygon([rendered_vertices[i][:2] for i in ids])
                if p.area>1e-9:
                    GROUND_TRIANGLES.append(p)
    GROUND_INDEX=shapely.STRtree(GROUND_TRIANGLES)
    rendered_sampler=TriangleHeights(rendered_vertices,rendered_faces)
    rendered_cache={}
    def rendered_height(x,y):
        key=(round(x,5),round(y,5))
        if key not in rendered_cache:
            z=rendered_sampler.at(x,y)
            rendered_cache[key]=height(x,y) if z is None else z
        return rendered_cache[key]
    return rendered_height,dict(vertices=len(vertices),faces=len(row['faces']),main_flat_radius_m=50,terrain_blend_end_m=90,
        pavement_support='Exact rendered terrain triangles; all pavement and marking layers conform to the same planes',
        rendered_support_triangles=len(GROUND_TRIANGLES))

def vehicles_and_campus(main,layout,height,cad):
    roads=layout['roads'];other=layout['building_protection'].difference(main.buffer(3))
    minx,miny,maxx,maxy=main.bounds
    # Main dispatch apron follows the immutable dock facade; outer roads stay source-derived.
    yard=main.buffer(13,join_style=2).union(box(minx-12,miny-45,maxx+10,miny+3)).difference(main)
    yard=yard.difference(roads.buffer(.22)).difference(other).difference(layout['rail_corridor'])
    old=read(V4/'validation_blender/composition_instances.json')['site']
    accepted=[];rejected=[];occupied=[]
    for name,rows in old.items():
        if not any(token in name for token in ('Trailer','Tractor','_Car_')):continue
        length,width=(16.4,2.68) if 'Trailer' in name else (6.71,3.) if 'Tractor' in name else (4.52,1.90)
        for row in rows:
            x,y=row['position_m'][:2];yaw=row['rotation_deg'];f=pose_footprint((x,y),length,width,yaw)
            if f.intersects(main.buffer(.10)) or f.intersects(roads.buffer(.15)) or f.intersects(other) or f.intersects(layout['rail_corridor']):
                rejected.append(dict(mesh=name,position_m=[x,y],reason='new full-source layout conflict'));continue
            yard=yard.union(f.buffer(.65,join_style=2));occupied.append(f)
            instance(name,x,y,height(x,y)+.10,yaw,row.get('scale',[1,1,1]),assembly_id=row.get('assembly_id'))
            accepted.append(dict(mesh=name,position_m=[x,y],yaw=yaw))
    # A complete dispatch unit is retained or rejected together.
    trailers={r.get('assembly_id') for n,rows in INST.items() if 'Trailer' in n for r in rows}
    tractors={r.get('assembly_id') for n,rows in INST.items() if 'Tractor' in n for r in rows}
    coupled=trailers&tractors
    for name in list(INST):
        if 'Tractor' in name or 'Trailer' in name:
            INST[name]=[r for r in INST[name] if not r.get('assembly_id') or r['assembly_id'] in coupled]
    surface('SM_MPRR_MainApron','MPR3_Concrete',yard,lambda x,y:height(x,y)+.075)
    island=yard.buffer(4.8,quad_segs=12).difference(yard).difference(main).difference(roads.buffer(.5)).difference(other).difference(layout['rail_corridor']).difference(layout['water'])
    surface('SM_MPRR_CampusGreen','MPRR_CampusGreen',island,lambda x,y:height(x,y)+.045)
    # Flush apron seams and dock stand guide lines, never across the roadway.
    marks=[]
    for door in cad['dock_doors']:
        x,y=door['position_m'][:2];nx,ny=door['outward_normal_xy'];tx,ty=-ny,nx
        for sign in (-1,1):
            line=LineString([(x+tx*sign*1.65+nx*1,y+ty*sign*1.65+ny*1),(x+tx*sign*1.65+nx*23,y+ty*sign*1.65+ny*23)])
            marks.append(line.buffer(.055,cap_style=2).intersection(yard))
    surface('SM_MPRR_DockLines','MPR3_YellowLine',unary_union(marks),lambda x,y:height(x,y)+.096)
    parking=[]
    for side in (-1,1):
        x=minx-7 if side<0 else maxx+7
        for i in range(24):
            y=miny+3+i*5.4;slot=box(x-2.7,y-.05,x+2.7,y+.05).intersection(yard)
            parking.append(slot)
            if i%4!=3:
                car=pose_footprint((x,y+2.7),4.52,1.90,0)
                if yard.buffer(-.15).covers(car) and not any(car.buffer(.15).intersects(f)for f in occupied):
                    instance('SM_MPR4_Car_'+str(i%2),x,y+2.7,height(x,y+2.7)+.075,0 if side<0 else 180)
                    occupied.append(car)
    surface('SM_MPRR_ParkingLines','MPR3_WhiteLine',unary_union(parking),lambda x,y:height(x,y)+.096)
    return yard,island,dict(accepted=len(accepted),rejected=rejected,vehicle_counts={n:len(v)for n,v in INST.items()})

def neighbor_aprons(source,tx,main,layout,height):
    pieces=[]
    for row in source['objects']:
        if row.get('layer')!='TPX_BUILDINGS':continue
        p=source_footprint(row,tx)
        if p.is_empty or p.area<3000 or p.intersects(main.buffer(3)):continue
        for poly in polygons(p):
            if poly.area<3000 or 4*math.pi*poly.area/poly.length**2>.94:continue
            xy=list(poly.exterior.coords);edges=[(a,b,math.dist(a,b))for a,b in zip(xy,xy[1:])]
            longest=max(e[2]for e in edges)
            edges=[e for e in edges if e[2]>max(55,longest*.60)]
            if not edges:continue
            a,b,_=min(edges,key=lambda e:Point((e[0][0]+e[1][0])/2,(e[0][1]+e[1][1])/2).distance(main.centroid))
            pieces.append(LineString([a,b]).buffer(13,cap_style=2))
    g=unary_union(pieces).difference(layout['building_protection']).difference(layout['roads'].buffer(.22)).difference(layout['rail_corridor']).difference(layout['water'])
    surface('SM_MPRR_NeighborApron','MPRR_ContextPaving',g,lambda x,y:height(x,y)+.075)
    return g

def railway(layout,height):
    tracks=[dict(id=r['id'],layer='railways',vertices=r['points_m']) for r in layout['rail_centerlines']]
    regions={f'{x}_{y}':g for x,y,g in tile(layout['rail_corridor'])}
    rail_detail.HEAD_WIDTH_M=.09;rail_detail.RAIL_OFFSET_M=(rail_detail.GAUGE_M+.09)/2
    def sink(name,role,v,f):
        GEO.mesh(name.replace('SM_MPR_Env_','SM_MPRR_Rail_'),'MPR3_'+role,[(x,y,z+height(x,y)-G)for x,y,z in v],f)
    rail=build_railways(dict(mesh=sink,zone=lambda x,y:f'{math.floor(x/TILE)}_{math.floor(y/TILE)}',regions=regions,include_freight=False),tracks,G)
    surface('SM_MPRR_RailCorridor','MPR3_Ballast',layout['rail_corridor'],lambda x,y:height(x,y)+.022,step=6)
    deck=unary_union([LineString(r['points_m']).buffer(1.7,cap_style=2) for r in layout['rail_centerlines']]).intersection(layout['roads'])
    ramps=deck.buffer(2.4,quad_segs=8).difference(deck).intersection(layout['roads'])
    surface('SM_MPRR_CrossingDeck','MPR3_Concrete',deck,lambda x,y:height(x,y)+.375,step=.65)
    surface('SM_MPRR_CrossingRamp','MPR3_Asphalt',ramps,lambda x,y:height(x,y)+.08+.295*(1-min(1,Point(x,y).distance(deck)/2.4)),step=.65)
    # Whole coupled consists on long source tracks, with locomotives and real wheel meshes.
    candidates=sorted([(LineString(r['points_m']).distance(Point(260,-20)),r['id'],LineString(r['points_m'])) for r in layout['rail_centerlines'] if r['length_m']>350])
    train_occupancy=[];train_audit=[]
    for _,track_id,line in candidates:
        if len(train_audit)>=3:break
        start=max(25,min(line.length-260,line.project(Point(260,-20))-110));count=min(16,int((line.length-start-20)/20.95))
        if count<6:continue
        train=[];safe=True
        for index in range(count):
            d=start+index*20.95;p=line.interpolate(d);a=line.interpolate(d-9);b=line.interpolate(d+9)
            yaw=math.degrees(math.atan2(b.y-a.y,b.x-a.x));f=pose_footprint((p.x,p.y),20.8,3.3,yaw)
            if f.intersects(layout['roads'].buffer(2)) or any(f.buffer(.2).intersects(q) for q in train_occupancy):safe=False;break
            train.append((p,yaw,f,index))
        if not safe:continue
        for p,yaw,f,index in train:
            name='SM_MPR4_Locomotive' if index==count-1 else 'SM_MPR4_FreightBoxcar'
            d=line.project(p);a=line.interpolate(d-8);b=line.interpolate(d+8)
            za,zb=height(a.x,a.y),height(b.x,b.y)
            pitch=math.degrees(math.atan2(zb-za,16.))
            instance(name,p.x,p.y,(za+zb)/2+.445,yaw,pitch_deg=pitch)
            train_occupancy.append(f)
        train_audit.append(dict(track=track_id,vehicles=count,spacing_m=20.95))
    return rail,deck.union(ramps),train_audit

def main():
    source,reg,hashes=inputs();t=reg['transform'];m=t['rotation_row_matrix'];s=t['scale'];o=t['offset_xy_m']
    def tx(p):return [s*(p[0]*m[0][0]+p[1]*m[1][0])+o[0],s*(p[0]*m[0][1]+p[1]*m[1][1])+o[1]]
    cad=read(ROOT/'SourceAssets/MPR/mpr_cad_layout.json');main=Polygon(cad['footprint_outline_m'])
    layout=build_layout(source,t,main);dump_layout(layout,OUT/'layout.json')
    print('MPRR_LAYOUT_READY',flush=True)
    height,terrain_audit=terrain(source,tx,main,layout['frame'],layout['water'])
    print('MPRR_TERRAIN_READY',flush=True)
    rail,crossing_mask,trains=railway(layout,height)
    yard,green,vehicles=vehicles_and_campus(main,layout,height,cad)
    neighbor_yards=neighbor_aprons(source,tx,main,layout,height)
    surface('SM_MPRR_Roads','MPR4_TerminalAsphalt',layout['roads'].difference(crossing_mask),lambda x,y:height(x,y)+.08)
    surface('SM_MPRR_Curblines','MPR4_TerminalCurb',layout['curbs'],lambda x,y:height(x,y)+.20)
    surface('SM_MPRR_WhiteEdges','MPR4_TerminalWhiteLine',layout['white_edges'].difference(crossing_mask),lambda x,y:height(x,y)+.105)
    surface('SM_MPRR_RoadDashes','MPR4_TerminalWhiteLine',layout['dash_lines'].difference(crossing_mask),lambda x,y:height(x,y)+.107)
    water=layout['water'].difference(yard)
    for i,p in enumerate(polygons(water)):
        level=min(height(x,y) for x,y in p.exterior.coords)+.02
        surface(f'SM_MPRR_Water{i}','MPR3_PondWater',p,level)
        banks=p.buffer(.7).difference(water).difference(layout['roads']).difference(main)
        def bank_height(x,y,pond=p,z=level):
            t=min(1,Point(x,y).distance(pond)/.7)
            return z+(height(x,y)+.025-z)*t
        surface(f'SM_MPRR_WaterBank{i}','MPR3_Concrete',banks,bank_height,step=.7,conform=False)
    print('MPRR_SITE_READY',flush=True)
    context=build_rebuild_context(GEO,source,tx,main.buffer(.5),layout['roads'].union(yard),layout['rail_corridor'],water,layout['frame'],ground_z=G,ground_elevation=height,campus_green=green,tree_exclusion=neighbor_yards)
    for name,rows in context['instances'].items():INST[name].extend(rows)
    REUSED.update(context['reused_meshes'])
    print('MPRR_CONTEXT_READY',context['audit']['summary'],flush=True)
    materials=copy.deepcopy(read(V4/'site/manifest.json')['materials']);materials.update(context['materials'])
    materials['MPR3_Grass'].update(base_color=[.36,.415,.345],normal_strength=.025,roughness=.98)
    materials['MPR3_Concrete'].update(base_color=[.59,.605,.60],normal_strength=.035)
    materials['MPR3_Asphalt'].update(base_color=[.205,.235,.265],normal_strength=.08)
    materials['MPR3_Ballast'].update(base_color=[.285,.30,.315],normal_strength=.15)
    materials['MPRR_CampusGreen']=dict(base_color=[.235,.32,.19],roughness=.98)
    materials['MPRR_ContextPaving']=dict(base_color=[.43,.46,.455],roughness=.96)
    materials['MPR4_TerminalAsphalt'].update(base_color=[.205,.235,.265],normal_strength=.08)
    materials['MPR4_TerminalCurb']['normal_strength']=.035
    apply_style({'materials':materials})
    for spec in materials.values():
        if spec.get('vertex_color_fade'):
            spec['vertex_color_fade']['ground_base_color']=materials['MPR3_Grass']['base_color']
    used={r for model in GEO.data.values()for r in model}|{r for roles in context['instance_material_roles'].values()for r in roles}
    used.add('MPR3_Grass');materials={k:v for k,v in materials.items() if k in used}
    textures={}
    for spec in materials.values():
        if spec.get('texture') and spec.get('textures'):textures[spec['texture']]=spec['textures']
    if '--geometry-only' in sys.argv:
        audit=dict(source_hashes=hashes,registration=reg,main_footprint=mapping(main),terrain=terrain_audit,
            roads=layout['audit'],crossings=layout['crossings'],rail=rail['stats'],trains=trains,vehicles=vehicles,
            context=context['audit'],main_apron=mapping(yard),neighbor_aprons=mapping(neighbor_yards),
            campus_green=mapping(green),water=mapping(water),old_resources_modified=False,
            triangulation=dict(calls=len(TRI_AUDIT),absolute_area_change_m2=sum(r['area_change_m2']for r in TRI_AUDIT)))
        payload=dict(geometry=GEO.data,instances=INST,materials=materials,textures=textures,
            counts=context['audit']['summary'],input_hashes=hashes,frame=mapping(layout['frame']),audit=audit,
            metadata=dict(rebuild_namespace='/Game/MPRWarehouse/RebuildB50B57',map='/Game/Maps/MPR_CAD_Warehouse_B50B57',
                reused_meshes=REUSED,instance_material_roles=context['instance_material_roles'],source_sha256=source['sha256']))
        with gzip.open(CACHE/'geometry_payload.json.gz','wt',encoding='utf8')as stream:json.dump(payload,stream,separators=(',',':'))
        print('MPRR_GEOMETRY_READY',len(GEO.data),flush=True)
        return
    # Only real project perimeter receives fade, never an internal road connection.
    def fade(name,p):
        d=layout['frame'].boundary.distance(Point(p[:2]));v=max(0,min(1,1-d/24))
        return v*v*(3-2*v)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    bpy.context.preferences.filepaths.save_version=0
    exporter.OUT,exporter.GEO,exporter.G,exporter.MATERIALS,exporter.INSTANCES=OUT,GEO,G,materials,INST
    exporter.COUNTS=Counter(context['audit']['summary'])
    exporter.export(textures,dict(rebuild_namespace='/Game/MPRWarehouse/RebuildB50B57',map='/Game/Maps/MPR_CAD_Warehouse_B50B57',
        reused_meshes=REUSED,instance_material_roles=context['instance_material_roles'],source_sha256=source['sha256']),vertex_fade=fade,flatten_fade=False)
    outblend=OUT/'MPR_B50B57_Rebuild.blend'
    for image in bpy.data.images:
        if image.source=='FILE' and image.filepath:image.filepath=bpy.path.relpath(bpy.path.abspath(image.filepath),start=str(OUT))
    bpy.ops.wm.save_as_mainfile(filepath=str(outblend))
    generated=OUT/'MPR_ReferenceSite.blend';assert generated.parent==OUT;generated.unlink()
    manifest=read(OUT/'manifest.json')
    for row in manifest['meshes']:
        row['category']='Context' if 'Context' in row['name'] else 'Site';row['full_precision_uvs']=True
    manifest['blend']=outblend.relative_to(ROOT).as_posix();manifest['source_generated_triangles']=sum(r['triangles']for r in manifest['meshes'])
    manifest['input_hashes']=hashes
    manifest['lighting_overrides']=[
        dict(actor_label='MPR4_KeyLight',component_name='LightComponent0',property='light_source_angle',value=5.),
        dict(actor_label='MPR4_ReferenceStyle',property='settings',value={
            'auto_exposure_bias':.2,
            'override_ambient_occlusion_fade_distance':True,
            'ambient_occlusion_fade_distance':180000.,
            'override_ambient_occlusion_fade_radius':True,
            'ambient_occlusion_fade_radius':20000.})]
    apply_style(manifest)
    write(OUT/'manifest.json',manifest)
    audit=dict(source_hashes=hashes,registration=reg,main_footprint=mapping(main),terrain=terrain_audit,
        roads=layout['audit'],crossings=layout['crossings'],rail=rail['stats'],trains=trains,vehicles=vehicles,
        context=context['audit'],main_apron=mapping(yard),neighbor_aprons=mapping(neighbor_yards),campus_green=mapping(green),water=mapping(water),
        triangulation=dict(calls=len(TRI_AUDIT),absolute_area_change_m2=sum(r['area_change_m2']for r in TRI_AUDIT)),
        geometry_triangles=manifest['source_generated_triangles'],old_resources_modified=False)
    write(OUT/'geometry_audit.json',audit)
    print('MPRR_BUILD_COMPLETE',len(manifest['meshes']),manifest['source_generated_triangles'],flush=True)
if __name__=='__main__':main()
