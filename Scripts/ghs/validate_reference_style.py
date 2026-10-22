"""Read-only fresh-load validation of the reference campus presentation.

Run with UE -run=pythonscript, normally -NullRHI. The current 360-actor baseline
is authoritative, including all camera transforms and the user's ground scale.
Only two component material bindings and the key light rotation may differ.
No actor, material, map, or older validation report is saved by this script.
"""
from datetime import datetime,timezone
from pathlib import Path
from collections import Counter
import copy
import hashlib
import json
import math
import runpy
import traceback

import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/ParkReferenceStyle'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
MAP_FILE=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
PARK_MANIFEST=ROOT/'SourceAssets/GHS/Park/park_manifest.json'
ROOF_MANIFEST=ROOT/'SourceAssets/GHS/MainRoof/roof_manifest.json'
ROOF_LABEL='GHS_MainWarehouseRoof'
MATINEE='/Engine/EditorMeshes/MatineeCam_SM.MatineeCam_SM'
CHANGED_GEOMETRY={'Landscape','Trees','TreesLight','TreesDark','Trunk'}


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def close(a,b,tolerance=1e-4):assert abs(float(a)-float(b))<tolerance,(a,b)
def xyz(v):return [float(v.x),float(v.y),float(v.z)]
def finite(values):return all(math.isfinite(float(v)) for v in values)


def material_check(path,color,roughness,metallic,specular=.15):
    material=unreal.load_asset(path)
    assert isinstance(material,unreal.Material),path
    ml=unreal.MaterialEditingLibrary
    tint=ml.get_material_default_vector_parameter_value(material,'SurfaceTint')
    for actual,expected in zip((tint.r,tint.g,tint.b),color):close(actual,expected)
    scalars={}
    for name,expected in [('Roughness',roughness),('Metallic',metallic),('Specular',specular)]:
        actual=ml.get_material_default_scalar_parameter_value(material,name)
        close(actual,expected);scalars[name]=actual
    assert ml.get_num_material_expressions(material)==4,(path,'Unexpected extra/grid expressions')
    assert material.get_editor_property('blend_mode')==unreal.BlendMode.BLEND_OPAQUE
    assert material.get_editor_property('shading_model')==unreal.MaterialShadingModel.MSM_DEFAULT_LIT
    return dict(path=material.get_path_name(),color_linear=[tint.r,tint.g,tint.b],
                scalars=scalars,expressions=4,opaque=True,default_lit=True)


def light_color_check(component,linear):
    # Light components store an 8-bit sRGB Color after set_light_color. Compare
    # at that precision rather than treating these bytes as linear channels.
    color=component.get_editor_property('light_color')
    expected=[round((12.92*v if v<=.0031308 else 1.055*(v**(1/2.4))-.055)*255) for v in linear]
    actual=[color.r,color.g,color.b]
    assert all(abs(a-b)<=1 for a,b in zip(actual,expected)),(actual,expected)
    return actual


def mesh_bounds_check(mesh,spec):
    bounds=mesh.get_bounds()
    result=dict(min=xyz(bounds.origin-bounds.box_extent),max=xyz(bounds.origin+bounds.box_extent))
    for key in ('min','max'):
        assert max(abs(a-b) for a,b in zip(result[key],spec['bounds_ue_cm'][key]))<2.,(mesh.get_name(),key,result[key],spec['bounds_ue_cm'][key])
    return result


