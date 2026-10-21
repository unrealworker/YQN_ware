"""Read-only verification of the reopened editor; safe as the dispatcher's last request."""
import json
import os
from pathlib import Path
import unreal

editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
eye,rotation=editor.get_level_viewport_camera_info()
world=editor.get_editor_world()
result=dict(success=world is not None,pid=os.getpid(),map=world.get_path_name() if world else None,
    dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
    eye=[eye.x,eye.y,eye.z],rotation=[rotation.pitch,rotation.yaw,rotation.roll])
Path('D:/UEPro/Test/Saved/RoundedHUD/editor_verified.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
