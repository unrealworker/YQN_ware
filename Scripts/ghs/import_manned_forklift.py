"""Import one Blender-built staffed forklift into the current Normal warehouse.

Run with UE's Python console, after saving the Blender FBX and JSON manifest.
This deliberately refuses replacement imports and never reloads another level.
The existing CAD meshes, materials, HUD, camera and vehicles are preserved.
"""
import hashlib
import itertools
import json
import math
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

import unreal

ROOT = Path(r'D:\UEPro\Test')
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
from sync_wall_heights import snapshot, xyz, transform

MAP = '/Game/Maps/GHS_CAD_NormalWarehouse'
MAP_FILE = 'Content/Maps/GHS_CAD_NormalWarehouse.umap'
SOURCE = ROOT / 'SourceAssets/GHS_Normal/MannedForklift'
MANIFEST = SOURCE / 'manned_forklift.json'
FBX = SOURCE / 'manned_forklift.fbx'
DEST = '/Game/GHSNormalWarehouse/MannedForklift'
MESH_NAME = 'SM_GHN_MannedForklift'
MESH_PATH = DEST + '/Meshes/' + MESH_NAME
LABEL = 'GHN_MannedForklift_01'
FOLDER = 'GHS_Normal/Vehicles/MannedForklifts'
REPORT = ROOT / 'Saved/GHS_MannedForkliftImport.json'
TARGET_LABEL = 'GHS_CAD_PalletCargo'
TARGET_INDEX = 744
FORK_GAP_CM = 50.0
MIN_CLEARANCE_CM = 25.0
GROUND_GAP_CM = 0.5
WALLS = {'GHS_CAD_WallFaces', 'GHS_CAD_WallSections', 'GHS_CAD_WallEdges'}

A = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
E = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
L = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
LIB = unreal.EditorAssetLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
ML = unreal.MaterialEditingLibrary


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def content_hashes():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in (ROOT / 'Content').rglob('*') if p.is_file()}


def labels():
    actors = A.get_all_level_actors()
    result = {a.get_actor_label(): a for a in actors}
    assert len(result) == len(actors), 'Duplicate actor labels require inspection before this import'
    return result


def component_transforms(component):
    if isinstance(component, unreal.InstancedStaticMeshComponent):
        return [component.get_instance_transform(i, world_space=True) for i in range(component.get_instance_count())]
    return [component.get_world_transform()]


def mesh_box(mesh, world_transform):
    b = mesh.get_bounds()
    o, e = xyz(b.origin), xyz(b.box_extent)
    points = [xyz(unreal.MathLibrary.transform_location(world_transform,
              unreal.Vector(*(o[i] + sign[i] * e[i] for i in range(3)))))
              for sign in itertools.product((-1, 1), repeat=3)]
    return [min(p[i] for p in points) for i in range(3)] + [max(p[i] for p in points) for i in range(3)]


def xy_gap(a, b):
    return math.hypot(max(a[0] - b[3], b[0] - a[3], 0), max(a[1] - b[4], b[1] - a[4], 0))


def overlap_z(a, b):
    return min(a[5], b[5]) > max(a[2], b[2]) + 1e-5


def ignored_solid(label):
    return (label in WALLS or label in {'GHS_CAD_ExactFootprint', 'GHS_DarkSurround',
            'GHN_StudioGround', 'GHN_StudioSky'} or label.startswith('CAM_') or
            any(s in label for s in ('ContextGrid', 'Outlines', 'Clearances')))


def live_obstacles(by):
    result = []
    for label, actor in by.items():
        if label == LABEL or ignored_solid(label) or bool(actor.get_editor_property('hidden')):
            continue
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = component.static_mesh
            if not mesh or not component.get_editor_property('visible') or component.get_editor_property('hidden_in_game'):
                continue
            for index, t in enumerate(component_transforms(component)):
                result.append(dict(label=label, component=component.get_name(), index=index,
                                   bounds_cm=mesh_box(mesh, t)))
    return result


