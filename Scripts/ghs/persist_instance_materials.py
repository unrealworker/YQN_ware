"""Persist instancing support in GHS copies, preserving original style assets."""
import json
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test')
assets=unreal.EditorAssetLibrary
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
copies={};overrides=[]
for actor in actors.get_all_level_actors():
    c=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    if not c:continue
    names=[]
    for slot in range(c.get_num_materials()):
        source=c.get_material(slot)
        assert source
        if source.get_path_name().startswith('/Game/GHSDigitalTwin/Materials/Instanced/'):
            copy=source
        else:
            path='/Game/GHSDigitalTwin/Materials/Instanced/'+source.get_name().replace('M_VR_','M_GHS_')
            copy=assets.load_asset(path) if assets.does_asset_exist(path) else assets.duplicate_asset(source.get_path_name().split('.')[0],path)
            assert isinstance(copy,unreal.Material)
            copies[source.get_path_name()]=copy.get_path_name()
        if not copy.get_editor_property('used_with_instanced_static_meshes'):
            copy.set_editor_property('used_with_instanced_static_meshes',True)
            unreal.MaterialEditingLibrary.recompile_material(copy)
        assert assets.save_loaded_asset(copy,only_if_is_dirty=False)
        c.set_material(slot,copy)
        names.append(copy.get_path_name())
    overrides.append(dict(actor=actor.get_actor_label(),materials=names))
assert levels.save_current_level()
(root/'Saved/GHS_InstanceMaterials.json').write_text(json.dumps(dict(success=True,copies=copies,groups=overrides,original_material_files_modified=False),indent=2))
unreal.log('GHS_INSTANCE_MATERIALS_SAVED')
