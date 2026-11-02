"""Static preview of verified CAD sorter meshes; no scene state is modified."""
import bpy,json,math,sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/equipment'
sys.path.insert(0,str(Path(__file__).resolve().parent));import build_mpr_sorter as g
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
manifest=json.loads((OUT/'sorter_variants_manifest.json').read_text(encoding='utf8'))
for idx,s in enumerate([s for s in manifest['meshes'] if s['lod']==0]):
 bpy.ops.import_scene.fbx(filepath=s['fbx'])
 o=bpy.context.selected_objects[0];o.location.y=idx*3.25
 for mat in o.data.materials:
  role=mat.name.removeprefix('M_Zcool_').split('.')[0]
  p=mat.node_tree.nodes.get('Principled BSDF')
  if p and role in g.ROLES:p.inputs['Base Color'].default_value=(*g.COLORS[g.ROLES.index(role)],1)
floor=g.material('PreviewFloor',(.45,.52,.61));g.MATS['PreviewFloor']=floor
g.box('PreviewFloor',(0,3.3,-.10),(200,200,.10),'PreviewFloor',bpy.context.scene.collection)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=24
scene.render.resolution_x=1900;scene.render.resolution_y=1250;scene.render.resolution_percentage=100
world=bpy.data.worlds.new('PreviewWorld');world.use_nodes=True
world.node_tree.nodes.get('Background').inputs[0].default_value=(.60,.69,.78,1);world.node_tree.nodes.get('Background').inputs[1].default_value=.65;scene.world=world
for loc,energy in [((0,-5,12),2600),((5,8,9),1800)]:
 d=bpy.data.lights.new('Softbox','AREA');d.energy=energy;d.size=8
 o=bpy.data.objects.new(d.name,d);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,3,1))-o.location).to_track_quat('-Z','Y').to_euler()
d=bpy.data.cameras.new('PreviewCamera');o=bpy.data.objects.new(d.name,d);scene.collection.objects.link(o)
o.location=(11,-15,14);o.rotation_euler=(Vector((0,3,1))-o.location).to_track_quat('-Z','Y').to_euler();d.type='ORTHO';d.ortho_scale=15;scene.camera=o
scene.render.filepath=str(OUT/'mpr_sorter_variants_preview.png');scene.render.image_settings.file_format='PNG'
bpy.ops.render.render(write_still=True)
