"""Read-only audit of road extensions, visibility and material bindings."""
import json
import runpy
from pathlib import Path
import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'Saved/RoadTerminalFade'
OUT.mkdir(parents=True, exist_ok=True)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert not levels.is_in_play_in_editor()
world = editor.get_editor_world()
assert world.get_path_name().split('.')[0] == '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
snap = runpy.run_path(str(ROOT / 'Scripts/ghs/validate_park_expansion.py'))['snapshot']
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
all_actors = actors.get_all_level_actors()
report = {'world': world.get_path_name(), 'count':len(all_actors), 'actors':{}, 'targets':{}, 'materials':{},
          'selected':[a.get_actor_label() for a in actors.get_selected_level_actors()],
          'dirty_maps':[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
          'dirty_content':[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]}
loc,rot = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
report['camera']={'location':[loc.x,loc.y,loc.z], 'rotation':[rot.pitch,rot.yaw,rot.roll]}
for a in all_actors:
    label=a.get_actor_label()
    report['actors'][label]=snap(a,unreal)
    if not (label.startswith('GHSContextTransition_') or label in ['GHSPark_ContextRoads','GHSPark_Curbs','GHSPark_Ground','GHN_StudioGround','GHSPark_Markings']): continue
    row={'hidden':a.get_editor_property('hidden'),'temporary_hidden':a.is_temporarily_hidden_in_editor(), 'components':[]}
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        comp={'visible':c.is_visible(), 'hidden_in_game':c.get_editor_property('hidden_in_game')}
        mesh=c.static_mesh
        if mesh:
            b=mesh.get_bounds()
            comp.update(mesh=mesh.get_path_name(),bounds_origin=[b.origin.x,b.origin.y,b.origin.z],bounds_extent=[b.box_extent.x,b.box_extent.y,b.box_extent.z])
        for i in range(c.get_num_materials()):
            m=c.get_material(i)
            if not m or m.get_path_name() in report['materials']: continue
            data={'class':m.get_class().get_name()}
            if isinstance(m,unreal.Material):
                data['base']=str(unreal.MaterialEditingLibrary.get_material_property_input_node(m,unreal.MaterialProperty.MP_BASE_COLOR))
                data['vectors']={}
                for n in unreal.MaterialEditingLibrary.get_vector_parameter_names(m):
                    v=unreal.MaterialEditingLibrary.get_material_default_vector_parameter_value(m,n)
                    data['vectors'][str(n)]=[v.r,v.g,v.b,v.a]
            report['materials'][m.get_path_name()]=data
        row['components'].append(comp)
    report['targets'][label]=row
(OUT/'inspection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
unreal.log('GHS_ROAD_TERMINAL_INSPECTED '+str(len(report['targets'])))
