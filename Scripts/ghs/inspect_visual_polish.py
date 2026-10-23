"""Read the current live scene; never saves or modifies an Unreal object."""
import json
from pathlib import Path
import runpy
import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'Saved/VisualPolish'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
assert not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()
assert unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name().split('.')[0] == MAP
snapshot = runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']

def values(obj, names):
    out = {}
    for name in names:
        try:
            value = obj.get_editor_property(name)
            if isinstance(value, (str, int, float, bool, type(None))): out[name] = value
            elif hasattr(value, 'r'): out[name] = [value.r, value.g, value.b, value.a]
            else: out[name] = str(value)
        except Exception as error: out[name] = {'unavailable': str(error)}
    return out

report = {'map': MAP, 'actors': [], 'lights': [], 'post_process': [], 'materials': {}}
for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    row = snapshot(actor, unreal)
    report['actors'].append(row)
    for cls, kind, names in [
        (unreal.DirectionalLightComponent, 'directional', ['intensity','light_color','light_source_angle','contact_shadow_length','shadow_bias','shadow_slope_bias','cast_shadows']),
        (unreal.SkyLightComponent, 'sky', ['intensity','light_color','lower_hemisphere_is_black','lower_hemisphere_color','cast_shadows','source_type','real_time_capture'])]:
        component = actor.get_component_by_class(cls)
        if component:
            rotation = actor.get_actor_rotation()
            report['lights'].append({'label': actor.get_actor_label(), 'kind': kind, 'rotation': [rotation.pitch,rotation.yaw,rotation.roll], 'values': values(component,names)})
    if isinstance(actor, unreal.PostProcessVolume):
        report['post_process'].append({'label': actor.get_actor_label(), 'values': values(actor.get_editor_property('settings'), ['dynamic_global_illumination_method','reflection_method','auto_exposure_method','auto_exposure_min_brightness','auto_exposure_max_brightness','auto_exposure_bias','ambient_occlusion_intensity','ambient_occlusion_radius','ambient_occlusion_quality','bloom_intensity'])})
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        for i in range(component.get_num_materials()):
            mat = component.get_material(i)
            if not mat or mat.get_path_name() in report['materials']: continue
            if not (actor.get_actor_label().startswith('GHSPark_') or actor.get_actor_label() in ['GHN_StudioGround','GHS_MainWarehouseRoof','GHS_CAD_WallFaces','GHS_CAD_WallEdges','GHS_CAD_WallSections']): continue
            entry = {'class': mat.get_class().get_path_name()}
            if isinstance(mat, unreal.Material):
                entry.update(values(mat, ['blend_mode','shading_model','used_with_instanced_static_meshes','used_with_nanite']))
                entry['expressions'] = unreal.MaterialEditingLibrary.get_num_material_expressions(mat)
                entry['vector_parameters'] = [str(n) for n in unreal.MaterialEditingLibrary.get_vector_parameter_names(mat)]
                entry['scalar_parameters'] = [str(n) for n in unreal.MaterialEditingLibrary.get_scalar_parameter_names(mat)]
            report['materials'][mat.get_path_name()] = entry
report['actors'].sort(key=lambda row: row['label'])
report['dirty_content'] = [p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
report['dirty_maps'] = [p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
OUT.mkdir(parents=True, exist_ok=True)
(OUT/'inspection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
unreal.log('GHS_VISUAL_POLISH_INSPECTED')
