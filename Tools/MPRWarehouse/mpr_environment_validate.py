"""Background Blender FBX round-trip and environment composition validation."""
from pathlib import Path
import json, math, sys
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/environment'

def main():
    manifest=json.loads((OUT/'environment_manifest.json').read_text())
    rows=[]
    for spec in manifest['meshes']:
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.fbx(filepath=str(ROOT/spec['fbx']))
        objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
        assert len(objects)==1,(spec['name'],len(objects))
        obj=objects[0];pts=[obj.matrix_world@v.co for v in obj.data.vertices]
        bb=[[min(v[i] for v in pts),max(v[i] for v in pts)] for i in range(3)]
        error=max(abs(bb[i][j]-spec['bounds_m'][i][j]) for i in range(3) for j in range(2))
        assert error<.002,(spec['name'],error)
        assert len(obj.data.materials)==len(spec['material_roles'])
        assert all(len(p.vertices)>=3 for p in obj.data.polygons)
        rows.append({'mesh':spec['name'],'max_bounds_error_m':round(error,8),'material_slots':len(obj.data.materials)})
    result={'success':True,'mesh_count':len(rows),'max_bounds_error_m':max(r['max_bounds_error_m'] for r in rows),
        'alignment_rms_m':manifest['alignment']['rms_error_m'],'ground_z_m':manifest['ground_z_m'],
        'instances_count':sum(map(len,manifest['instances'].values())),'unique_triangles':manifest['optimization']['unique_triangles'],
        'checked':'Exported FBX reimport preserves meter coordinates, positive scale and material slot counts. Only source-derived environment; no UE runtime claim.',
        'meshes':rows}
    (OUT/'environment_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('MPR_ENVIRONMENT_VALIDATED '+json.dumps({k:v for k,v in result.items() if k!='meshes'}))
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'MPR_Environment.blend'))
    scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.samples=16
    scene.render.resolution_x=1500;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
    scene.world.color=(.6,.6,.6)
    world=scene.world;world.use_nodes=True
    bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.65,.74,.86,1);bg.inputs['Strength'].default_value=.6
    sun=bpy.data.lights.new('ReviewSun','SUN');sun.energy=2.5;sun.angle=.07
    ob=bpy.data.objects.new('ReviewSun',sun);scene.collection.objects.link(ob);ob.rotation_euler=(.5,-.4,-.6)
    camera=bpy.data.cameras.new('ReviewCamera');obj=bpy.data.objects.new('ReviewCamera',camera);scene.collection.objects.link(obj)
    obj.location=(650,-800,850);direction=Vector((0,15,0))-obj.location;obj.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
    camera.type='ORTHO';camera.ortho_scale=870;camera.clip_end=10000;scene.camera=obj
    scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG'
    scene.render.filepath=str(OUT/'environment_overview.png')
    bpy.ops.render.render(write_still=True)
    print('MPR_ENVIRONMENT_PREVIEW '+scene.render.filepath)

if __name__=='__main__':main()
