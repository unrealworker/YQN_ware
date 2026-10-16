"""Install the camera only into the Normal warehouse; preserve existing actors."""
import hashlib
import json
import sys
import traceback
from pathlib import Path
import unreal

ROOT = Path(r'D:\UEPro\Test')
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
from sync_wall_heights import snapshot

MAP = '/Game/Maps/GHS_CAD_NormalWarehouse'
DEST = '/Game/GHSNormalWarehouse/Camera'
REPORT = ROOT / 'Saved/GHS_WarehouseCameraSetup.json'
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
lib = unreal.EditorAssetLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

def hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / 'Content').rglob('*') if p.is_file()}

def blueprint(name, parent):
    path = DEST + '/' + name
    if lib.does_asset_exist(path):
        bp = lib.load_asset(path)
    else:
        factory = unreal.BlueprintFactory()
        factory.set_editor_property('parent_class', parent)
        bp = asset_tools.create_asset(name, DEST, unreal.Blueprint, factory)
    assert bp
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    cls = lib.load_blueprint_class(path)
    assert unreal.MathLibrary.class_is_child_of(cls, parent)
    return bp, cls

def main():
    assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
    result = dict(success=False, map=MAP)
    before_hashes = hashes()
    try:
        assert levels.load_level(MAP)
        labels = {a.get_actor_label(): a for a in actors.get_all_level_actors()}
        checkpoint = json.loads((ROOT / 'Saved/GHS_WarehouseCameraCheckpoint.json').read_text())
        baseline = json.loads(Path(checkpoint['backup_root'], 'live_before.json').read_text())
        current = snapshot({k: v for k, v in labels.items() if k != 'GHS_WarehouseCamera'})
        assert current == baseline, 'Original scene differs from saved pre-restart checkpoint'
        native_pawn = unreal.load_class(None, '/Script/Test.GHSWarehouseCameraPawn')
        native_gm = unreal.load_class(None, '/Script/Test.GHSWarehouseGameMode')
        native_pc = unreal.load_class(None, '/Script/Test.GHSWarehousePlayerController')
        assert native_pawn and native_gm and native_pc
        pawn_bp, pawn_class = blueprint('BP_GHS_WarehouseCamera', native_pawn)
        gm_bp, gm_class = blueprint('BP_GHS_WarehouseGameMode', native_gm)
        gm = unreal.get_default_object(gm_class)
        gm.set_editor_property('default_pawn_class', pawn_class)
        gm.set_editor_property('player_controller_class', native_pc)
        unreal.BlueprintEditorLibrary.compile_blueprint(gm_bp)
        gm_class = lib.load_blueprint_class(DEST + '/BP_GHS_WarehouseGameMode')
        assert unreal.get_default_object(gm_class).get_editor_property('default_pawn_class') == pawn_class
        world = editor.get_editor_world()
        world.get_world_settings().set_editor_property('default_game_mode', gm_class)
        pawn = labels.get('GHS_WarehouseCamera')
        if not pawn:
            pawn = actors.spawn_actor_from_class(pawn_class, unreal.Vector(-646.665, 833.981, 250.0))
        assert unreal.MathLibrary.class_is_child_of(pawn.get_class(), native_pawn)
        pawn.set_actor_label('GHS_WarehouseCamera')
        pawn.set_folder_path('GHS_Normal/Camera')
        pawn.set_editor_property('auto_possess_player', unreal.AutoReceiveInput.PLAYER0)
        pawn.set_editor_property('tags', [unreal.Name('GHS_WarehouseCamera')])
        pawn.reset_overview(True)
        assert lib.save_loaded_asset(pawn_bp, only_if_is_dirty=False)
        assert lib.save_loaded_asset(gm_bp, only_if_is_dirty=False)
        assert levels.save_current_level()
        after_labels = {a.get_actor_label(): a for a in actors.get_all_level_actors()}
        preserved = snapshot({k: v for k, v in after_labels.items() if k != 'GHS_WarehouseCamera'})
        assert preserved == baseline, 'An original actor was modified'
        after_hashes = hashes()
        changed = sorted(p for p in set(before_hashes) | set(after_hashes)
                         if before_hashes.get(p) != after_hashes.get(p))
        allowed = {'Content/Maps/GHS_CAD_NormalWarehouse.umap',
                   'Content/GHSNormalWarehouse/Camera/BP_GHS_WarehouseCamera.uasset',
                   'Content/GHSNormalWarehouse/Camera/BP_GHS_WarehouseGameMode.uasset'}
        assert set(changed) <= allowed, changed
        result.update(success=True, preserved_actor_count=len(baseline), actor_count=len(after_labels),
                      blueprint_pawn=pawn_class.get_path_name(), blueprint_game_mode=gm_class.get_path_name(),
                      modified_content=changed, existing_actors_unchanged=True,
                      content_hashes_after=after_hashes)
    except Exception:
        result['error'] = traceback.format_exc()
        raise
    finally:
        REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    unreal.log('WAREHOUSE_CAMERA_SETUP_SUCCESS')

if __name__ == '__main__':
    main()
