"""Blender background authoring: real geographic sphere, LODs, packed source and FBX.
Run blender --background --factory-startup --python Tools/GlobeNavigation/create_globe.py.
Only this isolated Blender process is changed. No live user's scene is touched.
"""
import bpy, math, json
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/GlobeNavigation'
TEX=OUT/'Textures'
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.unit_settings.system='METRIC'; scene.unit_settings.scale_length=1
scene.render.engine='CYCLES'
scene.cycles.samples=48
scene.cycles.use_denoising=True
scene.render.resolution_x=1400;scene.render.resolution_y=1400;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
scene.render.film_transparent=True
scene.view_settings.view_transform='AgX'
world=bpy.data.worlds.new('Globe_Daylight');scene.world=world;world.use_nodes=True
bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.62,.78,.91,1);bg.inputs['Strength'].default_value=.55
height_image=bpy.data.images.load(str(TEX/'T_Earth_Height.png'),check_existing=True)
height_image.colorspace_settings.name='Non-Color'
hp=list(height_image.pixels);hw,hh=height_image.size
def height(u,v):
 x=min(hw-1,max(0,int(u*(hw-1))));y=min(hh-1,max(0,int(v*(hh-1))))
 return hp[(y*hw+x)*4]
mat=bpy.data.materials.new('M_Earth_Atlas');mat.use_nodes=True
nodes=mat.node_tree.nodes;links=mat.node_tree.links
bs=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
bs.inputs['Metallic'].default_value=0
bs.inputs['Specular IOR Level'].default_value=.24
for filename,socket,noncolor in [('T_Earth_BaseColor.png','Base Color',False),('T_Earth_Roughness.png','Roughness',True)]:
 tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(TEX/filename),check_existing=True)
 if noncolor:tex.image.colorspace_settings.name='Non-Color'
 links.new(tex.outputs['Color'],bs.inputs[socket])
normtex=nodes.new('ShaderNodeTexImage');normtex.image=bpy.data.images.load(str(TEX/'T_Earth_Normal_OpenGL.png'))
normtex.image.colorspace_settings.name='Non-Color';normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.8
links.new(normtex.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],bs.inputs['Normal'])
lods=[]
def make_sphere(name,nlon,nlat):
 verts=[];uvs=[];faces=[]
 for j in range(nlat+1):
  v=j/nlat;lat=(v-.5)*math.pi
  for i in range(nlon+1):
   u=i/nlon;lon=(u-.5)*math.tau
   r=1+.024*height(u,v)
   verts.append((r*math.cos(lat)*math.cos(lon),r*math.cos(lat)*math.sin(lon),r*math.sin(lat)));uvs.append((u,v))
 for j in range(nlat):
  for i in range(nlon):
   a=j*(nlon+1)+i;b=a+1;c=b+nlon+1;d=a+nlon+1
   if j==0:faces.append((a,c,d))
   elif j==nlat-1:faces.append((a,b,c))
   else:faces.append((a,b,c,d))
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
 obj=bpy.data.objects.new(name,mesh);scene.collection.objects.link(obj);mesh.materials.append(mat)
 uv=mesh.uv_layers.new(name='UVMap')
 for p in mesh.polygons:
  p.use_smooth=True
  for li in p.loop_indices:uv.data[li].uv=uvs[mesh.loops[li].vertex_index]
 mesh.calc_loop_triangles()
 lods.append({'name':name,'vertices':len(verts),'triangles':len(mesh.loop_triangles),'radiusMeters':1,'heightExaggerationMaxMeters':.024})
 return obj
