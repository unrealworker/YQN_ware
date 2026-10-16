"""Keep annotation colors neutral blue; UE Color positional fields are BGRA."""
import unreal,json
from pathlib import Path
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.load_level('/Game/Maps/GHS_CAD_NormalWarehouse')
labels=[]
for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    component=actor.get_component_by_class(unreal.TextRenderComponent)
    if component:
        component.set_text_render_color(unreal.Color(r=36,g=64,b=98,a=255))
        labels.append(actor.get_actor_label())
assert len(labels)==68
assert levels.save_current_level()
Path(r'D:\UEPro\Test\Saved\GHS_NormalLabelPolish.json').write_text(json.dumps(dict(success=True,count=len(labels),color_srgb=[36,64,98]),indent=2),encoding='utf-8')
