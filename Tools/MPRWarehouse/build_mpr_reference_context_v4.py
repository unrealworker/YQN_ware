"""Reference-aligned context modules/instances for V4, isolated Blender only.

Run --samples-only before the image-to-ground calibration is available. Other
mode consumes the pixel layout and calibration and emits context manifolds.
This script never opens UE or touches existing MPR interior assets.
"""
import sys, json, math, hashlib
from pathlib import Path
from collections import defaultdict
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from mpr_blender_common import Geometry, PALETTE
from calibrate_mpr_reference_camera import image_to_ground, load_calibration
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union,triangulate
from park_curves import rounded_path

OUT=ROOT/'SourceAssets/MPR/reference_v4/context'
G=Geometry()
MATERIALS={
 'MPR4_ContextWall':dict(base_color=[.72,.735,.72],roughness=.88),
 'MPR4_ContextRoof':dict(base_color=[.78,.79,.785],roughness=.85),
 'MPR4_ContextTrim':dict(base_color=[.57,.59,.58],roughness=.88),
 'MPR4_ContextGlass':dict(base_color=[.31,.36,.365],roughness=.42),
 'MPR4_ContextPaving':dict(base_color=[.54,.565,.55],roughness=.95),
}
PALETTE.update({r:s['base_color'] for r,s in MATERIALS.items()})
W,R,T,V,P=list(MATERIALS)


def box(name,role,center,size,yaw=0):G.box(name,role,center,size,yaw)


def roof(name,x,y,width,depth,eave,ridge,axis='x'):
    a,b=width/2,depth/2
    verts=[(x-a,y-b,eave),(x+a,y-b,eave),(x+a,y+b,eave),(x-a,y+b,eave),(x-a,y,ridge),(x+a,y,ridge)]
    G.mesh(name,R,verts,[(0,1,5,4),(4,5,2,3)])
    G.mesh(name,W,verts,[(0,4,3),(1,2,5)])
    for sy in (-1,1):box(name,T,(x,y+sy*b,eave-.06),(width+.08,.13,.14))
    box(name,T,(x,y,ridge+.025),(width+.12,.14,.09))


def house(name,width,depth,eave,ridge,variant=0,lod=0):
    box(name,W,(0,0,eave/2),(width,depth,eave))
    roof(name,0,0,width+.38,depth+.38,eave,ridge)
    if lod:return
    box(name,T,(0,0,.12),(width+.12,depth+.12,.24))
    front=-depth/2
    # Front-door recess, understated window frames, and shallow front porch.
    box(name,V,(-width*.22,front-.025,1.1),(.9,.055,2.05))
    for x in (-width*.33,width*.26):
        for sy in (-1,1):
            yy=sy*(depth/2+.025)
            box(name,T,(x,yy,2.25),(1.55,.085,1.4))
            box(name,V,(x,yy+sy*.046,2.25),(1.3,.025,1.16))
            box(name,W,(x,yy+sy*.066,2.25),(.06,.035,1.16))
    for sx in (-1,1):
        for yy in (-depth*.25,depth*.25):
            box(name,T,(sx*(width/2+.02),yy,2.2),(.08,1.3,1.35))
            box(name,V,(sx*(width/2+.065),yy,2.2),(.025,1.08,1.12))
    if variant==1:
        # Attached garage extends the front silhouette without a detached prop.
        gx=width*.25;gw=width*.43
        box(name,W,(gx,front-.6,1.55),(gw,1.2,3.1))
        box(name,R,(gx,front-.65,3.16),(gw+.2,1.45,.15))
        box(name,T,(gx,front-1.22,1.4),(gw-.35,.045,2.5))
        for z in (.6,1.2,1.8,2.4):box(name,W,(gx,front-1.25,z),(gw-.5,.025,.035))
    else:
        px=-width*.22;pw=3.1
        box(name,P,(px,front-.75,.17),(pw,1.6,.34))
        box(name,R,(px,front-.8,2.9),(pw+.18,1.8,.18))
        for sx in (-1,1):box(name,W,(px+sx*(pw/2-.15),front-1.45,1.55),(.13,.13,2.65))
    box(name,T,(width*.24,depth*.16,ridge-.20),(.55,.65,1.0))


