"""Render source-geometry before/after views; these are not UE screenshots."""
from pathlib import Path
import json
import math
import bpy

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/GHS/RoadEndcaps/Review'
ORIGIN=(239.33385,60.24019)


def load(path,names):
    with bpy.data.libraries.load(str(path),link=False) as (_,target):
        target.objects=names
    for obj in target.objects:
        bpy.context.collection.objects.link(obj)
        obj.color=(.84,.88,.92,1) if 'Curbs' in obj.name else (.91,.94,.98,1) if 'Markings' in obj.name else (.31,.38,.45,1)
    return target.objects


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    originals=load(ROOT/'SourceAssets/GHS/Park/GHS_Park_Source.blend',
                   ['SM_GHSPark_Curbs','SM_GHSPark_ContextRoads','SM_GHSPark_Markings'])
    revised=load(ROOT/'SourceAssets/GHS/RoadEndcaps/GHS_RoadEndcaps.blend',['SM_GHSRoadEndcaps_Curbs'])[0]
    load(ROOT/'SourceAssets/GHS/ContextTransition/GHS_ContextTransition.blend',
         ['SM_GHSContextTransition_ContextRoads','SM_GHSContextTransition_Curbs','SM_GHSContextTransition_Markings'])
    scene=bpy.context.scene
    scene.render.engine='BLENDER_WORKBENCH'
    scene.display.shading.light='FLAT';scene.display.shading.color_type='OBJECT'
    scene.display.shading.show_shadows=False;scene.display.shading.show_cavity=False
    scene.display.shading.show_specular_highlight=False
    scene.display.shading.background_type='WORLD';scene.world.color=(.61,.65,.68)
    scene.view_settings.view_transform='Standard'
    scene.render.resolution_x=1200;scene.render.resolution_y=720;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    camera=bpy.data.objects.new('RoadEndcapReviewCamera',bpy.data.cameras.new('RoadEndcapReviewCamera'))
    bpy.context.collection.objects.link(camera);scene.camera=camera
    camera.data.type='ORTHO';camera.data.ortho_scale=54
    ends=[end for end in json.loads((ROOT/'SourceAssets/GHS/ContextTransition/context_transition.json')
                                  .read_text(encoding='utf-8'))['roads'] if end['road_id']=='glen']
    for end in ends:
        p,q=end['old_end_uv_m'],end['new_end_uv_m']
        theta=math.atan2(-(q[1]-p[1]),q[0]-p[0])
        camera.location=(p[0]-ORIGIN[0],-(p[1]-ORIGIN[1]),80)
        camera.rotation_euler=(0,0,theta)
        for state in ('before','after'):
            originals[0].hide_render=state=='after';revised.hide_render=state=='before'
            scene.render.filepath=str(OUT/('glen-'+end['side']+'-'+state+'.png'))
            bpy.ops.render.render(write_still=True)
    print('GHS_ROAD_ENDCAP_PREVIEWS',str(OUT))


if __name__=='__main__':
    main()
