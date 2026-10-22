"""Fresh saved-map validation for independent roof, style and preservation."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import runpy
import traceback
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/ParkRoofStyle'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
ROOF_LABEL='GHS_MainWarehouseRoof'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def close(a,b):assert abs(float(a)-float(b))<1e-4,(a,b)
report=dict(success=False,map=MAP)
try:
    assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assert levels.load_level(MAP)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    by={a.get_actor_label():a for a in actors}
    baseline=read(OUT/'Before/scene_state.json')
    helper=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))
    helper['main']()
    rows=[helper['snapshot'](a,unreal) for a in actors if a.get_actor_label()!=ROOF_LABEL]
    errors=helper['compare_preservation'](baseline['actors'],rows,True)
    assert not errors,errors
    assert len(actors)==len(baseline['actors'])+1 and len(by)==len(actors)
    # Camera transforms are preserved as well; the older generic comparator
    # allows an overview change, which this style operation does not need.
    before_by={r['label']:r for r in baseline['actors']}
    for row in rows: assert row['transform']==before_by[row['label']]['transform'],row['label']
    roof=by[ROOF_LABEL];spec=read(ROOT/'SourceAssets/GHS/MainRoof/roof_manifest.json')
    assert isinstance(roof,unreal.StaticMeshActor)
    assert set(str(t) for t in roof.tags)=={'GHS_WarehouseRoof','RemovableRoof','GHS_ArchitecturalContext'}
    assert not roof.get_actor_enable_collision() and not roof.is_actor_tick_enabled()
    assert not roof.get_editor_property('hidden')
    components=roof.get_components_by_class(unreal.StaticMeshComponent)
    assert len(components)==1
    component=components[0];mesh=component.static_mesh
    assert mesh.get_name()==spec['mesh']['name']
    assert component.get_collision_enabled()==unreal.CollisionEnabled.NO_COLLISION
    assert component.get_editor_property('mobility')==unreal.ComponentMobility.STATIC
    assert component.get_num_materials()==len(spec['mesh']['material_roles'])
    ml=unreal.MaterialEditingLibrary
    for i,role in enumerate(spec['mesh']['material_roles']):
        mat=component.get_material(i)
        assert mat.get_path_name()==f'/Game/GHSZcoolSmartFactory/Roof/Materials/M_GHSRoof_{role}.M_GHSRoof_{role}'
        value=ml.get_material_default_vector_parameter_value(mat,'SurfaceTint')
        for actual,expected in zip([value.r,value.g,value.b],spec['materials'][role]['color_linear']):close(actual,expected)
        for name,expected in [('Roughness',spec['materials'][role]['roughness']),
                              ('Metallic',spec['materials'][role]['metallic']),('Specular',.15)]:
            close(ml.get_material_default_scalar_parameter_value(mat,name),expected)
    bounds=mesh.get_bounds()
    for key,vec in [('min',bounds.origin-bounds.box_extent),('max',bounds.origin+bounds.box_extent)]:
        assert max(abs(a-b) for a,b in zip((vec.x,vec.y,vec.z),spec['mesh']['bounds_ue_cm'][key]))<2
    roof.set_actor_hidden_in_game(True);assert roof.get_editor_property('hidden')
    roof.set_actor_hidden_in_game(False);assert not roof.get_editor_property('hidden')
    style=read(ROOT/'SourceAssets/GHS/Park/presentation_style.json')
    manifest=read(ROOT/'SourceAssets/GHS/Park/park_manifest.json')
    for role in style['smooth_mesh_roles']:
        mat=unreal.load_asset('/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_'+role)
        value=ml.get_material_default_vector_parameter_value(mat,'SurfaceTint')
        for actual,expected in zip([value.r,value.g,value.b],manifest['materials'][role]):close(actual,expected)
        close(ml.get_material_default_scalar_parameter_value(mat,'Roughness'),style['tree_roughness'])
        close(ml.get_material_default_scalar_parameter_value(mat,'Specular'),style['tree_specular'])
    for record in baseline['lights']:
        actor=by[record['label']]
        cls=unreal.DirectionalLightComponent if record['kind']=='directional' else unreal.SkyLightComponent
        light=actor.get_component_by_class(cls)
        close(light.get_editor_property('intensity'),record['values']['intensity'])
        if record['kind']=='directional':close(light.get_editor_property('light_source_angle'),style['directional_source_angle'])
    for record in baseline['post_process']:
        settings=by[record['label']].get_editor_property('settings')
        for key,old in record['values'].items():
            expected=style['ambient_occlusion_intensity'] if key=='ambient_occlusion_intensity' else style['ambient_occlusion_radius_cm'] if key=='ambient_occlusion_radius' else old
            close(settings.get_editor_property(key),expected)
    source=read(ROOT/'Saved/ParkExpansion/source_map_baseline.json')
    assert sha(Path(source['path']))==source['sha256']
    assert read(ROOT/'SourceAssets/GHS/Park/site_geometry_report.json')==read(OUT/'Before/site_geometry_report.json')
    report.update(success=True,preserved_existing_actors=len(rows),total_actor_count=len(actors),
        roof_one_actor_one_mesh=True,roof_visibility_toggle_passed=True,
        roof_triangles=spec['mesh']['triangles'],material_parameters_verified=True,
        tree_geometry_and_placements_unchanged=True,original_source_map_preserved=True,
        map_sha256=sha(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'),
        roof_manifest_sha256=sha(ROOT/'SourceAssets/GHS/MainRoof/roof_manifest.json'),
        park_manifest_sha256=sha(ROOT/'SourceAssets/GHS/Park/park_manifest.json'))
except Exception:
    report['error']=traceback.format_exc();unreal.log_error(report['error'])
report['finished_utc']=datetime.now(timezone.utc).isoformat()
(OUT/'saved_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert report['success'],report.get('error')
unreal.log('GHS_ROOF_STYLE_SAVED_VALIDATION_COMPLETE')
