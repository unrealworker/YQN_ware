"""Record current scene/camera state for the native middle-click acceptance."""
import json
from pathlib import Path
import unreal
result=dict(game_found=False)
for world in unreal.ObjectIterator(unreal.World):
    pc=unreal.GameplayStatics.get_player_controller(world,0)
    if not pc or not hasattr(pc,'twin_hud_widget'): continue
    widget=pc.get_editor_property('twin_hud_widget')
    if not widget: continue
    pawn=pc.get_controlled_pawn()
    p=pawn.get_actor_location(); overview=pawn.get_editor_property('overview_center')
    arm=pawn.get_editor_property('spring_arm_component')
    camera=pawn.get_editor_property('warehouse_camera')
    rotation=camera.get_world_rotation()
    result=dict(game_found=True,world=world.get_path_name(),selected=widget.get_editor_property('selected_id'),
        pivot=[p.x,p.y,p.z],overview=[overview.x,overview.y,overview.z],
        transitioning=pawn.is_pose_transition_active(),object_pivot=pawn.uses_object_pivot(),
        zoom=arm.get_editor_property('target_arm_length'),overview_distance=pawn.get_editor_property('overview_distance'),
        rotation=[rotation.pitch,rotation.yaw,rotation.roll],
        scene_controls=[widget.get_scene_controls_position().x,widget.get_scene_controls_position().y],
        poi=json.loads(widget.get_poi_report()))
    break
Path('D:/UEPro/Test/Saved/SceneRefinements/live_probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
