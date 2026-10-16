"""Assemble editable Blender reference AGV, without changing other scenes."""
import bpy
import sys
import json
import math
from pathlib import Path
from mathutils import Vector
ROOT=Path(r"D:\UEPro\Test")
CODE=ROOT/'Scripts/agv_reference'
OUT=ROOT/'SourceAssets/AGV_Reference'
if str(CODE) not in sys.path:sys.path.insert(0,str(CODE))
import importlib
import agv_common,body,wheels,sensors
for m in [agv_common,body,wheels,sensors]:importlib.reload(m)
from agv_common import *

previous=[s for s in bpy.data.scenes if s.name.startswith('AGV_Reference_Model')]
scene=bpy.data.scenes.new('AGV_Reference_Model')
bpy.context.window.scene=scene
for old in previous:
    for obj in list(old.objects):bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.scenes.remove(old)
scene.name='AGV_Reference_Model'
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.0
body.build_body();wheels.build_wheels();sensors.build_sensors()
parts=[o for o in scene.objects if o.get('agv_part')]
root=bpy.data.objects.new('AGV_Reference_Root',None);scene.collection.objects.link(root)
root['nominal_length_m']=1.6
root['source']='User photograph; proportions reconstructed; rear and internal details inferred.'
for o in parts:o.parent=root

# Neutral studio presentation matches the supplied reference viewpoint.
collection('99_Presentation')
floor=material('StudioFloor',(.10,.11,.12),.43,.15)
ground=box('Studio_Ground',(0,0,-.009),(200,200,.012),floor,0)
ground['agv_part']=False;ground.hide_select=True
world=bpy.data.worlds.new('AGV_StudioWorld');world.use_nodes=True
bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND')
bg.inputs['Color'].default_value=(.33,.36,.40,1);bg.inputs['Strength'].default_value=.45
scene.world=world
def area(name,loc,energy,size,color):
    d=bpy.data.lights.new(name,'AREA');d.energy=energy;d.shape='DISK';d.size=size;d.color=color
    o=bpy.data.objects.new(name,d);scene.collection.objects.link(o);o.location=loc
    o.rotation_euler=(Vector((0,0,.4))-o.location).to_track_quat('-Z','Y').to_euler()
area('Studio_Key',(-3,-4,5),650,4,(1,.965,.91))
area('Studio_Fill',(-.5,3,2.5),380,3,(.82,.90,1))
area('Studio_Rim',(3,1,4),750,2.5,(1,1,1))
d=bpy.data.cameras.new('AGV_ReferenceCamera');cam=bpy.data.objects.new('AGV_ReferenceCamera',d);scene.collection.objects.link(cam)
cam.location=(-3.8,-2.8,2.5);target=Vector((0,0,.48))
cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
d.type='ORTHO';d.ortho_scale=2.28;d.lens=55;scene.camera=cam
scene.render.resolution_x=1400;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
try:scene.render.engine='CYCLES'
except TypeError:pass
scene.cycles.samples=48;scene.cycles.use_denoising=True
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(OUT/'AGV_Blender_Preview.png')
scene.view_settings.view_transform='AgX'
for screen in bpy.data.screens:
    for a in screen.areas:
        if a.type=='VIEW_3D':
            a.spaces.active.region_3d.view_perspective='CAMERA'
            a.spaces.active.shading.type='MATERIAL'
bpy.ops.object.select_all(action='DESELECT')
root.select_set(True);bpy.context.view_layer.objects.active=root
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'AGV_Reference.blend'))
(OUT/'material_manifest.json').write_text(json.dumps(list(agv_common.MATERIALS.values()),indent=2))
print('AGV_MODEL_READY',len(parts),'parts',str(OUT/'AGV_Reference.blend'))
