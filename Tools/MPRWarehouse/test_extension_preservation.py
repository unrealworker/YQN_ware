"""Append-only scene safeguards; no Unreal runtime or project asset writes."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import extension_preservation as guard
from test_mpr_interior_preservation import baseline as old_baseline, actor


def baseline():
    value = old_baseline()
    value.update(preservation_scope=guard.SCOPE, dirty_maps=[], dirty_content=[],
                 assets_hashed=True, frozen_files={})
    value['actors'][3]['render_settings'] = {'intensity': 3.8}
    return value


def addition():
    return actor('extension', 'MPR_Ext_House', guard.EXTENSION_FOLDER + '/Buildings',
                 tags=[guard.EXTENSION_TAG], components=[
                     {'name': 'Mesh', 'mesh': guard.EXTENSION_NAMESPACE + '/House.House'}])


class ExtensionPreservationTests(unittest.TestCase):
    def setUp(self):
        self.before = baseline()
        self.after = deepcopy(self.before)

    def check(self):
        return guard.assert_preserved(self.before, self.after)

    def test_append_new_namespace_preserves_every_existing_actor(self):
        self.after['actors'].append(addition())
        self.after['asset_hashes'][guard.EXTENSION_NAMESPACE + '/House'] = {
            'Content/MPRWarehouse/ExtensionB50B57/House.uasset': 'newhash'}
        result = self.check()
        self.assertEqual(result['protected_actors'], 5)
        self.assertEqual(result['protected_instances'], 2)
        self.assertEqual(result['new_actor_guids'], ['extension'])

    def test_existing_exterior_cannot_be_replaced(self):
        self.after['actors'].pop(2)
        with self.assertRaisesRegex(guard.PreservationError, 'disappeared/recreated'):
            self.check()

    def test_camera_framing_is_frozen(self):
        self.after['actors'][4]['transform'][0] = 100
        with self.assertRaisesRegex(guard.PreservationError, 'MPR_WarehouseCamera'):
            self.check()

    def test_live_light_settings_are_frozen(self):
        self.after['actors'][3]['render_settings']['intensity'] = 4.0
        with self.assertRaisesRegex(guard.PreservationError, 'render_settings'):
            self.check()

    def test_instance_order_and_per_instance_data_are_frozen(self):
        self.after['actors'][1]['components'][0]['instance_transforms'].reverse()
        with self.assertRaisesRegex(guard.PreservationError, 'components'):
            self.check()

    def test_existing_dependency_reimport_fails_even_if_path_stays_the_same(self):
        self.after['asset_hashes']['/Game/Shared/M']['Content/Shared/M.uasset'] = 'changed'
        with self.assertRaisesRegex(guard.PreservationError, 'dependency package'):
            self.check()

    def test_unsaved_existing_material_edit_fails_before_bytes_change(self):
        self.after['dirty_content'] = ['/Game/Shared/M']
        with self.assertRaisesRegex(guard.PreservationError, 'dirty content'):
            self.check()

    def test_dirty_baseline_fails_instead_of_overwriting_live_work(self):
        self.before['dirty_maps'] = [guard.MAP]
        with self.assertRaisesRegex(guard.PreservationError, 'Baseline has unsaved'):
            self.check()

    def test_unknown_actor_and_near_matching_folder_fail(self):
        row = addition()
        row['folder'] = guard.EXTENSION_FOLDER + 'Other/Buildings'
        self.after['actors'].append(row)
        with self.assertRaisesRegex(guard.PreservationError, 'Unexpected new actor'):
            self.check()

    def test_new_asset_outside_namespace_fails(self):
        self.after['asset_hashes']['/Game/MPRWarehouse/ReferenceV4/Bad'] = {'bad': 'new'}
        with self.assertRaisesRegex(guard.PreservationError, 'outside extension namespace'):
            self.check()

    def test_tagged_new_lighting_cannot_change_whole_scene(self):
        row = addition()
        row['components'][0]['render_settings'] = {'intensity': 10}
        self.after['actors'].append(row)
        with self.assertRaisesRegex(guard.PreservationError, 'render controller'):
            self.check()

    def test_actor_attachment_to_existing_actor_is_rejected(self):
        row = addition()
        row['attachment_parent'] = self.before['actors'][0]['path']
        self.after['actors'].append(row)
        with self.assertRaisesRegex(guard.PreservationError, 'attached to existing'):
            self.check()

    def test_component_cannot_attach_to_a_protected_actors_component(self):
        row = addition()
        row['components'][0]['attach_parent'] = self.before['actors'][0]['path'] + '.Mesh'
        self.after['actors'].append(row)
        with self.assertRaisesRegex(guard.PreservationError, 'component attached to existing'):
            self.check()

    def test_unhashed_or_legacy_snapshot_cannot_claim_protection(self):
        for key, value in [('assets_hashed', False), ('preservation_scope', 'interior-only')]:
            with self.subTest(key=key):
                saved = self.before[key]
                self.before[key] = value
                with self.assertRaises(guard.PreservationError):
                    self.check()
                self.before[key] = saved

    def test_duplicate_guids_and_unexpected_reloaded_additions_fail(self):
        self.after['actors'].append(deepcopy(self.after['actors'][0]))
        with self.assertRaisesRegex(guard.PreservationError, 'Duplicate actor GUID'):
            self.check()
        self.after['actors'][-1] = addition()
        with self.assertRaisesRegex(guard.PreservationError, 'Expected new actor GUIDs'):
            guard.assert_preserved(self.before, self.after, expected_new_guids=['wrong'])


class TerminalReplacementTests(unittest.TestCase):
    def setUp(self):
        self.before = baseline()
        name = 'SM_MPR4_Site_RoadTerminalRoads'
        self.old_mesh = '/Game/MPRWarehouse/ReferenceV4/Site/Meshes/' + name + '.' + name
        self.new_mesh = guard.EXTENSION_NAMESPACE + '/RoadJoin.RoadJoin'
        self.before['actors'].append(actor('terminal', name.removeprefix('SM_'),
            'MPR/ReferenceV4/Site', tags=['MPRWarehouse', 'mpr-reference-exterior-v4'],
            components=[{'name': 'StaticMeshComponent0', 'class': '/Script/Engine.StaticMeshComponent',
                'mesh': self.old_mesh, 'materials': ['/Game/Shared/M.M'],
                'cast_shadow': False, 'transform': [0, 0, 0]}]))
        self.before['asset_hashes'][self.old_mesh.split('.')[0]] = {'terminal.uasset': 'oldbytes'}
        self.after = deepcopy(self.before)
        self.after['actors'][-1]['components'][0]['mesh'] = self.new_mesh
        self.after['asset_hashes'][self.new_mesh.split('.')[0]] = {'new.uasset': 'newbytes'}
        self.plan = [{'actor_guid': 'terminal', 'component_name': 'StaticMeshComponent0',
                      'old_mesh': self.old_mesh, 'new_mesh': self.new_mesh}]

    def check(self):
        return guard.assert_preserved(self.before, self.after, allowed_mesh_replacements=self.plan)

    def test_only_exact_approved_mesh_swap_passes(self):
        result = self.check()
        self.assertEqual(result['approved_mesh_replacements'], self.plan)
        self.assertEqual(result['unchanged_actor_count'], 5)
        self.assertEqual(guard.terminal_mesh_replacement_plan(self.before,
                         {self.old_mesh: self.new_mesh}), self.plan)

    def test_without_allowlist_mesh_swap_is_rejected(self):
        with self.assertRaisesRegex(guard.PreservationError, 'Existing actor changed'):
            guard.assert_preserved(self.before, self.after)

    def test_shadow_material_transform_and_guid_changes_still_fail(self):
        for field, value in [('cast_shadow', True), ('materials', []), ('transform', [1, 0, 0])]:
            with self.subTest(field=field):
                original = deepcopy(self.after['actors'][-1]['components'][0][field])
                self.after['actors'][-1]['components'][0][field] = value
                with self.assertRaisesRegex(guard.PreservationError, 'Existing actor changed'):
                    self.check()
                self.after['actors'][-1]['components'][0][field] = original
        self.after['actors'][-1]['guid'] = 'replacement-guid'
        with self.assertRaisesRegex(guard.PreservationError, 'disappeared/recreated'):
            self.check()

    def test_plan_cannot_target_a_building_or_wrong_baseline_mesh(self):
        for field, value in [('actor_guid', 'a'), ('old_mesh', '/Game/Shared/Rack.Rack'),
                             ('component_name', 'Missing')]:
            with self.subTest(field=field):
                original = self.plan[0][field]
                self.plan[0][field] = value
                with self.assertRaises(guard.PreservationError):
                    self.check()
                self.plan[0][field] = original

    def test_new_mesh_must_be_exact_namespaced_asset_and_applied(self):
        for value in ['/Game/Other/Road.Road', guard.EXTENSION_NAMESPACE + 'Other/Road.Road',
                      guard.EXTENSION_NAMESPACE + '/Road.WrongObjectName']:
            with self.subTest(value=value):
                self.plan[0]['new_mesh'] = value
                with self.assertRaises(guard.PreservationError):
                    self.check()
        self.plan[0]['new_mesh'] = self.new_mesh
        self.after['actors'][-1]['components'][0]['mesh'] = self.old_mesh
        with self.assertRaisesRegex(guard.PreservationError, 'replacement was not applied'):
            self.check()

    def test_old_mesh_bytes_remain_protected_after_reference_swap(self):
        self.after['asset_hashes'][self.old_mesh.split('.')[0]]['terminal.uasset'] = 'mutated'
        with self.assertRaisesRegex(guard.PreservationError, 'dependency package'):
            self.check()

    def test_duplicates_unknown_fields_and_hism_are_rejected(self):
        self.plan.append(deepcopy(self.plan[0]))
        with self.assertRaisesRegex(guard.PreservationError, 'Duplicate'):
            self.check()
        self.plan.pop()
        self.plan[0]['allow_shadow_change'] = True
        with self.assertRaisesRegex(guard.PreservationError, 'exactly'):
            self.check()
        self.plan[0].pop('allow_shadow_change')
        self.before['actors'][-1]['components'][0]['instance_count'] = 1
        with self.assertRaisesRegex(guard.PreservationError, 'StaticMeshComponent'):
            self.check()


class PackageGuardTests(unittest.TestCase):
    def test_dependency_hash_covers_sidecars_and_map_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'Content/Test').mkdir(parents=True)
            for name in ['Material.uasset', 'Material.ubulk', 'OtherMap.umap']:
                (root / 'Content/Test' / name).write_bytes(b'original')
            hashes = guard.package_hashes(root, ['/Game/Test/Material.Material', '/Game/Test/OtherMap'])
            self.assertEqual(len(hashes['/Game/Test/Material']), 2)
            self.assertIn('Content/Test/OtherMap.umap', hashes['/Game/Test/OtherMap'])
            snapshot = {'asset_hashes': hashes, 'frozen_files': {}}
            guard.verify_protected_files(snapshot, project_root=root)
            (root / 'Content/Test/Material.uexp').write_bytes(b'new sidecar')
            with self.assertRaisesRegex(guard.PreservationError, 'dependency package'):
                guard.verify_protected_files(snapshot, project_root=root)

    def test_new_package_preflight_rejects_existing_path_and_prefix_trick(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = guard.EXTENSION_NAMESPACE + '/Road'
            guard.assert_new_package_destinations(root, [name])
            path = root / 'Content/MPRWarehouse/ExtensionB50B57/Road.ubulk'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'leftover')
            with self.assertRaisesRegex(guard.PreservationError, 'already exists'):
                guard.assert_new_package_destinations(root, [name])
            with self.assertRaisesRegex(guard.PreservationError, 'namespace'):
                guard.assert_new_package_destinations(root, [guard.EXTENSION_NAMESPACE + 'Else/Road'])

    def test_missing_or_path_traversal_dependencies_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            for package in ['/Game/Missing', '/Game/../Outside', '/Game/Foo//Bar']:
                with self.subTest(package=package), self.assertRaises(guard.PreservationError):
                    guard.package_hashes(tmp, [package])

    def test_dependency_closure_includes_map_soft_refs_and_all_actor_classes(self):
        class Registry:
            def get_dependencies(self, package, options):
                return {'/Game/TestMap': ['/Game/HiddenMaterial'],
                        '/Game/Exterior': ['/Game/BaseMaterial'],
                        '/Game/BaseMaterial': ['/Game/BaseTexture']}.get(package, [])
        class U:
            class AssetRegistryHelpers:
                get_asset_registry = staticmethod(Registry)
            AssetRegistryDependencyOptions = staticmethod(lambda **kwargs: kwargs)
        value = {'map': '/Game/TestMap', 'actors': [
            {'class': '/Game/Exterior.Exterior_C', 'components': []}]}
        found = guard.dependency_packages(U, value)
        self.assertEqual(found, {'/Game/HiddenMaterial', '/Game/Exterior',
                                 '/Game/BaseMaterial', '/Game/BaseTexture'})

    def test_unknown_dependency_node_fails_closed_with_package_name(self):
        registry=SimpleNamespace(get_dependencies=lambda package,options: None)
        u=SimpleNamespace(AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda:registry),
                          AssetRegistryDependencyOptions=lambda **kwargs:kwargs)
        with self.assertRaisesRegex(guard.PreservationError,
                                    'dependency node unavailable: /Game/NewMesh'):
            guard.dependency_packages(u,dict(map='/Game/NewMesh',actors=[]))

    def test_known_leaf_empty_array_is_valid(self):
        registry=SimpleNamespace(get_dependencies=lambda package,options: [])
        u=SimpleNamespace(AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda:registry),
                          AssetRegistryDependencyOptions=lambda **kwargs:kwargs)
        self.assertEqual(guard.dependency_packages(u,dict(map='/Game/Map',actors=[]),
                                                  additional_packages=['/Game/Leaf']),{'/Game/Leaf'})

    def test_capture_records_camera_settings_and_uses_full_dependency_scope(self):
        class Struct:
            def export_text(self):
                return '(bOverride_BloomIntensity=True,BloomIntensity=0.0)'
        class Camera:
            def get_name(self):
                return 'Camera'
            def get_editor_property(self, name):
                if name == 'post_process_settings':
                    return Struct()
                return {'projection_mode': 'PERSPECTIVE', 'field_of_view': 52.5,
                        'aspect_ratio': 1.777, 'constrain_aspect_ratio': False,
                        'ortho_width': 512.0, 'post_process_blend_weight': 1.0}[name]
        class Actor:
            def get_editor_property(self, name):
                self.assert_name = name
                return 'camera-guid'
            def get_components_by_class(self, _):
                return [Camera()]
        class ActorSubsystem:
            def get_all_level_actors(self):
                return [Actor()]
        u = SimpleNamespace(EditorActorSubsystem=ActorSubsystem, ActorComponent=object,
                            get_editor_subsystem=lambda _: ActorSubsystem(),
                            CameraComponent=Camera,
                            GuidLibrary=SimpleNamespace(conv_guid_to_string=lambda guid: guid))
        state = baseline()
        state['actors'] = [actor('camera-guid', 'Camera', 'MPR/Cameras',
                                components=[{'name': 'Camera', 'class': '/Script/Engine.CameraComponent'}])]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'Content/Maps').mkdir(parents=True)
            (root / 'Content/Maps/MPR_CAD_Warehouse.umap').write_bytes(b'map')
            with patch.object(guard.interior, 'capture_editor_snapshot', return_value=state), \
                 patch.object(guard, 'dependency_packages', return_value=set()) as dependencies:
                result = guard.capture_editor_snapshot(u, project_root=root)
            self.assertEqual(dependencies.call_count, 1)
            camera = result['actors'][0]['components'][0]['render_settings']
            self.assertEqual(camera['field_of_view'], 52.5)
            self.assertIn('bOverride_BloomIntensity=True', camera['post_process_settings'])
            self.assertEqual(result['protected_digest'], guard.canonical_digest(result['actors']))
            self.assertTrue(result['assets_hashed'])

    def test_explicit_frozen_sources_detect_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'scene.json'
            path.write_bytes(b'original')
            snapshot = {'asset_hashes': {}, 'frozen_files': guard._frozen_file_hashes(root, [path])}
            guard.verify_protected_files(snapshot, project_root=root)
            path.write_bytes(b'manual edit')
            with self.assertRaisesRegex(guard.PreservationError, 'source/file bytes'):
                guard.verify_protected_files(snapshot, project_root=root)


if __name__ == '__main__':
    unittest.main()