def world_triangles(actor):
    """Use mesh triangles, not a merged wall's warehouse-sized bounding box."""
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        mesh = component.static_mesh
        if not mesh or not component.get_editor_property('visible'):
            continue
        description = mesh.get_static_mesh_description(0)
        assert description, ('Missing editable mesh triangles', actor.get_actor_label())
        expected, seen = description.get_triangle_count(), 0
        transforms = component_transforms(component)
        for index in range(expected * 4 + 1024):
            tid = unreal.TriangleID(id_value=index)
            if not description.is_triangle_valid(tid):
                continue
            seen += 1
            local = [description.get_vertex_position(description.get_vertex_instance_vertex(
                     description.get_triangle_vertex_instance(tid, corner))) for corner in range(3)]
            for t in transforms:
                yield [xyz(unreal.MathLibrary.transform_location(t, p)) for p in local]
            if seen == expected:
                break
        assert seen == expected, ('Triangle enumeration incomplete', actor.get_actor_label(), seen, expected)


def contains_xy(point, triangle):
    a, b, c = triangle
    x, y = point
    den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(den) < 1e-8:
        return False
    u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / den
    v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / den
    return min(u, v, 1 - u - v) >= -1e-8


def validate_geometry(by, bounds, obstacles):
    solid = [o for o in obstacles if overlap_z(bounds, o['bounds_cm'])]
    assert solid
    ordered = sorted((dict(o, clearance_cm=xy_gap(bounds, o['bounds_cm'])) for o in solid),
                     key=lambda o: o['clearance_cm'])
    assert ordered[0]['clearance_cm'] >= MIN_CLEARANCE_CM - .01, ('Forklift overlaps/approaches scene geometry', ordered[0])
    assert abs(bounds[2] - GROUND_GAP_CM) < .01, ('Wheel ground height', bounds)
    floor = [t for t in world_triangles(by['GHS_CAD_ExactFootprint']) if all(abs(p[2]) < .01 for p in t)]
    assert floor, 'No ground surface at warehouse Z=0'
    samples = [(x, y) for x in (bounds[0], (bounds[0] + bounds[3]) / 2, bounds[3])
               for y in (bounds[1], (bounds[1] + bounds[4]) / 2, bounds[4])]
    for point in samples:
        assert any(contains_xy(point, triangle) for triangle in floor), ('Forklift outside CAD footprint', point)
    wall_count, closest_wall = 0, float('inf')
    for name in sorted(WALLS):
        assert name in by, ('Required wall missing', name)
        for triangle in world_triangles(by[name]):
            wall_count += 1
            box = [min(p[i] for p in triangle) for i in range(3)] + [max(p[i] for p in triangle) for i in range(3)]
            if box[5] < bounds[2] or box[2] > bounds[5]:
                continue
            clearance = xy_gap(bounds, box)
            closest_wall = min(closest_wall, clearance)
            assert clearance >= MIN_CLEARANCE_CM, ('Forklift too close to wall triangle', name, box)
    old_stackers = [o for o in obstacles if o['label'].startswith('GHN_FloorStacker_')]
    assert len({o['label'] for o in old_stackers}) == 12, 'Expected 12 existing floor stackers; inspect changed scene'
    return dict(bounds_cm=bounds, nearest_solid=ordered[0], nearest_five_solids=ordered[:5],
                obstacle_count=len(obstacles), full_fork_and_driver_envelope_checked=True,
                floor_test_points=len(samples), wall_triangles_checked=wall_count,
                nearest_wall_cm=closest_wall,
                existing_stacker_clearance_cm=min(xy_gap(bounds, o['bounds_cm']) for o in old_stackers))


