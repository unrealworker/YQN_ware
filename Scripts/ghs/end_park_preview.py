"""End PIE before an authorised campus reimport; never close or save the editor."""
import json
from pathlib import Path
import unreal

levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
was_playing=levels.is_in_play_in_editor()
if was_playing:
    levels.editor_request_end_play()
(Path('D:/UEPro/Test/Saved/ParkPolish')/'preview_stop.json').write_text(
    json.dumps(dict(was_playing=was_playing,end_play_requested=was_playing)),encoding='utf-8')
