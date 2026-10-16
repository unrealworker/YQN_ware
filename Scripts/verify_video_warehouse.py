"""Verify the saved video warehouse in a fresh UE process; no asset mutation."""
import ast
import json
import traceback
from collections import Counter
from pathlib import Path

import unreal

ROOT = Path(r'D:\UEPro\Test')
SOURCE = ROOT / 'SourceAssets/VideoReference'
DEST = '/Game/VideoDigitalTwin'
MAP = '/Game/Maps/VideoDigitalTwinWarehouse'
REPORT = ROOT / 'Saved/VideoWarehouse_Verification.json'
ROBOT_MESHES = {
    'CDD14-1': 'SM_VR_BlueStacker', 'CDD14-2': 'SM_VR_BlueStacker',
    'CDD14-3': 'SM_VR_BlueStacker', 'CDD14-4': 'SM_VR_BlueStacker',
    'CBD50-1': 'SM_VR_OrangeTransporter', 'HR-1': 'SM_VR_WhiteRackRobot',
    'DN-1': 'SM_VR_AlarmRobot',
}
LANDMARKS = [
    'Warehouse_Footprint', 'LIFT_02_BlueElevator', 'GATE_Rack',
    'GATE_UpperCrossing', 'GATE_Transfer', 'CTRL_UpperCrossing',
    'CONVEYOR_FrontTransfer', 'ALARM_DN1_Ring', 'CONE_AvoidanceObstacle',
    'SCAN_AvoidanceFan', 'TARGET_ActiveRoute', 'ALARM_DN1_DiagnosticPanel',
]


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def mesh_size_cm(mesh):
    """Measure the saved mesh locally, independently of a placed actor's yaw."""
    bounds = mesh.get_bounds()
    return [value * 2 for value in xyz(bounds.box_extent)]


def expected_views():
    tree = ast.parse((ROOT / 'Scripts/finalize_video_warehouse.py').read_text(encoding='utf-8'))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'newviews' for t in statement.targets):
            return ast.literal_eval(statement.value)
    raise AssertionError('No final top-level newviews camera specifications found')


def expression_nodes(material, property_name):
    """Read a material graph when this UE Python build exposes graph access."""
    ml = unreal.MaterialEditingLibrary
    errors = []
    if hasattr(ml, 'get_material_property_input_node') and hasattr(ml, 'get_inputs_for_material_expression'):
        try:
            root = ml.get_material_property_input_node(material, property_name)
            pending = [root] if root else []
            nodes = []
            seen = set()
            while pending:
                node = pending.pop()
                if node.get_path_name() in seen:
                    continue
                seen.add(node.get_path_name())
                nodes.append(node)
                pending.extend(value for value in ml.get_inputs_for_material_expression(material, node) if value)
            return nodes, 'MaterialEditingLibrary graph traversal', errors
        except Exception as error:
            errors.append(str(error))
    # Older Python wrappers can still expose the serialized expression array.
    try:
        return list(material.get_editor_property('expressions')), 'Material.expressions', errors
    except Exception as error:
        errors.append(str(error))
    if hasattr(unreal, 'ObjectIterator'):
        try:
            nodes = [node for node in unreal.ObjectIterator(unreal.MaterialExpression)
                     if node.get_outer() == material]
            return nodes, 'ObjectIterator', errors
        except Exception as error:
            errors.append(str(error))
    return None, 'unavailable in this UE Python API', errors


