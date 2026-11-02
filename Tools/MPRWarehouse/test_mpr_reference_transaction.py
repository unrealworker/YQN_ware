"""Exercise rollback with isolated temporary files, never project/UE assets."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import mpr_reference_transaction as tx

EXISTING = '/Game/MPRWarehouse/ReferenceV3/Props/Meshes/Existing'
NEW = '/Game/MPRWarehouse/ReferenceV3/Props/Meshes/New'
ASSET = 'Content/MPRWarehouse/ReferenceV3/Props/Meshes/Existing.uasset'
NEW_FILE = 'Content/MPRWarehouse/ReferenceV3/Props/Meshes/New.uasset'
MAP_FILE = 'Content/Maps/MPR_CAD_Warehouse.umap'


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mpr-transaction-test-')
        self.root = Path(self.temp.name)
        for relative, data in [(MAP_FILE, b'original-map'), (tx.OWNERSHIP, b'original-ownership'),
                               (tx.BUILD_REPORT, b'original-success-report'),
                               (ASSET, b'original-mesh'), (ASSET.replace('.uasset', '.ubulk'), b'original-bulk')]:
            self.write(relative, data)
        self.processes = patch.object(tx, 'editor_process_ids', return_value=[])
        self.processes.start()

    def tearDown(self):
        self.processes.stop()
        self.temp.cleanup()

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def begin(self):
        return tx.begin_transaction(self.root, planned_assets=[EXISTING, NEW])

    def failed(self):
        token = self.begin()
        self.write(ASSET, b'overwritten-mesh')
        self.write(ASSET.replace('.uasset', '.ubulk'), b'overwritten-bulk')
        self.write(ASSET.replace('.uasset', '.uexp'), b'new-sidecar')
        self.write(NEW_FILE, b'new-mesh')
        self.write(MAP_FILE, b'new-map')
        self.write(tx.OWNERSHIP, b'new-ownership')
        self.write(tx.BUILD_REPORT, b'final-failed-report')
        tx.record_failure(token, 'failure after asset/map saves')
        return token

    def test_restores_existing_new_sidecars_map_and_ownership(self):
        token = self.failed()
        result = tx.restore_transaction(token)
        self.assertTrue(result['success'])
        self.assertEqual((self.root / ASSET).read_bytes(), b'original-mesh')
        self.assertEqual((self.root / ASSET.replace('.uasset', '.ubulk')).read_bytes(), b'original-bulk')
        self.assertEqual((self.root / MAP_FILE).read_bytes(), b'original-map')
        self.assertEqual((self.root / tx.OWNERSHIP).read_bytes(), b'original-ownership')
        self.assertEqual((self.root / tx.BUILD_REPORT).read_bytes(), b'original-success-report')
        self.assertFalse((self.root / NEW_FILE).exists())
        self.assertFalse((self.root / ASSET.replace('.uasset', '.uexp')).exists())

    def test_post_failure_user_edit_rejects_every_write(self):
        token = self.failed()
        self.write(NEW_FILE, b'user-corrected-new-mesh')
        with self.assertRaisesRegex(tx.TransactionError, 'preserving user edits'):
            tx.restore_transaction(token)
        self.assertEqual((self.root / ASSET).read_bytes(), b'overwritten-mesh')
        self.assertEqual((self.root / MAP_FILE).read_bytes(), b'new-map')
        self.assertEqual((self.root / NEW_FILE).read_bytes(), b'user-corrected-new-mesh')

    def test_unknown_extra_files_are_never_removed(self):
        token = self.failed()
        unknown = 'Content/MPRWarehouse/ReferenceV3/Props/Meshes/User.uasset'
        self.write(unknown, b'user-work')
        tx.restore_transaction(token)
        self.assertEqual((self.root / unknown).read_bytes(), b'user-work')

    def test_active_editor_refuses_restore(self):
        token = self.failed()
        with patch.object(tx, 'editor_process_ids', return_value=[123]):
            with self.assertRaisesRegex(tx.TransactionError, 'active PID'):
                tx.restore_transaction(token)
        self.assertEqual((self.root / ASSET).read_bytes(), b'overwritten-mesh')

    def test_corrupt_backup_refuses_before_any_write(self):
        token = self.failed()
        (Path(token['directory'])/'backup'/ASSET).write_bytes(b'corrupt')
        with self.assertRaisesRegex(tx.TransactionError, 'corrupt'):
            tx.restore_transaction(token)
        self.assertEqual((self.root / MAP_FILE).read_bytes(), b'new-map')

    def test_each_run_backs_up_current_state_not_first_state(self):
        one = self.begin()
        self.write(ASSET, b'successful-v3')
        tx.record_success(one)
        two = self.begin()
        self.write(ASSET, b'broken-v4')
        tx.record_failure(two, 'later run failed')
        self.assertNotEqual(one['directory'], two['directory'])
        tx.restore_transaction(two)
        self.assertEqual((self.root / ASSET).read_bytes(), b'successful-v3')

    def test_successful_run_cannot_be_restored(self):
        token = self.begin()
        tx.record_success(token)
        with self.assertRaisesRegex(tx.TransactionError, 'recorded failed'):
            tx.restore_transaction(token)

    def test_prepared_run_cannot_be_restored_or_failure_overwritten(self):
        token = self.begin()
        with self.assertRaises(tx.TransactionError):
            tx.restore_transaction(token)
        tx.record_failure(token, 'original-error')
        with self.assertRaises(tx.TransactionError):
            tx.record_failure(token, 'do not adopt new hashes')

    def test_unknown_target_or_path_escape_is_rejected(self):
        for package in ['/Game/GHS/Shared', '/Game/MPRWarehouse/../GHS/Shared', '/Engine/BasicShapes/Cube']:
            with self.assertRaises(tx.TransactionError):
                tx.begin_transaction(self.root, planned_assets=[package])

    def test_deleted_original_is_recreated(self):
        token = self.begin()
        (self.root / ASSET).unlink()
        tx.record_failure(token, 'asset removed')
        tx.restore_transaction(token)
        self.assertEqual((self.root / ASSET).read_bytes(), b'original-mesh')

    def test_deleted_new_file_after_failure_is_unknown_change(self):
        token = self.failed()
        (self.root / NEW_FILE).unlink()
        with self.assertRaisesRegex(tx.TransactionError, 'preserving user edits'):
            tx.restore_transaction(token)

    def test_interrupted_atomic_restore_can_resume(self):
        token = self.failed()
        original = tx._atomic_restore
        calls = []
        def interrupt(backup, target):
            calls.append(str(target))
            if len(calls) == 2:
                raise OSError('simulated disk interruption')
            return original(backup, target)
        with patch.object(tx, '_atomic_restore', side_effect=interrupt):
            with self.assertRaises(OSError):
                tx.restore_transaction(token)
        result = tx.restore_transaction(token)
        self.assertTrue(result['success'])
        self.assertEqual((self.root / ASSET).read_bytes(), b'original-mesh')

    def test_manifest_cannot_add_unplanned_file(self):
        token = self.failed()
        path = Path(token['manifest'])
        data = json.loads(path.read_text())
        data['files']['Content/Other/User.uasset'] = {'before_sha256': None, 'backup': None}
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(tx.TransactionError, 'file list differs'):
            tx.restore_transaction(token)

    def test_v4_report_restores_without_touching_v3_report(self):
        report = 'Saved/MPR/reference_v4_build.json'
        self.write(report, b'v4-before')
        token = tx.begin_transaction(self.root, planned_assets=[EXISTING], build_report=report)
        self.write(report, b'v4-failure')
        self.write(tx.BUILD_REPORT, b'independent-v3-log')
        tx.record_failure(token, 'v4 failure')
        tx.restore_transaction(token)
        self.assertEqual((self.root/report).read_bytes(), b'v4-before')
        self.assertEqual((self.root/tx.BUILD_REPORT).read_bytes(), b'independent-v3-log')

    def test_build_report_path_cannot_escape_saved_mpr(self):
        for report in ['../user.json', 'Content/User.json', 'Saved/MPR/../../User.json']:
            with self.assertRaises(tx.TransactionError):
                tx.begin_transaction(self.root, planned_assets=[EXISTING], build_report=report)


if __name__ == '__main__':
    unittest.main()
