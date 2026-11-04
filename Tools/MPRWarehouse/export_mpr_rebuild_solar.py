"""Blender-only solar export/roundtrip. No NumPy, GEOS or model generation.

Run in a fresh background Blender process after build_mpr_rebuild_solar.py.
Writes only the independent solar directory, not the main scene or old assets.
"""
import gzip
import hashlib
import json
import math
from pathlib import Path
import traceback
import bpy

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/rebuild_b50b57/solar'
ROLES=['MPR4_SolarFrame','MPR4_SolarCells','MPR4_SolarMid','MPR4_SolarFar']
REPORT=dict(success=False,meshes=[],old_assets_modified=False)


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')


def material(role,spec):
    mat=bpy.data.materials.new(role);mat.use_nodes=True
    bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    bs.inputs['Base Color'].default_value=(*spec['color'],1)
    bs.inputs['Roughness'].default_value=spec['roughness'];bs.inputs['Metallic'].default_value=spec.get('metallic',0)
    for kind,relative in spec.get('textures',{}).items():
        path=(ROOT/relative).resolve();assert path.is_file()
        node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=bpy.data.images.load(str(path),check_existing=True)
        if kind=='normal':
            node.image.colorspace_settings.name='Non-Color'
            normal=mat.node_tree.nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=spec.get('normal_strength',0)
            mat.node_tree.links.new(node.outputs['Color'],normal.inputs['Color']);mat.node_tree.links.new(normal.outputs['Normal'],bs.inputs['Normal'])
        else:
            # Source textures remain untouched. UE uses the already-reviewed
            # independent rebuild material instances for these four roles.
            mix=mat.node_tree.nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1
            mix.inputs[2].default_value=(*spec['color'],1)
            mat.node_tree.links.new(node.outputs['Color'],mix.inputs[1]);mat.node_tree.links.new(mix.outputs[0],bs.inputs['Base Color'])
    return mat


def bounds(vertices):return [[min(v[i]for v in vertices),max(v[i]for v in vertices)]for i in range(3)]


