"""Verify the saved logistics map and capture actual Unreal Editor renders."""
import json
import time
import traceback
from pathlib import Path
from collections import Counter
import unreal

ROOT = Path(r"D:\UEPro\Test")
MAP = "/Game/Maps/LogisticsWarehouse"
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.load_level(MAP)
all_actors = actors.get_all_level_actors()
by_label = {a.get_actor_label(): a for a in all_actors}
required = ["WH01_MainWarehouse", "WH01_RemovableRoof", "OFF01_OperationsOffice",
            "Truck_Apron", "GATE01_Guardhouse", "Road_Entrance", "Sun_LateAfternoon",
            "CAM_Overview", "CAM_Loading", "CAM_Gate", "CAM_Interior"]
assert all(name in by_label for name in required)
assert sum(name.startswith("DockLabel") for name in by_label) == 10
assert sum(name.startswith("RACK_") for name in by_label) == 64
meshes = []
missing = []
for a in all_actors:
    c = a.get_component_by_class(unreal.StaticMeshComponent)
    if not c:
        continue
    meshes.append(a)
    if not c.static_mesh or any(c.get_material(i) is None or "WorldGridMaterial" in c.get_material(i).get_path_name() for i in range(c.get_num_materials())):
        missing.append(a.get_actor_label())
assert not missing, missing
registry = json.loads((ROOT / "SourceAssets/LogisticsWarehouse/twin_asset_registry.json").read_text())
assert len({r["id"] for r in registry}) == len(registry), "Duplicate twin identifiers"
assert all(r["id"] in by_label for r in registry), "Registry does not match saved map"
for r in registry:
    rotation = by_label[r["id"]].get_actor_rotation()
    assert abs(rotation.pitch) < .01 and abs(rotation.roll) < .01, r["id"]
report = dict(success=True, map=MAP, actor_count=len(all_actors), static_mesh_actors=len(meshes),
              dock_count=10, rack_count=64, registry_count=len(registry), missing_materials=missing,
              tree_count=sum("TREE_" in n for n in by_label),
              categories=dict(Counter(r["category"].split("/")[0] for r in registry)),
              live_telemetry_connected=False, screenshots_complete=False)
report_path = ROOT / "Saved/Warehouse_Verification.json"
report_path.write_text(json.dumps(report,indent=2), encoding="utf-8")

wh_views = ["Overview", "Loading", "Gate", "Interior"]
wh_index = 0
wh_started = time.monotonic()
wh_task = None
wh_busy = False
wh_done = False

def wh_tick(delta):
    global wh_index, wh_started, wh_task, wh_busy, wh_done, wh_handle
    if wh_busy or wh_done:
        return
    wh_busy = True
    try:
        if time.monotonic() - wh_started < 8:
            return
        if wh_task is not None and not wh_task.is_task_done():
            return
        if wh_index >= len(wh_views):
            wh_done = True
            cam = by_label["CAM_Overview"]
            unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(cam.get_actor_location(),cam.get_actor_rotation())
            actors.set_selected_level_actors([])
            assert levels.save_current_level()
            report["screenshots_complete"] = True
            report["screenshots"] = [str(ROOT / ("Saved/Warehouse_UE_"+v+".png")) for v in wh_views]
            report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
            unreal.unregister_slate_post_tick_callback(wh_handle)
            unreal.log("WAREHOUSE_VISUAL_VERIFICATION_COMPLETE")
            return
        view = wh_views[wh_index]
        camera = by_label["CAM_" + view]
        wh_index += 1
        wh_task = unreal.AutomationLibrary.take_high_res_screenshot(1920,1080,
            str(ROOT / ("Saved/Warehouse_UE_"+view+".png")),camera=camera,delay=3.0)
        wh_started = time.monotonic()
    except Exception:
        wh_done = True
        report["capture_error"] = traceback.format_exc()
        report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
        unreal.log_error(traceback.format_exc())
        unreal.unregister_slate_post_tick_callback(wh_handle)
    finally:
        wh_busy = False

wh_handle = unreal.register_slate_post_tick_callback(wh_tick)
unreal.log("WAREHOUSE_SAVED_ASSETS_VERIFIED")
