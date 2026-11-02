"""Compose editable MPR reference-v3 exterior from validated source libraries.

Only manifest geometry / CAD instances are appended. No props display stands,
review duplicates, old exterior or warehouse interior are imported.
Run isolated Blender: -b --factory-startup -t 1 --python this.py [-- --render]
"""
from pathlib import Path
import bpy,json,math,hashlib,sys
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/reference_v3';REV=OUT/'validation_blender';REV.mkdir(parents=True,exist_ok=True)
FILES={
 'architecture':(OUT/'architecture/reference_shell_manifest.json',OUT/'architecture/mpr_reference_shell.blend'),
 'site':(OUT/'site/manifest.json',OUT/'site/MPR_ReferenceSite.blend'),
 'props':(OUT/'props/manifest.json',OUT/'props/MPR_Reference_Props.blend')}
INSTANCE_GROUPS=['architecture','site']

def augment_manifests(manifests,masters):
 """Optional composition-only hook; source manifests always remain read-only."""
 return {}

def collection(name):
 c=bpy.data.collections.new(name);bpy.context.scene.collection.children.link(c);return c

def append_meshes(path,names):
 with bpy.data.libraries.load(str(path),link=False) as (source,target):
  missing=set(names)-set(source.objects);assert not missing,(path,missing)
  target.objects=list(names)
 return {o.name:o for o in target.objects}

def configure_preview():
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=20
 scene.cycles.use_denoising=True;scene.cycles.max_bounces=4;scene.cycles.diffuse_bounces=2
 scene.render.threads_mode='FIXED';scene.render.threads=1
 scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
 scene.view_settings.view_transform='AgX';scene.view_settings.exposure=.30
 scene.view_settings.look='AgX - Medium High Contrast'
 world=bpy.data.worlds.new('MPR3_ExteriorDaylight');world.use_nodes=True;scene.world=world
 background=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND')
 background.inputs['Color'].default_value=(.70,.80,.92,1);background.inputs['Strength'].default_value=.28
 lights=collection('PREVIEW_LIGHTS_CAMERAS')
 sun=bpy.data.lights.new('MPR3_Sun','SUN');sun.energy=2.8;sun.angle=math.radians(10)
 ob=bpy.data.objects.new('MPR3_Sun',sun);lights.objects.link(ob);ob.rotation_euler=(math.radians(25),math.radians(-26),math.radians(-28))
 views=[('South_Overview',(60,-760,730),(20,5,0),850),('SouthWest_Site',(-440,-660,410),(-5,0,0),655),
        ('DockYard_Close',(-200,-170,60),(-130,-102,1),95)]
 cameras=[]
 for name,p,target,scale in views:
  data=bpy.data.cameras.new('CAM_'+name);data.type='ORTHO';data.ortho_scale=scale;data.clip_end=4000;data.lens=48
  camera=bpy.data.objects.new('CAM_'+name,data);lights.objects.link(camera);camera.location=p
  camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler();cameras.append((name,camera))
 scene.camera=cameras[0][1];return cameras

def build():
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 for c in list(bpy.data.collections):bpy.data.collections.remove(c)
 scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
 library=collection('MODULE_LIBRARY__HIDDEN');library.hide_render=True;library.hide_viewport=True
 masters={};manifests={};report={'schema_version':1,'scope':'complete external appearance only, no interior','sources':{},'geometry':{},'instances':{}}
 for key,(manifest,blend) in FILES.items():
  m=json.loads(manifest.read_text(encoding='utf8'));manifests[key]=m
  report['sources'][key]={'manifest':manifest.relative_to(ROOT).as_posix(),'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
                          'blend':blend.relative_to(ROOT).as_posix(),'blend_sha256':hashlib.sha256(blend.read_bytes()).hexdigest()}
  rows=[r for r in m['meshes'] if r.get('lod',0)==0]
  loaded=append_meshes(blend,[r['name'] for r in rows]);coll=collection(key.upper()+'_GEOMETRY')
  for row in rows:
   ob=loaded[row['name']];assert ob.type=='MESH'
   # Source props have library/display transforms; all module placements come from manifests.
   ob.location=(0,0,0);ob.rotation_euler=(0,0,0);ob.scale=(1,1,1);ob.hide_render=False;ob.hide_viewport=False;ob.hide_set(False)
   if row.get('instance_only'):
    library.objects.link(ob);masters[row['name']]=ob
   else:coll.objects.link(ob)
   ob['mpr_source_manifest']=manifest.relative_to(ROOT).as_posix()
  report['geometry'][key]={'source_meshes':len(rows),'static_partitions':sum(not r.get('instance_only',False) for r in rows)}
  # Site maps are DirectX tangent normals. Flip green for Blender only, retaining
  # the on-disk texture and UE import contract unmodified.
  if key=='site':
   for mat in {mat for ob in loaded.values() for mat in ob.data.materials if mat}:
    if not mat.use_nodes:continue
    for node in list(mat.node_tree.nodes):
     if node.type!='NORMAL_MAP' or not node.inputs['Color'].links:continue
     link=node.inputs['Color'].links[0];source=link.from_socket;mat.node_tree.links.remove(link)
     separate=mat.node_tree.nodes.new('ShaderNodeSeparateColor');separate.mode='RGB'
     combine=mat.node_tree.nodes.new('ShaderNodeCombineColor');combine.mode='RGB'
     inv=mat.node_tree.nodes.new('ShaderNodeMath');inv.operation='SUBTRACT';inv.inputs[0].default_value=1
     mat.node_tree.links.new(source,separate.inputs[0]);mat.node_tree.links.new(separate.outputs[0],combine.inputs[0])
     mat.node_tree.links.new(separate.outputs[1],inv.inputs[1]);mat.node_tree.links.new(inv.outputs[0],combine.inputs[1])
     mat.node_tree.links.new(separate.outputs[2],combine.inputs[2]);mat.node_tree.links.new(combine.outputs[0],node.inputs['Color'])
 report.update(augment_manifests(manifests,masters))
 for key in INSTANCE_GROUPS:
  coll=collection(key.upper()+'_LINKED_INSTANCES');count=0
  for name,placements in manifests[key].get('instances',{}).items():
   assert name in masters,('Missing instance module',name)
   for i,p in enumerate(placements):
    obj=bpy.data.objects.new(f'{key}_{name}_{i:04}',masters[name].data);coll.objects.link(obj)
    obj.location=p['position_m'];obj.rotation_euler.z=math.radians(p.get('rotation_deg',0));obj.scale=p.get('scale',[1,1,1])
    obj['mpr_module']=name;obj['mpr_instance_source']=key;count+=1
  report['instances'][key]=count
 cameras=configure_preview()
 for im in bpy.data.images:
  if im.source=='FILE' and not im.packed_file:im.pack()
 path=OUT/'MPR_ReferenceExterior.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path))
 report['output']=path.relative_to(ROOT).as_posix();report['mesh_datablocks']=len(bpy.data.meshes)
 report['visible_mesh_objects']=len([o for o in scene.objects if o.type=='MESH' and o.name not in masters])
 report['total_manifest_instances']=sum(report['instances'].values());report['props_display_objects_imported']=False
 report['validation_boundary']='Blender source composition and optional rendered previews only; UE acceptance is separate.'
 (REV/'composition_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 if '--render' in sys.argv:
  for name,camera in cameras:
   scene.camera=camera;scene.render.filepath=str(REV/(name+'.png'));bpy.ops.render.render(write_still=True)
 print('MPR_REFERENCE_EXTERIOR_COMPLETE',json.dumps(report['instances']),flush=True)

if __name__=='__main__':build()
