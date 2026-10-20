"""Normally exit only the clean hidden restored editor so it can be shown."""
import os
import unreal
assert os.getpid() == 40584, 'Wrong editor process'
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert not levels.is_in_play_in_editor(), 'PIE must be stopped'
assert editor.get_editor_world().get_path_name().split('.')[0] == '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Do not discard dirty maps'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages(), 'Do not discard dirty assets'
unreal.log('GHS_TWIN_CLEAN_HIDDEN_EDITOR_NORMAL_EXIT')
unreal.SystemLibrary.quit_editor()