def material(spec):
    name = spec['name']
    path = DEST + '/Materials/' + name
    assert not LIB.does_asset_exist(path), ('Refusing to overwrite material', path)
    mat = TOOLS.create_asset(name, DEST + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    assert mat
    color = ML.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector)
    rgb = spec['base_color'][:3]
    color.set_editor_property('constant', unreal.LinearColor(*rgb, 1))
    assert ML.connect_material_property(color, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for prop, value in ((unreal.MaterialProperty.MP_ROUGHNESS, spec['roughness']),
                        (unreal.MaterialProperty.MP_METALLIC, spec['metallic']),
                        (unreal.MaterialProperty.MP_SPECULAR, .3)):
        node = ML.create_material_expression(mat, unreal.MaterialExpressionConstant)
        node.set_editor_property('r', float(value))
        assert ML.connect_material_property(node, '', prop)
    emission = spec.get('emission', 0)
    if emission:
        rgb_emission = emission[:3] if isinstance(emission, list) else [v * float(emission) for v in rgb]
        node = ML.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector)
        node.set_editor_property('constant', unreal.LinearColor(*rgb_emission, 1))
        assert ML.connect_material_property(node, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    ML.recompile_material(mat)
    assert LIB.save_loaded_asset(mat, only_if_is_dirty=False)
    return mat


def run():
    assert not REPORT.exists(), 'Review existing import report before retrying; never overwrite blindly'
    report = dict(success=False, map=MAP, source_fbx=str(FBX), source_manifest=str(MANIFEST))
    spawned = None
    map_saved = False
    try:
        assert E.get_editor_world().get_path_name().split('.')[0] == MAP, 'Open GHS_CAD_NormalWarehouse first'
        assert not E.get_game_world(), 'Stop PIE before importing the forklift'
        assert FBX.is_file() and MANIFEST.is_file(), 'Blender export and manifest must exist before import'
        assert not LIB.does_asset_exist(MESH_PATH), 'Forklift asset already exists; refusing destructive reimport'
        spec = read(MANIFEST)
        assert spec.get('materials') and spec.get('bounds_m'), 'Missing material or precise bounds contract'
        assert len({m['name'] for m in spec['materials']}) == len(spec['materials'])
        for entry in spec['materials']:
            assert not LIB.does_asset_exist(DEST + '/Materials/' + entry['name'])
        by = labels()
        assert LABEL not in by
        assert TARGET_LABEL in by
        before = snapshot(by)
        old_content = content_hashes()
        backup = ROOT / 'Saved/Backups' / ('GHS_MannedForklift_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        backup.mkdir(parents=True)
        shutil.copy2(ROOT / MAP_FILE, backup / 'GHS_CAD_NormalWarehouse.before.umap')
        write(backup / 'content_hashes.json', old_content)
        write(backup / 'live_scene_before.json', before)
        write(backup / 'source_manifest.json', spec)
        report.update(backup_root=str(backup), original_actor_count=len(by), fbx_sha256=sha(FBX),
                      manifest_sha256=sha(MANIFEST), dirty_maps_before=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()])
        write(REPORT, report)
        mats = {s['name']: material(s) for s in spec['materials']}
        task = unreal.AssetImportTask()
        task.filename = str(FBX)
        task.destination_path = DEST + '/Meshes'
        task.destination_name = MESH_NAME
        task.automated = True
        task.replace_existing = False
        task.save = True
        options = unreal.FbxImportUI()
        options.import_mesh = True
        options.import_as_skeletal = False
        options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
        options.automated_import_should_detect_type = False
        options.import_materials = False
        options.import_textures = False
        options.import_animations = False
        data = options.static_mesh_import_data
        data.combine_meshes = True
        data.generate_lightmap_u_vs = False
        data.auto_generate_collision = False
        data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        data.normal_generation_method = unreal.FBXNormalGenerationMethod.BUILT_IN
        task.options = options
        TOOLS.import_asset_tasks([task])
        mesh = LIB.load_asset(MESH_PATH)
        assert isinstance(mesh, unreal.StaticMesh), task.imported_object_paths
        static_materials = mesh.get_editor_property('static_materials')
        used = []
        for index, slot in enumerate(static_materials):
            name = str(slot.get_editor_property('imported_material_slot_name'))
            assert name in mats, ('Unexpected material slot', name, list(mats))
            slot.set_editor_property('material_interface', mats[name])
            static_materials[index] = slot
            used.append(name)
        assert set(used) == set(mats), ('Unused/missing exported material', used, list(mats))
        mesh.set_editor_property('static_materials', static_materials)
        unreal.load_module('StaticMeshEditor')
        sm_editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        reduction = unreal.StaticMeshReductionOptions()
        reduction.auto_compute_lod_screen_size = False
        reduction.reduction_settings = [unreal.StaticMeshReductionSettings(percent_triangles=p, screen_size=s)
                                        for p, s in [(1., 1.), (.6, .25), (.3, .08), (.15, .025)]]
        assert sm_editor.set_lods(mesh, reduction) == 4
        local = mesh_box(mesh, unreal.Transform())
        expected = spec['bounds_m']
        expected_local = [expected[0][0]*100, -expected[1][1]*100, expected[2][0]*100,
                          expected[0][1]*100, -expected[1][0]*100, expected[2][1]*100]
        assert max(abs(a-b) for a, b in zip(local, expected_local)) < .25, ('FBX axis/scale mismatch', local, expected_local)
        assert 300 < local[3] - local[0] < 370 and 95 < local[4] - local[1] < 135 and 200 < local[5] - local[2] < 250
        assert LIB.save_loaded_asset(mesh, only_if_is_dirty=False)
        target_component = by[TARGET_LABEL].get_component_by_class(unreal.InstancedStaticMeshComponent)
        assert target_component and target_component.get_instance_count() > TARGET_INDEX
        target_box = mesh_box(target_component.static_mesh, target_component.get_instance_transform(TARGET_INDEX, world_space=True))
        position = [(target_box[0]+target_box[3]+local[1]+local[4])/2,
                    target_box[1]-FORK_GAP_CM-local[3], GROUND_GAP_CM-local[2]]
        rotation = unreal.Rotator(yaw=90)
        placed_transform = unreal.Transform(location=unreal.Vector(*position), rotation=rotation, scale=unreal.Vector(1, 1, 1))
        placed_bounds = mesh_box(mesh, placed_transform)
        obstacles = live_obstacles(by)
        geometry = validate_geometry(by, placed_bounds, obstacles)
        assert abs(xy_gap(placed_bounds, target_box)-FORK_GAP_CM) < .01
        with unreal.ScopedEditorTransaction('Add independent manned forklift with safety-equipped operator'):
            spawned = A.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*position), rotation)
            assert spawned
            spawned.set_actor_label(LABEL)
            spawned.set_folder_path(FOLDER)
            spawned.set_actor_scale3d(unreal.Vector(1, 1, 1))
            spawned.tags = [unreal.Name('NormalWarehouseMannedForklift'), unreal.Name('WorkArea=FloorStorage'),
                            unreal.Name('Driver=SafetyHelmetAndWorkwear')]
            component = spawned.get_component_by_class(unreal.StaticMeshComponent)
            assert component.set_static_mesh(mesh)
            component.set_mobility(unreal.ComponentMobility.MOVABLE)
            component.set_collision_profile_name('NoCollision')
            component.set_editor_property('receives_decals', False)
            component.set_editor_property('cast_shadow', True)
        after = labels()
        assert set(after) == set(by) | {LABEL}
        after_snapshot = snapshot(after)
        for name, value in before.items():
            assert after_snapshot[name] == value, ('Existing actor changed', name)
        assert spawned.get_attach_parent_actor() is None
        assert transform(spawned.get_actor_transform())['scale'] == [1., 1., 1.]
        actual_bounds = mesh_box(mesh, component.get_world_transform())
        assert max(abs(a-b) for a, b in zip(actual_bounds, placed_bounds)) < .01
        assert L.save_current_level()
        map_saved = True
        now = content_hashes()
        assert set(old_content) <= set(now), 'Existing content was deleted'
        changed = [p for p, h in old_content.items() if now[p] != h]
        assert changed == [MAP_FILE], ('Only target map may change', changed)
        new_files = sorted(set(now)-set(old_content))
        assert new_files and all(p.startswith('Content/GHSNormalWarehouse/MannedForklift/') for p in new_files)
        report.update(success=True, actor_label=LABEL, actor_count=len(after), mesh=mesh.get_path_name(),
                      independent_static_mesh_actor=True, original_actors_unchanged=True,
                      placement=dict(position_cm=position, yaw_deg=90., scale=1., target_label=TARGET_LABEL,
                                     target_instance=TARGET_INDEX, fork_gap_cm=FORK_GAP_CM),
                      geometry=geometry, local_bounds_cm=local, material_slots=used,
                      lod_triangles=[mesh.get_num_triangles(i) for i in range(sm_editor.get_lod_count(mesh))],
                      changed_content=changed, new_content=new_files, map_sha256=sha(ROOT/MAP_FILE),
                      old_maps_shared_meshes_materials_and_hud_unchanged=True)
        write(backup / 'live_scene_after.json', after_snapshot)
        unreal.log('GHS_MANNED_FORKLIFT_IMPORTED: 1 independent staffed forklift; scene and asset preservation verified')
    except Exception:
        report['error'] = traceback.format_exc()
        # Existing content is never rolled back over newer user changes.  A failed
        # new placement is removed only in memory; generated new assets are kept
        # for diagnosis.  The named backup contains the untouched original map.
        if spawned is not None and not map_saved and not report['success']:
            A.destroy_actor(spawned)
        raise
    finally:
        write(REPORT, report)