for idx,(nx,ny) in enumerate([(256,128),(128,64),(64,32)]):
 obj=make_sphere('SM_Earth_LOD'+str(idx),nx,ny)
 bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
 bpy.ops.export_scene.fbx(filepath=str(OUT/(obj.name+'.fbx')),use_selection=True,object_types={'MESH'},global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',axis_forward='-Y',axis_up='Z',use_mesh_modifiers=True,mesh_smooth_type='FACE',bake_anim=False,path_mode='RELATIVE',use_custom_props=True)
 obj.hide_render=idx>0;obj.hide_set(idx>0)
globe=bpy.data.objects['SM_Earth_LOD0']
camera=bpy.data.cameras.new('Camera_Atlas_Americas');cam=bpy.data.objects.new('Camera_Atlas_Americas',camera);scene.collection.objects.link(cam)
lon,lat=map(math.radians,(-84,17))
cam.location=(4.3*math.cos(lat)*math.cos(lon),4.3*math.cos(lat)*math.sin(lon),4.3*math.sin(lat))
cam.rotation_euler=(-cam.location).to_track_quat('-Z','Y').to_euler();camera.type='ORTHO';camera.ortho_scale=2.17;scene.camera=cam
def area(name,loc,power,size):
 light=bpy.data.lights.new(name,'AREA');light.energy=power;light.shape='DISK';light.size=size
 ob=bpy.data.objects.new(name,light);scene.collection.objects.link(ob);ob.location=loc;ob.rotation_euler=(-ob.location).to_track_quat('-Z','Y').to_euler()
area('Key_Soft_Daylight',(-3,-4,5),340,4)
area('Fill_Cool',(4,-1,1),110,5)
bpy.context.view_layer.update()
points=[('GHS',34.190629582941,-117.428430792609),('加拿大',56,-105),('美国',39,-98),('墨西哥',23,-102),('哥伦比亚',4,-74),('委内瑞拉',8,-66),('秘鲁',-10,-75),('巴西',-12,-52),('智利',-35,-71),('阿根廷',-37,-64),('北极',90,0),('零经线',0,0),('东经90',0,90)]
projected=[];calibration=[]
for name,lat,lon in points:
 u=(lon+180)/360;v=(lat+90)/180;r=1+.024*height(u,v)+.003
 la,lo=math.radians(lat),math.radians(lon)
 xyz=Vector((r*math.cos(la)*math.cos(lo),r*math.cos(la)*math.sin(lo),r*math.sin(la)))
 p=world_to_camera_view(scene,cam,xyz)
 projected.append({'name':name,'latitude':lat,'longitude':lon,'x':p.x,'y':1-p.y,'visible':xyz.dot(cam.location)>0,'blenderMeters':list(xyz)})
 if name in ['GHS','北极','零经线','东经90']:
  bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=.002,location=xyz)
  marker=bpy.context.object;marker.name='CAL_'+{'GHS':'GHS','北极':'North','零经线':'Greenwich','东经90':'East90'}[name];marker.hide_render=True;calibration.append(marker)
bpy.ops.object.select_all(action='DESELECT')
for marker in calibration:marker.select_set(True)
bpy.ops.export_scene.fbx(filepath=str(OUT/'GeographicCalibration.fbx'),use_selection=True,object_types={'MESH'},global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',axis_forward='-Y',axis_up='Z',bake_anim=False)
for marker in calibration:marker.hide_set(True)
(OUT/'render-projections.json').write_text(json.dumps({'image':'earth-americas.png','width':1400,'height':1400,'points':projected},ensure_ascii=False,indent=2),encoding='utf-8')
for image in bpy.data.images:
 if image.source=='FILE':image.pack()
manifest={'generator':'Blender '+bpy.app.version_string,'lods':lods,'coordinateConvention':'canonical geographic Cartesian: X=cos(lat)cos(lon),Y=cos(lat)sin(lon),Z=sin(lat); Blender meters; FBX authored in centimeters metadata; verify importer axis conversion','uvConvention':'u=(lon+180)/360; v=(lat+90)/180. PNG top row north.','textures':{'baseColor':'Textures/T_Earth_BaseColor.png','normalUnrealDirectX':'Textures/T_Earth_Normal_UE.png','normalBlenderOpenGL':'Textures/T_Earth_Normal_OpenGL.png','roughness':'Textures/T_Earth_Roughness.png'},'baseRadiusUECentimeters':100,'relief':'NASA GEBCO 0-6400m scaled plus elevated land mask; max radial exaggeration2.4% for atlas legibility','camera':{'longitude':-84,'latitude':17,'orthographicScaleMeters':2.17},'warehouse':json.loads((OUT/'warehouse-location.json').read_text(encoding='utf-8'))}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'YQN_Earth.blend'))
scene.render.filepath=str(OUT/'earth-americas.png');bpy.ops.render.render(write_still=True)
print('GLOBE_ASSET_COMPLETE '+json.dumps(manifest,ensure_ascii=False))
