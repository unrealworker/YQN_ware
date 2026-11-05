"""Deletion/replacement boundary tests without importing Unreal or changing a map."""
import copy
import unittest
import mpr_transport_cleanup as patch

class ApplyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.keep='SM_MPRR_Roads_3_-1';self.remove='SM_MPRR_CrossingDeck_3_-1'
        def actor(name):
            return dict(guid=name,path='Level.'+name,**{'class':'/Script/Engine.StaticMeshActor'},attachment_parent=None,
                components=[dict(name='StaticMeshComponent0',**{'class':'/Script/Engine.StaticMeshComponent'},mesh=patch.OLD+name)])
        self.snapshot=dict(map=patch.MAP,actors=[actor(self.keep),actor(self.remove)])
        self.rows=[dict(name=self.keep)];self.removed=[self.remove]

    def plan(self):return patch.plan_from_snapshot(self.snapshot,self.rows,self.removed)

    def test_exact_component_and_actor_identities(self):
        result=self.plan()
        self.assertEqual(result['replacements'][0]['guid'],self.keep)
        self.assertEqual(result['deletions'][0]['guid'],self.remove)
        self.assertFalse(result['already_applied'])

    def test_same_basename_in_another_namespace_is_not_a_target(self):
        self.snapshot['actors'][0]['components'][0]['mesh']='/Game/UserScene/'+self.keep
        with self.assertRaisesRegex(RuntimeError,'Missing reviewed'):self.plan()

    def test_mixed_component_actor_is_not_deleted(self):
        self.snapshot['actors'][1]['components'].append(dict(name='UserMesh',**{'class':'/Script/Engine.StaticMeshComponent'},mesh='/Game/UserScene/UserMesh'))
        with self.assertRaisesRegex(RuntimeError,'mixed/duplicate'):self.plan()

    def test_parent_of_user_actor_is_not_deleted(self):
        self.snapshot['actors'].append(dict(guid='User',path='Level.User',**{'class':'/Script/Engine.Actor'},
            attachment_parent='Level.'+self.remove,components=[]))
        with self.assertRaisesRegex(RuntimeError,'attached transport'):self.plan()

    def test_duplicate_or_missing_targets_fail_closed(self):
        self.snapshot['actors'].append(copy.deepcopy(self.snapshot['actors'][0]))
        with self.assertRaisesRegex(RuntimeError,'Duplicate target'):self.plan()
        self.snapshot['actors']=self.snapshot['actors'][:1]
        with self.assertRaisesRegex(RuntimeError,'Partial/unreviewed'):self.plan()

    def test_completed_patch_is_idempotent(self):
        self.snapshot['actors']=self.snapshot['actors'][:1]
        self.snapshot['actors'][0]['components'][0]['mesh']=patch.DEST+'/Meshes/'+self.keep
        result=self.plan()
        self.assertTrue(result['already_applied']);self.assertEqual(result['deletions'],[])

if __name__=='__main__':unittest.main(verbosity=2)
