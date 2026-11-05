"""Apply the reviewed 111-tree colour mask and 20-tree campus infill in place.

Call apply(unreal) from the current editor. This module never loads or saves a
map and never modifies an existing asset. Assets are cloned into Hierarchy;
only reviewed component materials/custom data and one new HISM are changed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT/'SourceAssets/MPR/hierarchy_20261105/landscape/selection.json'
DEST = '/Game/MPRWarehouse/Hierarchy/Materials'
OWNER = 'mpr-campus-hierarchy-20261105'
OWNER_KEY = 'MPRHierarchyOwner'
SOURCE_KEY = 'MPRHierarchySource'
GRAPH_KEY = 'MPRHierarchyMaskGraph'
INFILL_LABEL = 'MPRH_CampusPerimeterInfill'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def package(value):
    return (value.get_path_name() if hasattr(value, 'get_path_name') else str(value)).split('.')[0]


def linear(hex_color):
    values = [int(hex_color[i:i+2], 16)/255 for i in (0, 2, 4)]
    return [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in values]


def color_values(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


def set_vector_verified(u, material, name, color):
    # UE 5.8 MaterialEditingLibrary.cpp's vector setter performs the write and
    # UpdateMaterialInstance, but returns its unmodified false bResult. Verify
    # the actual stored value instead of interpreting that return as failure.
    ml = u.MaterialEditingLibrary
    ml.set_material_instance_vector_parameter_value(material, name, color)
    actual = ml.get_material_instance_vector_parameter_value(material, name)
    require(all(abs(a-b) < 2e-6 for a, b in zip(color_values(actual), color_values(color))),
            'Material vector read-back differs: '+package(material)+' / '+name)


def transform_values(value):
    q = value.rotation
    return dict(translation_cm=[float(value.translation.x), float(value.translation.y), float(value.translation.z)],
                rotation_xyzw=[float(q.x), float(q.y), float(q.z), float(q.w)],
                scale=[float(value.scale3d.x), float(value.scale3d.y), float(value.scale3d.z)])


def close_transform(actual, expected):
    # Matrix-backed HISM instances can read back the equivalent quaternion -q.
    linear_match = all(abs(a-b) < 1e-6 for key in ('translation_cm', 'scale')
                       for a, b in zip(actual[key], expected[key]))
    a, b = actual['rotation_xyzw'], expected['rotation_xyzw']
    rotation_error = min(max(abs(x-y) for x, y in zip(a, b)),
                         max(abs(x+y) for x, y in zip(a, b)))
    return linear_match and rotation_error < 1e-6


def component_of(u, actor, name):
    matches = [c for c in actor.get_components_by_class(u.ActorComponent) if c.get_name() == name]
    require(len(matches) == 1, 'Component identity changed: '+actor.get_name()+'.'+name)
    return matches[0]


def clone_owned(u, source, destination):
    """Only duplicate assets; never retarget or overwrite the source asset."""
    lib = u.EditorAssetLibrary
    if lib.does_asset_exist(destination):
        asset = lib.load_asset(destination)
        require(lib.get_metadata_tag(asset, OWNER_KEY) == OWNER,
                'Refusing to overwrite an unowned asset: '+destination)
        require(lib.get_metadata_tag(asset, SOURCE_KEY) == package(source),
                'Owned clone source differs: '+destination)
        return asset
    require(lib.does_asset_exist(package(source)), 'Missing source: '+package(source))
    asset = lib.duplicate_asset(package(source), destination)
    require(asset is not None, 'Cannot clone: '+destination)
    lib.set_metadata_tag(asset, OWNER_KEY, OWNER)
    lib.set_metadata_tag(asset, SOURCE_KEY, package(source))
    return asset


def prepare_materials(u, plan):
    """Create/reuse five owned material assets; source material properties remain intact."""
    lib, ml = u.EditorAssetLibrary, u.MaterialEditingLibrary
    representative = plan['groups'][0]['materials']
    source_leaf = [lib.load_asset(p) for p in representative[1:]]
    require(all(source_leaf), 'Current site leaf instances are missing')
    parents = [m.get_editor_property('parent') for m in source_leaf]
    require(len({package(p) for p in parents}) == 1, 'Leaf parent family differs; review before changing')
    parent = clone_owned(u, parents[0], DEST+'/M_MPRH_LeafMask')
    color_property = u.MaterialProperty.MP_BASE_COLOR
    if lib.get_metadata_tag(parent, GRAPH_KEY) != 'custom0-via-vertex-v1':
        base_color = ml.get_material_property_input_node(parent, color_property)
        base_output = str(ml.get_material_property_input_node_output_name(parent, color_property))
        # Existing leaves are solid Tint material. A failed earlier attempt may
        # leave disconnected nodes; the original base colour stays the input
        # until every connection below has succeeded.
        require(base_color is not None and base_color.get_class().get_name() == 'MaterialExpressionVectorParameter',
                'Leaf clone has an unexpected base-colour graph')
        require(str(base_color.get_editor_property('parameter_name')) == 'Tint',
                'Original leaf colour is not the reviewed Tint parameter')
        mask = ml.create_material_expression(parent, u.MaterialExpressionPerInstanceCustomData, -650, 250)
        mask.set_editor_property('data_index', 0)
        mask.set_editor_property('const_default_value', 0.)
        interpolator = ml.create_material_expression(parent, u.MaterialExpressionVertexInterpolator, -420, 250)
        campus = ml.create_material_expression(parent, u.MaterialExpressionVectorParameter, -420, 100)
        campus.set_editor_property('parameter_name', 'CampusTint')
        campus.set_editor_property('default_value', u.LinearColor(*linear(plan['palette_srgb']['leaf_mid']), 1.))
        blend = ml.create_material_expression(parent, u.MaterialExpressionLinearInterpolate, -130, 0)
        for a, output, b, input_name in [(base_color, base_output, blend, 'A'),
                                       (campus, 'RGB', blend, 'B'),
                                       (mask, '', interpolator, 'VS'),
                                       (interpolator, '', blend, 'Alpha')]:
            require(ml.connect_material_expressions(a, output, b, input_name),
                    'Cannot connect hierarchy material input '+input_name)
        require(ml.connect_material_property(blend, '', color_property), 'Cannot connect hierarchy base colour')
        lib.set_metadata_tag(parent, GRAPH_KEY, 'custom0-via-vertex-v1')
    require(ml.get_material_property_input_node(parent, color_property).get_class().get_name()
            == 'MaterialExpressionLinearInterpolate', 'Mask graph is not connected')
    ml.set_material_usage(parent, u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    parent.set_editor_property('used_with_nanite', True)
    ml.recompile_material(parent)
    require(lib.save_loaded_asset(parent, only_if_is_dirty=False), 'Failed saving new leaf parent')

    result = dict(parent=parent, leaf=[], assets=[package(parent)])
    for source, role, key in zip(source_leaf, ('LeafMid', 'LeafLight', 'LeafShade'),
                                 ('leaf_mid', 'leaf_light', 'leaf_shade')):
        material = clone_owned(u, source, DEST+'/MI_MPRH_'+role)
        ml.set_material_instance_parent(material, parent)
        set_vector_verified(u, material, 'CampusTint', u.LinearColor(*linear(plan['palette_srgb'][key]), 1.))
        # The original Tint overrides are copied verbatim; this is the exact
        # colour rendered by every background instance whose mask remains 0.
        require(color_values(ml.get_material_instance_vector_parameter_value(material, 'Tint')) ==
                color_values(ml.get_material_instance_vector_parameter_value(source, 'Tint')), 'Background Tint changed')
        ml.update_material_instance(material)
        require(lib.save_loaded_asset(material, only_if_is_dirty=False), 'Failed saving new leaf instance')
        result['leaf'].append(material)
        result['assets'].append(package(material))
    grass_source = lib.load_asset(plan['campus_green']['materials'][0])
    grass = clone_owned(u, grass_source, DEST+'/MI_MPRH_CampusGreen')
    set_vector_verified(u, grass, 'Tint', u.LinearColor(*linear(plan['palette_srgb']['campus_grass']), 1.))
    ml.update_material_instance(grass)
    require(lib.save_loaded_asset(grass, only_if_is_dirty=False), 'Failed saving new campus grass instance')
    result['grass'] = grass
    result['assets'].append(package(grass))
    return result


def check_group(u, actor, spec):
    require(actor.get_actor_label() == spec['label'], 'Tree actor label changed: '+spec['actor_name'])
    c = component_of(u, actor, spec['component_name'])
    require(close_transform(transform_values(actor.get_actor_transform()), spec['actor_transform']) and
            close_transform(transform_values(c.get_relative_transform()), spec['component_transform']),
            'Tree parent/component transform changed: '+spec['actor_name'])
    require(package(c.static_mesh) == package(spec['mesh']), 'Tree geometry changed')
    require(c.get_instance_count() == spec['instance_count'], 'Tree instance count changed')
    actual = [transform_values(c.get_instance_transform(i, world_space=False)) for i in range(c.get_instance_count())]
    require(all(close_transform(a, b) for a, b in zip(actual, spec['instance_transforms'])),
            'Existing tree instances moved/reordered: '+spec['actor_name'])
    require(hasattr(c, 'set_num_custom_data_floats') and hasattr(c, 'set_custom_data_value'),
            'Required reflected UE5.8 HISM methods are not available')
    existing_materials = [package(c.get_material(i)) for i in range(c.get_num_materials())]
    old_materials = [package(p) for p in spec['materials']]
    new_materials = old_materials[:1]+[DEST+'/MI_MPRH_'+r for r in ('LeafMid', 'LeafLight', 'LeafShade')]
    require(existing_materials == old_materials or (spec['selected_indices'] and existing_materials == new_materials),
            'Unreviewed tree material overrides: '+spec['actor_name'])
    floats = c.get_editor_property('num_custom_data_floats')
    require(floats == 0 or (floats == 1 and existing_materials == new_materials),
            'Per-instance custom data is already owned by another feature: '+spec['actor_name'])
    return c


def write_mask(component, indices):
    # Engine API SetNumCustomDataFloats reallocates and resets the whole buffer.
    # It is called only on untouched components; retries reuse the one-float
    # buffer already owned by this exact leaf-material family.
    if component.get_editor_property('num_custom_data_floats') == 0:
        component.set_num_custom_data_floats(1)
    selected = set(indices)
    count = component.get_instance_count()
    for i in range(count):
        require(component.set_custom_data_value(i, 0, 1. if i in selected else 0., i == count-1),
                'Cannot write tree colour mask at instance '+str(i))
    expected = [1. if i in selected else 0. for i in range(count)]
    require(list(component.get_editor_property('per_instance_sm_custom_data')) == expected,
            'Tree colour mask read-back differs')
    return expected


def infill(u, actors, plan, materials):
    existing = [a for a in actors if a.get_actor_label() == INFILL_LABEL]
    require(len(existing) <= 1, 'Duplicate campus infill actors')
    rows = plan['infill']
    if existing:
        actor = existing[0]
        require(OWNER in [str(t) for t in actor.tags], 'Infill label belongs to another task')
    else:
        bp = u.EditorAssetLibrary.load_asset('/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup')
        actor = u.get_editor_subsystem(u.EditorActorSubsystem).spawn_actor_from_class(bp.generated_class(), u.Vector())
        require(actor is not None, 'Cannot create campus infill HISM actor')
        # All SCS/actor property changes precede the HISM batch; changing tags
        # later can reconstruct and clear the Blueprint instance component.
        actor.set_actor_label(INFILL_LABEL)
        actor.set_folder_path('MPR/Hierarchy')
        actor.tags = ['MPRWarehouse', OWNER, 'InstanceCount='+str(len(rows))]
        actor.set_actor_tick_enabled(False)
        actor.set_actor_enable_collision(False)
        c = actor.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
        c.set_editor_property('receives_decals', False)
    c = actor.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
    require(c is not None, 'Infill HISM component is missing')
    require(c.get_instance_count() in (0, len(rows)), 'Partially-filled infill group; manual review required')
    tree = u.EditorAssetLibrary.load_asset(plan['groups'][0]['mesh'])
    c.set_static_mesh(tree)
    c.set_collision_profile_name('NoCollision')
    bark = u.EditorAssetLibrary.load_asset(plan['groups'][0]['materials'][0])
    for slot, material in enumerate([bark]+materials['leaf']):
        c.set_material(slot, material)
    transforms = [u.Transform(location=u.Vector(r['position_m'][0]*100, -r['position_m'][1]*100, r['position_m'][2]*100),
                              rotation=u.Rotator(yaw=-r['rotation_deg']), scale=u.Vector(*r['scale'])) for r in rows]
    if c.get_instance_count() == 0:
        result = c.add_instances(transforms, should_return_indices=True, world_space=True, update_navigation=False)
        require(list(result) == list(range(len(rows))), 'Infill instance allocation failed')
    require(c.get_instance_count() == len(rows), 'Infill tree count mismatch')
    require(all(close_transform(transform_values(c.get_instance_transform(i, world_space=True)), transform_values(t))
                for i, t in enumerate(transforms)), 'Infill transforms changed')
    values = write_mask(c, list(range(len(rows))))
    return dict(actor_name=actor.get_name(), actor_guid=u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid')),
                label=INFILL_LABEL, component_name=c.get_name(), instance_count=len(rows), custom_data=values,
                materials=[m.get_path_name() for m in [bark]+materials['leaf']],
                instance_transforms=[transform_values(c.get_instance_transform(i, world_space=False)) for i in range(len(rows))])


def apply(u, plan_path=PLAN):
    """Return exact component changes and new actor IDs for the root save guard."""
    plan_path = Path(plan_path)
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    require(not u.get_editor_subsystem(u.LevelEditorSubsystem).is_in_play_in_editor(), 'Exit PIE before applying hierarchy')
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    require(package(world) == package(plan['map']), 'Hierarchy requires the existing MPR map')
    actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    by_guid = {u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')): a for a in actors}
    targets = []
    for spec in plan['groups']:
        require(spec['actor_guid'] in by_guid, 'Original tree actor is missing: '+spec['actor_name'])
        actor = by_guid[spec['actor_guid']]
        require(actor.get_name() == spec['actor_name'], 'Tree identity changed')
        c = check_group(u, actor, spec)
        if spec['selected_indices']:
            targets.append((actor, c, spec))
    green_spec = plan['campus_green']
    require(green_spec['actor_guid'] in by_guid, 'Current campus green actor missing')
    green_actor = by_guid[green_spec['actor_guid']]
    require(green_actor.get_actor_label() == green_spec['label'], 'Campus green identity changed')
    green_c = component_of(u, green_actor, green_spec['component_name'])
    require(close_transform(transform_values(green_actor.get_actor_transform()), green_spec['actor_transform']) and
            close_transform(transform_values(green_c.get_relative_transform()), green_spec['component_transform']),
            'Campus green transform changed')
    require(package(green_c.static_mesh) == package(green_spec['mesh']), 'Campus green geometry changed')
    require(green_c.get_num_materials() == 1 and package(green_c.get_material(0)) in
            (package(green_spec['materials'][0]), DEST+'/MI_MPRH_CampusGreen'), 'Unreviewed campus green material')
    # Every source component passes the preflight before any scene mutation.
    materials = prepare_materials(u, plan)
    changes = []
    for actor, c, spec in targets:
        before = [transform_values(c.get_instance_transform(i, world_space=False)) for i in range(c.get_instance_count())]
        for i, material in enumerate(materials['leaf'], 1):
            c.set_material(i, material)
        mask = write_mask(c, spec['selected_indices'])
        after = [transform_values(c.get_instance_transform(i, world_space=False)) for i in range(c.get_instance_count())]
        require(after == before, 'HISM material/data mutation changed original transforms')
        changes.append(dict(actor_name=spec['actor_name'], actor_guid=spec['actor_guid'],
                            component_name=spec['component_name'], allowed_fields=['materials', 'num_custom_data_floats', 'custom_data'],
                            materials=[c.get_material(i).get_path_name() for i in range(c.get_num_materials())],
                            num_custom_data_floats=1, custom_data=mask, selected_indices=spec['selected_indices']))
    green_c.set_material(0, materials['grass'])
    changes.append(dict(actor_name=green_spec['actor_name'], actor_guid=green_spec['actor_guid'],
                        component_name=green_spec['component_name'], allowed_fields=['materials'],
                        materials=[materials['grass'].get_path_name()]))
    added = infill(u, actors, plan, materials)
    return dict(schema_version=1, owner=OWNER, plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                counts=plan['counts'], palette_srgb=plan['palette_srgb'], expected_changes=changes,
                new_actors=[added], new_actor_ids=[added['actor_guid']], new_assets=materials['assets'],
                map_saved=False, unchanged_background_count=1171)
