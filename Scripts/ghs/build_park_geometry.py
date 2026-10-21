"""Build additive GHS campus/context meshes in isolated background Blender.

Satellite-reference massing, not a surveyed property plan. All dimensions are
metres. Local u follows the warehouse long axis; v points toward the dock yard.
FBX import at UE origin/scale 1 reproduces X=(u-239.33385)*100,
Y=(v-60.24019)*100. Existing warehouse content is never read or modified here.
"""
from pathlib import Path
import hashlib
import json
import math
import random
import sys
from collections import defaultdict

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/GHS/Park'
OUT.mkdir(parents=True, exist_ok=True)
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
from park_vegetation import PALETTE as VEGETATION_PALETTE, build_tree
from park_vehicles import build_car
RNG = random.Random(17335)
ORIGIN = (239.33385, 60.24019)
CAMPUS = [(-10,-10),(475,-15),(500,-25),(535,0),(570,68),
          (548,115),(452,157),(251,209),(46,278),(11,266),(-2,220),(-10,170)]
WAREHOUSE = [(0,0),(465.7344,0),(465.7344,111.98368),(440.88196,118.872),
             (45.8724,118.872),(45.8724,137.16),(0,137.16)]
PALETTE = {
    'Ground': (.70,.75,.78), 'Hardstand': (.72,.76,.79),
    'Roads': (.27,.33,.39), 'CampusRoads': (.60,.65,.69),
    'ContextRoads': (.31,.38,.45), 'Curbs': (.84,.88,.92),
    'Markings': (.91,.94,.98), 'Buildings': (.87,.90,.93),
    'Roofs': (.72,.78,.83), 'Trees': (.43,.56,.50),
    'Landscape': (.53,.63,.57), 'Glass': (.24,.34,.44),
    'Blue': (.018,.075,.51), 'Detail': (.30,.39,.46),
    'Fence': (.23,.31,.40), 'Solar': (.045,.075,.13),
    'Rubber': (.018,.024,.028), 'VehicleLights': (.46,.035,.025),
}
PALETTE.update(VEGETATION_PALETTE)

DATA = defaultdict(lambda: {'vertices': [], 'faces': [], 'parts': 0})
COUNTS = defaultdict(int)
PREVIEW = []
ROAD_INDEX = 0
CONTEXT_ROADS = []
HOUSE_CLEARANCES = []
PARKED_VEHICLES = []


def road_clearance(u,v,radius):
    result=float('inf')
    for path,road_width in CONTEXT_ROADS:
        for a,b in zip(path,path[1:]):
            dx,dy=b[0]-a[0],b[1]-a[1]
            denominator=dx*dx+dy*dy
            t=max(0,min(1,((u-a[0])*dx+(v-a[1])*dy)/denominator)) if denominator else 0
            distance=math.hypot(u-a[0]-t*dx,v-a[1]-t*dy)
            result=min(result,distance-radius-road_width*.5)
    return result


def mesh(role, vertices, faces):
    data = DATA[role]
    offset = len(data['vertices'])
    data['vertices'].extend((u-ORIGIN[0], -(v-ORIGIN[1]), z) for u,v,z in vertices)
    # The Y reflection reverses winding.
    data['faces'].extend(tuple(offset+i for i in reversed(face)) for face in faces)
    data['parts'] += 1


def poly(role, points, z, record=False):
    verts = [Vector((u,v,z)) for u,v in points]
    triangles = tessellate_polygon([verts])
    faces = []
    for triangle in triangles:
        ids = [p if isinstance(p,int) else min(range(len(verts)), key=lambda i: (verts[i]-p).length_squared)
               for p in triangle]
        a,b,c = [points[i] for i in ids]
        if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]) < 0:
            ids.reverse()
        faces.append(ids)
    mesh(role, [(u,v,z) for u,v in points], faces)
    if record:
        PREVIEW.append((role, points))


def rotate_point(x, y, center, angle):
    c,s = math.cos(angle), math.sin(angle)
    return center[0]+x*c-y*s, center[1]+x*s+y*c


