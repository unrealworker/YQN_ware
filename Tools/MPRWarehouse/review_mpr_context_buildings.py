"""Standalone background-Blender review of the context-only building module."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,math,sys
import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
from mpr_context_buildings import build_context_buildings,MATERIALS
OUT=ROOT/'SourceAssets/MPR/environment'
SOURCE_PATH=OUT/'environment_local.json'
source_bytes=SOURCE_PATH.read_bytes();source=json.loads(source_bytes)
DATA=defaultdict(lambda:dict(vertices=[],faces=[],roles=[]))

def mesh(name,role,vertices,faces):
    d=DATA[name];off=len(d['vertices']);d['vertices'].extend(vertices)
    d['faces'].extend(tuple(i+off for i in face) for face in faces);d['roles'].extend([role]*len(faces))

def poly(name,role,points,z):
    vv=[Vector((p[0],p[1],z)) for p in points];faces=[]
    for tri in tessellate_polygon([vv]):
        ids=[i if isinstance(i,int) else min(range(len(vv)),key=lambda k:(vv[k]-i).length_squared) for i in tri]
        a,b,c=[vv[i] for i in ids]
        if (b-a).cross(c-a).z<0:ids.reverse()
        faces.append(ids)
    mesh(name,role,[tuple(v) for v in vv],faces)

def box(name,role,center,size,yaw=0):
    x,y,z=center;a,b,h=[v*.5 for v in size];c,s=math.cos(yaw),math.sin(yaw)
    xy=[(x+i*c-j*s,y+i*s+j*c) for i,j in [(-a,-b),(a,-b),(a,b),(-a,b)]]
    mesh(name,role,[(u,v,z-h) for u,v in xy]+[(u,v,z+h) for u,v in xy],[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])

def strip(name,role,a,b,width,z):
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);nx,ny=-dy/length*width*.5,dx/length*width*.5
    poly(name,role,[(a[0]-nx,a[1]-ny),(b[0]-nx,b[1]-ny),(b[0]+nx,b[1]+ny),(a[0]+nx,a[1]+ny)],z)

def zone(x,y):
    if abs(x)<250 and -170<y<240:return 'Near'
    return 'Far_'+('E' if x>250 else 'W' if x<-250 else 'N' if y>240 else 'S')

api=dict(mesh=mesh,poly=poly,box=box,strip=strip,zone=zone)
report=build_context_buildings(api,source,-1.2)
assert len(report['footprints'])==140
assert all(x['source_id']!='1583' for x in report['buildings'])
assert SOURCE_PATH.read_bytes()==source_bytes
expected=[m for m in source['meshes'] if m['layer']=='buildings' and m['id']!='1583']
for original,footprint in zip(expected,report['footprints']):
    indices=original['footprintLoops'][0]
    assert set(tuple(original['vertices'][i][:2]) for i in indices)==set(footprint)
assert all(len(set(row['roles']))<=4 for row in DATA.values())
assert all(math.isfinite(v) for row in DATA.values() for point in row['vertices'] for v in point)
triangles=sum(sum(len(face)-2 for face in row['faces']) for row in DATA.values())
assert triangles<14000,triangles
# Every roof projects to the exact source footprint, including the pitched ones.
full_data=DATA;roof_checks=[]
for original in expected:
    DATA=defaultdict(lambda:dict(vertices=[],faces=[],roles=[]))
    build_context_buildings(api,{'meshes':[original]},-1.2)
    area=0.
    for row in DATA.values():
        for face,role in zip(row['faces'],row['roles']):
            if role!='ContextRoof':continue
            points=[row['vertices'][i] for i in face]
            area+=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))*.5
    error=abs(area-original['footprintAreaM2'])
    assert error<.02,(original['id'],error)
    roof_checks.append(error)
DATA=full_data
report.update(triangles=triangles,batches=len(DATA),source_sha256=hashlib.sha256(source_bytes).hexdigest(),
              validation={'source_file_unchanged':True,'all_140_footprints_exact':True,'main_1583_excluded':True,
                          'four_material_role_limit':True,'all_roofs_exact_projection':True,
                          'max_roof_projection_error_m2':max(roof_checks)},materials=MATERIALS)
(OUT/'context_buildings_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')

bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
materials={}
for role,spec in MATERIALS.items():
    mat=bpy.data.materials.new(role);mat.diffuse_color=(*spec['color_linear'],1);mat.use_nodes=True
    bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*spec['color_linear'],1);bs.inputs['Roughness'].default_value=spec['roughness'];materials[role]=mat
for name,row in DATA.items():
    data=bpy.data.meshes.new(name);data.from_pydata(row['vertices'],[],row['faces']);data.update()
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj)
    for material in materials.values():data.materials.append(material)
    slots={r:i for i,r in enumerate(materials)}
    for face,role in zip(data.polygons,row['roles']):face.material_index=slots[role]
bpy.ops.mesh.primitive_plane_add(size=2500,location=(0,0,-1.24));ground=bpy.context.object
mat=bpy.data.materials.new('Review ground');mat.diffuse_color=(.37,.43,.44,1);ground.data.materials.append(mat)
bpy.ops.object.light_add(type='AREA',location=(-180,-150,500));light=bpy.context.object;light.data.energy=1800000;light.data.shape='DISK';light.data.size=420
light.rotation_euler=(Vector((0,140,0))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.light_add(type='SUN',location=(0,0,300));bpy.context.object.rotation_euler=(.55,-.4,-.5);bpy.context.object.data.energy=2.5;bpy.context.object.data.angle=.2
scene=bpy.context.scene;scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.5,.6,.7,1);scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.5
scene.render.engine='CYCLES';scene.cycles.samples=48;scene.cycles.use_denoising=True
scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG'
scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast'
bpy.ops.object.camera_add(location=(520,-530,650));cam=bpy.context.object;cam.rotation_euler=(Vector((-30,200,5))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=760;cam.data.clip_end=10000;scene.camera=cam
scene.render.filepath=str(OUT/'context_buildings_preview.png');bpy.ops.render.render(write_still=True)
print('MPR_CONTEXT_REVIEW',json.dumps({'counts':report['counts'],'triangles':triangles,'batches':len(DATA),'validation':report['validation']}))
