from pathlib import Path
import sys,importlib,json
import unreal
root=Path(r'D:\UEPro\Test');sys.path.insert(0,str(root/'Scripts/ghs'))
import uniform_lighting
importlib.reload(uniform_lighting)
settings=uniform_lighting.configure()
assert unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
(root/'Saved/GHS_PresentationLighting.json').write_text(json.dumps(dict(success=True,settings=settings),indent=2))
