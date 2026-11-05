"""Mutation tests for the post-retirement validator's protected scene contract."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
import validate_mpr_current as current


class CurrentMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = current.ROOT
        src = root/current.SOURCE
        index = current.read(src/'validation/index.json')
        cls.historical = current.archived_json(root,index,'after_reload_normalized.json.gz')
        cls.baseline = current.archived_json(root,index,'after_reload_observed.json.gz')
        cls.observed = cls.baseline
        cls.ownership = current.read(src/'scene_ownership.json')
        cls.manifest = current.read(src/'manifest.json')
        cls.core = set(cls.ownership['retention']['source_to_copy_guid'].values())
        cls.transport = current.transport_packages(cls.manifest)

    def compare(self, snapshot, patch=None):
        return current.compare_snapshot(self.baseline,snapshot,self.ownership,self.manifest,patch)

    def patch(self):
        return dict(success=True,map_sha256_before=self.baseline['map_file_sha256'],
            map_sha256_after=self.baseline['map_file_sha256'],changed_meshes=[],
            removed_actor_guids=[],added_actor_guids=[])

    def test_exact_saved_snapshot(self):
        result=self.compare(self.observed)
        self.assertEqual(result['core_actor_count'],256)
        self.assertEqual(result['actor_count'],906)

    def test_core_transform_cannot_hide_in_transport_patch(self):
        changed=deepcopy(self.observed)
        actor=next(a for a in changed['actors'] if a['guid'] in self.core)
        actor['transform']['translation_cm'][0]+=1
        with self.assertRaises(current.guard.ERROR):self.compare(changed,self.patch())

    def test_non_core_material_change_is_rejected(self):
        changed=deepcopy(self.observed)
        actor=next(a for a in changed['actors'] if a['guid'] not in self.core
                   and not current.is_transport_actor(a,self.transport) and a['components'][0].get('materials'))
        actor['components'][0]['materials'][0]='/Game/Unexpected.Material'
        with self.assertRaises(current.guard.ERROR):self.compare(changed,self.patch())

    def test_transport_transform_change_is_not_implicitly_allowed(self):
        changed=deepcopy(self.observed)
        actor=next(a for a in changed['actors'] if current.is_transport_actor(a,self.transport))
        actor['transform']['translation_cm'][0]+=10
        with self.assertRaises(current.guard.ERROR):self.compare(changed,self.patch())

    def test_exact_transport_removal_and_coverage(self):
        changed=deepcopy(self.observed)
        actor=next(a for a in changed['actors'] if current.is_transport_actor(a,self.transport))
        changed['actors'].remove(actor)
        changed['world_actor_coverage']=[a for a in changed['world_actor_coverage'] if a['path']!=actor['path']]
        patch=self.patch();patch['removed_actor_guids']=[actor['guid']]
        self.assertEqual(self.compare(changed,patch)['actor_count'],905)
        with self.assertRaises(current.guard.ERROR):self.compare(changed)

    def test_transport_record_cannot_remove_main_actor(self):
        patch=self.patch();patch['removed_actor_guids']=[next(iter(self.core))]
        with self.assertRaises(current.guard.ERROR):self.compare(self.observed,patch)

    def test_explicit_transport_addition_does_not_change_auxiliary_coverage(self):
        changed=deepcopy(self.observed)
        actor=deepcopy(next(a for a in changed['actors'] if current.is_transport_actor(a,self.transport)))
        actor.update(guid='TEST_ADDED_TRANSPORT',name='TestTransportAddition',
            path=current.guard.MAP+'.MPR_CAD_Warehouse_B50B57:PersistentLevel.TestTransportAddition')
        changed['actors'].append(actor)
        patch=self.patch();patch['added_actor_guids']=[actor['guid']];patch['added_actors']=[actor]
        self.assertEqual(self.compare(changed,patch)['actor_count'],907)

    def test_user_baseline_changes_are_preserved_and_history_is_informational(self):
        user=deepcopy(self.observed)
        actor=next(a for a in user['actors'] if a['guid'] in self.core)
        actor['transform']['translation_cm'][0]+=10
        removed=next(a for a in user['actors'] if a['guid'] not in self.core)
        user['actors'].remove(removed)
        user['map_file_sha256']='user-authored-map-hash'
        history=current.historical_differences(self.historical,user,self.ownership)
        self.assertEqual(history['removed_actor_guids'],[removed['guid']])
        self.assertIn(actor['guid'],[r['guid'] for r in history['changed_actors']])
        result=current.compare_snapshot(user,deepcopy(user),self.ownership,self.manifest)
        self.assertEqual(result['actor_count'],905)
        corrupted=deepcopy(user);corrupted['actors'][0]['label']='Unapproved post-audit change'
        with self.assertRaises(current.guard.ERROR):
            current.compare_snapshot(user,corrupted,self.ownership,self.manifest)

    def test_disk_hash_change_requires_manifest(self):
        changed=deepcopy(self.observed);changed['map_file_sha256']='0'*64
        with self.assertRaises(current.guard.ERROR):self.compare(changed)

    def test_retired_asset_reappearance_or_retained_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            new=root/current.MAP_FILE;new.parent.mkdir(parents=True);new.write_bytes(b'new')
            old=root/'Content/Maps/MPR_CAD_Warehouse.umap'
            report=dict(success=True,deleted_files=[old.relative_to(root).as_posix()],
                retained_content_hashes={current.MAP_FILE:current.sha(new)})
            self.assertTrue(current.check_retirement(root,report)['checked'])
            old.write_bytes(b'reappeared')
            with self.assertRaises(current.guard.ERROR):current.check_retirement(root,report)
            old.unlink();new.write_bytes(b'changed')
            with self.assertRaises(current.guard.ERROR):current.check_retirement(root,report)
            # Historical cleanup evidence remains unchanged; only the exact
            # hash supplied by a verified transport contract is accepted.
            before=deepcopy(report)
            result=current.check_retirement(root,report,{current.MAP_FILE:current.sha(new)})
            self.assertTrue(result['checked']);self.assertEqual(report,before)
            with self.assertRaises(current.guard.ERROR):
                current.check_retirement(root,report,{'Content/Unknown.uasset':'unapproved'})


if __name__=='__main__':unittest.main()
