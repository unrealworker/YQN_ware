"""CPU guard tests; these never import Unreal or modify project assets."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import apply_mpr_transport_revision as apply


class TransportApplyTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        name='SM_MPRR_Roads_0_0'
        fbx=apply.REVISION+'/'+name+'.fbx';path=self.root/fbx
        path.parent.mkdir(parents=True);path.write_bytes(b'reviewed FBX source')
        self.base=dict(materials={'MPR3_Asphalt':{}},meshes=[dict(name=name,category='Site')])
        basepath=self.root/apply.SOURCE/'manifest.json';basepath.write_text('{}')
        self.manifest=dict(map=apply.guard.MAP,rebuild_namespace=apply.guard.DEST,transport_revision=True,
            instances={},base_manifest=apply.SOURCE+'/manifest.json',remove_mesh_names=[],
            source_hashes={'manifest.json':apply.sha(basepath)},
            meshes=[dict(name=name,category='Site',fbx=fbx,sha256=apply.sha(path),
                instance_only=False,full_precision_uvs=True,material_roles=['MPR3_Asphalt'])])

    def check(self):return apply.validate_manifest(self.root,self.manifest,self.base)

    def test_accepts_existing_transport_mesh_only(self):
        self.assertEqual(self.check()[0][0]['name'],'SM_MPRR_Roads_0_0')

    def test_nontransport_and_new_package_are_rejected(self):
        for name in ('SM_MPRR_Terrain_0_0','SM_MPRR_Roads_99_99'):
            self.manifest['meshes'][0]['name']=name
            with self.assertRaises(apply.guard.ERROR):self.check()

    def test_railbed_cannot_be_reintroduced(self):
        name='SM_MPRR_Rail_0_0_RailBed'
        self.base['meshes'].append(dict(name=name,category='Site'))
        self.manifest['meshes'][0]['name']=name
        with self.assertRaises(apply.guard.ERROR):self.check()

    def test_source_escape_and_hash_change_are_rejected(self):
        row=self.manifest['meshes'][0];original=row['fbx'];row['fbx']='../outside.fbx'
        with self.assertRaises(apply.guard.ERROR):self.check()
        row['fbx']=original;(self.root/original).write_bytes(b'changed after approval')
        with self.assertRaises(apply.guard.ERROR):self.check()

    def test_unknown_material_and_duplicate_rows_are_rejected(self):
        row=self.manifest['meshes'][0];row['material_roles']=['UnapprovedMaterial']
        with self.assertRaises(apply.guard.ERROR):self.check()
        row['material_roles']=['MPR3_Asphalt'];self.manifest['meshes'].append(deepcopy(row))
        with self.assertRaises(apply.guard.ERROR):self.check()

    def test_content_changes_are_exactly_scoped(self):
        before={'road':dict(sha256='old',bytes=3),'main':dict(sha256='main',bytes=4)}
        after=deepcopy(before);after['road']['sha256']='new'
        self.assertEqual(set(apply.content_scope(before,after,{'road'})),{'road'})
        after['main']['sha256']='changed'
        with self.assertRaises(apply.guard.ERROR):apply.content_scope(before,after,{'road'})
        after=deepcopy(before);del after['road']
        with self.assertRaises(apply.guard.ERROR):apply.content_scope(before,after,{'road'})

    def test_retry_never_overwrites_previous_apply_report(self):
        report=self.root/apply.OUTPUT/'transport_apply.json'
        report.parent.mkdir(parents=True);report.write_text('existing audit evidence')
        with self.assertRaises(apply.guard.ERROR):apply.run(root=self.root,apply=True)
        self.assertEqual(report.read_text(),'existing audit evidence')

    def test_legacy_factory_selector_is_scoped_even_on_failure(self):
        class System:
            value=1
            def get_console_variable_int_value(self,name):return self.value
            def execute_console_command(self,world,command):self.value=int(command.rsplit(' ',1)[1])
        system=System();u=SimpleNamespace(SystemLibrary=system)
        with apply.legacy_fbx_import(u) as original:
            self.assertEqual(original,1);self.assertEqual(system.value,0)
        self.assertEqual(system.value,1)
        with self.assertRaisesRegex(RuntimeError,'import failed'):
            with apply.legacy_fbx_import(u):raise RuntimeError('import failed')
        self.assertEqual(system.value,1)

    def test_resume_never_accepts_unrelated_dirty_packages(self):
        package=apply.guard.DEST+'/Site/Meshes/SM_MPRR_Roads_0_0'
        state=dict(dirty_maps=[apply.guard.MAP],dirty_content=[package])
        apply.assert_resume_clean(state,[package])
        state['dirty_content'].append('/Game/MPRWarehouse/RebuildB50B57/Materials/MI_MPR3_Asphalt')
        with self.assertRaises(apply.guard.ERROR):apply.assert_resume_clean(state,[package])
        state=dict(dirty_maps=['/Game/Maps/GHS'],dirty_content=[])
        with self.assertRaises(apply.guard.ERROR):apply.assert_resume_clean(state,[package])

    def test_explicit_user_deleted_railbed_is_only_skipped(self):
        source=apply.ROOT/apply.SOURCE
        index=apply.read(source/'validation/index.json')
        scene=apply.validation.archived_json(apply.ROOT,index,'after_reload_observed.json.gz')
        base=apply.read(source/'manifest.json');ownership=apply.read(source/'scene_ownership.json')
        names=[r['name'] for r in base['meshes'] if r['name'].endswith('_RailBed')][:2]
        removed,absent=apply.plan_removals(scene,names,base,ownership)
        self.assertEqual(len(removed),2);self.assertEqual(absent,[])
        scene['actors']=[r for r in scene['actors'] if r['guid']!=removed[0]]
        remaining,absent=apply.plan_removals(scene,names,base,ownership)
        self.assertEqual(remaining,removed[1:]);self.assertEqual(len(absent),1)

    def test_effective_slot_changes_require_exact_manifest_and_preserve_other_state(self):
        source=apply.ROOT/apply.SOURCE;index=apply.read(source/'validation/index.json')
        scene=apply.validation.archived_json(apply.ROOT,index,'after_reload_observed.json.gz')
        base=apply.read(source/'manifest.json');ownership=apply.read(source/'scene_ownership.json')
        row=deepcopy(next(r for r in base['meshes'] if r['name'].endswith('_Rails')
                         and r['material_roles']==['MPR3_RailSteel']))
        row['material_roles']=['MPR3_RailSteel','MPR3_Sleepers']
        changes=apply.planned_effective_material_changes(scene,[row],base,ownership)
        self.assertEqual(len(changes),1);change=changes[0]
        after=deepcopy(scene)
        actor=next(a for a in after['actors'] if a['guid']==change['guid'])
        component=next(c for c in actor['components'] if c['name']==change['component'])
        component['materials']=change['after']
        patch=dict(success=True,map_sha256_before=scene['map_file_sha256'],
            map_sha256_after=scene['map_file_sha256'],removed_actor_guids=[],added_actor_guids=[],
            actor_material_changes=changes)
        apply.validation.compare_snapshot(scene,after,ownership,base,patch,{'meshes':[row]})
        with self.assertRaises(apply.guard.ERROR):
            apply.validation.compare_snapshot(scene,after,ownership,base,patch)
        component['transform']['translation_cm'][0]+=1
        with self.assertRaises(apply.guard.ERROR):
            apply.validation.compare_snapshot(scene,after,ownership,base,patch,{'meshes':[row]})
        component['transform']['translation_cm'][0]-=1
        bad=deepcopy(patch);bad['actor_material_changes'][0]['after']=['/Game/Unexpected.Material']
        with self.assertRaises(apply.guard.ERROR):
            apply.validation.compare_snapshot(scene,after,ownership,base,bad,{'meshes':[row]})
        before_actor=next(a for a in scene['actors'] if a['guid']==change['guid'])
        next(c for c in before_actor['components'] if c['name']==change['component'])['materials']=['/Game/UserOverride.Material']
        with self.assertRaises(apply.guard.ERROR):
            apply.planned_effective_material_changes(scene,[row],base,ownership)


if __name__=='__main__':unittest.main()
