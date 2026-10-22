"""Import complete-capacity racks and material masks in the current saved map.

Parent workflow owns UE execution. This script never starts/stops the editor.
Only private capacity assets and the target map are saved. Floor mesh assets,
original materials, transforms, instance order and unrelated actors are preserved.
"""
from pathlib import Path
import hashlib
import importlib
import json
import sys
import traceback
import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'Saved/SceneControls'
DEST = '/Game/GHSZcoolSmartFactory/StorageCapacity'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
VERSION = 'ghs-complete-storage-capacity-v1'
LIB = unreal.EditorAssetLibrary
ML = unreal.MaterialEditingLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
import storage_capacity_import_validation as capacity_validation
# UE's Python interpreter persists between parent-owned retry executions.
importlib.reload(capacity_validation)
configure_capacity_component = capacity_validation.configure_capacity_component
validate_lod_layout = capacity_validation.validate_lod_layout


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def path(obj):
    return obj.get_path_name() if obj else None


def sha(asset_path):
    filename = ROOT / 'Content' / (asset_path.split('.')[0].removeprefix('/Game/') + '.uasset')
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def transform(value):
    return dict(position=list(value.translation.to_tuple()), rotation=list(value.rotation.to_tuple()), scale=list(value.scale3d.to_tuple()))


def snapshot(actors):
    result = {}
    for actor in actors:
        components = {}
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            row = dict(mesh=path(component.static_mesh), materials=[path(component.get_material(i)) for i in range(component.get_num_materials())],
                       transform=transform(component.get_world_transform()), tags=[str(t) for t in component.component_tags],
                       visible=component.get_editor_property('visible'), cast_shadow=component.get_editor_property('cast_shadow'),
                       cast_static_shadow=component.get_editor_property('cast_static_shadow'),
                       affect_distance_field_lighting=component.get_editor_property('affect_distance_field_lighting'),
                       shadow_cache_invalidation_behavior=str(component.get_editor_property('shadow_cache_invalidation_behavior')))
            if isinstance(component, unreal.InstancedStaticMeshComponent):
                row['instances'] = [transform(component.get_instance_transform(i, world_space=True)) for i in range(component.get_instance_count())]
            components[component.get_name()] = row
        result[actor.get_actor_label()] = dict(transform=transform(actor.get_actor_transform()), tags=[str(t) for t in actor.tags], components=components)
    return result


def node(material, cls, **properties):
    value = ML.create_material_expression(material, cls)
    for name, item in properties.items():
        value.set_editor_property(name, item)
    return value


def connect(a, b, pin):
    assert ML.connect_material_expressions(a, '', b, pin)


def source_material(material):
    original = LIB.get_metadata_tag(material, 'GHS.Capacity.Source')
    return LIB.load_asset(original) if original else material


