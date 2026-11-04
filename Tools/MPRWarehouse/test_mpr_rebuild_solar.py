"""Focused, native-free regressions for the five explicitly approved PV replacements."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import rebuild_preservation as guard

ROOT=Path(__file__).resolve().parents[2]

def specs():
    rows=[]
    for guid,(_,suffix) in guard.SOLAR_IDENTITIES.items():
        old='SM_MPR4_SolarBank_'+suffix;new='SM_MPRR_SolarBank_'+suffix
        rows.append(dict(source_guid=guid,component_name='StaticMeshComponent0',
            source_mesh='/Game/MPRWarehouse/ReferenceV4/Architecture/Meshes/'+old+'.'+old,
            target_mesh=guard.DEST+'/Architecture/Meshes/'+new+'.'+new))
    return rows

def scene():
    actors=[];plan=dict(actors=[]);mapping={}
    for spec in specs():
        guid=spec['source_guid'];name,suffix=guard.SOLAR_IDENTITIES[guid]
        path=guard.SOURCE_MAP+'.MPR_CAD_Warehouse:PersistentLevel.'+name
        transform=dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],scale=[1.,1.,1.])
        actor=dict(guid=guid,name=name,label='MPR4_SolarBank_'+suffix,path=path,
            folder='MPR/ReferenceV4/Architecture/RemovableRoof',tags=['MPRWarehouse'],
            attachment_parent=None,transform=transform,components=[dict(name='StaticMeshComponent0',
                mesh=spec['source_mesh'],materials=['/Game/MPRWarehouse/ReferenceV4/Materials/MI_'+r+'.MI_'+r for r in guard.SOLAR_ROLES],
                transform=deepcopy(transform),cast_shadow=True,**{'class':'/Script/Engine.StaticMeshComponent'})],
            **{'class':'/Script/Engine.StaticMeshActor'})
        actors.append(actor);plan['actors'].append(dict(name=name,guid=guid,action='keep_main_shell'));mapping[guid]='copy-'+guid
    source=dict(map=guard.SOURCE_MAP,actors=actors,world_settings={})
    current=guard.remap(source,guard.SOURCE_MAP,guard.MAP);current['map']=guard.MAP
    for actor in current['actors']:actor['guid']=mapping[actor['guid']]
    changes=guard.expected_retained_mesh_changes(source,plan,mapping,specs())
    for actor in current['actors']:
        change=next(c for c in changes if c['actor_guid']==actor['guid'])
        actor['components'][0]['mesh']=change['after']
    return source,current,plan,mapping,changes

class SolarRetentionTests(unittest.TestCase):
    def validate(self,source,current,plan,mapping,changes):
        return guard.assert_retained(source,current,plan,guid_map=mapping,mesh_changes=changes,mesh_overrides=specs())

    def test_five_mesh_fields_only_and_exact_original_to_copy_guids(self):
        args=scene();audit=self.validate(*args)
        self.assertEqual(audit['retained_actor_count'],5)
        self.assertEqual(audit['source_to_copy_guid'],args[3])
        with self.assertRaisesRegex(guard.ERROR,'state changed'):
            guard.assert_retained(args[0],args[1],args[2])

    def test_replacement_does_not_waive_transform_material_shadow_or_geometry_elsewhere(self):
        mutations=[lambda c:c.update(transform=dict(translation_cm=[0.,0.,.00001])),
            lambda c:c['materials'].reverse(),lambda c:c.update(cast_shadow=False),
            lambda c:c.update(instance_count=1),lambda c:c.update(mesh='/Game/Other.Other')]
        for mutate in mutations:
            args=scene();mutate(args[1]['actors'][0]['components'][0])
            with self.subTest(mutate=mutate),self.assertRaises(guard.ERROR):self.validate(*args)

    def test_specs_cannot_authorize_other_actor_component_source_or_destination(self):
        for key,value in [('source_guid','other'),('component_name','Other'),
                          ('source_mesh','/Game/Old.Other'),('target_mesh',guard.DEST+'/Architecture/Meshes/Other.Other')]:
            rows=specs();rows[0][key]=value
            with self.subTest(key=key),self.assertRaises(guard.ERROR):guard.retained_mesh_spec_map(rows)
        for rows in [specs()[:4],specs()+specs()[:1]]:
            with self.assertRaises(guard.ERROR):guard.retained_mesh_spec_map(rows)

    def test_records_cannot_fake_or_omit_actual_exception(self):
        for key,value in [('source_guid','other'),('actor_guid','other'),('component_name','Other'),('after','other'),('before','other')]:
            args=scene();args[4][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(guard.ERROR,'Mesh change record'):self.validate(*args)

    def test_interior_and_altered_source_slot_order_are_never_authorized(self):
        args=scene();args[2]['actors'][0]['action']='keep_interior'
        with self.assertRaisesRegex(guard.ERROR,'non-shell'):self.validate(*args)
        args=scene();args[0]['actors'][0]['components'][0]['materials'].reverse()
        with self.assertRaisesRegex(guard.ERROR,'material order'):self.validate(*args)

    def test_material_clones_and_mesh_exceptions_must_both_be_explicit(self):
        source,current,plan,mapping,changes=scene()
        overrides=[dict(source='/Game/MPRWarehouse/ReferenceV4/Materials/MI_'+r,role=r) for r in guard.SOLAR_ROLES[1:]]
        materials=guard.expected_retained_material_changes(source,plan,mapping,overrides)
        for change in materials:
            actor=next(a for a in current['actors'] if a['guid']==change['actor_guid'])
            actor['components'][0]['materials'][change['slot']]=change['after']
        guard.assert_retained(source,current,plan,guid_map=mapping,mesh_changes=changes,mesh_overrides=specs(),
            material_changes=materials,material_overrides=overrides)
        with self.assertRaisesRegex(guard.ERROR,'state changed'):
            self.validate(source,current,plan,mapping,changes)

class SolarSourceTests(unittest.TestCase):
    def setup_source(self,root):
        base=root/guard.SOLAR_ROOT;base.mkdir(parents=True);rows=[]
        for _,suffix in guard.SOLAR_IDENTITIES.values():
            name='SM_MPRR_SolarBank_'+suffix;paths=[];hashes=[]
            for lod in range(3):
                path=base/(name+('_LOD'+str(lod) if lod else '')+'.fbx')
                path.write_bytes(('unique-'+path.name).encode());paths.append(path.relative_to(root).as_posix());hashes.append(guard.sha(path))
            rows.append(dict(name=name,category='Architecture',fbx=paths[0],sha256=hashes[0],
                lod_files=paths[1:],lod_sha256=hashes[1:],triangles=100,lod_triangles=[100,60,40],
                full_precision_uvs=True,bounds_m=[[0,10],[0,10],[11,12]],lod_screen_sizes=[1,.5,.2],
                material_roles=guard.SOLAR_ROLES[:2],all_lod_material_roles=guard.SOLAR_ROLES,
                lod_material_roles=[[guard.SOLAR_ROLES[0],r] for r in guard.SOLAR_ROLES[1:]]))
        path=base/'manifest.json';path.write_text(json.dumps(dict(meshes=rows)),encoding='utf-8')
        main=dict(meshes=[dict(name='SM_MPRR_Main')],materials={r:{} for r in guard.SOLAR_ROLES[1:]},
            retained_mesh_overrides=specs(),solar_rebuild=dict(manifest=path.relative_to(root).as_posix(),sha256=guard.sha(path)))
        return main,rows,path

    def test_all_fifteen_sources_and_independent_manifest_are_hashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);main,rows,path=self.setup_source(root)
            actual,files=guard.solar_source_contract(root,main)
            self.assertEqual(actual,rows);self.assertEqual(len(files),16)
            (root/rows[-1]['lod_files'][-1]).write_bytes(b'changed')
            with self.assertRaisesRegex(guard.ERROR,'hash mismatch'):guard.solar_source_contract(root,main)

    def test_missing_duplicate_or_reordered_lod_contract_cannot_pass(self):
        for mutate in [lambda r:r[0]['lod_sha256'].pop(),lambda r:r[0]['lod_files'].reverse(),
                       lambda r:r[0]['all_lod_material_roles'].reverse(),lambda r:r.append(r[0]),
                       lambda r:r[0].update(lod_screen_sizes=[1,float('nan'),.2])]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);main,rows,path=self.setup_source(root);mutate(rows)
                path.write_text(json.dumps(dict(meshes=rows)),encoding='utf-8');main['solar_rebuild']['sha256']=guard.sha(path)
                with self.subTest(mutate=mutate),self.assertRaises(guard.ERROR):guard.solar_source_contract(root,main)

    def test_main_rows_and_read_only_frame_cannot_be_overridden(self):
        for mutate in [lambda m:m['materials'].update(MPR4_SolarFrame={}),
                       lambda m:m['meshes'].append(dict(name='SM_MPRR_SolarBank_00_0')),
                       lambda m:m.update(retained_mesh_overrides=[])]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);main,_,_=self.setup_source(root);mutate(main)
                with self.assertRaises(guard.ERROR):guard.solar_source_contract(root,main)

class SolarImporterTests(unittest.TestCase):
    def test_mesh_assignment_restores_all_four_original_effective_materials(self):
        source,current,plan,mapping,changes=scene();objects=[];meshes={}
        def obj(path):return SimpleNamespace(get_path_name=lambda:path)
        class Component:
            def __init__(self,row):
                self.static_mesh=obj(row['mesh']);self.materials=[obj(p) for p in row['materials']]
            def get_name(self):return 'StaticMeshComponent0'
            def get_num_materials(self):return len(self.materials)
            def get_material(self,slot):return self.materials[slot]
            def set_static_mesh(self,mesh):
                self.static_mesh=mesh;self.materials=[obj('wrong-default')]*4;return True
            def set_material(self,slot,material):self.materials[slot]=material
        for original,change in zip(source['actors'],[next(c for c in changes if c['source_guid']==r['guid']) for r in source['actors']]):
            component=Component(original['components'][0]);guid=change['actor_guid'];name=original['name']
            actor=SimpleNamespace(get_editor_property=lambda key,g=guid:g,get_name=lambda n=name:n,
                get_components_by_class=lambda cls,c=component:[c])
            objects.append(actor);meshes[change['after'].rsplit('.',1)[1]]=obj(change['after'])
        tree=ast.parse((ROOT/'Tools/MPRWarehouse/import_mpr_rebuild.py').read_text(encoding='utf-8'))
        module=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='apply_retained_meshes'],type_ignores=[])
        scope=dict(guard=guard,require=guard.require,u=SimpleNamespace(StaticMeshComponent=object,
            GuidLibrary=SimpleNamespace(conv_guid_to_string=lambda x:x)),
            core=SimpleNamespace(A=SimpleNamespace(get_all_level_actors=lambda:objects),MESHES=meshes))
        exec(compile(module,'solar-importer','exec'),scope)
        actual=scope['apply_retained_meshes'](dict(retained_mesh_overrides=specs()),source,plan,mapping)
        self.assertEqual(actual,changes)
        for actor,original in zip(objects,source['actors']):
            component=actor.get_components_by_class(object)[0]
            self.assertEqual([m.get_path_name() for m in component.materials],original['components'][0]['materials'])

if __name__=='__main__':unittest.main()
