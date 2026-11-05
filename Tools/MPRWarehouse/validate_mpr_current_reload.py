"""Read-only disk reload validation for a dedicated UE process.

Execute this script in UE after importing/saving the transport revision. It
loads only the current B50B57 map and writes to cleanup_20261105/reload/. Add
-MPRCurrentValidationQuit to the dedicated process command line to quit after
the report is written. Never run that flag in the user's interactive editor.
No baseline, Content package, or historical cleanup report is overwritten.
"""
from pathlib import Path
import json
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import validate_mpr_current as current


def run(u=None, *, root=ROOT, reload_map=True, quit_editor=False):
    root=Path(root).resolve()
    report=root/current.OUTPUT/'reload/current_validation.json'
    result=dict(success=False,map=current.guard.MAP,assets_saved=False,maps_switched=False,
                reload_requested=reload_map,quit_requested=quit_editor,quit_performed=False)
    try:
        if u is None:import unreal as u
        current.require(not u.EditorLoadingAndSavingUtils.get_dirty_map_packages()
                        and not u.EditorLoadingAndSavingUtils.get_dirty_content_packages(),
                        'Reload validation requires an editor without unsaved packages')
        map_hash=current.sha(root/current.MAP_FILE)
        if reload_map:
            # Keep no UWorld/UObject from the previous world alive across load.
            levels=u.get_editor_subsystem(u.LevelEditorSubsystem)
            current.require(levels.load_level(current.guard.MAP), 'Cannot reload current saved map')
        result=current.run(u,root=root,report_path=report)
        result.update(reload_requested=reload_map,quit_requested=quit_editor,quit_performed=False,
                      maps_switched=reload_map)
        current.require(current.sha(root/current.MAP_FILE)==map_hash, 'Read-only reload changed map bytes')
    except Exception:
        result.update(success=False,error=traceback.format_exc())
    if quit_editor and u is not None:
        dirty=bool(u.EditorLoadingAndSavingUtils.get_dirty_map_packages()
                   or u.EditorLoadingAndSavingUtils.get_dirty_content_packages())
        result['quit_performed']=not dirty
        if dirty:result['quit_blocked']='Packages became dirty; editor kept open without saving.'
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('MPR_CURRENT_RELOAD',result['success'],str(report),flush=True)
    if result.get('error'):print(result['error'],flush=True)
    if result.get('quit_performed'):u.SystemLibrary.quit_editor()
    return result


if __name__=='__main__':
    import unreal as unreal_module
    run(unreal_module,quit_editor='-MPRCurrentValidationQuit' in unreal_module.SystemLibrary.get_command_line())
