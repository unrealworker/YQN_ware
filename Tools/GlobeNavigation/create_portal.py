"""Author only the lightweight warehouse portal map in an isolated UE editor.

Run with UnrealEditor-Cmd -ExecutePythonScript=<this file>. Existing maps are
never loaded or resaved. Re-running validates the existing portal, not replaces it.
"""
import json
from pathlib import Path
import unreal as u

MAP = '/Game/Maps/GHS_WarehousePortal'
editor = u.get_editor_subsystem(u.LevelEditorSubsystem)
assets = u.EditorAssetLibrary
game_mode = u.load_class(None, '/Script/Test.GHSGlobeGameMode')
if not game_mode:
    raise RuntimeError('Warehouse portal controller must be compiled first')
exists = assets.does_asset_exist(MAP)
if not (editor.load_level(MAP) if exists else editor.new_level(MAP)):
    raise RuntimeError('Cannot open warehouse portal map')
world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
settings = world.get_world_settings()
if exists:
    if settings.get_editor_property('default_game_mode') != game_mode:
        raise RuntimeError('Existing portal has a different game mode; leave it unchanged')
else:
    settings.set_editor_property('default_game_mode', game_mode)
    if not editor.save_current_level():
        raise RuntimeError('Portal map save failed')
actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
if any(a.actor_has_tag('GHS_GlobeRoot') for a in actors):
    raise RuntimeError('Portal must not contain a globe')
report = Path(u.Paths.project_saved_dir()) / 'PortalValidation/map.json'
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps({'map': MAP, 'gameMode': game_mode.get_path_name(),
                              'actors': len(actors), 'created': not exists}, indent=2), encoding='utf-8')
u.log('WAREHOUSE_PORTAL_MAP_READY ' + MAP)