def cylinder(name,role,center,radius,height,segments=40):
    x,y,z=center;vv=[]
    for dz in (0,height):
        vv.extend((x+radius*math.cos(i*math.tau/segments),y+radius*math.sin(i*math.tau/segments),z+dz) for i in range(segments))
    faces=[tuple(range(segments-1,-1,-1)),tuple(range(segments,segments*2))]
    faces.extend((i,(i+1)%segments,(i+1)%segments+segments,i+segments) for i in range(segments))
    G.mesh(name,role,vv,faces)


def tank(name,radius=12,height=12,lod=0):
    n=48 if not lod else 16
    cylinder(name,W,(0,0,0),radius,height,n)
    cylinder(name,R,(0,0,height),radius+.12,.15,n)
    cylinder(name,T,(0,0,.05),radius+.35,.15,n)
    if not lod:
        for angle in (0,math.pi/2,math.pi,3*math.pi/2):
            x,y=(radius+.13)*math.cos(angle),(radius+.13)*math.sin(angle)
            box(name,T,(x,y,height*.5),(.08,.08,height))
        box(name,T,(radius+.35,0,height*.5),(.15,.65,height))
        for z in range(1,int(height)):box(name,W,(radius+.45,0,z),(.12,.7,.055))


def reference_tank(row,ground,calibration,lod=0):
    """Match the visible ellipse at its top elevation, then extrude vertically."""
    name='SM_MPR4_Context_TankField'+('_LOD1' if lod else '')
    height=row['estimated_height_m'];cx,cy=row['pixel_roof_center'];rx,ry=row['pixel_roof_ellipse_radius_px'];n=64 if not lod else 24
    points=[image_to_ground(cx+rx*math.cos(i*math.tau/n),cy+ry*math.sin(i*math.tau/n),z=ground+height,calibration=calibration)[:2] for i in range(n)]
    G.prism(name,W,points,ground,ground+height-.11)
    G.prism(name,R,points,ground+height-.11,ground+height)
    if not lod:
        for a,b in zip(points,points[1:]+points[:1]):G.segment(name,T,a,b,.11,ground+height+.02,.08)
        # A ladder on the far side is deliberately quiet in the overview.
        x,y=points[n//4];box(name,T,(x,y,ground+height*.5),(.14,.58,height))
        for z in range(1,int(height)):box(name,W,(x,y-.1,ground+z),(.18,.74,.055))
    return points


def context_paving(layout,ground,calibration):
    """Reference tank pads and service pipes; clip pads against traced roads."""
    world=lambda p,z=ground:image_to_ground(*p,z=z,calibration=calibration)[:2]
    source=json.loads((ROOT/'SourceAssets/MPR/reference_v4/site/reference_site_pixels.json').read_text(encoding='utf-8'))
    roads=[]
    for row in source['roads']:
        at=row['points'][len(row['points'])//2]
        width=math.dist(world(at),world([at[0]+row['width_px'],at[1]]))
        radius=math.dist(world(at),world([at[0]+row['radius_px'],at[1]]))
        roads.append(LineString(rounded_path([world(p) for p in row['points']],radius=radius,max_step=.5)).buffer(width/2+.5,quad_segs=16))
    pads=unary_union([Polygon([world(p) for p in row['outline']]) for row in layout.get('tank_pads',[])]).difference(unary_union(roads))
    pieces=list(pads.geoms) if hasattr(pads,'geoms') else [pads]
    for poly in pieces:
        for triangle in triangulate(poly):
            if not poly.covers(triangle):continue
            vertices=[(x,y,ground+.12) for x,y in list(triangle.exterior.coords)[:-1]]
            G.mesh('SM_MPR4_Context_TankPads',P,vertices,[(0,1,2)])
        for a,b in zip(poly.exterior.coords,list(poly.exterior.coords)[1:]):G.segment('SM_MPR4_Context_TankPads',T,a,b,.27,ground+.18,.22)
    for path in layout.get('tank_pipes',[]):
        controls=[world(p,ground+2.0) for p in path]
        for a,b in zip(controls,controls[1:]):
            dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);nx,ny=-dy/length,dx/length
            for offset in (-.35,.35):
                aa=(a[0]+nx*offset,a[1]+ny*offset);bb=(b[0]+nx*offset,b[1]+ny*offset)
                G.segment('SM_MPR4_Context_TankPipes',R,aa,bb,.24,ground+2.0,.24)
            for i in range(int(length/8)+1):
                t=i/max(1,int(length/8));x=a[0]*(1-t)+b[0]*t;y=a[1]*(1-t)+b[1]*t
                box('SM_MPR4_Context_TankPipes',T,(x,y,ground+1.0),(.2,.2,2.0))
    return [list(p.exterior.coords)[:-1] for p in pieces]


def warehouse(name,outline,height,dock_edge=None,docks=0):
    G.prism(name,W,outline,0,height)
    # Facade recesses are actual open geometry in front of the rear wall,
    # separated by projecting columns and a clear overhead canopy.
    cx=sum(p[0] for p in outline)/len(outline);cy=sum(p[1] for p in outline)/len(outline)
    G.prism(name,R,outline,height,height+.14)
    for a,b in zip(outline,outline[1:]+outline[:1]):G.segment(name,T,a,b,.17,height+.18,.22)
    if dock_edge:
        a,b=dock_edge;dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);tx,ty=dx/length,dy/length
        nx,ny=ty,-tx
        if nx*(cx-a[0])+ny*(cy-a[1])>0:nx,ny=-nx,-ny
        yaw=math.degrees(math.atan2(ty,tx));span=(length-10)/docks
        for k in range(docks):
            s=5+(k+.5)*span;x=a[0]+tx*s;y=a[1]+ty*s
            # A 2.1 m-deep loading recess has a rear door, projecting piers,
            # a deep canopy and a concrete platform to read in the overview.
            box(name,V,(x+nx*.05,y+ny*.05,height*.25),(min(span-1,6.0),.08,height*.44),yaw)
            box(name,T,(x+nx*.25,y+ny*.25,2.1),(3.4,.13,3.8),yaw)
            box(name,W,(x+nx*2.1,y+ny*2.1,height*.48),(span-.1,4.3,.48),yaw)
            for sign in (-1,1):
                box(name,W,(x+nx*1.1+tx*sign*(span/2-.23),y+ny*1.1+ty*sign*(span/2-.23),height*.24),(.46,2.35,height*.48),yaw)
            box(name,P,(x+nx*2.2,y+ny*2.2,.28),(span-.12,4.6,.56),yaw)
        xs=[p[0] for p in outline];ys=[p[1] for p in outline]
        for i in range(7):
            for j in range(2):
                x=min(xs)+(max(xs)-min(xs))*(i+.7)/7.5;y=min(ys)+(max(ys)-min(ys))*(j+1)/3
                box(name,T,(x,y,height+.3),(1.9,1.6,.6))