report=dict(success=False,map=MAP,stage='initialization',materials_checked=[])
OUT.mkdir(parents=True,exist_ok=True)
try:
    assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
    disk_hash_before=sha(MAP_FILE)
    baseline=read(OUT/'Before/scene_state.json')
    style=read(ROOT/'SourceAssets/GHS/Park/reference_style.json')
    before_manifest=read(OUT/'Before/park_manifest.json')
    manifest=read(PARK_MANIFEST)
    roof_spec=read(ROOF_MANIFEST)
    site=read(ROOT/'SourceAssets/GHS/Park/site_geometry_report.json')
    roughness=runpy.run_path(str(ROOT/'Scripts/ghs/reference_style_materials.py'))['ROUGHNESS']
    helper=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assert levels.load_level(MAP)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    by={a.get_actor_label():a for a in actors}
    assert len(actors)==len(by)==len(baseline['actors'])==360
    rows=[helper['snapshot'](a,unreal) for a in actors]
    current={row['label']:row for row in rows}
    old={row['label']:row for row in baseline['actors']}
    assert set(current)==set(old),'Actor additions/removals are not allowed'
    (OUT/'reloaded_actors.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    key_labels=[item['label'] for item in baseline['lights'] if item['kind']=='directional']
    sky_labels=[item['label'] for item in baseline['lights'] if item['kind']=='sky']
    assert len(key_labels)==len(sky_labels)==1
    key_actor=by[key_labels[0]]
    actual_rotation=key_actor.get_actor_rotation()
    for actual,expected in zip((actual_rotation.pitch,actual_rotation.yaw,actual_rotation.roll),style['lighting']['directional_rotation']):
        close((actual-expected+180)%360-180,0.)
    bindings={'GHSPark_Ground':style['ground_material'],'GHN_StudioGround':style['studio_ground_material']}
    report['stage']='actor preservation'
    for label,original in old.items():
        expected=copy.deepcopy(original)
        actual=copy.deepcopy(current[label])
        # Light orientation is the sole permitted actor-transform change and
        # has been checked against the requested rotator immediately above.
        if label==key_labels[0]:expected['transform']['rotation']=actual['transform']['rotation']
        if label in bindings:
            assert len(expected['components'])==len(actual['components'])==1,label
            assert len(expected['components'][0]['materials'])==1,label
            expected['components'][0]['materials']=[bindings[label]]
        if expected['actor_class']=='/Script/Engine.CameraActor' or label=='GHS_WarehouseCamera':
            present={component['name'] for component in actual['components']}
            expected['components']=[component for component in expected['components']
                if component['name'] in present or component['mesh']!=MATINEE]
        for row in (expected,actual):row['components'].sort(key=lambda c:c['name'])
        # Camera actor transforms and any present preview component are still
        # compared. Only genuinely absent Matinee editor meshes are ignored.
        assert expected==actual,(label,'Actor, component, transform, material, tags or instances changed')
    assert current['GHSPark_Ground']['transform']['position']==[170.,240.,0.]
    assert current['GHSPark_Ground']['transform']==old['GHSPark_Ground']['transform']
    report['ground_transform_preserved']=current['GHSPark_Ground']['transform']

    report['stage']='material defaults'
    for role,color in style['palette'].items():
        report['materials_checked'].append(material_check('/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_'+role,
            color,roughness[role],0.))
        assert manifest['materials'][role]==color,(role,'Manifest palette is stale')
    report['materials_checked'].append(material_check('/Game/GHSZcoolSmartFactory/Presentation/M_GHSReference_Backdrop',
        style['palette']['Ground'],.9,0.))
    for role in roof_spec['mesh']['material_roles']:
        values=roof_spec['materials'][role]
        color=style['roof_color_linear'] if role=='Roof' else values['color_linear']
        report['materials_checked'].append(material_check('/Game/GHSZcoolSmartFactory/Roof/Materials/M_GHSRoof_'+role,
            color,values['roughness'],values['metallic']))
    for label,path in bindings.items():
        assert by[label].get_component_by_class(unreal.StaticMeshComponent).get_material(0).get_path_name()==path

    report['stage']='roof and park assets'
    roof=by[ROOF_LABEL]
    assert isinstance(roof,unreal.StaticMeshActor)
    assert set(str(t) for t in roof.tags)=={'GHS_WarehouseRoof','RemovableRoof','GHS_ArchitecturalContext'}
    assert not roof.get_actor_enable_collision() and not roof.is_actor_tick_enabled()
    assert not roof.get_editor_property('hidden'),'Roof must be visible by default'
    components=roof.get_components_by_class(unreal.StaticMeshComponent)
    assert len(components)==1
    component=components[0]
    assert component.get_editor_property('visible') and not component.get_editor_property('hidden_in_game')
    assert component.get_collision_enabled()==unreal.CollisionEnabled.NO_COLLISION
    assert component.get_editor_property('mobility')==unreal.ComponentMobility.STATIC
    assert component.static_mesh.get_name()==roof_spec['mesh']['name']
    assert component.get_num_materials()==5
    for i,role in enumerate(roof_spec['mesh']['material_roles']):
        expected='/Game/GHSZcoolSmartFactory/Roof/Materials/M_GHSRoof_'+role+'.M_GHSRoof_'+role
        assert component.get_material(i).get_path_name()==expected
    report['roof_bounds_ue_cm']=mesh_bounds_check(component.static_mesh,roof_spec['mesh'])
    assert manifest['asset_count']==len(manifest['meshes'])==22
    expected_meshes={row['name']:row for row in manifest['meshes']}
    previous_meshes={row['name']:row for row in before_manifest['meshes']}
    assert set(expected_meshes)==set(previous_meshes)
    unchanged=[]
    for name,spec in expected_meshes.items():
        previous=previous_meshes[name]
        assert spec['role']==previous['role']
        if spec['role'] not in CHANGED_GEOMETRY:
            for key in ('vertices','triangles','bounds_ue_cm','instances','material_roles','slot_names'):
                assert spec.get(key)==previous.get(key),(name,key,'Unrelated geometry changed')
            unchanged.append(name)
    assert len(unchanged)==17
    park_uses=Counter();park_instances=0
    for actor in actors:
        label=actor.get_actor_label()
        if not label.startswith('GHSPark_'):continue
        assert 'GHS_ParkContext' in [str(t) for t in actor.tags],label
        assert not actor.get_actor_enable_collision() and not actor.is_actor_tick_enabled(),label
        for mesh_component in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh=mesh_component.static_mesh
            if not mesh or mesh.get_name() not in expected_meshes:
                assert isinstance(actor,unreal.CameraActor),label
                continue
            spec=expected_meshes[mesh.get_name()]
            park_uses[mesh.get_name()]+=1
            mesh_bounds_check(mesh,spec)
            if spec['role'] in ('Trees','TreesLight','TreesDark'):
                assert mesh.get_editor_property('nanite_settings').enabled,(mesh.get_name(),'Nanite crown not saved')
                assert mesh_component.get_material(0).get_editor_property('used_with_nanite')
            if mesh.get_name()=='SM_GHSPark_ClosedTruck':
                assert mesh_component.get_num_materials()==7
                for slot in range(7):
                    assert mesh_component.get_material(slot).get_editor_property('used_with_instanced_static_meshes')
            assert mesh_component.get_collision_enabled()==unreal.CollisionEnabled.NO_COLLISION
            if 'instances' in spec:
                assert isinstance(mesh_component,unreal.HierarchicalInstancedStaticMeshComponent)
                assert mesh_component.get_instance_count()==len(spec['instances'])==27
                park_instances+=mesh_component.get_instance_count()
            else:assert not isinstance(mesh_component,unreal.InstancedStaticMeshComponent)
    assert park_uses==Counter({name:1 for name in expected_meshes})
    assert park_instances==27

    report['stage']='lights and post process'
    light=key_actor.get_component_by_class(unreal.DirectionalLightComponent)
    sky=by[sky_labels[0]].get_component_by_class(unreal.SkyLightComponent)
    lighting=style['lighting']
    close(light.get_editor_property('intensity'),lighting['directional_intensity'])
    close(light.get_editor_property('light_source_angle'),lighting['directional_source_angle'])
    close(sky.get_editor_property('intensity'),lighting['skylight_intensity'])
    light_color_check(light,lighting['directional_color'])
    light_color_check(sky,lighting['skylight_color'])
    assert light.get_editor_property('cast_shadows')
    assert not sky.get_editor_property('cast_shadows')
    assert sky.get_editor_property('source_type')==unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP
    assert not sky.get_editor_property('real_time_capture')
    assert sky.get_editor_property('lower_hemisphere_is_black')==bool(lighting.get('lower_hemisphere_is_black',True))
    hemisphere=sky.get_editor_property('lower_hemisphere_color')
    for actual,expected in zip((hemisphere.r,hemisphere.g,hemisphere.b),lighting['lower_hemisphere_color']):close(actual,expected)
    assert len(baseline['post_process'])==1
    pp_actor=by[baseline['post_process'][0]['label']]
    pp=pp_actor.get_editor_property('settings')
    assert pp.get_editor_property('override_dynamic_global_illumination_method')
    assert pp.get_editor_property('dynamic_global_illumination_method')==unreal.DynamicGlobalIlluminationMethod.NONE
    assert pp.get_editor_property('override_reflection_method')
    assert pp.get_editor_property('reflection_method')==unreal.ReflectionMethod.NONE
    pp_targets=dict(ambient_occlusion_intensity=lighting['ambient_occlusion_intensity'],
        ambient_occlusion_radius=lighting['ambient_occlusion_radius_cm'],
        ambient_occlusion_quality=lighting['ambient_occlusion_quality'],bloom_intensity=lighting['bloom_intensity'],
        auto_exposure_min_brightness=0.,auto_exposure_max_brightness=0.,auto_exposure_bias=0.)
    for name,expected in pp_targets.items():
        assert pp.get_editor_property('override_'+name),name
        close(pp.get_editor_property(name),expected)
    for name in ('auto_exposure_method','local_exposure_highlight_contrast_scale','local_exposure_shadow_contrast_scale'):
        expected=baseline['post_process'][0]['values'][name]
        actual=pp.get_editor_property(name)
        if isinstance(expected,(int,float)):close(actual,expected)
        else:assert str(actual)==expected,(name,actual,expected)

    report['stage']='forest geometry metadata and preservation'
    forest=site['forests'];groups=forest['groups'];policy=forest['clearance_policy_m']
    assert groups and forest['total_trees']>0 and forest['total_islands']>0
    assert site['road_surface_valid'] and site['fence_road_overlap_m']<1e-6
    assert forest['public_site_scope_changed'] is False
    assert abs(forest['original_ground_overlap_m2'])<1e-6
    assert sum(group['trees'] for group in groups)==forest['total_trees']==manifest['counts']['woodland_trees']
    assert sum(len(group['islands']) for group in groups)==forest['total_islands']
    positions=[]
    minima={name:float('inf') for name in ('roads','buildings_and_driveways','campus','water')}
    fields={'roads':'road_canopy_clearance_m','buildings_and_driveways':'building_canopy_clearance_m',
            'campus':'campus_canopy_clearance_m','water':'water_canopy_clearance_m'}
    for group in groups:
        assert len(group['positions'])==group['trees']>0,group['name']
        assert group['planted_ground_area_m2']>0 and group['ground_polygons_uv_m'],group['name']
        for island in group['islands']:
            assert island['trees']>0 and island['area_m2']>0 and island['polygons_uv_m']
            assert island['top_z_m']>island['base_z_m']
        for position in group['positions']:
            uv=position['center_uv_m']
            assert len(uv)==2 and finite(uv)
            assert position['height_m']>0 and position['crown_radius_m']>0
            assert finite([position['height_m'],position['crown_radius_m'],position['base_z_m']])
            for name,field in fields.items():
                value=position[field]
                assert value is not None and math.isfinite(value) and value>=policy[name]-1e-6,(group['name'],uv,field,value)
                minima[name]=min(minima[name],value)
            positions.append(uv)
    measured_spacing=min(math.dist(a,b) for i,a in enumerate(positions) for b in positions[:i])
    assert measured_spacing>=forest['required_center_spacing_m']-1e-6
    close(measured_spacing,forest['minimum_tree_center_spacing_m'])
    old_site=read(OUT/'Before/site_geometry_report.json')
    for name in old_site:
        if name=='forests':continue
        expected=copy.deepcopy(old_site[name])
        if name=='parking':
            # Larger measured canopies legitimately prune unsafe garden trees;
            # parking bays, pavement, vehicles and all remaining data stay exact.
            for actual_group,expected_group in [(site[name],expected),
                                                (site[name]['northeast'],expected['northeast'])]:
                count=actual_group['garden_tree_candidates']
                assert 0<=count<=expected_group['garden_tree_candidates']
                expected_group['garden_tree_candidates']=count
        assert site[name]==expected,('Unrelated site layout changed',name)
    source=read(ROOT/'Saved/ParkExpansion/source_map_baseline.json')
    assert sha(Path(source['path']))==source['sha256'],'Original NormalWarehouse map changed'
    assert sha(MAP_FILE)==disk_hash_before,'Validation must not save or alter the map'
    report.update(success=True,stage='complete',actor_count=len(actors),preserved_actor_count=360,
        authorized_component_material_changes=bindings,key_rotation=lighting['directional_rotation'],
        roof_default_visible=True,roof_one_actor_one_mesh=True,roof_no_collision_no_tick=True,
        unchanged_nonvegetation_meshes=unchanged,park_mesh_count=22,park_hism_instances=27,
        materials_checked_count=len(report['materials_checked']),gi_and_reflection_none_preserved=True,
        nanite_crown_meshes_verified=3,truck_instancing_materials_verified=7,
        forest_safety=dict(trees=len(positions),islands=forest['total_islands'],minimum_spacing_m=measured_spacing,
            minimum_canopy_clearance_m=minima,source='Checked saved geometry metadata and independently recomputed tree spacing'),
        original_source_map_preserved=True,map_sha256=sha(MAP_FILE),
        park_manifest_sha256=sha(PARK_MANIFEST),roof_manifest_sha256=sha(ROOF_MANIFEST),
        reference_style_sha256=sha(ROOT/'SourceAssets/GHS/Park/reference_style.json'),validation_saved_map=False)
except Exception:
    report['error']=traceback.format_exc()
    unreal.log_error(report['error'])
finally:
    report['finished_utc']=datetime.now(timezone.utc).isoformat()
    (OUT/'saved_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert report['success'],report.get('error')
unreal.log('GHS_REFERENCE_STYLE_SAVED_VALIDATION_COMPLETE')
