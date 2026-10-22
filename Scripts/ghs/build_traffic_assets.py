"""Export reusable cars from the exact parking-car generator in background Blender."""
from pathlib import Path
import hashlib
import json
import sys
import bpy

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
sys.dont_write_bytecode=True
from park_vehicles import build_car
OUT=ROOT/'SourceAssets/GHS/Traffic'
OUT.mkdir(parents=True,exist_ok=True)
palette=json.loads((ROOT/'SourceAssets/GHS/Park/park_manifest.json').read_text(encoding='utf8'))['materials']
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.context.scene.unit_settings.system='METRIC'
bpy.context.scene.unit_settings.scale_length=1
materials={}
for role in ['Buildings','Blue','Detail','Markings','Solar','Rubber','VehicleLights']:
    m=bpy.data.materials.new('M_GHSPark_'+role)
    m.diffuse_color=(*palette[role],1)
    materials[role]=m
manifest={'source_generator':'Scripts/ghs/park_vehicles.py','source_sha256':hashlib.sha256((ROOT/'Scripts/ghs/park_vehicles.py').read_bytes()).hexdigest(),'meshes':[]}
for suffix,variant,blue in [('Sedan',0,False),('SUV',1,False),('BlueSedan',0,True)]:
    vertices=[];faces=[];indices=[];roles=[]
    def emit(role,points,polygons):
        if role not in roles:roles.append(role)
        offset=len(vertices)
        vertices.extend((x,-y,z) for x,y,z in points)
        faces.extend(tuple(offset+i for i in reversed(face)) for face in polygons)
        indices.extend([roles.index(role)]*len(polygons))
    stats=build_car({'mesh':emit},0,0,variant=variant,blue=blue)
    name='SM_GHSTraffic_'+suffix
    geo=bpy.data.meshes.new(name);geo.from_pydata(vertices,[],faces);geo.update()
    assert not geo.validate()
    obj=bpy.data.objects.new(name,geo);bpy.context.scene.collection.objects.link(obj)
    for role in roles:geo.materials.append(materials[role])
    for polygon,index in zip(geo.polygons,indices):polygon.material_index=index
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    fbx=OUT/(name+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False)
    geo.calc_loop_triangles()
    manifest['meshes'].append(dict(name=name,fbx=str(fbx),material_roles=roles,slot_names=['M_GHSPark_'+r for r in roles],triangles=len(geo.loop_triangles),bounds_ue_cm={k:[v*100 for v in val] for k,val in stats['bounds_uvz_m'].items()},sha256=hashlib.sha256(fbx.read_bytes()).hexdigest()))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'GHS_TrafficCars.blend'))
(OUT/'cars.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print('GHS_TRAFFIC_CARS_READY '+json.dumps({'meshes':len(manifest['meshes']),'triangles':sum(m['triangles'] for m in manifest['meshes'])}))