def minimum_rectangle(points):
    best=None
    for a,b in zip(points,points[1:]+points[:1]):
        angle=math.atan2(b[1]-a[1],b[0]-a[0]);c,s=math.cos(angle),math.sin(angle)
        p=[(x*c+y*s,-x*s+y*c) for x,y in points]
        lo=[min(v[i] for v in p) for i in (0,1)];hi=[max(v[i] for v in p) for i in (0,1)]
        size=[hi[i]-lo[i] for i in (0,1)];area=size[0]*size[1]
        if best is None or area<best[0]:
            x,y=(hi[0]+lo[0])/2,(hi[1]+lo[1])/2
            best=(area,[x*c-y*s,x*s+y*c],size,math.degrees(angle))
    _,center,size,yaw=best
    if size[1]>size[0]:size=list(reversed(size));yaw+=90
    return center,size,yaw


def mapped_context():
    global G
    G=Geometry();layout=json.loads((OUT/'reference_context_layout.json').read_text(encoding='utf-8'));calibration=load_calibration()
    ground=calibration['ground_plane_z_m'];instances=defaultdict(list);world_rows=[]
    specs={'Cottage':(10,8,3.8,5.9,0),'Garage':(11.2,8.8,4.0,6.3,1),'LongGable':(14,8.2,4.2,6.4,2)}
    prototypes={}
    for style,(w,d,e,r,v) in specs.items():
        for lod in (0,1):
            temporary='HousePrototype_'+style+str(lod);house(temporary,w,d,e,r,v,lod)
            prototypes[style,lod]=G.data.pop(temporary)
    for index,row in enumerate(layout['buildings']):
        height=row['estimated_height_m'];points=[image_to_ground(*p,z=ground+height,calibration=calibration)[:2] for p in row['pixel_outline']]
        record=dict(id=row['id'],type=row['type'],footprint_m=points,estimated_height_m=height,source='visible reference roof with height compensation')
        if row['type']=='house_gable':
            # A screen-space rectangle back-projects to a sheared quadrilateral.
            # Reboxing it in world space enlarged the houses into strips. Warp
            # the small detailed module inside those exact four corners, then
            # merge spatial batches, preserving the intended pixel footprint.
            pixels=list(row['pixel_outline'])
            if math.dist(pixels[0],pixels[1])<math.dist(pixels[1],pixels[2]):pixels=pixels[1:]+pixels[:1]
            short_world=min(math.dist(points[i],points[(i+1)%4]) for i in range(4))
            height=max(5.6,min(13.,short_world*.50))
            style='LongGable' if math.dist(pixels[0],pixels[1])/max(math.dist(pixels[1],pixels[2]),1)>1.65 else ('Garage' if index%3==1 else 'Cottage')
            w,d,e,r,v=specs[style]
            quad=[image_to_ground(*p,z=ground+height*e/r,calibration=calibration)[:2] for p in pixels]
            center=[sum(p[i] for p in quad)/4 for i in (0,1)]
            name='SM_MPR4_Context_Houses_%d_%d'%(math.floor(center[0]/150),math.floor(center[1]/150))
            for lod in (0,1):
                target=name+('_LOD1' if lod else '')
                for role,(vertices,faces) in prototypes[style,lod].items():
                    vv=[]
                    for x,y,z in vertices:
                        a=x/(w+.38)+.5;b=y/(d+.38)+.5
                        px=(1-a)*(1-b)*quad[0][0]+a*(1-b)*quad[1][0]+a*b*quad[2][0]+(1-a)*b*quad[3][0]
                        py=(1-a)*(1-b)*quad[0][1]+a*(1-b)*quad[1][1]+a*b*quad[2][1]+(1-a)*b*quad[3][1]
                        vv.append((px,py,ground+z*height/r))
                    signed_area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(quad,quad[1:]+quad[:1]))
                    G.mesh(target,role,vv,[tuple(reversed(f)) for f in faces] if signed_area<0 else faces)
            record.update(mesh=name,footprint_m=quad,estimated_height_m=height,
                          placement_method='screen-outline quadrilateral; spatially batched low-poly detailed houses')
        else:
            name='SM_MPR4_Context_'+row['id'];edge=None
            if row.get('dock_facade_pixel_edge'):edge=[image_to_ground(*p,z=ground+height,calibration=calibration)[:2] for p in row['dock_facade_pixel_edge']]
            warehouse(name,points,height,edge,row.get('dock_count',0))
            if row['type']=='sawtooth_industrial':
                a,b,c,d=points
                for k in range(1,8):
                    t=k/8;aa=[a[i]*(1-t)+b[i]*t for i in (0,1)];bb=[d[i]*(1-t)+c[i]*t for i in (0,1)]
                    G.segment(name,T,aa,bb,.14,height+.23,.18)
            # Static world meshes include the common ground offset; no actor
            # transform is required when the importer spawns their origin.
            for role,(vertices,faces) in G.data[name].items():G.data[name][role][0]=[(x,y,z+ground) for x,y,z in vertices]
            record['mesh']=name
        world_rows.append(record)
    for row in layout['tanks']:
        footprint=reference_tank(row,ground,calibration);reference_tank(row,ground,calibration,lod=1)
        world_rows.append(dict(id=row['id'],type=row['type'],footprint_m=footprint,estimated_height_m=row['estimated_height_m'],mesh='SM_MPR4_Context_TankField',
                               placement_method='visible top ellipse back-projected at estimated height; vertical extrusion, visual reconstruction'))
    paved=context_paving(layout,ground,calibration)
    calibration_path=ROOT/'SourceAssets/MPR/reference_v3/calibration/camera_calibration.json'
    manifest=G.export(OUT,'mpr4_reference_context',dict(materials=MATERIALS,instances=dict(instances),
        source_pixel_layout='SourceAssets/MPR/reference_v4/context/reference_context_layout.json',
        calibration_path=calibration_path.relative_to(ROOT).as_posix(),calibration_sha256=hashlib.sha256(calibration_path.read_bytes()).hexdigest(),
        source_policy='Exterior placement follows reference image; heights and occluded details estimated; MPR interior untouched'))
    names={r['name']:r for r in manifest['meshes']}
    for name,row in names.items():
        row['instance_only']=name in instances or name.endswith('_LOD1');row['lod']=1 if name.endswith('_LOD1') else 0
        if name+'_LOD1' in names:
            row['lod_files']=[names[name+'_LOD1']['fbx']];row['lod_screen_sizes']=[1.,.09]
        row['collision']=False
    manifest['context_buildings']=world_rows
    manifest['footprints_m']=[r['footprint_m'] for r in world_rows]
    manifest['paved_footprints_m']=paved
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'reference_context_ground_layout.json').write_text(json.dumps(dict(schema_version=4,buildings=world_rows,calibration_sha256=manifest['calibration_sha256']),ensure_ascii=False,indent=2),encoding='utf-8')
    print('MPR4_MAPPED_CONTEXT_READY',len(world_rows),sum(len(v) for v in instances.values()))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    samples='--samples-only' in sys.argv
    if not samples:
        mapped_context();return
    specs=[('Cottage',10,8,3.8,5.9,0),('Garage',11.2,8.8,4.0,6.3,1),('LongGable',14,8.2,4.2,6.4,2)]
    for style,w,d,e,r,v in specs:
        house('SM_MPR4_Context_'+style,w,d,e,r,v)
        house('SM_MPR4_Context_'+style+'_LOD1',w,d,e,r,v,1)
    tank('SM_MPR4_Context_Tank');tank('SM_MPR4_Context_Tank_LOD1',lod=1)
    warehouse('SM_MPR4_Context_NeighborSample',[[-28,-12],[28,-12],[28,12],[-28,12]],12,[[-28,-12],[28,-12]],6)
    metadata=dict(materials=MATERIALS,source='reference_context_layout.json',scope='Context only; no MPR interior assets',samples_only=samples)
    manifest=G.export(OUT/'samples','mpr4_context_samples',metadata)
    for row in manifest['meshes']:
        row['instance_only']=not row['name'].endswith('NeighborSample')
        row['lod']=1 if row['name'].endswith('_LOD1') else 0
    (OUT/'samples/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    if '--render-samples' in sys.argv:
        positions={'Cottage':(-34,-7,0),'Garage':(-15,-7,0),'LongGable':(7,-7,0),'Tank':(36,2,0),'NeighborSample':(0,34,0)}
        for ob in bpy.context.scene.objects:
            if ob.type!='MESH':continue
            ob.hide_render=ob.name.endswith('_LOD1')
            key=ob.name.removeprefix('SM_MPR4_Context_').removesuffix('_LOD1');ob.location=positions[key]
        bpy.ops.mesh.primitive_plane_add(size=250,location=(0,0,-.06));floor=bpy.context.object
        mat=bpy.data.materials.new('SampleGround');mat.diffuse_color=(.43,.48,.44,1);floor.data.materials.append(mat)
        bpy.ops.object.light_add(type='SUN',location=(40,-45,75));sun=bpy.context.object;sun.data.energy=2.1;sun.rotation_euler=(math.radians(27),math.radians(-19),math.radians(-27));sun.data.angle=math.radians(12)
        bpy.ops.object.camera_add(location=(84,-112,83));cam=bpy.context.object;target=Vector((0,16,3));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=126
        scene=bpy.context.scene;scene.camera=cam;scene.render.engine='CYCLES';scene.cycles.samples=24
        scene.world.color=(.30,.33,.37);scene.render.resolution_x=1500;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
        scene.view_settings.view_transform='Standard';scene.render.image_settings.file_format='PNG';scene.render.filepath=str(OUT/'samples/representative_models.png');bpy.ops.render.render(write_still=True)
    print('MPR4_CONTEXT_SAMPLES_READY')


if __name__=='__main__':main()
