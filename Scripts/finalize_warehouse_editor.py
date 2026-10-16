from pathlib import Path
import unreal
root=Path(r"D:\UEPro\Test")
exec(compile((root/"Scripts/persist_warehouse_materials.py").read_text(encoding="utf-8"),"persist_warehouse_materials.py","exec"),globals())
aa=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in aa.get_all_level_actors():
    if a.get_actor_label()=="WH01_RemovableRoof":
        a.set_editor_property("tags",["LogisticsWarehouse","TwinId=WH01_RemovableRoof","RemovableRoof"])
    if a.get_actor_label()=="PP_NaturalExposure":
        settings=a.get_editor_property("settings")
        settings.set_editor_property("auto_exposure_bias",.5)
        a.set_editor_property("settings",settings)
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
exec(compile((root/"Scripts/verify_warehouse_editor.py").read_text(encoding="utf-8"),"verify_warehouse_editor.py","exec"),globals())
