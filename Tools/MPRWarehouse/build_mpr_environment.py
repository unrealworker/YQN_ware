"""Build MPR source environment in isolated background Blender.

Coordinates are metres, main-CAD +Y retained. No source CAD/UE assets modified.
CADMapper streets/rails/buildings are preserved; fine campus geometry is a
reference-derived reconstruction, explicitly separated from measured data.
"""
from pathlib import Path
from collections import defaultdict
import json, math, hashlib, random, sys
import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/environment'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
from park_vegetation import build_tree
from park_vehicles import build_car
import shapely
from shapely.geometry import Polygon, Point, box as polygon_box
from shapely.ops import unary_union
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_site_roads import build_site_roads, emit_shape, MATERIALS as SITE_MATERIALS
from mpr_context_buildings import build_context_buildings, MATERIALS as CONTEXT_MATERIALS
from mpr_railway_detail import build_railways, PALETTE as RAIL_PALETTE, MATERIAL_PROPERTIES as RAIL_PROPERTIES

G=-1.2
DATA=defaultdict(lambda:{'vertices':[],'faces':[],'roles':[]})
INSTANCES=defaultdict(list)
SOURCE=json.loads((OUT/'environment_local.json').read_text())
FOOTPRINT=SOURCE['alignment']['targetFootprint_m']
PALETTE=json.loads((ROOT/'SourceAssets/GHS/Park/reference_style.json').read_text())['palette']
PALETTE.update({'Solar':[.045,.075,.13],'Glass':[.24,.34,.44],
    'Detail':[.3,.39,.46],'Blue':[.018,.075,.51],'Rubber':[.018,.024,.028],
    'VehicleLights':[.46,.035,.025],'Water':[.23,.39,.46]})
CUSTOM_MATERIALS={**SITE_MATERIALS,
    **{r:dict(color=p['color_linear'],roughness=p['roughness'],parent='Buildings' if r=='ContextWall' else 'Roofs') for r,p in CONTEXT_MATERIALS.items()},
    **{r:dict(color=c,parent='Detail',**RAIL_PROPERTIES[r]) for r,c in RAIL_PALETTE.items()}}
for role, spec in CUSTOM_MATERIALS.items():PALETTE[role]=spec['color']
RNG=random.Random(1001)
SITE=RAIL=CONTEXT=None
TREE_REJECTIONS=defaultdict(int)
COUNTS=defaultdict(int)
BUILDING_POLYS=[]
ROAD_POLYS=[]
ROAD_TRIANGLES=defaultdict(list)


def zone(x,y):
    if abs(x)<250 and -170<y<240: return 'Near'
    return 'Far_'+('E' if x>250 else 'W' if x<-250 else 'N' if y>240 else 'S')


def mesh(name,role,verts,faces):
    d=DATA[name]; off=len(d['vertices'])
    d['vertices'].extend(verts)
    d['faces'].extend(tuple(i+off for i in face) for face in faces)
    d['roles'].extend([role]*len(faces))


def poly(name,role,points,z):
    if len(points)<3:return
    vv=[Vector((p[0],p[1],z)) for p in points]
    ff=[]
    for tri in tessellate_polygon([vv]):
        ids=[i if isinstance(i,int) else min(range(len(vv)),key=lambda k:(vv[k]-i).length_squared) for i in tri]
        a,b,c=[vv[i] for i in ids]
        if (b-a).cross(c-a).z<0:ids.reverse()
        ff.append(ids)
    mesh(name,role,[tuple(v) for v in vv],ff)


def box(name,role,center,size,yaw=0):
    x,y,z=center; a,b,h=[s*.5 for s in size];c,s=math.cos(yaw),math.sin(yaw)
    pts=[(x+u*c-v*s,y+u*s+v*c) for u,v in [(-a,-b),(a,-b),(a,b),(-a,b)]]
    verts=[(u,v,z-h) for u,v in pts]+[(u,v,z+h) for u,v in pts]
    mesh(name,role,verts,[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])


