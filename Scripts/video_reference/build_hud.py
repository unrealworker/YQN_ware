"""Generate transparent Chinese fault-panel texture and UV-correct Blender HUD asset.

Run bundled Python with --texture first, then background Blender for mesh export.
"""
import sys
import json
from pathlib import Path

OUT=Path(r'D:\UEPro\Test\SourceAssets\VideoReference')
OUT.mkdir(parents=True,exist_ok=True)

if '--texture' in sys.argv:
    from PIL import Image, ImageDraw, ImageFont
    image=Image.new('RGBA',(1024,512),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    font_path=r'C:\Windows\Fonts\msyh.ttc'
    def f(size):return ImageFont.truetype(font_path,size)
    red=(255,55,32,255)
    white=(235,242,250,255)
    draw.rectangle((16,16,1007,495),outline=(255,55,32,220),width=3)
    draw.line((43,222,978,222),fill=(255,55,32,135),width=2)
    draw.text((45,40),'错误代码 - 50001',font=f(57),fill=red,stroke_width=0)
    draw.text((46,126),'车辆故障报警',font=f(48),fill=red)
    draw.text((48,249),'常见原因',font=f(30),fill=white)
    for y,text in [(305,'01  驱动单元或传感器异常'),(354,'02  检查电源与通信连接'),(403,'03  确认现场安全后复位')]:
        draw.text((48,y),text,font=f(29),fill=white)
    image.save(OUT/'T_VR_AlarmPanel.png')
    print('HUD_TEXTURE_COMPLETE',image.size,image.getextrema()[3])
    raise SystemExit(0)

sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *

reset()
name='SM_VR_AlarmPanel'
begin_asset(name)
mat=material('AlarmPanel',(1,1,1),1,0,texture='T_VR_AlarmPanel',unlit=True,opacity=1,two_sided=True)
texture=bpy.data.images.load(str(OUT/'T_VR_AlarmPanel.png'),check_existing=True)
texture.pack()
nodes=mat.node_tree.nodes
image_node=nodes.new('ShaderNodeTexImage');image_node.image=texture
bs=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
mat.node_tree.links.new(image_node.outputs['Color'],bs.inputs['Base Color'])
mat.node_tree.links.new(image_node.outputs['Color'],bs.inputs['Emission Color'])
bs.inputs['Emission Strength'].default_value=1
mat.node_tree.links.new(image_node.outputs['Alpha'],bs.inputs['Alpha'])
mat.use_backface_culling=False
obj=mesh(name,[(-1.25,0,0),(-1.25,0,1.25),(1.25,0,1.25),(1.25,0,0)],[(0,1,2,3)],mat)
uv=obj.data.uv_layers.new(name='UVMap')
for loop,coord in zip(obj.data.loops,[(0,0),(0,1),(1,1),(1,0)]):
    uv.data[loop.index].uv=coord
assert obj.data.polygons[0].normal.y>.99
assert list(obj.data.vertices[0].co)==[-1.25,0,0]
bpy.context.scene.name='VideoReference_hud'
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True);bpy.context.view_layer.objects.active=obj
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'hud.blend'))
fbx=OUT/(name+'.fbx')
bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False)
manifest=dict(meshes=[dict(name=name,fbx=str(fbx),slots=[mat.name],bounds_m=[[-1.25,1.25],[0,0],[0,1.25]],source_parts=1,vertices=4,polygons=1)],materials=[MATERIALS[mat.name]],blend=str(OUT/'hud.blend'))
(OUT/'hud.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('VIDEO_LIBRARY_COMPLETE hud 1; UV positive X/U and Z/V; normal +Y')
