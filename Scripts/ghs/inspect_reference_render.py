import json
from pathlib import Path
import unreal
root=Path('D:/UEPro/Test')
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
names=['r.AntiAliasingMethod','r.ScreenPercentage','r.TemporalAA.Quality','r.TSR.History.SampleCount',
       'r.Shadow.Virtual.NormalBias','r.Shadow.Virtual.SMRT.RayCountDirectional','r.Shadow.Virtual.SMRT.SamplesPerRayDirectional',
       'ShowFlag.PostProcessing','ShowFlag.AntiAliasing','ShowFlag.TemporalAA','r.HighResScreenshotDelay']
data={name:unreal.SystemLibrary.get_console_variable_float_value(name) for name in names}
data['pie']=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()
(root/'Saved/ParkReferenceStyle/render_state.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
