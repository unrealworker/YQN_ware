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
from shapely.geometry import Polygon, box as polygon_box
from shapely.ops import unary_union

G=-1.2
DATA=defaultdict(lambda:{'vertices':[],'faces':[],'roles':[]})
INSTANCES=defaultdict(list)
SOURCE=json.loads((OUT/'environment_local.json').read_text())
FOOTPRINT=SOURCE['alignment']['targetFootprint_m']
PALETTE=json.loads((ROOT/'SourceAssets/GHS/Park/reference_style.json').read_text())['palette']
PALETTE.update({'Solar':[.045,.075,.13],'Glass':[.24,.34,.44],
    'Detail':[.3,.39,.46],'Blue':[.018,.075,.51],'Rubber':[.018,.024,.028],
    'VehicleLights':[.46,.035,.025],'Water':[.23,.39,.46]})
RNG=random.Random(1001)
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


def source_context():
    for m in SOURCE['meshes']:
        pts=m['vertices'];center=[sum(v[i] for v in pts)/len(pts) for i in (0,1)]
        region=zone(*center);layer=m['layer']
        if layer in ('major_roads','minor_roads','paths'):
            role='Roads' if layer!='paths' else 'Hardstand'
            for f in m['faces']:
                face=Polygon([pts[i][:2] for i in f])
                if face.area>1e-7:ROAD_TRIANGLES[role].append(face)
            for loop in m['boundaryLoops']:
                ROAD_POLYS.append([pts[i][:2] for i in loop[:-1]])
            COUNTS['source_road_meshes']+=1
        elif layer=='buildings' and m['id']!='1583':
            if not m['footprintLoops']:continue
            outline=[pts[i][:2] for i in m['footprintLoops'][0][:-1]]
            BUILDING_POLYS.append(outline)
            height=14 if m['id']=='1582' else 9 if m['footprintAreaM2']>1000 else 6 if m['footprintAreaM2']>70 else 3.2
            # Context height inferred from building typology, never claimed surveyed.
            name='SM_MPR_Env_'+region+'_Buildings'
            poly(name,'Roofs',outline,G+height)
            for a,b in zip(outline,outline[1:]+outline[:1]):
                mesh(name,'Buildings',[(a[0],a[1],G),(b[0],b[1],G),(b[0],b[1],G+height),(a[0],a[1],G+height)],[(0,1,2,3)])
            COUNTS['source_context_buildings']+=1
    # Whole source tile provides the same extent as input map; simple subdivision
    # keeps batch bounds useful without duplicating street geometry.
    regions={'Near':polygon_box(-250,-170,250,240),'Far_E':polygon_box(250,-2000,2000,2000),
        'Far_W':polygon_box(-2000,-2000,-250,2000),'Far_N':polygon_box(-250,240,250,2000),'Far_S':polygon_box(-250,-2000,250,-170)}
    for role,polys in ROAD_TRIANGLES.items():
        merged=unary_union(polys)
        for region,clip in regions.items():
            clipped=shapely.make_valid(merged.intersection(clip))
            triangles=shapely.constrained_delaunay_triangles(clipped)
            for tri in triangles.geoms:
                if tri.area<1e-7:continue
                poly('SM_MPR_Env_'+region+'_'+role,role,list(tri.exterior.coords)[:-1],G+.035 if role=='Roads' else G+.045)
    for ix in range(-2,3):
        for iy in range(-2,3):
            box('SM_MPR_Env_Ground_'+str(ix+2)+'_'+str(iy+2),'Landscape',(ix*280,iy*280,G-.2),(280,280,.25))
    for line in SOURCE['polylines']:
        pts=line['vertices'];region=zone(sum(p[0] for p in pts)/len(pts),sum(p[1] for p in pts)/len(pts))
        if line['layer']=='railways':
            for a,b in zip(pts,pts[1:]):
                strip('SM_MPR_Env_'+region+'_RailBed','Detail',a,b,3.1,G+.04)
                dx,dy=b[0]-a[0],b[1]-a[1];ln=math.hypot(dx,dy)
                if ln<.01:continue
                nx,ny=-dy/ln,dx/ln
                for side in (-1,1):
                    aa=(a[0]+nx*.718*side,a[1]+ny*.718*side);bb=(b[0]+nx*.718*side,b[1]+ny*.718*side)
                    strip('SM_MPR_Env_'+region+'_Rails','Curbs',aa,bb,.08,G+.09)
                if region=='Near':
                    for k in range(int(ln/3.5)):
                        t=(k+.5)/max(1,int(ln/3.5));cx=a[0]+dx*t;cy=a[1]+dy*t
                        strip('SM_MPR_Env_Near_Sleepers','Trunk',(cx-nx*1.2,cy-ny*1.2),(cx+nx*1.2,cy+ny*1.2),.18,G+.07)
            COUNTS['source_railways']+=1
        else:
            poly('SM_MPR_Env_'+region+'_'+line['layer'],'Water' if line['layer']=='water' else 'Landscape',pts,G+.03)