def box(role, center, size, angle=0, record=False):
    u,v,z = center
    a,b,h = [d*.5 for d in size]
    xy = [rotate_point(x,y,(u,v),angle) for x,y in [(-a,-b),(a,-b),(a,b),(-a,b)]]
    verts = [(x,y,z-h) for x,y in xy] + [(x,y,z+h) for x,y in xy]
    mesh(role, verts, [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
    if record:
        PREVIEW.append((role,xy))


def ribbon(role, path, width, z, record=False):
    if len(path)<2:
        return
    left,right = [],[]
    for i,p in enumerate(path):
        before = path[max(0,i-1)]
        after = path[min(len(path)-1,i+1)]
        if i == 0:
            before=p
        if i == len(path)-1:
            after=p
        tangents=[]
        for a,b in ((before,p),(p,after)):
            dx,dy=b[0]-a[0],b[1]-a[1]
            length=math.hypot(dx,dy)
            if length>1e-6:
                tangents.append((dx/length,dy/length))
        nx=sum(-dy for dx,dy in tangents)
        ny=sum(dx for dx,dy in tangents)
        length=math.hypot(nx,ny)
        nx,ny=nx/length,ny/length
        normal=(-tangents[0][1],tangents[0][0])
        factor=min(1.8,1/max(.55,nx*normal[0]+ny*normal[1]))
        left.append((p[0]+nx*width*.5*factor,p[1]+ny*width*.5*factor))
        right.append((p[0]-nx*width*.5*factor,p[1]-ny*width*.5*factor))
    heights=z if isinstance(z,(list,tuple)) else [z]*len(path)
    vertices=[(x,y,heights[i]) for i,pair in enumerate(zip(left,right)) for x,y in pair]
    faces=[]
    for i in range(len(path)-1):
        quad=[2*i,2*i+1,2*i+3,2*i+2]
        a,b,c=[vertices[j] for j in quad[:3]]
        if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])<0:
            quad.reverse()
        faces.append(quad)
    mesh(role,vertices,faces)
    if record:
        PREVIEW.append((role,left+list(reversed(right))))


def offset_path(path, distance):
    result=[]
    for i,p in enumerate(path):
        a,b=path[max(0,i-1)],path[min(len(path)-1,i+1)]
        dx,dy=b[0]-a[0],b[1]-a[1]
        length=math.hypot(dx,dy)
        result.append((p[0]-dy/length*distance,p[1]+dx/length*distance))
    return result


def dashed(path, width=.15, length=4, gap=7, z=.021, role='Markings'):
    heights=z if isinstance(z,(list,tuple)) else [z]*len(path)
    for seg,(a,b) in enumerate(zip(path,path[1:])):
        dx,dy=b[0]-a[0],b[1]-a[1]
        size=math.hypot(dx,dy)
        along=2
        while along+length<size-2:
            fractions=(along/size,(along+length)/size)
            endpoints=[(a[0]+dx*t,a[1]+dy*t) for t in fractions]
            elevations=[heights[seg]+(heights[seg+1]-heights[seg])*t for t in fractions]
            # Both ends follow the road gradient. A level box would bury one
            # half of a long dash in the I-15 bridge approach ramp.
            ribbon(role,endpoints,width,elevations)
            along+=length+gap


def road(path, width=10, context=False, centerline=False):
    global ROAD_INDEX
    # Road strips intersect intentionally. Millimetric height separation makes
    # their overlap deterministic in UE and avoids coplanar shadow/z artifacts.
    # All curb beds remain below even the first road surface at junctions.
    index=ROAD_INDEX
    ROAD_INDEX+=1
    role='ContextRoads' if context else 'Roads'
    if context:
        CONTEXT_ROADS.append((path,width+2.2))
    curb_z=(-.006 if context else .005)+index*.0001
    road_z=(.008 if context else .015)+index*.001
    ribbon('Curbs',path,width+2.2,curb_z,True)
    ribbon(role,path,width,road_z,True)
    if centerline:
        dashed(path,.13,3.4,6,z=road_z+.012)


