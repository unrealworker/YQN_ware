"""End editor play preview before applying the authorized scene adjustments."""
import unreal
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if levels.is_in_play_in_editor():
    levels.editor_request_end_play()
unreal.log('GHS_VISUAL_POLISH_PREVIEW_END_REQUESTED')
