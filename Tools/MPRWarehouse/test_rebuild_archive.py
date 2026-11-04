"""Disk-only archive regressions, using disposable synthetic package files."""
import json,tempfile
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import archive_mpr_rebuild_attempt as archive

def fixture(root):
    def put(name,value):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(value if isinstance(value,bytes) else json.dumps(value).encode());return p
    old_map=put('Content/Maps/MPR_CAD_Warehouse.umap',b'old-map')
    old_metadata=put('SourceAssets/MPR/scene_ownership.json',{'original':True})
    old=archive.guard.content_hashes(root)
    old_ownership={old_metadata.relative_to(root).as_posix():archive.sha(old_metadata)}
    put('Content/MPRWarehouse/RebuildB50B57/Site/Mesh.uasset',b'new-mesh')
    new_map=put('Content/Maps/MPR_CAD_Warehouse_B50B57.umap',b'new-map')
    new=archive.guard.assert_old_files(root,old)
    for name in archive.AUDITS:put(archive.OUT+'/'+name,{'name':name})
    put(archive.OUT+'/old_content_hashes.json',old)
    put(archive.OUT+'/old_ownership_hashes.json',old_ownership)
    put(archive.OUT+'/source_map_backup.umap',old_map.read_bytes())
    plan=put(archive.SOURCE+'/protection_plan.json',{'keep':256})
    ownership=dict(owner=archive.guard.TAG,map=archive.guard.MAP,namespace=archive.guard.DEST,
        map_sha256=archive.sha(new_map),source_map_sha256=archive.sha(old_map),new_files=new,
        protection_plan_sha256=archive.sha(plan))
    for file,key in [('old_content_hashes.json','old_content_hashes_sha256'),
                     ('old_ownership_hashes.json','old_ownership_hashes_sha256'),
                     ('source_snapshot.json','source_snapshot_sha256'),
                     ('after_import.json','after_import_sha256'),
                     ('imported_manifest.json','source_manifest_sha256')]:
        ownership[key]=archive.sha(root/archive.OUT/file)
    own=put(archive.OWNERSHIP,ownership)
    put(archive.OUT+'/import_report.json',dict(success=True,ownership_sha256=archive.sha(own),map_sha256=ownership['map_sha256']))
    put(archive.OUT+'/reload_report.json',dict(success=True,map_sha256=ownership['map_sha256']))
    # Current builder inputs are not part of the move set.
    put(archive.SOURCE+'/manifest.json',{'new_build_in_progress':True})
    put(archive.SOURCE+'/model.fbx',b'current-builder-source')
    return archive.prepare(root)

class ArchiveTests(unittest.TestCase):
    def test_exact_archive_and_restore_preserve_old_assets_and_current_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);plan=fixture(root)
            with patch.object(archive,'ensure_project_closed'):
                folder=archive.archive(root,plan)
                self.assertFalse((root/archive.OWNERSHIP).exists())
                self.assertFalse((root/archive.OUT/'import_report.json').exists())
                self.assertTrue((root/archive.SOURCE/'model.fbx').is_file())
                self.assertTrue((root/'Content/Maps/MPR_CAD_Warehouse.umap').is_file())
                archive.restore(root,folder,True)
            for name,h in plan['files'].items():self.assertEqual(archive.sha(root/name),h)
            self.assertEqual(json.loads((folder/'archive_manifest.json').read_text())['status'],'restored')

    def test_old_package_changes_and_new_manual_edits_fail_before_archive(self):
        for relative in ['Content/Maps/MPR_CAD_Warehouse.umap','Content/MPRWarehouse/RebuildB50B57/Site/Mesh.uasset']:
            with self.subTest(relative=relative),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);fixture(root);(root/relative).write_bytes(b'manual-edit')
                with self.assertRaises(archive.guard.ERROR):archive.prepare(root)
                self.assertFalse((root/archive.ARCHIVES).exists())

    def test_move_manifest_cannot_name_an_old_or_unrelated_resource(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);plan=fixture(root)
            for name in ['Content/Maps/MPR_CAD_Warehouse.umap','Content/MPRWarehouse/ReferenceV4/Mesh.uasset']:
                changed=deepcopy(plan);changed['files'][name]='not-relevant'
                with self.assertRaises(archive.guard.ERROR):archive.validate_move_scope(changed)
            with self.assertRaises(archive.guard.ERROR):archive.inside(root,'../outside')

    def test_archive_failure_rolls_back_only_files_it_moved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);plan=fixture(root);original=Path.replace;injected=[False]
            def replace(source,target):
                if source==root/archive.OWNERSHIP and not injected[0]:
                    injected[0]=True;raise OSError('simulated move failure')
                return original(source,target)
            with patch.object(archive,'ensure_project_closed'),patch.object(Path,'replace',replace):
                with self.assertRaisesRegex(OSError,'simulated'):archive.archive(root,plan)
            self.assertEqual(plan['status'],'rolled_back')
            for name,h in plan['files'].items():self.assertEqual(archive.sha(root/name),h)

    def test_restore_refuses_a_newer_attempt_or_metadata_conflict(self):
        for collision in ['Content/MPRWarehouse/RebuildB50B57/Newer.uasset',archive.OWNERSHIP]:
            with self.subTest(collision=collision),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);plan=fixture(root)
                with patch.object(archive,'ensure_project_closed'):folder=archive.archive(root,plan)
                path=root/collision;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'newer')
                with self.assertRaises(archive.guard.ERROR):archive.restore(root,folder)
                self.assertEqual(path.read_bytes(),b'newer')

if __name__=='__main__':unittest.main()
