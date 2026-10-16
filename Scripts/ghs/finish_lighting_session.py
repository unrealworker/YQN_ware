"""Restore the user's view, save the new lighting, and retire the local bridge."""
from pathlib import Path
root=Path(r'D:\UEPro\Test')
source=(root/'Scripts/ghs/finish_session.py').read_text()
source=source.replace("camera=next(a for a in actors.get_all_level_actors() if a.get_actor_label()=='CAM_GHS_Overview')\neditor.set_level_viewport_camera_info(camera.get_actor_location(),camera.get_actor_rotation())",
    "view=json.loads((Path(r'D:\\UEPro\\Test')/'Saved/GHS_LightingBefore.json').read_text())['viewport']\nr=view['rotation']\neditor.set_level_viewport_camera_info(unreal.Vector(*view['position_cm']),unreal.Rotator(pitch=r[0],yaw=r[1],roll=r[2]))")
source=source.replace("viewport='Overview'","viewport='LightingOverview'")
exec(compile(source,str(root/'Scripts/ghs/finish_session.py'),'exec'),globals())
