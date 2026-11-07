"""Offline regression checks for the exact MPR scene mutation boundary."""
from copy import deepcopy
import unittest
import apply_mpr_sorter_simulation as app


class ApplyScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=app.patch.read(app.ROOT/'SourceAssets/MPR/conveyor_repair_20261106/after_scene.json.gz')
        cls.layout=app.patch.read(app.SRC/'layout.json')

    def setUp(self):
        self.plan=app.derive_plan(self.before,self.layout)
        self.after=deepcopy(self.before)
        for p in self.plan:
            a=next(a for a in self.after['actors'] if a['guid']==p['actor_guid'])
            next(c for c in a['components'] if c['name']==p['component_name'])['mesh']=p['new_mesh']
        self.guid='TEST_NEW_CONTROLLER'
        self.after['actors'].append(dict(guid=self.guid,path='test',name='test',label=app.LABEL,
            **{'class':app.CLASS},folder='MPR/Simulation',tags=['MPRWarehouse','mpr-sorter-simulation-20261107'],
            transform=dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],scale=[1.,1.,1.]),
            tick_enabled=True,collision_enabled=False,hidden=False,attachment_parent=None,
            components=[dict(name=n,**{'class':'/Script/Engine.InstancedStaticMeshComponent'},
                instance_count=0,instance_transforms=[],collision_profile='NoCollision') for n in app.COMPONENT_NAMES]))

    def check(self):return app.validate_scope(self.before,self.after,self.plan,self.guid)

    def test_exact_three_groups_accept(self):
        self.assertEqual(self.check()['changed_hism_groups'],3)
        self.assertEqual(sum(r['instance_count'] for r in self.plan),22)

    def test_pose_drift_rejects_before_mutation(self):
        source=deepcopy(self.before)
        a=next(a for a in source['actors'] if a['guid']==self.plan[0]['actor_guid'])
        c=next(c for c in a['components'] if 'instance_transforms' in c)
        c['instance_transforms'][0]['translation_cm'][0]+=1
        with self.assertRaises(AssertionError):app.derive_plan(source,self.layout)

    def test_group_transform_drift_rejects(self):
        source=deepcopy(self.before)
        next(a for a in source['actors'] if a['guid']==self.plan[0]['actor_guid'])['transform']['translation_cm'][0]+=1
        with self.assertRaises(AssertionError):app.derive_plan(source,self.layout)

    def test_instance_mutation_rejects(self):
        a=next(a for a in self.after['actors'] if a['guid']==self.plan[0]['actor_guid'])
        c=next(c for c in a['components'] if 'instance_transforms' in c)
        c['instance_transforms'][0]['scale'][0]=2
        with self.assertRaises(AssertionError):self.check()

    def test_short_sorter_material_change_rejects(self):
        c=next(c for a in self.after['actors'] for c in a['components'] if 'Short10' in c.get('mesh',''))
        c['materials'][0]='UNAUTHORIZED'
        with self.assertRaises(AssertionError):self.check()

    def test_extra_actor_rejects(self):
        extra=deepcopy(self.after['actors'][-1]);extra['guid']='UNAUTHORIZED'
        self.after['actors'].append(extra)
        with self.assertRaises(AssertionError):self.check()

    def test_missing_actor_rejects(self):
        self.after['actors'].pop(0)
        with self.assertRaises(AssertionError):self.check()

    def test_camera_changes_reject(self):
        a=next(a for a in self.after['actors'] if a['label']=='MPR_ReviewCamera')
        a['transform']['translation_cm'][0]+=1
        with self.assertRaises(AssertionError):self.check()

    def test_baked_runtime_instances_reject(self):
        self.after['actors'][-1]['components'][0]['instance_count']=1
        with self.assertRaises(AssertionError):self.check()


if __name__=='__main__':unittest.main()