def verify():
    """Read-only verification; run in a freshly opened editor/commandlet map."""
    destination = ROOT / 'Saved/GHS_MannedForkliftVerification.json'
    result = dict(success=False, map=MAP)
    try:
        assert E.get_editor_world().get_path_name().split('.')[0] == MAP
        assert not E.get_game_world(), 'Stop PIE before structural verification'
        report = read(REPORT)
        assert report['success']
        assert sha(ROOT / MAP_FILE) == report['map_sha256'], 'Scene changed since import; inspect before using old audit'
        backup = Path(report['backup_root'])
        old = read(backup / 'content_hashes.json')
        initial = content_hashes()
        assert set(old) <= set(initial)
        assert [p for p, h in old.items() if initial[p] != h] == [MAP_FILE]
        assert sorted(set(initial)-set(old)) == report['new_content']
        by = labels()
        before = read(backup / 'live_scene_before.json')
        after = snapshot(by)
        assert set(after) == set(before) | {LABEL}
        for name, value in before.items():
            assert after[name] == value, ('Existing actor changed', name)
        actor = by[LABEL]
        assert actor.get_class() == unreal.StaticMeshActor.static_class()
        assert actor.get_attach_parent_actor() is None
        assert str(actor.get_folder_path()) == FOLDER
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        mesh = component.static_mesh
        assert mesh.get_path_name().split('.')[0] == MESH_PATH
        assert transform(actor.get_actor_transform())['scale'] == [1., 1., 1.]
        assert all(component.get_material(i).get_path_name().split('.')[0] == DEST + '/Materials/' + name
                   for i, name in enumerate(report['material_slots']))
        geometry = validate_geometry(by, mesh_box(mesh, component.get_world_transform()), live_obstacles(by))
        assert content_hashes() == initial, 'Read-only verification must not modify any content file'
        result.update(success=True, actor_label=LABEL, mesh=mesh.get_path_name(), geometry=geometry,
                      original_actors_preserved=len(before), independent_vehicle_count=1,
                      no_content_mutation=True, only_normal_map_changed_since_baseline=True)
        unreal.log('GHS_MANNED_FORKLIFT_VERIFIED: exact saved asset, materials, placement, clearances and preservation')
    except Exception:
        result['error'] = traceback.format_exc()
        raise
    finally:
        write(destination, result)


if __name__ == '__main__':
    run()