def make_material(source, kind, total):
    source = source_material(source)
    assert isinstance(source, unreal.Material), ('Expected a saved editable source material', path(source))
    fingerprint = sha(path(source))
    name = 'M_Capacity_' + kind.title() + '_' + source.get_name()
    target = DEST + '/Materials/' + name
    if LIB.does_asset_exist(target):
        material = LIB.load_asset(target)
        assert LIB.get_metadata_tag(material, 'GHS.Capacity.Version') == VERSION, target
        assert LIB.get_metadata_tag(material, 'GHS.Capacity.SourceHash') == fingerprint, ('Source material changed; review before replacement', path(source))
        return material
    material = LIB.duplicate_asset(source.get_path_name().split('.')[0], target)
    assert material
    material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
    material.set_editor_property('opacity_mask_clip_value', .5)
    material.set_editor_property('used_with_instanced_static_meshes', True)
    capacity = node(material, unreal.MaterialExpressionScalarParameter,
                    parameter_name='StorageCapacity', default_value=.8 if kind == 'rack' else 1.)
    instance = node(material, unreal.MaterialExpressionPerInstanceCustomData, data_index=0, const_default_value=0.)
    interpolator = node(material, unreal.MaterialExpressionVertexInterpolator)
    connect(instance, interpolator, 'VS')
    if kind == 'rack':
        local = node(material, unreal.MaterialExpressionTextureCoordinate, coordinate_index=1)
    else:
        local = node(material, unreal.MaterialExpressionConstant, r=0.)
    inputs = []
    for name in ['BaseSlot', 'LocalSlot', 'Capacity']:
        entry = unreal.CustomInput()
        entry.set_editor_property('input_name', name)
        inputs.append(entry)
    mask = node(material, unreal.MaterialExpressionCustom, inputs=inputs,
                description='Stable complete storage slots; negative UV identifies retained steel',
                output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,
                code=f'''float local = floor(LocalSlot.x + 0.5);
float globalSlot = floor(BaseSlot + 0.5) + local;
float rank = fmod(globalSlot * 97.0 + 17.0, {float(total)});
float visibleCount = floor(saturate(Capacity) * {float(total)} + 0.5);
return local < -0.5 ? 1.0 : (rank < visibleCount ? 1.0 : 0.0);''')
    connect(interpolator, mask, 'BaseSlot')
    connect(local, mask, 'LocalSlot')
    connect(capacity, mask, 'Capacity')
    assert ML.connect_material_property(mask, '', unreal.MaterialProperty.MP_OPACITY_MASK)
    ML.recompile_material(material)
    LIB.set_metadata_tag(material, 'GHS.Capacity.Version', VERSION)
    LIB.set_metadata_tag(material, 'GHS.Capacity.SourceHash', fingerprint)
    LIB.set_metadata_tag(material, 'GHS.Capacity.Source', source.get_path_name().split('.')[0])
    assert LIB.save_loaded_asset(material, only_if_is_dirty=False)
    assert sha(path(source)) == fingerprint, 'Source material must remain unchanged'
    return material


