"""Pure filesystem regression tests; no Unreal, project scene or Saved state used."""
import ast
import json
from pathlib import Path
import tempfile
import unittest

import mpr_scene_ownership as ownership


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mpr-ownership-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mesh = '/Game/MPRWarehouse/Equipment/Meshes/SM_MPR_Test'
        self.mapfile = self.root/'Content/Maps/MPR_CAD_Warehouse.umap'
        self.meshfile = self.root/'Content/MPRWarehouse/Equipment/Meshes/SM_MPR_Test.uasset'
        for path, data in [(self.mapfile, b'original-map'), (self.meshfile, b'original-mesh')]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.report = {'success': True, 'owner': ownership.DEFAULT_OWNER,
                       'map': ownership.DEFAULT_MAP, 'meshes': [{'path': self.mesh}]}
        self.reportfile = self.root/'Saved/MPR/scene_build.json'
        self.reportfile.parent.mkdir(parents=True)
        self.reportfile.write_text(json.dumps(self.report), encoding='utf-8')

    def bootstrap(self):
        return ownership.bootstrap_from_report(self.root)

    def test_map_edit_refuses_rebuild_without_touching_bytes(self):
        self.bootstrap()
        self.mapfile.write_bytes(b'manual-scene-edit')
        with self.assertRaisesRegex(ownership.OwnershipError, 'Package changed'):
            ownership.verify_owned_scene(self.root, planned_assets=[self.mesh], allow_new=True)
        self.assertEqual(self.mapfile.read_bytes(), b'manual-scene-edit')

    def test_mesh_edit_refuses_rebuild(self):
        self.bootstrap()
        self.meshfile.write_bytes(b'manual-mesh-edit')
        with self.assertRaisesRegex(ownership.OwnershipError, 'Package changed'):
            ownership.verify_owned_scene(self.root, planned_assets=[self.mesh], allow_new=True)

    def test_missing_manifest_refuses_existing_scene_even_with_success_report(self):
        with self.assertRaisesRegex(ownership.OwnershipError, 'no durable ownership'):
            ownership.verify_owned_scene(self.root, planned_assets=[self.mesh], allow_new=True)

    def test_saved_directory_not_required_after_bootstrap(self):
        self.bootstrap()
        self.reportfile.unlink()
        self.reportfile.parent.rmdir()
        self.reportfile.parent.parent.rmdir()
        ownership.verify_owned_scene(self.root, planned_assets=[self.mesh])

    def test_unknown_asset_not_adopted_and_collision_refused(self):
        unknown = '/Game/MPRWarehouse/Equipment/Meshes/SM_User'
        file = self.meshfile.with_name('SM_User.uasset')
        file.write_bytes(b'user-asset')
        data = self.bootstrap()
        self.assertNotIn(unknown, [r['package'] for r in data['packages']])
        ownership.verify_owned_scene(self.root, planned_assets=[self.mesh])
        with self.assertRaisesRegex(ownership.OwnershipError, 'not owned'):
            ownership.verify_owned_scene(self.root, planned_assets=[self.mesh, unknown])
        self.assertEqual(file.read_bytes(), b'user-asset')

    def test_bootstrap_cannot_accept_drift_twice(self):
        self.bootstrap()
        self.mapfile.write_bytes(b'manual-edit')
        with self.assertRaisesRegex(ownership.OwnershipError, 'only run once'):
            self.bootstrap()

    def test_capture_can_refresh_only_map_after_prior_verification(self):
        self.bootstrap()
        token = ownership.verify_owned_scene(self.root)
        before = json.loads((self.root/ownership.MANIFEST).read_text(encoding='utf-8'))
        self.mapfile.write_bytes(b'restored-and-resaved-map')
        after = ownership.refresh_map_hash(self.root, token)
        self.assertEqual(before['packages'][1:], after['packages'][1:])
        ownership.verify_owned_scene(self.root)

    def test_capture_refuses_changed_mesh(self):
        self.bootstrap()
        token = ownership.verify_owned_scene(self.root)
        self.mapfile.write_bytes(b'resaved-map')
        self.meshfile.write_bytes(b'changed-mesh')
        with self.assertRaisesRegex(ownership.OwnershipError, 'Package changed'):
            ownership.refresh_map_hash(self.root, token)

    def test_new_sidecar_is_not_silently_accepted(self):
        self.bootstrap()
        self.meshfile.with_suffix('.ubulk').write_bytes(b'new-sidecar')
        with self.assertRaisesRegex(ownership.OwnershipError, 'Package changed'):
            ownership.verify_owned_scene(self.root)

    def test_clean_first_build_and_success_record(self):
        self.mapfile.unlink(); self.meshfile.unlink()
        token = ownership.verify_owned_scene(self.root, planned_assets=[self.mesh], allow_new=True)
        self.mapfile.write_bytes(b'generated-map'); self.meshfile.write_bytes(b'generated-mesh')
        ownership.record_successful_build(self.root, self.report, token)
        ownership.verify_owned_scene(self.root)

    def test_unchecked_generated_destination_refused(self):
        self.mapfile.unlink(); self.meshfile.unlink()
        token = ownership.verify_owned_scene(self.root, planned_assets=[], allow_new=True)
        self.mapfile.write_bytes(b'generated-map'); self.meshfile.write_bytes(b'generated-mesh')
        with self.assertRaisesRegex(ownership.OwnershipError, 'differs from the destinations'):
            ownership.record_successful_build(self.root, self.report, token)

    def test_created_material_drift_refuses_rebuild_and_map_refresh(self):
        material = '/Game/MPRWarehouse/Materials/M_MPR_HISM_Test'
        material_file = self.root/'Content/MPRWarehouse/Materials/M_MPR_HISM_Test.uasset'
        material_file.parent.mkdir(parents=True)
        material_file.write_bytes(b'generated-material')
        self.report['materials_created'] = [{'path': material, 'source': '/Game/GHS/Material'}]
        self.reportfile.write_text(json.dumps(self.report), encoding='utf-8')
        data = self.bootstrap()
        self.assertIn(material, [row['package'] for row in data['packages']])
        token = ownership.verify_owned_scene(self.root, planned_assets=[self.mesh, material])
        material_file.write_bytes(b'manual-material-edit')
        with self.assertRaisesRegex(ownership.OwnershipError, 'Package changed'):
            ownership.verify_owned_scene(self.root, planned_assets=[self.mesh, material])
        with self.assertRaisesRegex(ownership.OwnershipError, 'Package changed'):
            ownership.refresh_map_hash(self.root, token)
        self.assertEqual(material_file.read_bytes(), b'manual-material-edit')

    def test_unchecked_material_destination_not_adopted(self):
        self.bootstrap()
        material = '/Game/MPRWarehouse/Materials/M_MPR_HISM_Test'
        material_file = self.root/'Content/MPRWarehouse/Materials/M_MPR_HISM_Test.uasset'
        token = ownership.verify_owned_scene(self.root, planned_assets=[self.mesh])
        material_file.parent.mkdir(parents=True)
        material_file.write_bytes(b'unchecked-material')
        self.report['materials_created'] = [{'path': material}]
        with self.assertRaisesRegex(ownership.OwnershipError, 'differs from the destinations'):
            ownership.record_successful_build(self.root, self.report, token)
        with self.assertRaisesRegex(ownership.OwnershipError, 'not owned'):
            ownership.verify_owned_scene(self.root, planned_assets=[self.mesh, material])

    def test_planned_created_material_records_successfully(self):
        self.bootstrap()
        material = '/Game/MPRWarehouse/Materials/M_MPR_HISM_Test'
        material_file = self.root/'Content/MPRWarehouse/Materials/M_MPR_HISM_Test.uasset'
        token = ownership.verify_owned_scene(self.root, planned_assets=[self.mesh, material])
        material_file.parent.mkdir(parents=True)
        material_file.write_bytes(b'new-generated-material')
        self.report['materials_created'] = [{'path': material}]
        ownership.record_successful_build(self.root, self.report, token)
        ownership.verify_owned_scene(self.root, planned_assets=[self.mesh, material])


if __name__ == '__main__':
    for name in ['mpr_scene_ownership.py', 'import_mpr_scene.py', 'test_mpr_scene_ownership.py']:
        path = Path(__file__).with_name(name)
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    unittest.main(verbosity=2)
