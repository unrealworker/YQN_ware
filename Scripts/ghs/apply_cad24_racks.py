"""Install CAD 2.4 rack assemblies in the loaded GHS map. The caller saves after validation."""
import hashlib
import math
import json
from pathlib import Path
import sys

import unreal

ROOT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
from apply_storage_capacity import import_rack, DEST, MAP
from import_cad24_distance_lods import apply as apply_distance_lods
from storage_capacity_import_validation import configure_capacity_component
from ue_instancing import spawn_group
from prepare_cad24_racks import BUILT, RUNTIME, read
from apply_refinement_v2 import transform

LIB = unreal.EditorAssetLibrary
ROLE = unreal.HierarchicalInstancedStaticMeshComponent
PRIVATE = '/Game/GHSZcoolSmartFactory/CAD24/Materials/'


def make_capacity_materials(kind, total):
    """Return original material path -> same-look CAD24 material, with the current rank domain."""
    path = RUNTIME / 'inventory-materials.json'
    table = read(path)
    mapping = table['materials']
    lookup = {}
    for cap_path, inv_path in list(mapping.items()):
        if '/StorageCapacity/Materials/M_Capacity_' + kind.title() + '_' not in cap_path:
            continue
        pair = []
        for old_path in (cap_path, inv_path):
            source = LIB.load_asset(old_path)
            assert source, old_path
            target = PRIVATE + source.get_name()
            material = LIB.load_asset(target) if LIB.does_asset_exist(target) else LIB.duplicate_asset(old_path.split('.')[0], target)
            assert material and LIB.get_metadata_tag(material,'GHS.CAD24.Source') in ('', old_path)
            masks = [e for e in unreal.ObjectIterator(unreal.MaterialExpressionCustom)
                     if e.get_outer() == material and 'float rank = fmod(globalSlot' in e.get_editor_property('code')]
            assert len(masks) == 1, (target, len(masks))
            mask = masks[0]
            source_mask = next(e for e in unreal.ObjectIterator(unreal.MaterialExpressionCustom)
                               if e.get_outer() == source and 'float rank = fmod(globalSlot' in e.get_editor_property('code'))
            original_code = source_mask.get_editor_property('code')
            old_total = '25056.0' if kind == 'rack' else '7530.0'
            assert original_code.count(old_total) == 2, (old_path, original_code)
            code = original_code.replace(old_total, str(float(total)))
            multiplier = 97 if total % 97 else 101
            while math.gcd(multiplier, total) != 1:
                multiplier += 2
            code = code.replace('globalSlot * 97.0', 'globalSlot * ' + str(float(multiplier)))
            if mask.get_editor_property('code') != code or not LIB.get_metadata_tag(material,'GHS.CAD24.Source'):
                mask.set_editor_property('code', code)
                LIB.set_metadata_tag(material, 'GHS.CAD24.Source', old_path)
                unreal.MaterialEditingLibrary.recompile_material(material)
                assert LIB.save_loaded_asset(material, only_if_is_dirty=False), target
            pair.append(material)
        lookup[cap_path] = pair[0]
        lookup[pair[0].get_path_name()] = pair[0]
        mapping[pair[0].get_path_name()] = pair[1].get_path_name()
    assert lookup, kind
    path.write_bytes(json.dumps(table, ensure_ascii=False, indent=2).encode('utf8'))
    return lookup


def apply_racks():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert world.get_path_name().split('.')[0] == MAP
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    capacity = read(RUNTIME / 'storage-capacity.json')
    scene = read(RUNTIME / 'scene-bindings.json')
    built = read(BUILT)
    assert built['cad_sha256'] == scene['rackSourceSha256'] == capacity['rackSourceSha256']
    by_mesh = {row['name']:row for row in built['meshes']}
    by_actor = {g['actor']:g for g in scene['groups']}
    plans = [g for g in capacity['groups'] if g['kind']=='rack']
    desired = {g['actor'] for g in plans}
    old = {}
    for actor in actors.get_all_level_actors():
        hism = actor.get_component_by_class(ROLE)
        if not hism or not hism.static_mesh:
            continue
        if hism.static_mesh.get_name().startswith('SM_GHS_V2Rack_'):
            label = actor.get_actor_label()
            assert label not in old and 'GHSStorageGroup:' + label in {str(t) for t in hism.component_tags}, label
            old[label] = actor
    assert old and plans
    prototype = next(iter(old.values())).get_component_by_class(ROLE)
    remap = make_capacity_materials('rack', capacity['rack_total_slots'])
    materials = [prototype.get_material(i) for i in range(7)]
    materials[3:] = [remap[m.get_path_name()] for m in materials[3:]]
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    meshes = {}
    for g in plans:
        name = g['mesh']
        row = by_mesh[name]
        assert row['fbx_sha256'] == hashlib.sha256(Path(row['fbx']).read_bytes()).hexdigest()
        target = DEST + '/Meshes/' + name
        mesh = LIB.load_asset(target) if LIB.does_asset_exist(target) else None
        if not mesh or LIB.get_metadata_tag(mesh, 'GHS.Capacity.FBXHash') != row['fbx_sha256']:
            mesh, _ = import_rack(row, materials, editor, lod_ratios=[1., .65, .48, .40])
            apply_distance_lods(variants=(row['variant'],))
        meshes[name] = mesh
    for g in plans:
        label = g['actor']
        mesh = meshes[g['mesh']]
        poses = [transform(r) for r in by_actor[label]['instances']]
        assert len(poses) == g['count']
        actor = old.get(label)
        if actor is None:
            actor = spawn_group(label, 'GHS/Storage/CAD24', mesh, poses)
        else:
            component = actor.get_component_by_class(ROLE)
            component.modify()
            component.clear_instances()
            component.add_instances(poses, should_return_indices=False, world_space=True, update_navigation=False)
        tags = ['GHSStorageGroup:' + label]
        properties = dict(component_tags=tags, cast_static_shadow=False, affect_distance_field_lighting=False,
            shadow_cache_invalidation_behavior=unreal.ShadowCacheInvalidationBehavior.ALWAYS)
        bases = [float(g['base_slot'] + i * g['slots_per_instance']) for i in range(g['count'])]
        component = configure_capacity_component(lambda: actor.get_component_by_class(ROLE), mesh, materials, properties, bases)
        for i, pose in enumerate(poses):
            actual = component.get_instance_transform(i, world_space=True)
            assert (actual.translation - pose.translation).length() < .1 and actual.rotation.angular_distance(pose.rotation) < .001
    for label in old.keys() - desired:
        assert actors.destroy_actor(old[label]), label
    unreal.log('CAD24 replaced rack groups: ' + str({g['actor']:g['count'] for g in plans}))