def inspect_lod_layout(mesh, editor):
    lods = []
    for lod in range(editor.get_lod_count(mesh)):
        sections = []
        for section in range(mesh.get_num_sections(lod)):
            _, indices, _, _, _ = unreal.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, lod, section)
            sections.append(dict(material_index=editor.get_lod_material_slot(mesh, lod, section), triangle_count=len(indices)//3))
        lods.append(dict(lod=lod, triangles=mesh.get_num_triangles(lod), section_rows=sections))
    return lods


def validate_partial_recovery(manifest):
    """Recognize only the unsaved first mesh from the observed failed import."""
    row = manifest['meshes'][0]
    assert row['name'] == 'SM_GHS_V2Rack_A_Pass_W36176_Capacity'
    target = DEST + '/Meshes/' + row['name']
    previous = read(OUT / 'capacity-apply.json')
    assert previous.get('success') is False and previous.get('groups') == []
    assert 'mesh.get_num_sections(lod) == 7' in previous.get('error', '')
    assert not (ROOT / 'Content' / (target.removeprefix('/Game/') + '.uasset')).exists(), 'Recovery only covers the unsaved interrupted asset'
    old = LIB.load_asset(target)
    assert isinstance(old, unreal.StaticMesh) and not LIB.get_metadata_tag(old, 'GHS.Capacity.Version')
    imported = old.get_editor_property('asset_import_data').get_first_filename()
    assert Path(imported).resolve() == Path(row['fbx']).resolve(), 'Partial mesh has a different source'
    assert hashlib.sha256(Path(row['fbx']).read_bytes()).hexdigest() == row['fbx_sha256']
    assert old.get_num_triangles(0) == row['triangles']
    slots = old.get_editor_property('static_materials')
    assert [str(s.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1] for s in slots] == row['slot_roles']
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    assert dirty == [target], ('Unexpected unsaved user assets', dirty)
    return target


def import_rack(row, materials, editor, recover_target=None):
    target = DEST + '/Meshes/' + row['name']
    if LIB.does_asset_exist(target):
        old = LIB.load_asset(target)
        assert LIB.get_metadata_tag(old, 'GHS.Capacity.Version') == VERSION or target == recover_target, ('Unowned capacity mesh exists', target)
    task = unreal.AssetImportTask()
    task.filename = row['fbx']; task.destination_path = DEST + '/Meshes'; task.destination_name = row['name']
    task.automated = True; task.replace_existing = True; task.replace_existing_settings = True; task.save = False
    options = unreal.FbxImportUI()
    options.import_mesh = True; options.import_as_skeletal = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    options.automated_import_should_detect_type = False
    options.import_materials = False; options.import_textures = False; options.import_animations = False
    options.static_mesh_import_data.combine_meshes = True
    options.static_mesh_import_data.generate_lightmap_u_vs = False
    options.static_mesh_import_data.auto_generate_collision = False
    options.static_mesh_import_data.build_nanite = False
    options.static_mesh_import_data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    task.options = options
    TOOLS.import_asset_tasks([task])
    mesh = LIB.load_asset(target)
    assert isinstance(mesh, unreal.StaticMesh)
    slots = mesh.get_editor_property('static_materials')
    assert [str(s.get_editor_property('imported_material_slot_name')).rsplit('_', 1)[-1] for s in slots] == row['slot_roles']
    for index, slot in enumerate(slots):
        slot.material_interface = materials[index]
        slots[index] = slot
    mesh.set_editor_property('static_materials', slots)
    mesh.set_editor_property('allow_cpu_access', True)
    settings = editor.get_lod_build_settings(mesh, 0)
    settings.set_editor_property('use_full_precision_u_vs', True)
    settings.set_editor_property('generate_lightmap_u_vs', False)
    editor.set_lod_build_settings(mesh, 0, settings)
    reduction = unreal.StaticMeshReductionOptions()
    reduction.auto_compute_lod_screen_size = False
    ratios = [1., .55, .30, .18]
    policy_file = ROOT / 'SourceAssets/GHS/StorageCapacity/lod-policy.json'
    if policy_file.exists():
        policy = read(policy_file)
        assert policy['owner'] == VERSION
        if row['name'] in policy['meshes']:
            entry = policy['meshes'][row['name']]
            assert entry['fbx_sha256'] == row['fbx_sha256'], 'LOD policy must be revalidated for changed source geometry'
            assert len(entry['ratios']) == 4 and entry['ratios'][0] == 1.
            assert all(entry['ratios'][i] >= ratios[i] for i in range(4))
            assert all(entry['ratios'][i] <= entry['ratios'][i-1] for i in range(1,4))
            ratios = entry['ratios']
    reduction.reduction_settings = [unreal.StaticMeshReductionSettings(percent_triangles=p, screen_size=s)
        for p, s in zip(ratios, [1., .25, .08, .025])]
    assert editor.set_lods(mesh, reduction) == 4
    bounds = mesh.get_bounds()
    expected_center = [(a+b)*50 for a,b in row['bounds_m']]
    expected_center[1] *= -1
    expected_extent = [(b-a)*50 for a,b in row['bounds_m']]
    assert max(abs(v-e) for v,e in zip(bounds.origin.to_tuple(), expected_center)) < .15
    assert max(abs(v-e) for v,e in zip(bounds.box_extent.to_tuple(), expected_extent)) < .15
    # UE reduction drops tiny CargoEdges/Detail sections at distant LODs. Verify
    # the material remap and all core roles instead of requiring seven sections.
    # The native render-buffer automation separately checks UV1 on every triangle.
    lod_layout = inspect_lod_layout(mesh, editor)
    validate_lod_layout(lod_layout, row['slot_roles'], row['triangles'])
    assert editor.get_num_uv_channels(mesh, 0) >= 2
    LIB.set_metadata_tag(mesh, 'GHS.Capacity.Version', VERSION)
    LIB.set_metadata_tag(mesh, 'GHS.Capacity.FBXHash', row['fbx_sha256'])
    assert LIB.save_loaded_asset(mesh, only_if_is_dirty=False)
    return mesh, lod_layout


def validate_component_resume(actors, runtime, manifest):
    """Only resume the observed first-group interruption, preserving its baseline."""
    previous = read(OUT / 'capacity-apply.json')
    assert previous.get('success') is False and previous.get('groups') == []
    assert 'component.set_custom_data_value' in previous.get('error', '')
    assert len(previous.get('imported_lods', [])) == len(manifest['meshes']) == 10
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    assert [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()] == [MAP]
    baseline = read(OUT / 'capacity-before.json')
    current = snapshot(actors)
    group = runtime['groups'][0]
    assert group['actor'] == 'GHS_V2_Rack_A_Pass_W36176'
    by = {actor.get_actor_label(): actor for actor in actors}
    component = by[group['actor']].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    old = baseline[group['actor']]['components'][component.get_name()]
    changed = current[group['actor']]['components'][component.get_name()]
    target = DEST + '/Meshes/' + group['mesh']
    expected_materials = old['materials'][:3]
    for source in old['materials'][3:]:
        name = 'M_Capacity_Rack_' + source.rsplit('.', 1)[-1]
        expected_materials.append(DEST + '/Materials/' + name + '.' + name)
    expected = dict(mesh=target + '.' + group['mesh'], materials=expected_materials,
        tags=old['tags'] + ['GHSStorageGroup:' + group['actor']], cast_static_shadow=False)
    for key, value in expected.items():
        assert changed[key] == value, ('Unexpected interrupted component value', key, changed[key])
        changed[key] = old[key]
    assert current == baseline, 'Unrelated or unrecognized scene edits since original baseline'
    for item in runtime['groups']:
        live = by[item['actor']].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        assert live.get_instance_count() == item['count']
        assert live.get_editor_property('num_custom_data_floats') == 0
        assert len(live.get_editor_property('per_instance_sm_custom_data')) == 0
    return baseline


def load_completed_rack(row, materials, editor):
    mesh = LIB.load_asset(DEST + '/Meshes/' + row['name'])
    assert isinstance(mesh, unreal.StaticMesh)
    assert LIB.get_metadata_tag(mesh, 'GHS.Capacity.Version') == VERSION
    assert LIB.get_metadata_tag(mesh, 'GHS.Capacity.FBXHash') == row['fbx_sha256']
    slots = mesh.get_editor_property('static_materials')
    assert [str(s.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1] for s in slots] == row['slot_roles']
    assert [path(s.material_interface) for s in slots] == [path(m) for m in materials]
    lod_layout = inspect_lod_layout(mesh, editor)
    validate_lod_layout(lod_layout, row['slot_roles'], row['triangles'])
    return mesh, lod_layout


def apply(save_level=True, require_clean=True, recover_partial=False, resume_components=False):
    report = dict(success=False, materials=[], groups=[], imported_lods=[])
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        assert world.get_path_name().split('.')[0] == MAP, 'Open the Zcool target map first'
        assert not levels.is_in_play_in_editor()
        assert not (recover_partial and resume_components)
        manifest = read(ROOT / 'SourceAssets/GHS/StorageCapacity/storage_capacity.json')
        recover_target = validate_partial_recovery(manifest) if recover_partial else None
        if require_clean and not recover_partial and not resume_components:
            assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Save current user map edits before importing'
            assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages(), 'Save current user asset edits before importing'
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
        by = {actor.get_actor_label(): actor for actor in actors}
        runtime = read(ROOT / 'Content/GHSTwinUI/data/storage-capacity.json')
        assert manifest['owner'] == VERSION and runtime['owner'] == VERSION
        if resume_components:
            baseline = validate_component_resume(actors, runtime, manifest)
        else:
            baseline = snapshot(actors)
            (OUT / 'capacity-before.json').write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding='utf-8')
        meshes = {row['name']: row for row in manifest['meshes']}
        material_cache = {}
        plans = []
        original_hashes = {}
        unreal.load_module('StaticMeshEditor')
        editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        for group in runtime['groups']:
            actor = by[group['actor']]
            component = actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
            assert component and component.get_instance_count() == group['count'], group['actor']
            original_mesh = component.static_mesh
            assert original_mesh.get_name() in [group['source_mesh'], group['source_mesh']+'_Occ70', group['mesh']]
            if group['kind'] == 'floor':
                assert original_mesh.get_path_name().startswith('/Game/GHSZcoolSmartFactory/DoublePallet/Meshes/')
            original_hashes[path(original_mesh)] = sha(path(original_mesh))
            materials = []
            for index in range(component.get_num_materials()):
                source = source_material(component.get_material(index))
                original_hashes[path(source)] = sha(path(source))
                # First three rack slots are steel and retain their exact opaque materials.
                if group['kind'] == 'rack' and index < 3:
                    materials.append(source)
                    continue
                key = (group['kind'], path(source))
                if key not in material_cache:
                    total = runtime['rack_total_slots' if group['kind'] == 'rack' else 'floor_total_slots']
                    material_cache[key] = make_material(source, group['kind'], total)
                    report['materials'].append(dict(source=path(source), target=path(material_cache[key]), kind=group['kind']))
                materials.append(material_cache[key])
            if group['kind'] == 'rack':
                if resume_components:
                    mesh, lod_layout = load_completed_rack(meshes[group['mesh']], materials, editor)
                else:
                    mesh, lod_layout = import_rack(meshes[group['mesh']], materials, editor, recover_target)
                report['imported_lods'].append(dict(mesh=path(mesh), lods=lod_layout))
            else:
                mesh = original_mesh
            plans.append((group, component, mesh, materials))
        for group, component, mesh, materials in plans:
            actor = by[group['actor']]
            get_component = lambda: actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
            tags = [str(tag) for tag in get_component().component_tags if not str(tag).startswith('GHSStorageGroup:')]
            tags.append('GHSStorageGroup:' + group['actor'])
            # Runtime opacity does not alter baked/distance-field occluders. VSM
            # must invalidate cached pages even when only a material scalar moves.
            properties = dict(component_tags=tags, cast_static_shadow=False, affect_distance_field_lighting=False,
                shadow_cache_invalidation_behavior=unreal.ShadowCacheInvalidationBehavior.ALWAYS)
            bases = [float(group['base_slot']+index*group['slots_per_instance']) for index in range(group['count'])]
            component = configure_capacity_component(get_component, mesh, materials, properties, bases)
            old = baseline[group['actor']]['components'][component.get_name()]
            old.update(mesh=path(mesh), materials=[path(m) for m in materials], tags=tags,
                       cast_static_shadow=False, affect_distance_field_lighting=False,
                       shadow_cache_invalidation_behavior=str(unreal.ShadowCacheInvalidationBehavior.ALWAYS))
            report['groups'].append(dict(actor=group['actor'], mesh=path(mesh), count=group['count'],
                slots=group['count']*group['slots_per_instance'], kind=group['kind'], lod_triangles=[mesh.get_num_triangles(i) for i in range(4)]))
        assert snapshot(actors) == baseline, 'Unexpected scene edits outside capacity mesh/material/tag changes'
        for asset_path, fingerprint in original_hashes.items():
            if not asset_path.startswith(DEST+'/Meshes/'):
                assert sha(asset_path) == fingerprint, 'Original asset changed: ' + asset_path
        if save_level:
            assert levels.save_current_level()
        report.update(success=True, saved=save_level, runtime_metadata=runtime,
                      resumed_components=resume_components,
                      original_materials_and_floor_meshes_unchanged=True, instance_order_transforms_unchanged=True,
                      dynamic_mask_shadow_consistency=True, vsm_invalidation='Always; GPU cost requires measurement',
                      unrelated_scene_geometry_and_materials_unchanged=True)
        unreal.log('GHS_STORAGE_CAPACITY_APPLIED ' + str(len(plans)))
        return report
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        (OUT / 'capacity-apply.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    apply()
