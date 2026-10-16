"""Apply verified import corrections in the open editor, preserving the map layout."""
from pathlib import Path
import unreal
script = Path(r"D:\UEPro\Test\Scripts\build_logistics_warehouse.py").read_text(encoding="utf-8")
exec(compile(script.split("\ntry:\n    import_assets()")[0], "build_logistics_warehouse.py", "exec"),globals())
import_assets()
registry_path = SOURCE / "twin_asset_registry.json"
registry = json.loads(registry_path.read_text(encoding="utf-8"))
by_label = {a.get_actor_label():a for a in actors.get_all_level_actors()}
for record in registry:
    a = by_label[record["id"]]
    yaw = record.get("yaw",90 if a.get_component_by_class(unreal.TextRenderComponent) else 0)
    a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=yaw,roll=0),False)
    if record["id"] == "WH01_FloorCollision":
        a.set_actor_location(unreal.Vector(-2000,-1000,109),False,False)
        record["position_m"]=[-20,-10,1.09]
sun = by_label["Sun_LateAfternoon"]
sun.set_actor_rotation(unreal.Rotator(pitch=-38,yaw=-32,roll=0),False)
sun.get_component_by_class(unreal.DirectionalLightComponent).set_intensity(60000)
for a in actors.get_all_level_actors():
    if isinstance(a,unreal.PlayerStart):
        a.set_actor_rotation(unreal.Rotator(pitch=-5,yaw=-62,roll=0),False)
registry_path.write_text(json.dumps(registry,indent=2),encoding="utf-8")
assert levels.save_current_level()
exec(compile((ROOT / "Scripts/verify_warehouse_editor.py").read_text(encoding="utf-8"), "verify_warehouse_editor.py", "exec"),globals())
