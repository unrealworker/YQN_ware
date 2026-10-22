"""Restore the rendering-only diagnostic overrides; keep the selected style."""
import json
from pathlib import Path
import unreal
root=Path('D:/UEPro/Test')
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert not levels.is_in_play_in_editor()
world=editor.get_editor_world()
before=json.loads((root/'Saved/ParkReferenceStyle/render_state.json').read_text(encoding='utf-8'))
names=['r.HighResScreenshotDelay','ShowFlag.PostProcessing','ShowFlag.AntiAliasing','ShowFlag.TemporalAA','r.Shadow.Virtual.NormalBias']
for name in names:unreal.SystemLibrary.execute_console_command(world,name+' '+str(before[name]))
unreal.SystemLibrary.execute_console_command(world,'r.Shadow.Virtual.ScreenRayLength 0.015')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
light=next(a.get_component_by_class(unreal.DirectionalLightComponent) for a in actors if a.get_actor_label()=='GHS_CoolOverheadKey')
baseline=json.loads((root/'Saved/ParkReferenceStyle/Before/scene_state.json').read_text(encoding='utf-8'))
expected=next(r for r in baseline['lights'] if r['kind']=='directional')['values']['contact_shadow_length']
light.set_editor_property('contact_shadow_length',expected)
actual={name:unreal.SystemLibrary.get_console_variable_float_value(name) for name in names}
for name in names:assert abs(actual[name]-before[name])<1e-5
assert abs(unreal.SystemLibrary.get_console_variable_float_value('r.Shadow.Virtual.ScreenRayLength')-.015)<1e-5
assert levels.save_current_level()
(root/'Saved/ParkReferenceStyle/render_probe_restoration.json').write_text(json.dumps(dict(success=True,restored=actual,contact_shadow_length=expected),indent=2),encoding='utf-8')
