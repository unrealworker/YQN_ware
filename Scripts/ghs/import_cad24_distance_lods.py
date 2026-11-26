"""Install or preview CAD24 rack LOD2/3 from build_cad24_distance_lods.py.

In Unreal Python use apply(variants=('A',), preview=True) to obtain an
unsaved independent mesh for a visual A/B. Use apply() to update the eight
production meshes after the comparison. Only the named assets are saved.
"""
import hashlib
import json
from pathlib import Path
import uuid

import unreal

ROOT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
OUT = ROOT/'Saved/GHS_RenderStability/RackLODs'
DEST = '/Game/GHSZcoolSmartFactory/StorageCapacity/Meshes/'
LIB = unreal.EditorAssetLibrary


def signature(mesh):
    return [(str(slot.material_slot_name),str(slot.get_editor_property('imported_material_slot_name')),
             slot.material_interface.get_path_name()) for slot in mesh.static_materials]


def verify_slot_uvs(mesh, level, count):
    dynamic = unreal.DynamicMesh()
    request = unreal.GeometryScriptMeshReadLOD(lod_type=unreal.GeometryScriptLODType.RENDER_DATA,lod_index=level)
    _,outcome = unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(
        mesh,dynamic,unreal.GeometryScriptCopyMeshFromAssetOptions(),request)
    assert 'SUCCESS' in str(outcome), outcome
    query = unreal.GeometryScript_MeshQueries
    read_uv = getattr(query,'get_triangle_u_vs',None) or query.get_triangle_uvs
    read_role = unreal.GeometryScript_Materials.get_triangle_material_id
    seen = {}
    for i in range(mesh.get_num_triangles(level)):
        u0,u1,u2,valid = read_uv(dynamic,1,i)
        role,valid_role = read_role(dynamic,i)
        assert valid and valid_role and u0.x==u1.x==u2.x==round(u0.x)
        slot = int(u0.x)
        assert (slot==-1)==(role<3), (i,role,slot)
        seen.setdefault(slot,set()).add(role)
    assert seen.pop(-1)=={0,1,2}
    assert set(seen)==set(range(count)) and all(roles=={3,4} for roles in seen.values())


def apply(variants=None, preview=False):
    data = json.loads((OUT/'manifest.json').read_bytes())
    if variants is not None:
        data = {'SM_GHS_V2Rack_CAD24_'+v+'_Capacity':data['SM_GHS_V2Rack_CAD24_'+v+'_Capacity'] for v in variants}
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if preview:
        preview_path = OUT/'PreviewPackages'
        preview_path.mkdir(exist_ok=True)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        unreal.SystemLibrary.execute_console_command(world,
            f'PackageName.RegisterMountPoint /GHSDistancePreview/ "{preview_path.as_posix()}/"')
    dirty = {p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
    result = []
    for name, lods in data.items():
        original = LIB.load_asset(DEST+name)
        assert isinstance(original,unreal.StaticMesh) and original.get_num_lods()==4
        assert original.get_outermost().get_path_name() not in dirty or preview, name
        mesh = original
        if preview:
            mesh = unreal.AssetToolsHelpers.get_asset_tools().duplicate_asset(
                name+'_'+uuid.uuid4().hex[:8],'/GHSDistancePreview',original)
            assert mesh and mesh!=original
        original_materials = signature(original)
        before = [original.get_num_triangles(i) for i in range(4)]
        screen = list(editor.get_lod_screen_sizes(original))
        for level in (2,3):
            expected = lods[str(level)]
            fbx = OUT/expected['fbx']
            assert hashlib.sha256(fbx.read_bytes()).hexdigest()==expected['sha256']
            assert editor.import_lod(mesh,level,str(fbx))==level
            # Replacing an auto-reduced source model can leave its reduction
            # settings active. Explicit LOD geometry needs one-to-one triangles.
            if mesh.get_num_triangles(level)!=expected['triangles']:
                settings = editor.get_lod_reduction_settings(mesh,level)
                settings.percent_triangles = 1.
                settings.percent_vertices = 1.
                settings.base_lod_model = level
                editor.set_lod_reduction_settings(mesh,level,settings)
            assert mesh.get_num_triangles(level)==expected['triangles'], (name,level,mesh.get_num_triangles(level))
            assert editor.get_num_uv_channels(mesh,level)==2
            roles = {editor.get_lod_material_slot(mesh,level,i) for i in range(mesh.get_num_sections(level))}
            assert roles==set(range(5)),(name,level,roles)
            verify_slot_uvs(mesh,level,expected['slots'])
        if list(editor.get_lod_screen_sizes(mesh))!=screen:
            assert editor.set_lod_screen_sizes(mesh,screen)
        assert signature(mesh)==original_materials and list(editor.get_lod_screen_sizes(mesh))==screen
        assert [mesh.get_num_triangles(i) for i in range(2)]==before[:2]
        result.append(dict(asset=mesh.get_path_name(),before=before,
                           after=[mesh.get_num_triangles(i) for i in range(4)],screen=screen))
    if not preview:
        for row in result:
            assert LIB.save_loaded_asset(LIB.load_asset(row['asset']),only_if_is_dirty=False)
    (OUT/('preview.json' if preview else 'installed.json')).write_text(json.dumps(result,indent=2),encoding='utf8')
    return result