def main():
    lib = unreal.EditorAssetLibrary
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_system = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assert levels.load_level(MAP), 'Could not load the independently saved video map'
    all_actors = actor_system.get_all_level_actors()
    labels = {}
    for actor in all_actors:
        labels.setdefault(actor.get_actor_label(), []).append(actor)

    def single(label):
        matches = labels.get(label, [])
        assert len(matches) == 1, 'Expected exactly one %s, found %d' % (label, len(matches))
        return matches[0]

    for landmark in LANDMARKS:
        single(landmark)
    assert 'VideoTwinPresentationMirrored' in [str(tag) for tag in single('Warehouse_Footprint').tags], 'Final presentation mirror tag is missing'
    assert 'DN-1_State' not in labels, 'Superseded DN-1_State label remains'

    walls_path = SOURCE / 'walls.json'
    walls_spec = json.loads(walls_path.read_text(encoding='utf-8')) if walls_path.is_file() else None
    wall_material_name = 'M_VR_WallVolume' if walls_spec else 'M_VR_Wall'
    wall = lib.load_asset(DEST + '/Materials/' + wall_material_name)
    assert wall and wall.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_TRANSLUCENT, 'Wall material must remain translucent'
    if walls_spec:
        assert not wall.get_editor_property('two_sided'), 'WallVolume must use single-sided volume faces'
    else:
        assert wall.get_editor_property('two_sided'), 'Legacy wall material should be two-sided'
    wall_nodes, wall_graph_api, wall_graph_errors = expression_nodes(wall, unreal.MaterialProperty.MP_OPACITY)
    wall_masks = None
    if wall_nodes is not None:
        masks = [node for node in wall_nodes if isinstance(node, unreal.MaterialExpressionComponentMask)]
        assert masks, 'Wall opacity graph has no component mask'
        wall_masks = [{channel: bool(node.get_editor_property(channel)) for channel in ['r','g','b','a']} for node in masks]
        assert all(mask == dict(r=False,g=False,b=True,a=False) for mask in wall_masks), 'Wall height mask must select B only: ' + str(wall_masks)

    panel = single('ALARM_DN1_DiagnosticPanel')
    panel_component = panel.get_component_by_class(unreal.StaticMeshComponent)
    assert panel_component and panel_component.get_editor_property('static_mesh').get_name() == 'SM_VR_AlarmPanel'
    panel_material = lib.load_asset(DEST + '/Materials/M_VR_AlarmPanel')
    panel_texture = lib.load_asset(DEST + '/Textures/T_VR_AlarmPanel')
    assert panel_material and panel_texture, 'Diagnostic panel texture or material is missing'
    assert any(panel_component.get_material(index) == panel_material for index in range(panel_component.get_num_materials())), 'Diagnostic panel does not use its texture material'
    assert panel_material.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_TRANSLUCENT
    panel_nodes, panel_graph_api, panel_graph_errors = expression_nodes(panel_material, unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    panel_texture_verified = False
    if panel_nodes is not None:
        samples = [node for node in panel_nodes if isinstance(node, unreal.MaterialExpressionTextureSample)]
        assert any(node.get_editor_property('texture') == panel_texture for node in samples), 'Diagnostic material does not sample the alarm texture'
        panel_texture_verified = True
    specs = [json.loads((SOURCE / (stem + '.json')).read_text(encoding='utf-8'))
             for stem in ['storage', 'robots', 'architecture']]
    if (SOURCE / 'hud.json').is_file():
        specs.append(json.loads((SOURCE / 'hud.json').read_text(encoding='utf-8')))
    if walls_spec:
        specs.append(walls_spec)
    mesh_report = []
    expected_materials = {item['name'] for spec in specs for item in spec['materials']}
    for material_name in expected_materials:
        assert material_name.startswith('M_VR_'), material_name
        assert lib.does_asset_exist(DEST + '/Materials/' + material_name), 'Missing saved material ' + material_name
    for spec in specs:
        for item in spec['meshes']:
            mesh = lib.load_asset(DEST + '/Meshes/' + item['name'])
            assert isinstance(mesh, unreal.StaticMesh), 'Missing saved mesh ' + item['name']
            slots = mesh.get_editor_property('static_materials')
            assert slots, 'Mesh has no material slots: ' + item['name']
            material_paths = []
            for slot in slots:
                slot_name = str(slot.get_editor_property('imported_material_slot_name'))
                if slot_name not in item['slots']:
                    slot_name = str(slot.get_editor_property('material_slot_name'))
                assert slot_name in item['slots'], 'Unexpected slot ' + slot_name
                material = slot.get_editor_property('material_interface')
                expected = lib.load_asset(DEST + '/Materials/' + slot_name)
                assert material and expected and material == expected, 'Saved mesh assignment did not persist: ' + item['name'] + '/' + slot_name
                assert 'WorldGrid' not in material.get_path_name(), material.get_path_name()
                material_paths.append(material.get_path_name())
            mesh_report.append(dict(name=item['name'], slot_count=len(slots), materials=material_paths))

    wall_segments_report = []
    hidden_legacy_wall_parts = []
    wall_opaque_materials = []
    if walls_spec:
        assert len(walls_spec['meshes']) == 27, 'Expected 27 new wall segment meshes'
        wall_labels = [item['metadata']['wall_label'] for item in walls_spec['meshes']]
        assert len(set(wall_labels)) == 27, 'New wall labels must be unique'
        for material_name in ['M_VR_WallSection', 'M_VR_WallTrim', 'M_VR_WallFootTrim']:
            material = lib.load_asset(DEST + '/Materials/' + material_name)
            assert material and material.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_OPAQUE, material_name + ' must be opaque'
            wall_opaque_materials.append(material.get_path_name())
        for item in walls_spec['meshes']:
            label = item['metadata']['wall_label']
            actor = single(label)
            component = actor.get_component_by_class(unreal.StaticMeshComponent)
            assert component, 'Wall actor has no StaticMeshComponent: ' + label
            mesh = component.get_editor_property('static_mesh')
            assert mesh and mesh.get_name() == item['name'], 'Wall actor uses incorrect replacement mesh: ' + label
            assert all(abs(value-1) < .0001 for value in xyz(actor.get_actor_scale3d())), 'Wall actor must have unit scale: ' + label
            size = mesh_size_cm(mesh)
            assert abs(size[1]-20) < .25 and abs(size[2]-280) < .25, 'Wall local thickness/height must be 20/280cm: ' + label + ' ' + str(size)
            expected_length = item['metadata']['length'] * 100
            assert abs(size[0]-expected_length) < .25, 'Wall local length differs from manifest: ' + label
            assigned = [component.get_material(index) for index in range(component.get_num_materials())]
            assert wall in assigned, 'Wall actor does not use M_VR_WallVolume: ' + label
            for material in assigned:
                if material and material.get_name() in ['M_VR_WallSection', 'M_VR_WallTrim', 'M_VR_WallFootTrim']:
                    assert material.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_OPAQUE
            for old_label, matches in labels.items():
                if old_label.startswith(label + '_Rim') or old_label.startswith(label + '_Post'):
                    for old_actor in matches:
                        for old_component in old_actor.get_components_by_class(unreal.StaticMeshComponent):
                            assert not old_component.get_editor_property('visible'), 'Legacy wall trim remains visible: ' + old_label
                    hidden_legacy_wall_parts.append(old_label)
            wall_segments_report.append(dict(label=label, mesh=mesh.get_path_name(), local_size_cm=size,
                                             actor_scale=xyz(actor.get_actor_scale3d())))

    scene_components = 0
    scene_material_slots = 0
    meshes_by_label = {}
    for actor in all_actors:
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            assert mesh, 'Empty StaticMeshComponent on ' + actor.get_actor_label()
            meshes_by_label[actor.get_actor_label()] = mesh.get_name()
            scene_components += 1
            assert component.get_num_materials() > 0, 'No scene slots: ' + actor.get_actor_label()
            for index in range(component.get_num_materials()):
                material = component.get_material(index)
                assert material, 'Null scene material: %s[%d]' % (actor.get_actor_label(), index)
                assert material.get_name().startswith('M_VR_'), 'Non-video material on ' + actor.get_actor_label() + ': ' + material.get_path_name()
                assert 'WorldGrid' not in material.get_path_name(), material.get_path_name()
                scene_material_slots += 1

    racks = [label for label, mesh_name in meshes_by_label.items() if mesh_name == 'SM_VR_RackBay']
    assert len(racks) == 32, 'Expected 32 rack bays, got %d' % len(racks)
    robots = []
    for robot_id, expected_mesh in ROBOT_MESHES.items():
        actor = single(robot_id)
        assert meshes_by_label.get(robot_id) == expected_mesh, 'Robot mesh mismatch ' + robot_id
        assert str(actor.get_folder_path()) == 'VideoTwin/Equipment/Robots', robot_id
        robots.append(dict(id=robot_id, mesh=expected_mesh, actor=actor.get_path_name()))
    placed_robots = [a.get_actor_label() for a in all_actors if str(a.get_folder_path()) == 'VideoTwin/Equipment/Robots']
    assert set(placed_robots) == set(ROBOT_MESHES) and len(placed_robots) == 7, placed_robots

    registry = json.loads((SOURCE / 'scene_registry.json').read_text(encoding='utf-8'))
    id_counts = Counter(record['id'] for record in registry)
    assert all(count == 1 for count in id_counts.values()), 'Duplicate registry IDs'
    tagged_ids = []
    for actor in all_actors:
        tagged_ids.extend(str(tag)[7:] for tag in actor.tags if str(tag).startswith('TwinId='))
    assert Counter(tagged_ids) == id_counts, 'Actor TwinId tags and registry IDs differ'
    for record in registry:
        actor = single(record['id'])
        assert meshes_by_label.get(record['id']) == record['mesh'], 'Registry mesh mismatch ' + record['id']
        assert all(abs(actual - expected * 100) < .1 for actual, expected in zip(xyz(actor.get_actor_location()), record['position_m'])), 'Registry position mismatch ' + record['id']
        actual_yaw = actor.get_actor_rotation().yaw
        assert abs((actual_yaw-record['yaw']+180) % 360-180) < .01, 'Registry yaw mismatch ' + record['id']
        assert 'Category=' + record['category'].split('/')[0] in [str(tag) for tag in actor.tags], 'Registry category mismatch ' + record['id']

    camera_report = []
    views = expected_views()
    assert len(views) == 5
    camera_labels = [a.get_actor_label() for a in all_actors if a.get_component_by_class(unreal.CameraComponent)]
    assert set(camera_labels) == {'CAM_Video_' + view[0] for view in views}, camera_labels
    for name, position, target, fov in views:
        camera = single('CAM_Video_' + name)
        component = camera.get_component_by_class(unreal.CameraComponent)
        assert component
        assert abs(component.get_editor_property('field_of_view') - fov) < .01
        assert all(abs(actual-expected*100) < .1 for actual, expected in zip(xyz(camera.get_actor_location()), position)), name
        camera_report.append(dict(view=name, actor=camera.get_path_name(), fov=float(fov), position_m=list(position), target_m=list(target)))

    pallet = single('PAL_West_0_0')
    assert all(abs(value-1) < .0001 for value in xyz(pallet.get_actor_scale3d())), 'Pallet actor has unexpected scale'
    origin, extent = pallet.get_actor_bounds(False)
    size = [value*2 for value in xyz(extent)]
    assert abs(size[0]-120) < 1 and abs(size[1]-100) < 1, 'Pallet is not 1.2 x 1.0m: ' + str(size)
    preserved_maps = []
    for name in ['LogisticsWarehouse', 'SpongeBobScene']:
        path = ROOT / 'Content/Maps' / (name + '.umap')
        assert path.is_file() and path.stat().st_size > 0, 'Existing map file missing ' + name
        assert lib.does_asset_exist('/Game/Maps/' + name), 'Existing map asset missing ' + name
        preserved_maps.append(name)
    report = dict(
        success=True, map=MAP, verification_mode='Reload saved map and assets; run in a fresh UE process',
        actor_count=len(all_actors), landmark_labels=LANDMARKS, rack_count=len(racks), robots=robots,
        robot_actor_count=7, robot_mesh_type_count=len(set(ROBOT_MESHES.values())),
        imported_mesh_count=len(mesh_report), imported_material_count=len(expected_materials),
        mesh_materials=mesh_report, all_saved_mesh_material_assignments_persisted=True,
        static_mesh_components_checked=scene_components, scene_material_slots_checked=scene_material_slots,
        all_scene_static_mesh_slots_nonnull=True, no_world_grid=True, all_scene_materials_prefixed_M_VR=True,
        camera_count=len(camera_report), cameras=camera_report, registry_count=len(registry),
        registry_unique_ids=True, registry_matches_actor_tags_meshes_positions_yaws=True,
        presentation_mirror_tag_present=True, superseded_dn1_state_label_removed=True,
        wall_translucent=True, wall_opacity_component_masks=wall_masks,
        wall_material=wall.get_path_name(), wall_material_two_sided=bool(wall.get_editor_property('two_sided')),
        thick_walls_manifest_present=walls_spec is not None, thick_wall_count=len(wall_segments_report),
        thick_wall_segments=wall_segments_report, wall_opaque_materials=wall_opaque_materials,
        hidden_legacy_wall_parts=hidden_legacy_wall_parts,
        wall_mask_verified=wall_masks is not None, wall_graph_api=wall_graph_api,
        wall_graph_api_errors=wall_graph_errors,
        diagnostic_panel_material=panel_material.get_path_name(), diagnostic_panel_texture=panel_texture.get_path_name(),
        diagnostic_panel_texture_sampling_verified=panel_texture_verified,
        diagnostic_panel_graph_api=panel_graph_api, diagnostic_panel_graph_api_errors=panel_graph_errors,
        camera_specifications_source='Scripts/finalize_video_warehouse.py top-level newviews',
        pallet_size_cm=size, pallet_actor_scale=xyz(pallet.get_actor_scale3d()),
        existing_maps_preserved=preserved_maps,
    )
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    unreal.log('VIDEO_WAREHOUSE_VERIFIED ' + json.dumps({key: report[key] for key in ['success', 'rack_count', 'robot_actor_count', 'imported_mesh_count', 'camera_count', 'registry_count']}))


REPORT.parent.mkdir(parents=True, exist_ok=True)
try:
    main()
except Exception:
    REPORT.write_text(json.dumps(dict(success=False, map=MAP, error=traceback.format_exc()), indent=2), encoding='utf-8')
    raise