def strip(name,role,a,b,width,z):
    dx,dy=b[0]-a[0],b[1]-a[1]; length=math.hypot(dx,dy)
    if length<1e-6:return
    nx,ny=-dy/length*width/2,dx/length*width/2
    poly(name,role,[(a[0]-nx,a[1]-ny),(b[0]-nx,b[1]-ny),(b[0]+nx,b[1]+ny),(a[0]+nx,a[1]+ny)],z)


def inside(p,pts):
    x,y=p; result=False
    for a,b in zip(pts,pts[1:]+pts[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:result=not result
    return result


def boundary_clearance(x,y,pts):
    best=1e9
    for a,b in zip(pts,pts[1:]+pts[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
        t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/den)) if den else 0
        best=min(best,math.hypot(x-a[0]-t*dx,y-a[1]-t*dy))
    return -best if inside((x,y),pts) else best


def build_scene_context():
    global SITE,RAIL,CONTEXT,BUILDING_POLYS
    api=dict(mesh=mesh,poly=poly,box=box,strip=strip,zone=zone,footprint=FOOTPRINT,include_freight=True)
    CONTEXT=build_context_buildings(api,SOURCE,G)
    BUILDING_POLYS=CONTEXT['footprints']
    COUNTS.update(CONTEXT['counts'])
    SITE=build_site_roads(api,SOURCE,G)
    RAIL=build_railways(api,SOURCE['polylines'],G)
    for ix in range(-2,3):
        for iy in range(-2,3):
            box('SM_MPR_Env_Ground_'+str(ix+2)+'_'+str(iy+2),'SiteBackdrop',(ix*280,iy*280,G-.2),(280,280,.25))
    # Water/park footprints retain source extents. Buildings and roads always
    # win over planted surfaces; trees use their exact same exclusion geometry.
    for line in SOURCE['polylines']:
        if line['layer']=='railways' or len(line['vertices'])<3:continue
        pts=line['vertices'];region=zone(sum(p[0] for p in pts)/len(pts),sum(p[1] for p in pts)/len(pts))
        shape=shapely.make_valid(Polygon([p[:2] for p in pts])).difference(SITE['paved'])
        emit_shape(api,'SM_MPR_Env_'+region+'_'+line['layer'],'SiteWater' if line['layer']=='water' else 'SiteGrass',shape,G+.03)
    for i,row in enumerate(SITE['cars']):INSTANCES['SM_MPR_Env_Car_'+str(i%2)].append(row)
    COUNTS['parked_cars']=len(SITE['cars'])
    COUNTS['marked_car_spaces']=SITE['audit']['parking_spaces_drawn']
    # Compact planting islands and continuous belts observed in the imagery.
    # Every candidate, including deterministic rows, passes the same clearance.
    for x,y in SITE['tree_island_centers']:add_tree(x,y,.43)
    for y in range(-90,321,11):add_tree(-227,y,.63)
    for x in range(-174,142,10):
        # South landscape edge follows the real Prologis bend rather than a
        # straight row crossing the carriageway.
        y=-151+max(0,x+80)*.09
        add_tree(x,y,.61)
    for y in range(-12,91,12):add_tree(221,y,.60)
    for x,y in [(158,-59),(169,-36),(149,-80),(134,-94),(121,-111),(110,-119)]:add_tree(x,y,.62)
    # Muted woodland masses in photograph-backed bands, not uniform scattering.
    patches=[(-225,-205,-140,-150),(-160,-290,70,-180),(-450,-95,-345,30),
             (-175,335,185,415),(216,125,250,305),(285,245,425,410)]
    for x0,y0,x1,y1 in patches:
        for x in range(x0,x1,12):
            for y in range(y0,y1,13):
                if RNG.random()<.54:add_tree(x+RNG.uniform(-3,3),y+RNG.uniform(-3,3),RNG.uniform(.57,.82))
    COUNTS['tree_candidates_rejected']=sum(TREE_REJECTIONS.values())


def add_tree(x,y,scale):
    radius=4.1*scale
    crown=Point(x,y).buffer(radius+.3,quad_segs=6)
    if crown.intersects(SITE['paved']):TREE_REJECTIONS['paved_surface']+=1;return
    if crown.intersects(RAIL['exclusion']):TREE_REJECTIONS['railway_corridor']+=1;return
    if crown.intersects(SITE['pond']):TREE_REJECTIONS['water']+=1;return
    if any(crown.intersects(Polygon(p).buffer(.5)) for p in BUILDING_POLYS+[FOOTPRINT]):TREE_REJECTIONS['building']+=1;return
    for name,items in INSTANCES.items():
        if '_Tree_' not in name:continue
        if any(math.hypot(p['position_m'][0]-x,p['position_m'][1]-y)<radius+4.1*p['scale'][0]+.5 for p in items):
            TREE_REJECTIONS['other_tree']+=1;return
    variant=COUNTS['trees']%3
    INSTANCES['SM_MPR_Env_Tree_'+str(variant)].append({'position_m':[x,y,G+.1],'rotation_deg':RNG.uniform(0,360),'scale':[scale]*3})
    COUNTS['trees']+=1


def reusable_models():
    for v in range(3):
        name='SM_MPR_Env_Tree_'+str(v)
        build_tree({'mesh':lambda role,verts,faces:mesh(name,role,verts,faces)},0,0,variant=v,base_z=0)
    for v in range(2):
        name='SM_MPR_Env_Car_'+str(v)
        build_car({'mesh':lambda role,verts,faces:mesh(name,role,verts,faces)},0,0,variant=v,blue=bool(v))


def material(role):
    mat=bpy.data.materials.new('M_MPR_Env_'+role);mat.diffuse_color=(*PALETTE.get(role,[.4,.5,.6]),1)
    mat.use_nodes=True;bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value=mat.diffuse_color;bsdf.inputs['Roughness'].default_value=.8
    if role in ('Glass','Solar'):bsdf.inputs['Roughness'].default_value=.34
    return mat


def heal_coplanar_batches():
    # Railway branch fans and adjacent planter ribbons also overlap in the
    # source. Union only horizontal single-role surfaces; never alter volumes.
    for name,d in DATA.items():
        if not any(name.endswith(suffix) for suffix in ('_Rails','_RailBed','_Sleepers','_Landscape')):continue
        if len(set(d['roles']))!=1 or not d['vertices']:continue
        zz={round(v[2],5) for v in d['vertices']}
        if len(zz)!=1:continue
        role=d['roles'][0];z=next(iter(zz))
        polys=[Polygon([d['vertices'][i][:2] for i in face]) for face in d['faces']]
        merged=unary_union([p for p in polys if p.area>1e-7])
        d['vertices']=[];d['faces']=[];d['roles']=[]
        for triangle in shapely.constrained_delaunay_triangles(merged).geoms:
            poly(name,role,list(triangle.exterior.coords)[:-1],z)


def main():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    build_scene_context();reusable_models();heal_coplanar_batches()
    mats={r:material(r) for r in sorted(set(r for d in DATA.values() for r in d['roles']))}
    rows=[]
    for name,d in sorted(DATA.items()):
        if not d['faces']:continue
        # Far railway profiles intentionally keep only their visible top.
        # Drop unreferenced lower vertices so manifest/FBX/UE render bounds agree.
        used=sorted({i for face in d['faces'] for i in face})
        remap={old:new for new,old in enumerate(used)}
        d['vertices']=[d['vertices'][i] for i in used]
        d['faces']=[tuple(remap[i] for i in face) for face in d['faces']]
        meshdata=bpy.data.meshes.new(name);meshdata.from_pydata(d['vertices'],[],d['faces']);meshdata.update()
        obj=bpy.data.objects.new(name,meshdata);bpy.context.collection.objects.link(obj)
        roles=sorted(set(d['roles']))
        for r in roles:obj.data.materials.append(mats[r])
        for p,r in zip(obj.data.polygons,d['roles']):p.material_index=roles.index(r)
        # Smooth foliage / curved cars; hard context remains flat.
        if '_Tree_' in name or '_Car_' in name:
            for p in obj.data.polygons:p.use_smooth=True
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
        fbx=OUT/(name+'.fbx')
        bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},
            use_mesh_modifiers=True,add_leaf_bones=False,bake_anim=False,axis_forward='-Y',axis_up='Z',apply_unit_scale=True)
        bounds=[[min(v[i] for v in d['vertices']),max(v[i] for v in d['vertices'])] for i in range(3)]
        rows.append({'name':name,'fbx':fbx.relative_to(ROOT).as_posix(),'material_roles':roles,'bounds_m':bounds,
            'triangles':sum(len(f)-2 for f in d['faces']),'vertices':len(d['vertices']),
            'collision':False,'sha256':hashlib.sha256(fbx.read_bytes()).hexdigest(),
            'instance_only':name in INSTANCES,'source_geometry':'GHS reusable generator' if '_Tree_' in name or '_Car_' in name else 'CADMapper + documented reference reconstruction'})
    bpy.ops.object.select_all(action='DESELECT')
    for name,items in INSTANCES.items():
        base=bpy.data.objects[name];base.hide_render=True;base.hide_set(True)
        for i,p in enumerate(items):
            ob=bpy.data.objects.new(name+'_Instance_'+str(i),base.data);bpy.context.collection.objects.link(ob)
            ob.location=p['position_m'];ob.rotation_euler.z=math.radians(p['rotation_deg']);ob.scale=p['scale']
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_Environment.blend'))
    manifest={'schema_version':1,'coordinate_frame':'Main CAD metres; +Y retained; FBX forward -Y/up Z; UE reflects Y on import',
        'ground_z_m':G,'meshes':rows,'instances':dict(INSTANCES),'counts':dict(COUNTS),
        'material_palette':PALETTE,'material_overrides':CUSTOM_MATERIALS,
        'site_revision':2,'road_audit':SITE['audit'],'railway_audit':RAIL['stats'],
        'tree_clearance':{'all_candidates_checked':True,'crown_road_intersections':0,'railway_intersections':0,'rejected':dict(TREE_REJECTIONS)},
        'context_building_audit':CONTEXT['buildings'],
        'alignment':SOURCE['alignment'],
        'assumptions':['Context heights are inferred: adjacent warehouse 14m, other industrial 9m, homes 6m, sheds 3.2m.',
        'Loading court and parking markings are screenshot-derived approximations; main CAD wall placement remains exact.',
        'Exterior ground -1.2m relative to warehouse finished floor is a visual dock-level estimate, not a survey.',
        'No exact tree/car location survey exists; compact landscape bands follow supplied images and exclude all pavement, buildings and railway corridors.'],
        'optimization':{'geometry_batches':len(rows),'unique_triangles':sum(r['triangles'] for r in rows),
        'instance_count':sum(map(len,INSTANCES.values())),'material_slots':sum(len(r['material_roles']) for r in rows),
        'tree_variants':3,'car_variants':2,'context_collision':False,'partition':'Near campus and Far cardinal sectors; ground 280m tiles; road junction union removes coplanar overlaps'},
        'attribution':'Map geometry from user-supplied CADMapper export / OpenStreetMap contributors; reference screenshots are not used as textures.'}
    (OUT/'environment_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('MPR_ENVIRONMENT_COMPLETE '+json.dumps({'meshes':len(rows),'counts':dict(COUNTS),'optimization':manifest['optimization']}))


if __name__=='__main__':main()