def cylinder(role,u,v,z,radius,height,sides=8):
    vertices=[]
    for h in (z,z+height):
        vertices.extend((u+math.cos(i*2*math.pi/sides)*radius,
                         v+math.sin(i*2*math.pi/sides)*radius,h) for i in range(sides))
    faces=[tuple(reversed(range(sides))),tuple(range(sides,2*sides))]
    faces += [(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
    mesh(role,vertices,faces)


def tree(u,v,height=5.3,scale=1):
    variant=int(abs(u*7.31+v*11.17))%3
    size=height/(5.737,6.750,5.397)[variant]*scale
    if road_clearance(u,v,2.8*size)<.3:
        COUNTS['tree_candidates_omitted_for_road_clearance']+=1
        return None
    return build_tree({'mesh':mesh,'counts':COUNTS},u,v,size,variant)


def trailer(u,v,angle=math.pi/2):
    PARKED_VEHICLES.append(dict(kind='trailer',center=[u,v],size=[13.26,2.66],angle=angle))
    box('Buildings',(u,v,2.35),(13.2,2.6,3),angle,True)
    box('Roofs',(u,v,3.88),(13.26,2.66,.08),angle)
    box('Detail',(u,v,.72),(10.9,1.9,.3),angle)
    for x in (-3.9,-2.8):
        for y in (-1.05,1.05):
            px,py=rotate_point(x,y,(u,v),angle)
            box('Detail',(px,py,.55),(.78,.42,.85),angle)
    COUNTS['parked_trailers']+=1


def car(u,v,angle=0,blue=False):
    variant=int(abs(u*13.7+v*7.3))%2
    result=build_car({'mesh':mesh},u,v,angle,blue,variant)
    PARKED_VEHICLES.append(dict(kind='car',center=[u,v],size=result['parking_size_m'],angle=angle))
    COUNTS['parked_cars']+=1
    COUNTS['detailed_'+result['variant']]+=1
    return result


def parking(u,v,count,angle=0,filled=.55):
    # Local x is the row direction; parking stalls extend 5.3m away.
    width=count*2.8
    box('Roads',(*rotate_point(width*.5,2.7,(u,v),angle),.01),(width+1,6.4,.06),angle,True)
    for i in range(count+1):
        a=rotate_point(i*2.8,0,(u,v),angle)
        b=rotate_point(i*2.8,5.3,(u,v),angle)
        ribbon('Markings',[a,b],.11,.047)
    for i in range(count):
        if RNG.random()<filled:
            p=rotate_point((i+.5)*2.8,2.7,(u,v),angle)
            car(*p,angle+math.pi/2,blue=(i%13==3))
    COUNTS['car_spaces']+=count


def staging(u,v,count,angle=0,filled=.35):
    width=count*4.0
    for i in range(count+1):
        a=rotate_point(i*4,0,(u,v),angle)
        b=rotate_point(i*4,16,(u,v),angle)
        ribbon('Markings',[a,b],.14,.018)
    a=rotate_point(0,0,(u,v),angle)
    b=rotate_point(width,0,(u,v),angle)
    ribbon('Markings',[a,b],.14,.018)
    for i in range(count):
        if RNG.random()<filled:
            p=rotate_point((i+.5)*4,8,(u,v),angle)
            trailer(*p,angle+math.pi/2)
    COUNTS['trailer_spaces']+=count


def gatehouse(u,v,angle=0):
    box('Buildings',(u,v,1.7),(7,4,3.4),angle,True)
    box('Roofs',(u,v,3.51),(7.6,4.6,.22),angle)
    for y in (-2.015,2.015):
        p=rotate_point(0,y,(u,v),angle)
        box('Glass',(*p,2.0),(5.5,.045,.9),angle)
    for x in (-5.4,5.4):
        p=rotate_point(x,0,(u,v),angle)
        box('Blue',(*p,.65),(.35,.4,1.3),angle)
    COUNTS['gatehouses']+=1


def build():
    global CAMPUS, GEOMETRY_REPORT
    from park_site import build_site
    api={name:globals()[name] for name in
         ('mesh','poly','box','ribbon','cylinder','tree','trailer','car','parking','staging','gatehouse','rotate_point')}
    api.update(counts=COUNTS,preview=PREVIEW,warehouse=WAREHOUSE,context_roads=CONTEXT_ROADS,
               parked_vehicles=PARKED_VEHICLES)
    GEOMETRY_REPORT=build_site(api)
    CAMPUS=GEOMETRY_REPORT['campus_boundary_uv_m']


def write_svg():
    colors={role:'#%02x%02x%02x'%tuple(int((c**(1/2.2))*255) for c in color)
            for role,color in PALETTE.items()}
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-235 -190 1030 850" width="1545" height="1275">',
         '<rect x="-235" y="-190" width="1030" height="850" fill="#eef1f4"/>']
    for role,points in PREVIEW:
        svg.append('<polygon points="'+' '.join(f'{u:.2f},{v:.2f}' for u,v in points)+f'" fill="{colors[role]}"/>')
    svg.append('<polygon points="'+' '.join(f'{u},{v}' for u,v in WAREHOUSE)+'" fill="#f8fafc" stroke="#8499b7" stroke-width="1.2"/>')
    svg.append('<polygon points="'+' '.join(f'{u},{v}' for u,v in CAMPUS)+'" fill="none" stroke="#2254ca" stroke-width="1.5" stroke-dasharray="5 4"/>')
    for x,y,text in [(150,60,'EXISTING WAREHOUSE'),(160,145,'EXISTING DOCK COURT'),(60,245,'CAMPUS TRUCK YARD'),
                     (190,-44,'GLEN HELEN PKWY'),(300,238,'I-15 / ONTARIO FWY'),(-185,45,'OPEN WASH'),
                     (174,-162,'GRAY PINE PL'),(280,416,'LOW-POLY RESIDENTIAL CONTEXT')]:
        svg.append(f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" font-size="8" fill="#244265">{text}</text>')
    svg.append('<text x="-220" y="630" font-family="Arial,sans-serif" font-size="10" fill="#244265">GHS CAMPUS · SATELLITE-REFERENCE MASSING · APPROXIMATE, NOT SURVEYED</text></svg>')
    (OUT/'campus_plan.svg').write_text('\n'.join(svg),encoding='utf8')


def export():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.context.scene.unit_settings.scale_length=1.0
    assets=[]
    for role,data in DATA.items():
        name='SM_GHSPark_'+role
        material=bpy.data.materials.new('M_GHSPark_'+role)
        material.diffuse_color=(*PALETTE[role],1)
        material.use_nodes=True
        material.use_backface_culling=False if role=='Fence' else True
        principled=next((n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if principled is None:
            principled=material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
            output=next((n for n in material.node_tree.nodes if n.type=='OUTPUT_MATERIAL'),None)
            if output is None:
                output=material.node_tree.nodes.new('ShaderNodeOutputMaterial')
            material.node_tree.links.new(principled.outputs['BSDF'],output.inputs['Surface'])
        principled.inputs['Base Color'].default_value=(*PALETTE[role],1)
        principled.inputs['Roughness'].default_value=.82
        geo=bpy.data.meshes.new(name)
        geo.from_pydata(data['vertices'],[],data['faces'])
        geo.update()
        geo.validate(verbose=True)
        obj=bpy.data.objects.new(name,geo)
        bpy.context.collection.objects.link(obj)
        geo.materials.append(material)
        geo.calc_loop_triangles()
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active=obj
        fbx=OUT/(name+'.fbx')
        bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},
                                axis_forward='-Y',axis_up='Z',apply_unit_scale=True,
                                bake_anim=False,mesh_smooth_type='FACE',use_mesh_modifiers=True,
                                add_leaf_bones=False)
        bounds=[[min(v.co[i] for v in geo.vertices),max(v.co[i] for v in geo.vertices)] for i in range(3)]
        ue_bounds={'min':[bounds[0][0]*100,-bounds[1][1]*100,bounds[2][0]*100],
                   'max':[bounds[0][1]*100,-bounds[1][0]*100,bounds[2][1]*100]}
        assets.append({'name':name,'role':role,'fbx':str(fbx),'material_color_linear':PALETTE[role],
                       'vertices':len(geo.vertices),'triangles':len(geo.loop_triangles),
                       'source_parts':data['parts'],'blender_bounds_m':bounds,'bounds_ue_cm':ue_bounds,
                       'sha256':hashlib.sha256(fbx.read_bytes()).hexdigest()})
    total=sum(a['triangles'] for a in assets)
    # Clustered forests and recognisable cars share material batches. Keep an
    # explicit combined environment budget while avoiding per-prop Actors.
    assert total<950000, total
    minimum_house_clearance=min(h['road_clearance_m'] for h in GEOMETRY_REPORT['residential']['houses'])
    assert minimum_house_clearance>=.10, minimum_house_clearance
    manifest={'version':2,'purpose':'Full campus primary display; restrained public-road and residential context',
              'reference_address':'17335 Glen Helen Pkwy, San Bernardino, CA 92407',
              'measurement_status':'Roads and building placements registered from user CADmapper DXF. Parcel and architectural detail from satellite references; not a cadastral survey.',
              'coordinate_contract':'Local u,v metres; Blender X=u-239.33385, Y=-(v-60.24019); FBX -Y forward Z up; UE import at origin scale 1 yields cm X=(u-239.33385)*100,Y=(v-60.24019)*100.',
              'campus_boundary_uv_m':CAMPUS,'existing_warehouse_uv_m':WAREHOUSE,
              'warehouse_geometry_modified':False,'ground_title_clearance_uv_m':[189.5,277.1,147.9,159.7],
              'hardstand_elevation_ue_cm':-4,'asset_count':len(assets),'triangles_total':total,
              'counts':dict(COUNTS),'meshes':assets,'materials':PALETTE,
              'campus_boundary_ue_cm':[[(u-ORIGIN[0])*100,(v-ORIGIN[1])*100,-4] for u,v in CAMPUS],
              'stats':{'triangles':total,'asset_count':len(assets),**dict(COUNTS)}}
    manifest['geometry_checks']={
        'minimum_house_to_road_edge_m':minimum_house_clearance,
        'road_union_valid':GEOMETRY_REPORT['road_surface_valid'],
        'fence':GEOMETRY_REPORT['fence'],
        'original_dock_trucks_contained':GEOMETRY_REPORT['original_dock_trucks_contained'],
        'source_dxf':GEOMETRY_REPORT['source_dxf'],
        'lane_dash_vertices_follow_road_segment_gradient':True,
    }
    (OUT/'park_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'GHS_Park_Source.blend'))
    write_svg()
    print('GHS_PARK_READY '+json.dumps({'assets':len(assets),'triangles':total,'counts':dict(COUNTS)}))


def preview():
    """QA-only massing preview; reference warehouse is not exported or saved."""
    scene=bpy.context.scene
    scene.render.engine='CYCLES'
    scene.cycles.samples=16
    scene.cycles.use_denoising=True
    scene.render.resolution_x=1600
    scene.render.resolution_y=1440
    scene.render.resolution_percentage=100
    scene.world.color=(.5,.5,.5)
    scene.world.use_nodes=True
    background=next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND')
    background.inputs['Color'].default_value=(.75,.8,.85,1)
    background.inputs['Strength'].default_value=.7
    # Existing warehouse mass is a QA silhouette only.
    verts=[(u-ORIGIN[0],-(v-ORIGIN[1]),z) for z in (0,9.6) for u,v in WAREHOUSE]
    count=len(WAREHOUSE)
    faces=[tuple(reversed(range(count,2*count)))]
    faces += [(i,(i+1)%count,(i+1)%count+count,i+count) for i in range(count)]
    data=bpy.data.meshes.new('QA_REFERENCE_ONLY')
    data.from_pydata(verts,[],faces)
    obj=bpy.data.objects.new('QA_REFERENCE_WAREHOUSE_NOT_EXPORTED',data)
    scene.collection.objects.link(obj)
    data.materials.append(bpy.data.materials['M_GHSPark_Buildings'])
    bpy.ops.mesh.primitive_plane_add(size=4000,location=(0,0,-.19))
    floor=bpy.context.object
    mat=bpy.data.materials.new('QA_Floor')
    mat.diffuse_color=(.83,.85,.87,1)
    floor.data.materials.append(mat)
    light=bpy.data.lights.new('QA_Sun','SUN')
    light.energy=2
    light.angle=.15
    light_obj=bpy.data.objects.new('QA_Sun',light)
    scene.collection.objects.link(light_obj)
    light_obj.rotation_euler=(.35,-.45,.4)
    camdata=bpy.data.cameras.new('QA_Plan')
    cam=bpy.data.objects.new('QA_Plan',camdata)
    scene.collection.objects.link(cam)
    cam.location=(270-ORIGIN[0],-(190-ORIGIN[1]),1200)
    cam.rotation_euler=(0,0,0)
    camdata.type='ORTHO'
    camdata.ortho_scale=1030
    camdata.clip_end=4000
    scene.camera=cam
    scene.render.image_settings.file_format='PNG'
    scene.render.filepath=str(OUT/'campus_plan_preview.png')
    bpy.ops.render.render(write_still=True)


build()
export()
preview()