def run():
    validation=read(OUT/'geometry_validation.json');assert validation['success']
    assert sha(OUT/'geometry_payload.json.gz')==validation['payload_sha256']
    assert sha(OUT/'layout.json')==validation['layout_sha256']
    with gzip.open(OUT/'geometry_payload.json.gz','rt',encoding='utf8')as stream:payload=json.load(stream)
    for name,h in payload['input_hashes'].items():assert sha(OUT/'inputs'/name)==h
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    bpy.context.preferences.filepaths.save_version=0
    mats={r:material(r,payload['materials'][r])for r in ROLES};rows=[];objects={}
    for name,groups in payload['geometry'].items():
        vertices=[];faces=[];uvs=[];indices=[];keys=list(groups)
        for index,(role,(vv,ff,uu))in enumerate(groups.items()):
            offset=len(vertices);vertices.extend(vv);faces.extend(tuple(i+offset for i in f)for f in ff)
            uvs.extend(uu);indices.extend([index]*len(ff))
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj);objects[name]=obj
        for role in keys:mesh.materials.append(mats[role])
        layer=mesh.uv_layers.new(name='UVMap')
        for polygon,index,uv in zip(mesh.polygons,indices,uvs):
            polygon.material_index=index
            assert len(polygon.loop_indices)==len(uv)
            for loop,p in zip(polygon.loop_indices,uv):layer.data[loop].uv=p
        obj['mpr_source_role']='independent_solar_replacement';obj['mpr_units']='metres'
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
        path=OUT/(name+'.fbx')
        bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',
            apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False)
        mesh.calc_loop_triangles()
        rows.append(dict(name=name,category='Architecture',fbx=path.relative_to(ROOT).as_posix(),sha256=sha(path),
            material_roles=keys,bounds_m=bounds(vertices),vertices=len(vertices),triangles=len(mesh.loop_triangles),
            instance_only=False,collision=False,tick=False,full_precision_uvs=True,nanite=False))
    assert len(rows)==15
    for name,obj in objects.items():
        if name.endswith(('_LOD1','_LOD2')):obj.hide_render=True;obj.hide_viewport=True
    for image in bpy.data.images:
        if image.source=='FILE'and image.filepath:
            image.filepath=bpy.path.relpath(bpy.path.abspath(image.filepath),start=str(OUT))
    blend=OUT/'MPR_B50B57_Solar.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend));blend_hash=sha(blend)
    by_name={r['name']:r for r in rows};base=[]
    for bank in read(OUT/'layout.json')['bank_ids']:
        name='SM_MPRR_SolarBank_'+bank
        levels=[by_name[name],by_name[name+'_LOD1'],by_name[name+'_LOD2']]
        row=dict(levels[0]);radius=math.sqrt(sum(((hi-lo)*.5)**2 for lo,hi in row['bounds_m']))
        row.update(lod_files=[r['fbx']for r in levels[1:]],lod_sha256=[r['sha256']for r in levels[1:]],
            lod_triangles=[r['triangles']for r in levels],lod_screen_sizes=[1.,min(.99,.9*radius/70),min(.98,.35*radius/70)],
            lod_material_roles=[r['material_roles']for r in levels],all_lod_material_roles=ROLES,
            retained_actor_label='MPR4_SolarBank_'+bank,retained_mesh='/Game/MPRWarehouse/ReferenceV4/Architecture/Meshes/SM_MPR4_SolarBank_'+bank)
        base.append(row)
    manifest=dict(schema_version=1,units='metres',coordinate_frame='CAD +Y, UE import reflects Y once',
        rebuild_namespace='/Game/MPRWarehouse/RebuildB50B57',map='/Game/Maps/MPR_CAD_Warehouse_B50B57',
        meshes=base,export_meshes=rows,blend=blend.relative_to(ROOT).as_posix(),blend_sha256=blend_hash,
        layout='SourceAssets/MPR/rebuild_b50b57/solar/layout.json',layout_sha256=sha(OUT/'layout.json'),
        geometry_payload_sha256=sha(OUT/'geometry_payload.json.gz'),input_hashes=payload['input_hashes'],
        material_policy='Reuse four existing roles; frame source read-only, Cells/Mid/Far use independent rebuild instances',
        all_lod_material_roles=ROLES,existing_actor_transforms_unchanged=True,old_assets_modified=False)
    # A fresh short roundtrip of all fifteen exports proves axis/scale, UVs,
    # material slots and triangle counts before publishing the manifest.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for row in rows:
        REPORT['active_mesh']=row['name']
        bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']),use_custom_normals=True,colors_type='LINEAR')
        imported=[o for o in bpy.context.selected_objects if o.type=='MESH'];assert len(imported)==1
        obj=imported[0];obj.data.calc_loop_triangles()
        assert len(obj.data.loop_triangles)==row['triangles']
        actual=bounds([tuple(obj.matrix_world@v.co)for v in obj.data.vertices])
        error=max(abs(a-b)for av,bv in zip(actual,row['bounds_m'])for a,b in zip(av,bv));assert error<.002,(row['name'],error)
        roles=[slot.material.name for slot in obj.material_slots]
        roles=[r.rsplit('.',1)[0]if r.rsplit('.',1)[-1].isdigit()else r for r in roles]
        assert roles==row['material_roles'],(row['name'],roles)
        assert obj.data.uv_layers and len(obj.data.uv_layers[0].data)==len(obj.data.loops)
        assert all(math.isfinite(x)for item in obj.data.uv_layers[0].data for x in item.uv)
        REPORT['meshes'].append(dict(name=row['name'],triangles=row['triangles'],bounds_error_m=error,material_roles=roles,uvs_valid=True))
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        for collection in (bpy.data.meshes,bpy.data.materials,bpy.data.images):
            for item in list(collection):
                if item.users==0:collection.remove(item)
    assert sha(blend)==blend_hash
    for row in rows:assert sha(ROOT/row['fbx'])==row['sha256']
    for name,h in payload['input_hashes'].items():assert sha(OUT/'inputs'/name)==h
    write(OUT/'manifest.json',manifest)
    REPORT.pop('active_mesh',None)
    REPORT.update(success=True,fbx_roundtrip_meshes=15,render_meshes=5,blend_sha256=blend_hash,manifest_sha256=sha(OUT/'manifest.json'))


if __name__=='__main__':
    try:run()
    except Exception:REPORT['error']=traceback.format_exc();print(REPORT['error'],flush=True)
    write(OUT/'blender_validation.json',REPORT)
    print('MPRR_SOLAR_EXPORT',REPORT['success'],flush=True)
    if not REPORT['success']:raise RuntimeError(REPORT['error'])
