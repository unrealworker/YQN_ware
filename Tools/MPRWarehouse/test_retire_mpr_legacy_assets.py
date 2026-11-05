"""Deletion guard tests use temporary package stand-ins, never the UE workspace."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rebuild_preservation as guard
import retire_mpr_legacy_assets as cleanup


class CleanupGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.out = self.root / cleanup.OUT_REL
        self.out.mkdir(parents=True)
        self.old_asset = '/Game/MPRWarehouse/Environment/Meshes/Old'
        self.keep_asset = '/Game/MPRWarehouse/ReferenceV4/Materials/Shared'
        self.paths = {
            cleanup.OLD_MAP: 'Content/Maps/MPR_CAD_Warehouse.umap',
            cleanup.NEW_MAP: 'Content/Maps/MPR_CAD_Warehouse_B50B57.umap',
            self.old_asset: 'Content/MPRWarehouse/Environment/Meshes/Old.uasset',
            self.keep_asset: 'Content/MPRWarehouse/ReferenceV4/Materials/Shared.uasset',
        }
        for package, name in self.paths.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(('package ' + package).encode())
        tool = self.root / 'Tools/MPRWarehouse/retire_mpr_legacy_assets.py'
        tool.parent.mkdir(parents=True)
        tool.write_text('test stand-in', encoding='utf8')
        self.files, _ = cleanup.inventory(self.root)
        self.snapshot = dict(map=cleanup.NEW_MAP, dirty_maps=[], dirty_content=[],
                             actors=[dict(guid='UserModifiedActor', transform='latest-user-state')],
                             map_file_sha256=self.files[self.paths[cleanup.NEW_MAP]]['sha256'])
        snapshot_path = self.out / 'legacy_audit_scene_snapshot.json'
        cleanup.write(snapshot_path, self.snapshot)
        self.order = [cleanup.OLD_MAP, self.old_asset]
        rows = [dict(package=p, files={self.paths[p]: self.files[self.paths[p]]}) for p in self.order]
        self.baseline = dict(success=True, mode='audit', root=str(self.root), current_map=cleanup.NEW_MAP,
            map_sha256=self.snapshot['map_file_sha256'], scene_snapshot=snapshot_path.name,
            scene_snapshot_sha256=cleanup.sha(snapshot_path), all_content_files=self.files,
            deletable=rows, explicit_protected=[], cyclic_or_cycle_dependent_packages=[],
            deletion_order=self.order, eligible_for_review=True, retained_count=1,
            scene_guids=['UserModifiedActor'])
        cleanup.write(self.out / 'legacy_audit.json', self.baseline)
        self.deleted = []
        self.external_ref = False
        self.fail_package = None
        self.dirty = False
        registry = SimpleNamespace(
            get_referencers=lambda p, o: ['/Game/Unrelated'] if self.external_ref else [],
            scan_paths_synchronous=lambda *a: None,
            wait_for_completion=lambda: None)
        self.u = SimpleNamespace(
            Paths=SimpleNamespace(project_dir=lambda: str(self.root), convert_relative_path_to_full=lambda p: p),
            AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda: registry),
            AssetRegistryDependencyOptions=lambda **kwargs: kwargs,
            EditorLoadingAndSavingUtils=SimpleNamespace(
                get_dirty_map_packages=lambda: [cleanup.NEW_MAP] if self.dirty else [],
                get_dirty_content_packages=lambda: []),
            EditorAssetLibrary=SimpleNamespace(delete_asset=self.delete_asset,
                does_asset_exist=lambda p: (self.root / self.paths[p]).exists()))

    def delete_asset(self, package):
        if package == self.fail_package:
            return False
        # Only the fake API removes temporary stand-ins. Production code has no
        # unlink/remove fallback and cannot erase the user's package bytes.
        (self.root / self.paths[package]).unlink()
        self.deleted.append(package)
        return True

    def audit(self, u, **kwargs):
        fresh = copy.deepcopy(self.baseline)
        fresh['scene_snapshot'] = 'legacy_predelete_scene_snapshot.json'
        cleanup.write(self.out / fresh['scene_snapshot'], self.snapshot)
        cleanup.write(self.out / 'legacy_predelete.json', fresh)
        return fresh

    def run_apply(self):
        with patch.object(cleanup, 'audit', side_effect=self.audit), patch.object(guard, 'capture', return_value=self.snapshot):
            return cleanup.apply(self.u)

    def test_success_preserves_latest_user_scene_and_shared_package(self):
        result = self.run_apply()
        self.assertTrue(result['success'])
        self.assertEqual(self.deleted, self.order)
        self.assertEqual(result['scene_guids'], ['UserModifiedActor'])
        self.assertEqual(result['scene_actor_count'], 1)
        for package in [cleanup.NEW_MAP, self.keep_asset]:
            self.assertEqual(cleanup.sha(self.root / self.paths[package]), self.files[self.paths[package]]['sha256'])
        for package in self.order:
            self.assertEqual(cleanup.sha(self.out / 'backup' / self.paths[package]), self.files[self.paths[package]]['sha256'])

    def test_changed_file_blocks_before_first_delete(self):
        (self.root / self.paths[self.old_asset]).write_bytes(b'user changed')
        with self.assertRaisesRegex(RuntimeError, 'changed before backup'):
            self.run_apply()
        self.assertEqual(self.deleted, [])

    def test_new_external_reference_blocks_before_first_delete(self):
        self.external_ref = True
        with self.assertRaisesRegex(RuntimeError, 'New external reference'):
            self.run_apply()
        self.assertEqual(self.deleted, [])

    def test_dirty_package_blocks_before_first_delete(self):
        self.dirty = True
        with self.assertRaisesRegex(RuntimeError, 'Unsaved package'):
            self.run_apply()
        self.assertEqual(self.deleted, [])

    def test_refused_api_keeps_recovery_progress_and_backups(self):
        self.fail_package = self.old_asset
        with self.assertRaisesRegex(RuntimeError, 'UE refused'):
            self.run_apply()
        progress = cleanup.read(self.out / 'legacy_delete.json')
        self.assertFalse(progress['success'])
        self.assertEqual(progress['deleted_packages'], [cleanup.OLD_MAP])
        self.assertEqual(progress['in_progress_package'], self.old_asset)
        self.assertTrue((self.root / self.paths[self.old_asset]).is_file())
        self.assertTrue((self.out / 'backup' / self.paths[self.old_asset]).is_file())

    def test_closure_protects_transitive_shared_dependencies_and_cycles(self):
        candidates = {'a', 'b', 'c', 'd'}
        dependencies = {'a': ['b'], 'b': ['a', 'c'], 'c': [], 'd': []}
        refs = {'a': ['b', 'outside'], 'b': ['a'], 'c': ['b'], 'd': []}
        keep, remove, _ = cleanup.protected_closure(candidates, dependencies, refs)
        self.assertEqual(keep, {'a', 'b', 'c'})
        self.assertEqual(remove, {'d'})
        refs['a'] = ['b']
        keep, remove, _ = cleanup.protected_closure(candidates, dependencies, refs)
        self.assertFalse(keep)
        self.assertEqual(cleanup.deletion_order(remove, dependencies), (['d'], ['a', 'b', 'c']))


if __name__ == '__main__':
    unittest.main()