def campus():
    # Loading courts follow the authoritative main CAD wall coordinates.
    poly('SM_MPR_Env_Near_Hardstand','Hardstand',[(-166.08,74.546),(166.786,74.546),(166.786,132),(-166.08,132)],G+.06)
    poly('SM_MPR_Env_Near_Hardstand','Hardstand',[(-166.08,-83.95),(135.367,-83.95),(135.367,-102),(-110,-115),(-166.08,-115)],G+.06)
    # Dock aprons have an intentional contrasting concrete band.
    box('SM_MPR_Env_Near_DockAprons','Ground',(0,83.5,G+.065),(332,17.9,.06))
    box('SM_MPR_Env_Near_DockAprons','Ground',(-15.5,-93,G+.065),(301,18.1,.06))
    # Short-edge car parks: reference-derived asphalt/kerb/marking, not CAD-surveyed.
    for side,xlo,xhi,ylo,yhi in [('W',-211,-183.0,-89,80),('E',184,210,-16,80)]:
        box('SM_MPR_Env_Near_Parking','Roads',((xlo+xhi)/2,(ylo+yhi)/2,G+.075),(xhi-xlo,yhi-ylo,.05))
        for px in (xlo+.2,xhi-.2):
            box('SM_MPR_Env_Near_Curbs','Curbs',(px,(ylo+yhi)/2,G+.14),(.25,yhi-ylo,.24))
        rows=[xlo+3.2,xhi-3.2]
        for r,x in enumerate(rows):
            for k in range(int((yhi-ylo)/2.9)):
                y=ylo+k*2.9
                strip('SM_MPR_Env_Near_Markings','Markings',(x-2.7,y),(x+2.7,y),.11,G+.109)
                if k%12==8:
                    box('SM_MPR_Env_Near_Islands','Landscape',(x,y+1.45,G+.18),(5.4,2.7,.23))
                    add_tree(x,y+1.45, .56)
                elif k%4==1 and (k+r)%3!=0:
                    car='SM_MPR_Env_Car_'+str((k+r)%2)
                    INSTANCES[car].append({'position_m':[x,y+1.45,G+.075],'rotation_deg':0 if r==0 else 180,'scale':[1,1,1]})
                    COUNTS['parked_cars']+=1
            COUNTS['marked_car_spaces']+=int((yhi-ylo)/2.9)
    # Approximate trailer staging bays visible on southwest court; sparse occupancy.
    for i in range(22):
        x=-154+i*4.0
        strip('SM_MPR_Env_Near_Markings','Markings',(x,-107),(x,-114),.1,G+.10)
    for x in range(-160,163,12):
        strip('SM_MPR_Env_Near_Markings','Markings',(x,121),(x+5,121),.15,G+.10)
    # Narrow landscaping bordering parking and step-back facade.
    for a,b in zip(FOOTPRINT[5:14],FOOTPRINT[6:15]):
        if a[0]>130 and b[0]>130:
            strip('SM_MPR_Env_Near_Landscape','Landscape',(a[0]+5,a[1]-5),(b[0]+5,b[1]-5),8,G+.08)
    # Trees in observed perimeter/parking bands, plus moderate context clusters.
    for x in range(-150,126,16):add_tree(x,-124+max(0,x+70)*.05,.65)
    for y in range(-80,80,15):add_tree(-216,y,.67)
    for y in range(-10,80,16):add_tree(216,y,.64)
    for x,y in [(171,-29),(166,-55),(151,-75),(137,-88),(126,-102),(113,-113)]:add_tree(x,y,.67)
    for _ in range(1500):
        if COUNTS['trees']>=180:break
        x=RNG.uniform(-430,440);y=RNG.uniform(-340,410)
        if -231<x<229 and -145<y<136:continue
        if any(boundary_clearance(x,y,p)<6 for p in BUILDING_POLYS+[FOOTPRINT]):continue
        if any(boundary_clearance(x,y,p)<6 for p in ROAD_POLYS):continue
        if abs(x)<220 and 125<y<230:continue
        # Railway band is not planted.
        if y< -140 and x> -130:continue
        add_tree(x,y,RNG.uniform(.60,.93))


def add_tree(x,y,scale):
    for items in INSTANCES.values():
        if any(math.hypot(p['position_m'][0]-x,p['position_m'][1]-y)<6 for p in items):return
    variant=COUNTS['trees']%3
    INSTANCES['SM_MPR_Env_Tree_'+str(variant)].append({'position_m':[x,y,G+.10],'rotation_deg':RNG.uniform(0,360),'scale':[scale]*3})
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
    source_context();campus();reusable_models();heal_coplanar_batches()
    mats={r:material(r) for r in sorted(set(r for d in DATA.values() for r in d['roles']))}
    rows=[]
    for name,d in sorted(DATA.items()):
        if not d['faces']:continue
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
        'material_palette':PALETTE,
        'alignment':SOURCE['alignment'],
        'assumptions':['Context heights are inferred: adjacent warehouse 14m, other industrial 9m, homes 6m, sheds 3.2m.',
        'Loading court and parking markings are screenshot-derived approximations; main CAD wall placement remains exact.',
        'Exterior ground -1.2m relative to warehouse finished floor is a visual dock-level estimate, not a survey.',
        'No exact tree/car location survey exists; perimeter planting and sparse parking follow supplied reference images.'],
        'optimization':{'geometry_batches':len(rows),'unique_triangles':sum(r['triangles'] for r in rows),
        'instance_count':sum(map(len,INSTANCES.values())),'material_slots':sum(len(r['material_roles']) for r in rows),
        'tree_variants':3,'car_variants':2,'context_collision':False,'partition':'Near campus and Far cardinal sectors; ground 280m tiles; road junction union removes coplanar overlaps'},
        'attribution':'Map geometry from user-supplied CADMapper export / OpenStreetMap contributors; reference screenshots are not used as textures.'}
    (OUT/'environment_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('MPR_ENVIRONMENT_COMPLETE '+json.dumps({'meshes':len(rows),'counts':dict(COUNTS),'optimization':manifest['optimization']}))


if __name__=='__main__':main()
