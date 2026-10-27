"""Import the 20k CAD cart and replace only the six reviewed stacker visuals.

Run in the open Zcool editor via live_dispatcher.py. Actor identities, transforms
and the other 32 low-profile AGVs remain unchanged. All dimensions are UE cm.
"""
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
import unreal

ROOT = Path('D:/UEPro/Test')
SOURCE = ROOT / 'SourceAssets/CartShell_1026/20k'
DEST = '/Game/GHSZcoolSmartFactory/CartShell1026'
MESH_PATH = DEST + '/Meshes/SM_CartShell_1026'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
MAP_FILE = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
LABELS = {'GHN_FloorStacker_08', 'GHN_FloorStacker_12', 'GHN_FloorStacker_9',
          'GHN_FloorStacker_13', 'GHN_FloorStacker_10', 'GHN_FloorStacker_14'}
A = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
E = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
L = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
LIB = unreal.EditorAssetLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
ML = unreal.MaterialEditingLibrary


def xyz(v):
    return [float(v.x), float(v.y), float(v.z)]


def state(actor, include_mesh=True):
    t = actor.get_actor_transform()
    r = actor.get_actor_rotation()
    result = dict(path=actor.get_path_name(), label=actor.get_actor_label(),
                  tags=[str(t) for t in actor.tags], folder=str(actor.get_folder_path()),
                  location_cm=xyz(t.translation), scale=xyz(t.scale3d),
                  rotation=[float(r.pitch), float(r.yaw), float(r.roll)])
    if include_mesh:
        result['meshes'] = [dict(name=c.get_name(), mesh=c.static_mesh.get_path_name() if c.static_mesh else None,
            materials=[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())])
            for c in actor.get_components_by_class(unreal.StaticMeshComponent)]
    return result


