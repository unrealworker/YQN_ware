"""Reload and verify the saved GHS warehouse in a fresh UE process; never save."""
import hashlib
import json
import math
import sys
import traceback
from pathlib import Path

import unreal

ROOT = Path(r'D:\UEPro\Test')
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
from cad_rack_revision_state import dispatch_cad_rack_verification
SOURCE = ROOT / 'SourceAssets/GHS'
REPORT_PATH = ROOT / 'Saved/GHS_Verification.json'
MAP = '/Game/Maps/GHS_CAD_DigitalTwin'
DEST = '/Game/GHSDigitalTwin'
report = dict(success=False, map=MAP, verification_mode='Fresh UE process; reload saved map; no level or asset save',
              groups=[], individuals=[], effects=[], meshes=[])
CAD_GROUPS = {
    'GHS_CAD_Racks': ('racks', 1607),
    'GHS_CAD_PalletCargo': ('storage', 7530),
    'GHS_CAD_Columns': ('columns', 206),
    'GHS_CAD_WallFaces': ('walls', 330),
    'GHS_CAD_DockRacks': ('equipment', 87),
}
FOUR_LOD = {'SM_GHS_KukaLowProfileAGV', 'SM_GHS_WallCharger', 'SM_GHS_Shared_RackBay',
            'SM_GHS_Shared_PalletCargo', 'SM_GHS_Shared_Conveyor'}
CAMERAS = {'CAM_GHS_' + name for name in ['Overview', 'CADPlan', 'RackAisles',
                                        'FloorStorage', 'Charging', 'AGV_Charger']}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def expected_location(position):
    return [float(position[0]) * 100, -float(position[1]) * 100,
            float(position[2] if len(position) > 2 else 0) * 100]


def compare(actual, expected, tolerance, context):
    assert len(actual) == len(expected), context + ' length mismatch'
    delta = [abs(a - b) for a, b in zip(actual, expected)]
    assert all(math.isfinite(a) for a in actual) and max(delta, default=0) <= tolerance, (
        '%s: actual=%s expected=%s delta=%s' % (context, actual, expected, delta))
    return max(delta, default=0)


def check_transform(transform, record, context):
    rotation = transform.rotation.rotator()
    errors = dict(
        position_cm=compare(xyz(transform.translation), expected_location(record['position_m']), .05, context + ' position'),
        scale=compare(xyz(transform.scale3d), [float(v) for v in record.get('scale', [1, 1, 1])], .0002, context + ' scale'),
        yaw_deg=abs((float(rotation.yaw) + float(record.get('rotation_deg', 0)) + 180) % 360 - 180),
    )
    assert errors['yaw_deg'] <= .02, context + ' yaw is not mirrored from CAD: ' + str(errors)
    compare([float(rotation.pitch), float(rotation.roll)], [0, 0], .02, context + ' tilt')
    return errors


def expected_mesh_path(name):
    return '/Engine/BasicShapes/Cube.Cube' if name == 'Cube' else DEST + '/Meshes/' + name + '.' + name


def check_materials(component, context):
    assert component.get_num_materials() > 0, context + ' has no material slots'
    paths = []
    for index in range(component.get_num_materials()):
        material = component.get_material(index)
        assert material, context + ' has null material slot ' + str(index)
        path = material.get_path_name()
        assert 'WorldGrid' not in path, context + ' uses WorldGrid'
        paths.append(path)
    return paths


