"""CPU old/new solar-only preview at identical optics and final palette."""
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
import mpr_solar_hierarchy as old

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/solar_units_20261106'


def render(blend,prefix):
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    specs=old.source_contract()[0]['materials']
    for mat in bpy.data.materials:
        if mat.name in specs:
            next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color'].default_value=(*specs[mat.name]['base_color'],1.)
    for ob in bpy.context.scene.objects:ob.hide_render=not ob.name.endswith('_LOD2')
    outline=old.read(ROOT/'SourceAssets/MPR/rebuild_b50b57/solar/inputs/cad_layout.json')['footprint_outline_m']
    mesh=bpy.data.meshes.new('PreviewRoof')
    mesh.from_pydata([(p[0],p[1],13.4)for p in outline],[],[tuple(range(len(outline)))])
    mesh.update()
    roof=bpy.data.objects.new('PreviewRoof',mesh)
    bpy.context.scene.collection.objects.link(roof)
    mat=bpy.data.materials.new('PreviewRoofMaterial')
    mat.use_nodes=True
    bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value=(.67,.70,.73,1.)
    bsdf.inputs['Roughness'].default_value=.85
    mesh.materials.append(mat)
    scene=bpy.context.scene
    scene.world=bpy.data.worlds.new('NeutralWorld')
    scene.world.use_nodes=True
    background=next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND')
    background.inputs[0].default_value=(.73,.78,.83,1.)
    background.inputs[1].default_value=.6
    sun=bpy.data.lights.new('PreviewSun','SUN')
    sun.energy=2.
    sun.angle=math.radians(6)
    sunob=bpy.data.objects.new('PreviewSun',sun)
    scene.collection.objects.link(sunob)
    sunob.rotation_euler=(math.radians(20),math.radians(-30),math.radians(-20))
    cam=bpy.data.cameras.new('SolarReview')
    ob=bpy.data.objects.new('SolarReview',cam)
    scene.collection.objects.link(ob)
    scene.camera=ob
    target=Vector((0,-2,13.4))
    direction=Vector((0,-math.cos(math.radians(52)),math.sin(math.radians(52))))
    ob.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler()
    cam.type='PERSP'
    cam.lens_unit='FOV'
    cam.angle=math.radians(50)
    cam.clip_end=5000
    scene.render.engine='CYCLES'
    scene.cycles.device='CPU'
    scene.cycles.samples=24
    scene.cycles.use_denoising=False
    scene.render.resolution_x=1920
    scene.render.resolution_y=1080
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.view_settings.view_transform='AgX'
    for distance in (1100,572):
        ob.location=target+direction*distance
        scene.render.filepath=str(OUT/(prefix+'_'+str(distance)+'m.png'))
        bpy.ops.render.render(write_still=True)


render(ROOT/old.SOURCE/'MPR_Hierarchy_Solar.blend','previous')
render(OUT/'MPR_Solar_Units.blend','larger_units')