def make_material(name, color, roughness, metallic):
    path = DEST + '/Materials/' + name
    if LIB.does_asset_exist(path):
        return LIB.load_asset(path)
    mat = TOOLS.create_asset(name, DEST + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    base = ML.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -240, 0)
    base.set_editor_property('constant', unreal.LinearColor(*color, 1.0))
    ML.connect_material_property(base, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for row, value, prop in [(1, roughness, unreal.MaterialProperty.MP_ROUGHNESS),
                             (2, metallic, unreal.MaterialProperty.MP_METALLIC)]:
        node = ML.create_material_expression(mat, unreal.MaterialExpressionConstant, -240, row * 110)
        node.set_editor_property('r', value)
        ML.connect_material_property(node, '', prop)
    ML.recompile_material(mat)
    assert LIB.save_loaded_asset(mat, only_if_is_dirty=False)
    return mat


def main():
    assert E.get_editor_world().get_path_name().split('.')[0] == MAP, 'Wrong map: no scene changes made'
    assert not E.get_game_world(), 'Stop PIE before importing'
    verified = json.loads((SOURCE / 'verification.json').read_text(encoding='utf8'))
    assert verified['passed'] and verified['native']['triangles'] <= 20000
    actors = {a.get_actor_label(): a for a in A.get_all_level_actors()}
    assert LABELS <= actors.keys()
    targets = {name: actors[name].get_component_by_class(unreal.StaticMeshComponent) for name in LABELS}
    for name, component in targets.items():
        assert component and component.static_mesh.get_name() in ('SM_VR_BlueStacker', 'SM_CartShell_1026'), name
        assert xyz(actors[name].get_actor_scale3d()) == [1.0, 1.0, 1.0], name
    before_other = {n: state(a) for n, a in actors.items() if n not in LABELS}
    before_target = {n: state(actors[n], False) for n in sorted(LABELS)}
    backup = ROOT / 'Saved/Backups' / ('CartShell1026_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MAP_FILE, backup / MAP_FILE.name)
    (backup / 'target_actors.json').write_text(json.dumps({n: state(actors[n]) for n in sorted(LABELS)}, indent=2), encoding='utf8')

    # Reimport only this dedicated asset when the verified FBX changes.
    task = unreal.AssetImportTask()
    task.filename = str(SOURCE / 'SM_CartShell_1026.fbx')
    task.destination_path = DEST + '/Meshes'
    task.destination_name = 'SM_CartShell_1026'
    task.automated = True
    task.replace_existing = True
    task.replace_existing_settings = True
    task.save = False
    options = unreal.FbxImportUI()
    options.import_mesh = True
    options.import_as_skeletal = False
    options.import_materials = False
    options.import_textures = False
    options.import_animations = False
    options.automated_import_should_detect_type = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    data = options.static_mesh_import_data
    data.combine_meshes = True
    data.generate_lightmap_u_vs = False
    data.auto_generate_collision = False
    data.remove_degenerates = False
    data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    data.normal_generation_method = unreal.FBXNormalGenerationMethod.BUILT_IN
    data.import_uniform_scale = 1.0
    # Blender -Y becomes UE +Y. Bake a half turn so the large front opening
    # faces the same local -Y direction as the old stacker's fork tips.
    data.import_rotation = unreal.Rotator(yaw=180.0)
    task.options = options
    TOOLS.import_asset_tasks([task])
    mesh = LIB.load_asset(MESH_PATH)
    assert isinstance(mesh, unreal.StaticMesh), MESH_PATH
    specs = {
        'ghsindustrialblue': ('M_Cart_IndustrialBlue', (.015, .06, .42), .34, .15),
        'ghsdeepbluelowershell': ('M_Cart_DeepBlue', (.012, .045, .35), .38, .12),
        'ghssilverhardware': ('M_Cart_Silver', (.64, .68, .73), .31, .65),
        'ghsrubbercharcoal': ('M_Cart_Rubber', (.018, .023, .030), .76, 0),
        'ghsmotorgraphite': ('M_Cart_Graphite', (.035, .043, .052), .43, .35),
    }
    slots = list(mesh.get_editor_property('static_materials'))
    assigned = []
    for slot in slots:
        imported = str(slot.get_editor_property('imported_material_slot_name'))
        key = re.sub('[^a-z0-9]', '', imported.lower())
        assert key in specs, ('Unknown imported material', imported)
        mat = make_material(*specs[key])
        slot.set_editor_property('material_interface', mat)
        assigned.append(mat.get_path_name())
    assert len(set(assigned)) == 5, assigned
    mesh.set_editor_property('static_materials', slots)
    sm_editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    build = sm_editor.get_lod_build_settings(mesh, 0)
    build.set_editor_property('use_mikk_t_space', False)
    build.set_editor_property('recompute_normals', False)
    build.set_editor_property('recompute_tangents', True)
    sm_editor.set_lod_build_settings(mesh, 0, build)
    bounds = mesh.get_bounds()
    size = [v * 2 for v in xyz(bounds.box_extent)]
    bottom = bounds.origin.z - bounds.box_extent.z
    assert max(abs(a-b) for a, b in zip(size, [38.2, 50.0, 19.55])) < .01, size
    assert abs(bottom) < .01, bottom
    triangles = mesh.get_num_triangles(0)
    assert 19000 <= triangles <= 20000, triangles
    assert LIB.save_loaded_asset(mesh, only_if_is_dirty=False)

    rollback = {n: (c.static_mesh, list(c.get_editor_property('override_materials'))) for n, c in targets.items()}
    try:
        with unreal.ScopedEditorTransaction('Replace six warehouse carts with dimension-accurate CAD model'):
            for name, component in targets.items():
                actors[name].modify()
                component.modify()
                if component.static_mesh != mesh:
                    assert component.set_static_mesh(mesh), name
                component.set_editor_property('override_materials', [])
        assert {n: state(a) for n, a in actors.items() if n not in LABELS} == before_other
        assert {n: state(actors[n], False) for n in sorted(LABELS)} == before_target
        rows = []
        for name, component in sorted(targets.items()):
            assert component.static_mesh == mesh
            assert component.get_num_materials() == 5
            assert [component.get_material(i).get_path_name() for i in range(5)] == assigned
            center, extent = actors[name].get_actor_bounds(False)
            assert abs(center.z - extent.z - .5) < .01, name
            assert max(abs(2*v-s) for v,s in zip(xyz(extent),size)) < .01, name
            rows.append(dict(**before_target[name], mesh=MESH_PATH, size_cm=size, bottom_z_cm=center.z-extent.z))
        assert L.save_current_level(), 'Could not save the target map'
    except Exception:
        for name, component in targets.items():
            old_mesh, old_overrides = rollback[name]
            component.set_static_mesh(old_mesh)
            component.set_editor_property('override_materials', old_overrides)
        raise

    report = dict(passed=True, map=MAP, mesh=MESH_PATH, triangles=triangles, size_cm=size,
                  import_uniform_scale=1.0, baked_orientation_yaw=180.0, materials=assigned,
                  replaced_count=len(rows), actors=rows, other_actors_unchanged=len(before_other),
                  original_actor_count=len(actors), final_actor_count=len(A.get_all_level_actors()),
                  fbx_sha256=hashlib.sha256((SOURCE/'SM_CartShell_1026.fbx').read_bytes()).hexdigest(),
                  map_sha256=hashlib.sha256(MAP_FILE.read_bytes()).hexdigest(), backup=str(backup))
    (SOURCE/'ue-import-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf8')
    unreal.log('CART_SHELL_IMPORT_VERIFIED ' + json.dumps(dict(triangles=triangles,size_cm=size,replaced=len(rows))))


if __name__ == '__main__':
    main()