def main(clearance_layout=None):
    build = read_json(ROOT / 'Saved/GHS_BuildReport.json')
    registry = read_json(SOURCE / 'ue_scene_registry.json')
    cad = read_json(SOURCE / 'cad_layout.json')
    cad_groups = dict(CAD_GROUPS)
    if build.get('wall_joined_corrected'):
        # The 330 measured source segments are now represented by one union
        # mesh; verify_joined_walls checks their complete source ID mapping.
        cad_groups.pop('GHS_CAD_WallFaces')
    if clearance_layout is not None:
        for key in ['columns', 'storage', 'racks', 'equipment']:
            cad[key] = clearance_layout[key]
        cad_groups.update({
            'GHS_CAD_Racks': ('racks', 1617),
            'GHS_CAD_PalletCargo': ('storage', 7408),
            'GHS_CAD_Columns': ('columns', 170),
        })
    if build.get('presentation_refined'):
        cad_groups.pop('GHS_CAD_PalletCargo', None)  # Verified jointly across three height groups.
    imported = read_json(ROOT / 'Saved/GHS_AssetImport.json')
    instanced_materials = read_json(ROOT / 'Saved/GHS_InstanceMaterials.json')
    assert build['success'] and build['stage'] == 'saved', 'Build has not finished saving'
    assert imported['success'], 'Asset preparation did not succeed'
    assert instanced_materials['success'] and not instanced_materials['original_material_files_modified']
    material_copies = instanced_materials['copies']
    material_groups = {item['actor']: item['materials'] for item in instanced_materials['groups']}
    assert len(material_groups) == len(instanced_materials['groups'])
    # Read persisted flags before loading any HISM actors, which may otherwise
    # automatically enable missing material usage flags in editor memory.
    for source_path, copy_path in material_copies.items():
        assert source_path.startswith('/Game/VideoDigitalTwin/Materials/')
        assert copy_path.startswith(DEST + '/Materials/Instanced/')
        material = unreal.EditorAssetLibrary.load_asset(copy_path.split('.')[0])
        assert isinstance(material, unreal.Material), copy_path
        assert material.get_editor_property('used_with_instanced_static_meshes'), copy_path + ' usage flag was not saved'
    report['persisted_instancing_materials'] = dict(copy_count=len(material_copies),
                                                  all_usage_flags_saved=True, copies=material_copies)
    assert build['map'] == registry['map'] == MAP
    assert cad['schema_version'] == 2
    assert cad['origin_dxf_xy'] == registry['origin_dxf_xy'] == build['origin_dxf_xy']
    assert cad['units_to_m'] == registry['units_to_m'] == build['units_to_m']
    assert cad['units'] == build['cad_units']
    source_level = ROOT / 'Content/Maps/VideoDigitalTwinWarehouse.umap'
    source_sha = hashlib.sha256(source_level.read_bytes()).hexdigest()
    assert build['original_level_preserved'] and source_sha == build['source_level_sha256'], 'Original video map SHA differs'
    assert unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(MAP), 'Could not reload saved GHS map'
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert world.get_path_name().split('.')[0] == MAP
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    labels = {}
    for actor in actors:
        labels.setdefault(actor.get_actor_label(), []).append(actor)

    def single(label):
        matches = labels.get(label, [])
        assert len(matches) == 1, 'Expected one %s, found %d' % (label, len(matches))
        return matches[0]

    floor_actor = single('GHS_CAD_ExactFootprint')
    floor_component = floor_actor.get_component_by_class(unreal.StaticMeshComponent)
    floor_mesh = floor_component.get_editor_property('static_mesh')
    assert floor_mesh and floor_mesh.get_name() == 'SM_GHS_CAD_Floor'
    outline_ue = [[float(point[0]) * 100, -float(point[1]) * 100] for point in cad['footprint_outline_m']]
    minimum = [min(point[axis] for point in outline_ue) for axis in range(2)]
    maximum = [max(point[axis] for point in outline_ue) for axis in range(2)]
    center = [(lo + hi) / 2 for lo, hi in zip(minimum, maximum)]
    extent = [(hi - lo) / 2 for lo, hi in zip(minimum, maximum)]
    floor_bounds = floor_mesh.get_bounds()
    compare(xyz(floor_bounds.origin)[:2], center, .05, 'CAD footprint local mesh center; FBX Y mirror')
    compare(xyz(floor_bounds.box_extent)[:2], extent, .05, 'CAD footprint local mesh XY extent')
    report['footprint_bounds'] = dict(cad_outline_vertex_count=len(outline_ue),
                                    expected_center_xy_cm=center, expected_extent_xy_cm=extent,
                                    mesh_center_cm=xyz(floor_bounds.origin), mesh_extent_cm=xyz(floor_bounds.box_extent),
                                    fbx_axis_and_y_mirror_verified=True)

    assert len(actors) == build['actor_count'], 'Saved actor count differs from build report'
    groups = registry['groups']
    group_names = {item['actor'] for item in groups}
    assert len(group_names) == len(groups), 'Duplicate group label in registry'
    assert set(material_groups) == group_names, 'Saved instance material groups differ from registry'
    build_groups = {item['actor']: item for item in build['groups']}
    assert set(build_groups) == group_names
    actual_hism_actors = [actor for actor in actors if actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)]
    assert len(actual_hism_actors) == len(groups)
    assert {actor.get_actor_label() for actor in actual_hism_actors} == group_names
    total_instances = 0
    for group in groups:
        label = group['actor']
        actor = single(label)
        components = actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        assert len(components) == 1, label + ' must contain exactly one HISM'
        component = components[0]
        assert component.get_editor_property('visible') and not component.get_editor_property('hidden_in_game'), label
        count = component.get_instance_count()
        assert count == group['count'] == len(group['instances']) == build_groups[label]['count'], label + ' count mismatch'
        assert group['mesh'] == build_groups[label]['mesh']
        mesh = component.get_editor_property('static_mesh')
        assert mesh and mesh.get_path_name() == expected_mesh_path(group['mesh']), label + ' mesh mismatch'
        materials = check_materials(component, label)
        assert materials == material_groups[label], label + ' saved material overrides differ'
        assert all(path.startswith(DEST + '/Materials/Instanced/') for path in materials), label + ' uses a shared render material'
        for slot, path in enumerate(materials):
            assert component.get_material(slot).get_editor_property('used_with_instanced_static_meshes'), path
        if group.get('material_override'):
            name = group['material_override']
            source_path = '/Game/VideoDigitalTwin/Materials/' + name + '.' + name
            assert materials[0] == material_copies[source_path], label + ' material override copy mismatch'
        else:
            source_materials = [mesh.get_material(slot).get_path_name() for slot in range(component.get_num_materials())]
            assert materials == [material_copies.get(path, path) for path in source_materials], label + ' mesh material copy mapping mismatch'
        ids = [item['id'] for item in group['instances']]
        # Repeated DXF INSERTs share their block's leaf handles. The ancestor
        # handle chain plus the local segment ID identifies a placed segment.
        source_keys = [(tuple(item.get('source_handles', [])), item['id']) for item in group['instances']]
        assert len(set(source_keys)) == len(source_keys), label + ' duplicate instance source identities'
        if label in cad_groups:
            cad_key, expected_count = cad_groups[label]
            assert count == expected_count == len(cad[cad_key]), label + ' differs from CAD count'
            assert set(ids) == {item['id'] for item in cad[cad_key]}, label + ' CAD source IDs mismatch'
        largest = dict(position_cm=0.0, scale=0.0, yaw_deg=0.0)
        for index, item in enumerate(group['instances']):
            transform = component.get_instance_transform(index, world_space=True)
            assert transform is not None, label + ' missing instance ' + str(index)
            errors = check_transform(transform, item, '%s[%d] %s' % (label, index, item['id']))
            for key, error in errors.items():
                largest[key] = max(largest[key], error)
        total_instances += count
        report['groups'].append(dict(actor=label, mesh=mesh.get_path_name(), count=count,
                                     all_world_transforms_verified=True, maximum_error=largest, materials=materials))
    assert total_instances == build['instanced_count']
    assert set(cad_groups).issubset(group_names)

    individuals = registry['individuals']
    assert individuals == build['individuals'], 'Build report and individual registry differ'
    ids = [item['id'] for item in individuals]
    assert len(ids) == len(set(ids)), 'Duplicate individual IDs'
    twin_ids = [str(tag)[7:] for actor in actors for tag in actor.tags if str(tag).startswith('TwinId=')]
    assert sorted(twin_ids) == sorted(ids), 'Placed TwinId tags do not match individual registry'
    for item in individuals:
        label = item['id']
        actor = single(label)
        errors = check_transform(actor.get_actor_transform(), item, label)
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        assert component and not isinstance(component, unreal.InstancedStaticMeshComponent), label
        mesh = component.get_editor_property('static_mesh')
        assert mesh and mesh.get_path_name() == expected_mesh_path(item['mesh']), label + ' mesh mismatch'
        assert str(actor.get_folder_path()) == 'GHS/' + item['folder'], label + ' folder mismatch'
        check_materials(component, label)
        report['individuals'].append(dict(id=label, mesh=mesh.get_path_name(), transform_error=errors))
    agvs = [item for item in individuals if item['folder'] == 'Equipment/AGVs']
    chargers = [item for item in individuals if item['folder'] == 'Equipment/Chargers']
    assert len(agvs) == build['robot_count'] == 34
    assert len(chargers) == build['charging_bay_count'] == len(cad['chargers']) == 56
    assert {item['id'] for item in agvs} == {'GHS_AGV_%02d' % i for i in range(1, 35)}
    assert {item['id'] for item in chargers} == {'GHS_CH_%02d' % i for i in range(1, 57)}
    for index, charger in enumerate(chargers):
        assert charger['source_handles'] == cad['chargers'][index]['source_handles'], 'Charger bay CAD references differ'
    for item in agvs:
        assert single(item['id']).get_component_by_class(unreal.StaticMeshComponent).get_editor_property('mobility') == unreal.ComponentMobility.MOVABLE

    expected_fx = {'FX_GHS_AGV_%02d_Diffusion' % i: ('GHS_AGV_%02d' % i, 'Diffusion', 115) for i in range(1, 35)}
    expected_fx.update({'FX_GHS_AGV_%02d_Radar' % i: ('GHS_AGV_%02d' % i, 'Radar', 300) for i in range(29, 35)})
    fx_actors = [actor for actor in actors if actor.get_component_by_class(unreal.DecalComponent)]
    assert len(fx_actors) == build['fx_count'] == 40
    assert {actor.get_actor_label() for actor in fx_actors} == set(expected_fx)
    for label, (parent_label, kind, radius) in expected_fx.items():
        actor, parent = single(label), single(parent_label)
        assert isinstance(actor, unreal.DecalActor), label + ' is not a native DecalActor'
        assert not actor.get_components_by_class(unreal.StaticMeshComponent), label + ' contains an effect mesh'
        assert actor.get_attach_parent_actor() == parent, label + ' is not attached to the correct robot'
        component = actor.get_component_by_class(unreal.DecalComponent)
        assert component.get_editor_property('mobility') == unreal.ComponentMobility.MOVABLE
        assert component.get_editor_property('visible') and not component.get_editor_property('hidden_in_game')
        compare(xyz(component.get_editor_property('decal_size')), [3, radius, radius], .01, label + ' decal size')
        parent_location = xyz(parent.get_actor_location())
        compare(xyz(actor.get_actor_location()), parent_location[:2] + [1.5], .05, label + ' ground position')
        material = component.get_decal_material()
        assert isinstance(material, unreal.MaterialInstanceConstant) and material.get_path_name().startswith(DEST + '/FX/')
        master = material.get_editor_property('parent')
        assert master and master.get_name() == 'M_VR_FX_' + kind
        assert master.get_editor_property('material_domain') == unreal.MaterialDomain.MD_DEFERRED_DECAL
        speed = float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material, 'Speed'))
        assert math.isfinite(speed) and speed > 0, label + ' animation speed invalid'
        report['effects'].append(dict(actor=label, parent=parent_label, kind=kind,
                                      material=material.get_path_name(), mesh_count=0, speed=speed))

    cameras = [actor for actor in actors if actor.get_component_by_class(unreal.CameraComponent)]
    assert len(cameras) == 6 and {actor.get_actor_label() for actor in cameras} == CAMERAS
    unreal.load_module('StaticMeshEditor')
    mesh_editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    original_meshes = [item for item in imported['meshes'] if not item['name'].startswith(('SM_GHS_JoinedWall','SM_GHS_Presentation_'))]
    assert len(original_meshes) == 7
    for item in imported['meshes']:
        mesh = unreal.EditorAssetLibrary.load_asset(item['path'].split('.')[0])
        assert isinstance(mesh, unreal.StaticMesh) and mesh.get_path_name().startswith(DEST + '/Meshes/'), item['path']
        lod_count = mesh_editor.get_lod_count(mesh)
        assert lod_count == item['lod_count'] == (4 if item['name'] in FOUR_LOD or item['name'].startswith('SM_GHS_Presentation_') else 1), item['name'] + ' LOD mismatch'
        materials = []
        for slot in mesh.get_editor_property('static_materials'):
            material = slot.get_editor_property('material_interface')
            assert material and 'WorldGrid' not in material.get_path_name(), item['name'] + ' material missing'
            materials.append(material.get_path_name())
        assert materials, item['name'] + ' no saved materials'
        mesh_result = dict(path=mesh.get_path_name(), lod_count=lod_count, materials=materials,
                           screen_sizes=list(mesh_editor.get_lod_screen_sizes(mesh)),
                           triangles=[mesh.get_num_triangles(i) for i in range(lod_count)],
                           sections=[mesh.get_num_sections(i) for i in range(lod_count)])
        if item['name'] in {'SM_GHS_KukaLowProfileAGV', 'SM_GHS_WallCharger'}:
            compare(mesh_result['screen_sizes'], [1, .12, .04, .012], 1e-6,
                    item['name'] + ' refined LOD screen sizes')
        if item['name'] == 'SM_GHS_KukaLowProfileAGV':
            height_cm = float(mesh.get_bounds().box_extent.z) * 2
            compare([height_cm], [32.4], .02, 'Reimported AGV height')
            mesh_result['height_cm'] = height_cm
        if item['name'] == 'SM_GHS_Shared_PalletCargo':
            assert mesh_result['triangles'][3] >= mesh_result['triangles'][0] * .15, 'Cargo LOD3 is over-reduced'
            assert mesh_result['sections'][3] == 3, 'Cargo LOD3 lost pallet or seam material sections'
            compare(mesh_result['screen_sizes'], [1, .4, .15, .04], 1e-6,
                    'Cargo LOD screen sizes')
            mesh_result['cargo_lod3_refinement_verified'] = True
        report['meshes'].append(mesh_result)
    assert build['conveyors_added'] == 0
    assert not any(item['mesh'] == 'SM_GHS_Shared_Conveyor' for item in groups + individuals), 'Unexpected conveyor placement'
    assert hashlib.sha256(source_level.read_bytes()).hexdigest() == source_sha, 'Original map changed during verification'
    report.update(success=True, actor_count=len(actors), hism_group_count=len(groups),
                  all_hism_world_transforms_verified=True, instanced_count=total_instances,
                  rack_count=len(cad['racks']), pallet_count=len(cad['storage']), column_count=len(cad['columns']), wall_segment_count=330,
                  dock_rack_count=87, charger_count=56, agv_count=34, fx_count=40, camera_count=6,
                  cameras=sorted(CAMERAS), effect_mesh_count=0, four_lod_mesh_count=len(FOUR_LOD),
                  source_level_sha256=source_sha, original_level_preserved=True,
                  coordinate_mapping=registry['coordinate_mapping'], level_saved=False)


def run_legacy():
    if dispatch_cad_rack_verification():
        return
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        main()
    except Exception:
        report['error'] = traceback.format_exc()
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding='utf-8')
        raise
    else:
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding='utf-8')
        unreal.log('GHS_SCENE_VERIFIED ' + json.dumps({key: report[key] for key in
                   ['success', 'actor_count', 'instanced_count', 'rack_count', 'pallet_count', 'agv_count', 'fx_count']}))


if __name__ == '__main__':
    if dispatch_cad_rack_verification():
        pass
    elif (build_state := read_json(ROOT / 'Saved/GHS_BuildReport.json')).get('presentation_refined'):
        import sys
        sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
        import verify_presentation
        verify_presentation.run()
    elif build_state.get('lighting_optimized'):
        import sys
        sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
        import verify_lighting
        verify_lighting.run()
    elif build_state.get('column_outlines_added'):
        import sys
        sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
        import verify_column_outlines
        verify_column_outlines.run()
    elif build_state.get('wall_joined_corrected'):
        import sys
        sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
        import verify_joined_walls
        verify_joined_walls.run()
    elif build_state.get('clearance_corrected'):
        import sys
        sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
        import verify_clearance_scene
        verify_clearance_scene.run()
    else:
        run_legacy()
