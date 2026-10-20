"""Read-only saved-map acceptance, then leave the new map open for inspection.

Run in an editor with no unsaved map. This script loads only the new scene,
inventories its persisted geometry, checks every original Content file, and
sets the editor viewport. It never saves an asset or loads the original map.
"""
import importlib.util
import json
import traceback
from pathlib import Path

import unreal

ROOT = Path('D:/UEPro/Test')
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
REPORT = ROOT / 'Saved/GHS_Zcool_FinalEditor.json'
ORIGINAL_HASH = 'f7201ef820bcfca947071a5e936427362a0c002ba50398dba2e17755d7e40066'
result = dict(success=False, map=MAP, assets_saved=False)


try:
    # Importing the builder exposes its pure inventory/comparison helpers;
    # its guarded main() is deliberately never invoked here.
    spec = importlib.util.spec_from_file_location('zcool_readonly_inventory', ROOT / 'Scripts/ghs/build_zcool_smart_factory.py')
    utility = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(utility)
    build = json.loads((ROOT / 'Saved/GHS_ZcoolBuild.json').read_text(encoding='utf-8-sig'))
    assert build['success'] and build['saved_and_reloaded'], 'Builder has no successful saved result'
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Preserve unsaved work before opening the new map'
    assert utility.sha(ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap') == ORIGINAL_HASH
    target_file = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
    assert utility.sha(target_file) == build['map_sha256'], 'New map differs from saved build report'
    originals = json.loads((ROOT / 'Saved/GHS_ZcoolOriginalContentHashes.json').read_text(encoding='utf-8-sig'))
    assert originals, 'Original Content manifest is empty'
    changed = []
    for row in originals:
        path = ROOT / row['Path']
        if not path.is_file() or path.stat().st_size != row['Length'] or utility.sha(path).upper() != row['SHA256'].upper():
            changed.append(row['Path'])
    assert not changed, ('Original Content changed', changed)
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    # Load the saved target even if already open so acceptance observes disk.
    assert levels.load_level(MAP)
    assert editor.get_editor_world().get_path_name().split('.')[0] == MAP
    current = utility.inventory()
    expected_reload = json.loads(json.dumps(build['after']))
    # Blueprint construction can recompute only this camera's derived spring
    # arm/frustum transforms. Retain exact component membership, attachments,
    # meshes, materials, flags, and every other actor/instance comparison.
    expected_camera = expected_reload['GHS_WarehouseCamera']
    current_camera = current['GHS_WarehouseCamera']
    expected_camera['transform'] = current_camera['transform']
    assert set(expected_camera['components']) == set(current_camera['components'])
    for name, component in expected_camera['components'].items():
        for key in ('transform', 'relative_transform'):
            if key in component:
                component[key] = current_camera['components'][name][key]
    utility.check_equal(expected_reload, current, 'fresh_editor_reload')
    utility.assert_parity(build['before'], current, build['identity_changes'])
    counts = utility.counts(current)
    assert counts['actors'] == 248
    assert counts['dock_trucks'] == 52 and counts['stackers'] == 6
    assert counts['manual_forklifts'] == 16 and counts['agvs'] == 32
    stacker_ids = [t for a in current.values() if 'NormalWarehouseFloorStacker' in a['tags']
                   for t in a['tags'] if t.startswith('TwinId=GHN_FloorStacker_')]
    assert len(stacker_ids) == len(set(stacker_ids)) == 6
    native = unreal.load_class(None, '/Script/Test.GHSWarehouseCameraPawn')
    cameras = [a for a in actors.get_all_level_actors()
               if unreal.MathLibrary.class_is_child_of(a.get_class(), native)]
    assert len(cameras) == 1, 'Expected exactly one controllable warehouse camera'
    pawn = cameras[0]
    pawn_class = unreal.EditorAssetLibrary.load_blueprint_class('/Game/GHSNormalWarehouse/Camera/BP_GHS_WarehouseCamera')
    game_mode_class = unreal.EditorAssetLibrary.load_blueprint_class('/Game/GHSNormalWarehouse/Camera/BP_GHS_WarehouseGameMode')
    native_controller = unreal.load_class(None, '/Script/Test.GHSWarehousePlayerController')
    assert pawn.get_class() == pawn_class
    assert pawn.get_editor_property('auto_possess_player') == unreal.AutoReceiveInput.PLAYER0
    settings = editor.get_editor_world().get_world_settings()
    assert settings.get_editor_property('default_game_mode') == game_mode_class
    defaults = unreal.get_default_object(game_mode_class)
    assert defaults.get_editor_property('default_pawn_class') == pawn_class
    assert defaults.get_editor_property('player_controller_class') == native_controller
    camera_configuration = {}
    for property_name, report_name in (('overview_pitch', 'pitch'), ('overview_yaw', 'yaw'),
                                       ('overview_distance', 'distance')):
        value = float(pawn.get_editor_property(property_name))
        assert abs(value-build['camera_overview'][report_name]) < .001, property_name
        camera_configuration[property_name] = value
    camera_configuration['overview_center'] = utility.xyz(pawn.get_editor_property('overview_center'))
    for value, expected in zip(camera_configuration['overview_center'],
                               build['before']['GHS_WarehouseCamera']['transform']['position']):
        assert abs(value-expected) < .001, 'Camera ground pivot changed'
    spring = pawn.get_editor_property('spring_arm_component')
    view = pawn.get_editor_property('warehouse_camera')
    assert view and view.get_attach_parent() == spring, 'Camera detached from plugin spring arm'
    center = pawn.get_actor_location()
    rotation = pawn.get_actor_rotation()
    forward = unreal.MathLibrary.get_forward_vector(rotation)
    distance = float(pawn.get_editor_property('overview_distance'))
    eye = unreal.Vector(center.x-forward.x*distance, center.y-forward.y*distance, center.z-forward.z*distance)
    actors.set_selected_level_actors([])
    editor.set_level_viewport_camera_info(eye, rotation)
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Inspection unexpectedly dirtied a map'
    assert utility.sha(target_file) == build['map_sha256']
    assert utility.sha(ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap') == ORIGINAL_HASH
    result.update(success=True, counts=counts, original_content_files_checked=len(originals),
                  original_content_changed=changed, source_map_sha256=ORIGINAL_HASH,
                  map_sha256=build['map_sha256'], geometry_transform_attachment_parity=True,
                  saved_state_matches_build_report=True, unique_stacker_ids=sorted(stacker_ids),
                  viewport_eye=utility.xyz(eye), editor_world=editor.get_editor_world().get_path_name(),
                  dirty_map_packages=[], camera_count=len(cameras), camera_configuration=camera_configuration,
                  game_mode=game_mode_class.get_path_name(), controller_class=native_controller.get_path_name(),
                  camera_transform_recalculation_permitted=True)
    unreal.log('GHS_ZCOOL_FINAL_EDITOR_VERIFIED '+json.dumps(counts))
except Exception:
    result['error'] = traceback.format_exc()
    unreal.log_error('GHS_ZCOOL_FINAL_EDITOR_FAILED '+result['error'])
    raise
finally:
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
