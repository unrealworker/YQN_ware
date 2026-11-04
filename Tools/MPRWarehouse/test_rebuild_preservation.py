"""Pure safety regressions for cloning MPR into an independently owned map."""
import ast
from copy import deepcopy
import json,math,re
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import rebuild_preservation as guard

ROOT=Path(__file__).resolve().parents[2]

def fixture():
    original=dict(guid='original',name='Building',label='Main',path=guard.SOURCE_MAP+'.MPR_CAD_Warehouse:PersistentLevel.Building',
        folder='MPR/Architecture',tags=['MPRWarehouse'],**{'class':'/Script/Engine.StaticMeshActor'},
        attachment_parent=None,transform=dict(translation_cm=[1.,2.,3.]),components=[
            dict(name='Mesh',**{'class':'/Script/Engine.StaticMeshComponent'},mesh='/Game/Old.Mesh',materials=['/Game/Mat.Mat'],
                 transform=dict(translation_cm=[0.,0.,0.]),instance_count=2,instance_transforms=[[1.,2.],[3.,4.]])])
    source=dict(map=guard.SOURCE_MAP,actors=[original],world_settings=dict(default_game_mode='/Game/Mode.Mode_C'))
    copied=guard.remap(original,guard.SOURCE_MAP,guard.MAP);copied['guid']='copied'
    current=dict(map=guard.MAP,actors=[copied],world_settings=deepcopy(source['world_settings']))
    plan=dict(actors=[dict(name='Building',guid='original',action='keep_interior')])
    return source,current,plan

class RetentionTests(unittest.TestCase):
    def test_map_identity_and_duplicate_guid_are_the_only_durable_changes(self):
        source,current,plan=fixture()
        audit=guard.assert_retained(source,current,plan)
        self.assertEqual(audit['source_to_copy_guid'],{'original':'copied'})
        guard.assert_retained(source,current,plan,guid_map=audit['source_to_copy_guid'])
        current['actors'][0]['guid']='recreated'
        with self.assertRaisesRegex(guard.ERROR,'GUID changed'):
            guard.assert_retained(source,current,plan,guid_map=audit['source_to_copy_guid'])

    def test_main_material_transform_and_instance_order_are_exact(self):
        for key,value in [('materials',['/Game/Changed.Changed']),
                          ('transform',dict(translation_cm=[1e-12,0.,0.])),
                          ('instance_transforms',[[3.,4.],[1.,2.]]),('instance_count',1)]:
            source,current,plan=fixture();current['actors'][0]['components'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(guard.ERROR,'state changed'):
                guard.assert_retained(source,current,plan)

    def test_world_settings_are_not_silently_replaced(self):
        source,current,plan=fixture();current['world_settings']['default_game_mode']=None
        with self.assertRaisesRegex(guard.ERROR,'World settings'):
            guard.assert_retained(source,current,plan)

    def test_only_named_lighting_render_fields_can_differ(self):
        source,current,plan=fixture()
        source['actors'][0]['label']=current['actors'][0]['label']='MPR4_KeyLight'
        for row in [source['actors'][0],current['actors'][0]]:
            row['components'][0]['render_settings']=dict(intensity=4.)
        current['actors'][0]['components'][0]['render_settings']['intensity']=5.
        change=dict(actor_name='Building',field=['components','Mesh','render_settings','intensity'],before=4.,after=5.)
        guard.assert_retained(source,current,plan,lighting_changes=[change])
        source['actors'][0]['label']='Main'
        with self.assertRaisesRegex(guard.ERROR,'protected main-building'):
            guard.assert_retained(source,current,plan,lighting_changes=[change])

    def test_lighting_waiver_does_not_allow_other_fields(self):
        source,current,plan=fixture()
        source['actors'][0]['label']=current['actors'][0]['label']='MPR4_KeyLight'
        change=dict(actor_name='Building',field=['components','Mesh','mesh'],before='/Game/Old.Mesh',after='/Game/New.Mesh')
        with self.assertRaisesRegex(guard.ERROR,'render-settings'):
            guard.assert_retained(source,current,plan,lighting_changes=[change])

class RetainedMaterialTests(unittest.TestCase):
    def scene(self):
        source,current,plan=fixture();role='MPR4_IndustrialBlue'
        before='/Game/MPRWarehouse/ReferenceV4/Materials/MI_'+role+'.MI_'+role
        source['actors'][0]['components'][0]['materials']=[before,'/Game/Keep.Keep',before]
        current['actors'][0]['components'][0]['materials']=[before,'/Game/Keep.Keep',before]
        plan['actors'][0]['action']='keep_main_shell'
        interior=deepcopy(source['actors'][0]);interior.update(name='Interior',guid='inside',label='Interior')
        source['actors'].append(interior)
        clone=guard.remap(interior,guard.SOURCE_MAP,guard.MAP);clone['guid']='inside-copy';current['actors'].append(clone)
        plan['actors'].append(dict(name='Interior',guid='inside',action='keep_interior'))
        specs=[dict(source=before.split('.')[0],role=role)]
        changes=guard.expected_retained_material_changes(source,plan,{'original':'copied','inside':'inside-copy'},specs)
        for change in changes:current['actors'][0]['components'][0]['materials'][change['slot']]=change['after']
        return source,current,plan,specs,changes

    def test_only_all_matching_approved_exterior_slots_change(self):
        source,current,plan,specs,changes=self.scene()
        self.assertEqual([r['slot'] for r in changes],[0,2])
        self.assertEqual(source['actors'][1]['components'],current['actors'][1]['components'])
        guard.assert_retained(source,current,plan,material_changes=changes,material_overrides=specs)
        with self.assertRaisesRegex(guard.ERROR,'Material change record'):
            guard.assert_retained(source,current,plan,material_changes=changes[:1],material_overrides=specs)

    def test_exact_material_records_bind_actor_guid_component_slot_and_paths(self):
        for field,value in [('actor_guid','other-guid'),('source_guid','other-original'),
                            ('component_name','OtherMesh'),('slot',1),('before','/Game/Other.Other'),
                            ('after','/Game/MPRWarehouse/ReferenceV4/Materials/MI_Old.MI_Old')]:
            source,current,plan,specs,changes=self.scene();changes[0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(guard.ERROR,'Material change record'):
                guard.assert_retained(source,current,plan,material_changes=changes,material_overrides=specs)

    def test_authorized_materials_do_not_waive_geometry_other_slots_or_interior(self):
        for target,field,value in [(0,'mesh','/Game/OtherMesh.OtherMesh'),
                                  (0,'transform',dict(translation_cm=[.000001,0.,0.])),
                                  (1,'materials',['/Game/New.New'])]:
            source,current,plan,specs,changes=self.scene()
            current['actors'][target]['components'][0][field]=value
            with self.subTest(field=field),self.assertRaises(guard.ERROR):
                guard.assert_retained(source,current,plan,material_changes=changes,material_overrides=specs)

    def test_manifest_cannot_authorize_other_role_or_original_asset_destination(self):
        source,current,plan,specs,changes=self.scene()
        for spec in [dict(source=specs[0]['source'],role='MPR3_Grass'),
                     dict(source='/Game/Other/MI_MPR4_IndustrialBlue',role='MPR4_IndustrialBlue')]:
            with self.subTest(spec=spec),self.assertRaises(guard.ERROR):guard.retained_material_spec_map([spec])
        with self.assertRaisesRegex(guard.ERROR,'Duplicate'):
            guard.retained_material_spec_map(specs+specs)
        with self.assertRaisesRegex(guard.ERROR,'Missing new material'):
            guard.retained_material_spec_map(specs,{})

    def test_reviewed_native_source_has_exactly_77_six_role_slots(self):
        snapshot=ROOT/'Saved/MPR/rebuild_attempts/20261104T123658042520Z-c1b1a7d790b0/Saved/MPR/rebuild_20261104/source_snapshot.json'
        if not snapshot.exists():self.skipTest('Local archived native snapshot is not part of the test repository')
        source=json.loads(snapshot.read_text(encoding='utf-8'))
        plan=json.loads((ROOT/'SourceAssets/MPR/rebuild_b50b57/protection_plan.json').read_text(encoding='utf-8'))
        specs=[dict(source='/Game/MPRWarehouse/ReferenceV4/Materials/MI_'+role,role=role) for role in guard.RETAINED_MATERIAL_ROLES]
        changes=guard.expected_retained_material_changes(source,plan,{r['guid']:r['guid'] for r in source['actors']},specs)
        self.assertEqual(len(changes),77)
        allowed={r['guid'] for r in plan['actors'] if r['action'] in {'keep_main_shell','keep_main_attachments'}}
        self.assertTrue(all(r['source_guid'] in allowed for r in changes))

class FileIsolationTests(unittest.TestCase):
    def test_every_old_package_and_sidecar_stays_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'Content/Maps').mkdir(parents=True)
            old=root/'Content/Maps/MPR_CAD_Warehouse.umap';old.write_bytes(b'original')
            baseline=guard.content_hashes(root)
            new=root/'Content/MPRWarehouse/RebuildB50B57/Site/Meshes/A.uasset'
            new.parent.mkdir(parents=True);new.write_bytes(b'new')
            self.assertEqual(len(guard.assert_old_files(root,baseline)),1)
            old.write_bytes(b'changed')
            with self.assertRaisesRegex(guard.ERROR,'Pre-existing Content'):
                guard.assert_old_files(root,baseline)

    def test_new_unrelated_package_or_old_sidecar_is_rejected(self):
        for name in ['Content/Old.ubulk','Content/MPRWarehouse/RebuildB50B57Else/A.uasset']:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'Content').mkdir()
                before=guard.content_hashes(root);path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'x')
                with self.assertRaisesRegex(guard.ERROR,'outside rebuild'):
                    guard.assert_old_files(root,before)

class PlanAndScopeTests(unittest.TestCase):
    def test_hidden_default_brush_enum_conversion_is_the_only_exception(self):
        class Brush:
            def __init__(self,error=None,value=1):self.error=error;self.value=value
            def get_editor_property(self,name):
                if self.error:raise self.error
                return SimpleNamespace(value=self.value)
        self.assertEqual(guard.brush_type_value(Brush(value=1)),1)
        self.assertEqual(guard.brush_type_value(Brush(error=TypeError(
            "Cannot pythonize '0' (int64) as 'BrushType'"))),0)
        for error in [TypeError("Cannot pythonize '1' (int64) as 'BrushType'"),
                      TypeError("Cannot pythonize '0' (int64) as 'OtherType'"),
                      RuntimeError("Cannot pythonize '0' (int64) as 'BrushType'"),
                      TypeError('Property is missing')]:
            with self.subTest(error=str(error)),self.assertRaises(type(error)):
                guard.brush_type_value(Brush(error=error))

    def test_world_layout_uses_reflected_api_and_detects_unloaded_streaming(self):
        class Object:
            def __init__(self,name,outer=None):self.name=name;self.outer=outer
            def get_outer(self):return self.outer
            def get_path_name(self):return self.name
        world=Object('Map');level=Object('PersistentLevel',world)
        settings=Object('WorldSettings',level);other=Object('OtherMap')
        objects={'streaming':[],'partition':[]}
        u=SimpleNamespace(EditorLevelUtils=SimpleNamespace(get_levels=lambda w:[level]),
            LevelStreaming='streaming',WorldPartition='partition',ObjectIterator=lambda cls:objects[cls])
        self.assertIs(guard.assert_single_world_layout(u,world),level)
        objects['streaming']=[Object('OtherMapStreaming',other)]
        guard.assert_single_world_layout(u,world)
        objects['streaming'].append(Object('UnloadedStreamingLevel',world))
        with self.assertRaisesRegex(guard.ERROR,'Streaming levels'):
            guard.assert_single_world_layout(u,world)
        objects['streaming']=[];objects['partition']=[Object('WorldPartition',settings)]
        with self.assertRaisesRegex(guard.ERROR,'Partitioned worlds'):
            guard.assert_single_world_layout(u,world)

    def test_unfiltered_noneditable_scene_objects_cannot_be_omitted(self):
        rows=[dict(path='Main'),dict(path='WorldSettings',engine_role='world_settings')]
        self.assertEqual(len(guard.validate_actor_coverage({'Main'},rows)),1)
        rows.append(dict(path='HiddenBuilding',engine_role=None))
        with self.assertRaisesRegex(guard.ERROR,'Unrecorded/noneditable'):
            guard.validate_actor_coverage({'Main'},rows)

    def test_all_unknown_actors_are_reported_and_water_manager_is_exact_singleton(self):
        rows=[dict(path='WorldSettings',engine_role='world_settings'),
              dict(path='HiddenA',engine_role=None),dict(path='HiddenB',engine_role=None)]
        with self.assertRaises(guard.ERROR) as error:guard.validate_actor_coverage(set(),rows)
        self.assertIn('HiddenA',str(error.exception));self.assertIn('HiddenB',str(error.exception))
        rows=rows[:1]+[dict(path='BuoyancyManager_0',name='BuoyancyManager_0',components=[],engine_role='water_buoyancy_manager',
                          **{'class':'/Script/Water.BuoyancyManager'})]
        self.assertEqual(len(guard.validate_actor_coverage(set(),rows)),2)
        wrong=deepcopy(rows);wrong[-1]['class']='/Game/MyManager.MyManager_C'
        with self.assertRaisesRegex(guard.ERROR,'Unrecorded/noneditable'):
            guard.validate_actor_coverage(set(),wrong)
        rows.append(dict(rows[-1],path='BuoyancyManager_1'))
        with self.assertRaisesRegex(guard.ERROR,'auxiliary actor set'):
            guard.validate_actor_coverage(set(),rows)

    def test_observed_engine_auxiliaries_require_exact_name_class_component_shape(self):
        samples=[('/Script/Water.BuoyancyManager','BuoyancyManager_0',[],'water_buoyancy_manager'),
            ('/Script/Engine.DefaultPhysicsVolume','DefaultPhysicsVolume_0',
             [('BrushComponent0','/Script/Engine.BrushComponent')],'default_physics_volume'),
            ('/Script/GameplayDebugger.GameplayDebuggerPlayerManager','GameplayDebuggerPlayerManager_0',
             [('GameplayDebug_Input','/Script/Engine.InputComponent')],'gameplay_debugger_manager'),
            ('/Script/Engine.Actor','ChaosDebugDrawActor',
             [('ChaosDebugDrawComponent_0','/Script/ChaosSolverEngine.ChaosDebugDrawComponent')],'chaos_debug_draw'),
            ('/Script/NavigationSystem.AbstractNavData','AbstractNavData-Default',
             [('SceneComp','/Script/Engine.SceneComponent')],'abstract_navigation')]
        for cls,name,components,role in samples:
            shape=[dict(name=n,**{'class':c}) for n,c in components]
            self.assertEqual(guard.engine_aux_role(cls,name,shape),role)
            self.assertIsNone(guard.engine_aux_role(cls,'UserAuthoredActor',shape))
            self.assertIsNone(guard.engine_aux_role(cls,name,shape+[dict(name='Mesh',**{'class':'/Script/Engine.StaticMeshComponent'})]))
        self.assertIsNone(guard.engine_aux_role('/Script/Engine.Actor','ChaosDebugDrawActor',[]))

    def test_only_automatic_auxiliary_names_are_normalized(self):
        row=dict(path='/Game/Map.Map:PersistentLevel.BuoyancyManager_0',name='BuoyancyManager_0',
            label='BuoyancyManager_0',engine_role='water_buoyancy_manager',components=[],
            transform=[0.,0.,0.],**{'class':'/Script/Water.BuoyancyManager'})
        other=deepcopy(row);other.update(path=row['path'].replace('_0','_12'),name='BuoyancyManager_12',label='BuoyancyManager_12')
        self.assertEqual(guard.canonical_coverage([row]),guard.canonical_coverage([other]))
        other['transform'][0]=.000001
        self.assertNotEqual(guard.canonical_coverage([row]),guard.canonical_coverage([other]))

    def test_auxiliary_whitelist_is_singleton_and_main_actor_set_is_complete(self):
        rows=[dict(path='WorldSettings',engine_role='world_settings')]
        with self.assertRaisesRegex(guard.ERROR,'Recorded actor missing'):
            guard.validate_actor_coverage({'Main'},rows)
        rows.append(dict(path='OtherSettings',engine_role='world_settings'))
        with self.assertRaisesRegex(guard.ERROR,'auxiliary actor set'):
            guard.validate_actor_coverage(set(),rows)

    def test_engine_auxiliary_state_is_exact_after_copy(self):
        source,current,plan=fixture()
        row=dict(path=guard.SOURCE_MAP+'.MPR_CAD_Warehouse:PersistentLevel.WorldSettings',
                 engine_role='world_settings',transform=[0.,0.,0.])
        source['world_actor_coverage']=[row]
        current['world_actor_coverage']=guard.remap([row],guard.SOURCE_MAP,guard.MAP)
        guard.assert_retained(source,current,plan)
        current['world_actor_coverage'][0]['transform'][0]=.000001
        with self.assertRaisesRegex(guard.ERROR,'auxiliary actor state'):
            guard.assert_retained(source,current,plan)

    def test_current_review_plan_keeps_all_main_props_and_exact_counts(self):
        path=ROOT/'SourceAssets/MPR/rebuild_b50b57/protection_plan.json'
        plan=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(sum(v for k,v in plan['counts'].items() if k.startswith('keep_')),256)
        self.assertEqual(plan['counts']['remove_old_exterior'],353)
        for row in plan['actors']:
            if any(x in row['label'] for x in ['RollerDock','DockShelter','DockLeveller','Bollard','WallLamp','SolarBank']):
                self.assertTrue(row['action'].startswith('keep_'),row)

    def test_unknown_source_actor_needs_review(self):
        source,_,_=fixture();source['actors'][0]['folder']='MPR/Unreviewed'
        with self.assertRaisesRegex(guard.ERROR,'Unclassified'):
            guard.classify(source['actors'][0])

    def test_new_scene_controller_is_forbidden(self):
        source,current,plan=fixture()
        current['actors'].append(dict(name='Fog',guid='new',label='Fog',folder=guard.FOLDER+'/Site',
            tags=[guard.TAG],attachment_parent=None,**{'class':'/Script/Engine.ExponentialHeightFog'}))
        with self.assertRaisesRegex(guard.ERROR,'Unexpected new scene actor'):
            guard.assert_new_actor_scope(source,current,plan)

    def test_sprite_suffix_only_is_transient(self):
        source,_,_=fixture();row=source['actors'][0]
        row['components']+=[dict(name='DefaultSceneRoot',**{'class':'/Script/Engine.SceneComponent'}),
            dict(name='BillboardComponent_2',**{'class':'/Script/Engine.BillboardComponent'},hidden_in_game=True,
                 attach_parent=row['path']+'.DefaultSceneRoot',transform=dict(scale=[.5,.5,.5]))]
        other=deepcopy(row);other['components'][-1]['name']='BillboardComponent_1'
        self.assertEqual(guard.canonical_actor(row),guard.canonical_actor(other))
        other['components'][-1]['transform']['scale'][0]=.500001
        self.assertNotEqual(guard.canonical_actor(row),guard.canonical_actor(other))

    def test_canceled_extension_dependency_is_rejected_transitively(self):
        links={guard.MAP:['/Game/Shared'], '/Game/Shared':['/Game/MPRWarehouse/ExtensionB50B57/Meshes/Bad']}
        registry=SimpleNamespace(get_dependencies=lambda p,o:links.get(p,[]))
        u=SimpleNamespace(AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda:registry),
                          AssetRegistryDependencyOptions=lambda **kwargs:kwargs)
        with self.assertRaisesRegex(guard.ERROR,'cancelled extension'):
            guard.assert_independent_dependencies(u)
        links['/Game/Shared']=[]
        self.assertEqual(guard.assert_independent_dependencies(u),sorted([guard.MAP,'/Game/Shared']))
        links['/Game/Shared']=None
        with self.assertRaisesRegex(guard.ERROR,'Dependency node unavailable'):
            guard.assert_independent_dependencies(u)

class ManifestBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.src=self.root/'SourceAssets/MPR/rebuild_b50b57';self.src.mkdir(parents=True)
        fbx=self.src/'SM_Test.fbx';fbx.write_bytes(b'new geometry')
        code=ast.parse((ROOT/'Tools/MPRWarehouse/import_mpr_rebuild.py').read_text(encoding='utf-8'))
        module=ast.Module(body=[n for n in code.body if isinstance(n,ast.FunctionDef)
                             and n.name in {'source_path','validate_manifest'}],type_ignores=[])
        scope=dict(ROOT=self.root,SRC=self.src,guard=guard,DEST=guard.DEST,require=guard.require,
                   sha=guard.sha,re=re,math=math)
        exec(compile(module,'import_mpr_rebuild.py','exec'),scope);self.validate=scope['validate_manifest']
        self.manifest=dict(namespace=guard.DEST,map=guard.MAP,
            materials={'Solid':{'color':[.3,.4,.5]}},meshes=[dict(name='SM_Test',category='Site',
            fbx=fbx.relative_to(self.root).as_posix(),sha256=guard.sha(fbx),material_roles=['Solid'])])

    def test_same_contract_accepts_only_new_sources_and_no_replacement_plan(self):
        self.validate(self.manifest)
        self.manifest['allowed_replacements']=[dict(old_mesh='/Game/Original')]
        with self.assertRaisesRegex(guard.ERROR,'must not replace'):
            self.validate(self.manifest)

    def test_source_escape_and_duplicate_mesh_destinations_fail_preflight(self):
        old=self.root/'SourceAssets/MPR/old.fbx';old.write_bytes(b'old')
        manifest=deepcopy(self.manifest);manifest['meshes'][0]['fbx']=old.relative_to(self.root).as_posix()
        with self.assertRaisesRegex(guard.ERROR,'outside rebuild'):
            self.validate(manifest)
        self.manifest['meshes'].append(deepcopy(self.manifest['meshes'][0]))
        with self.assertRaisesRegex(guard.ERROR,'Duplicate rebuild mesh names'):
            self.validate(self.manifest)

    def test_train_pitch_must_be_finite_and_explicit_rebuild_namespace_is_checked(self):
        self.manifest['rebuild_namespace']=self.manifest.pop('namespace')
        self.manifest['instances']={'SM_Test':[dict(position_m=[1,2,3],rotation_deg=40,pitch_deg=2.5)]}
        self.validate(self.manifest)
        for pitch in [float('nan'),float('inf')]:
            self.manifest['instances']['SM_Test'][0]['pitch_deg']=pitch
            with self.assertRaisesRegex(guard.ERROR,'Invalid instance transform'):
                self.validate(self.manifest)
        self.manifest['rebuild_namespace']='/Game/Other'
        with self.assertRaisesRegex(guard.ERROR,'rebuild namespace'):
            self.validate(self.manifest)

class TrainPitchTests(unittest.TestCase):
    def test_cad_forward_up_maps_to_positive_ue_pitch_and_negative_yaw(self):
        code=ast.parse((ROOT/'Tools/MPRWarehouse/import_mpr_rebuild.py').read_text(encoding='utf-8'))
        module=ast.Module(body=[n for n in code.body if isinstance(n,ast.FunctionDef)
                             and n.name=='rebuild_instance_transform'],type_ignores=[])
        u=SimpleNamespace(Transform=lambda **kw:kw,Rotator=lambda **kw:kw,Vector=lambda *v:v)
        scope=dict(u=u,core=SimpleNamespace(pos=lambda v:(v[0]*100,-v[1]*100,v[2]*100)))
        exec(compile(module,'transform','exec'),scope)
        result=scope['rebuild_instance_transform'](dict(position_m=[1,2,3],rotation_deg=37,pitch_deg=2.5,scale=[1,1,1]))
        self.assertEqual(result['location'],(100,-200,300))
        self.assertEqual(result['rotation'],dict(pitch=2.5,yaw=-37.))
        flat=scope['rebuild_instance_transform'](dict(position_m=[0,0,0]))
        self.assertEqual(flat['rotation']['pitch'],0.)

    def test_recorded_instance_quaternion_cannot_lose_pitch_on_reload(self):
        code=ast.parse((ROOT/'Tools/MPRWarehouse/validate_mpr_rebuild.py').read_text(encoding='utf-8'))
        module=ast.Module(body=[n for n in code.body if isinstance(n,ast.FunctionDef)
                             and n.name=='assert_saved_state'],type_ignores=[])
        scope=dict(guard=guard,require=guard.require);exec(compile(module,'validator','exec'),scope)
        _,saved,_=fixture()
        transforms=[dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,.02,0.,.9998],scale=[1.,1.,1.])]
        saved['actors'][0]['components'][0]['instance_transforms']=transforms
        current=deepcopy(saved)
        scope['assert_saved_state'](saved,current)
        current['actors'][0]['components'][0]['instance_transforms'][0]['rotation_xyzw'][1]=0.
        with self.assertRaisesRegex(guard.ERROR,'instance state'):
            scope['assert_saved_state'](saved,current)

if __name__=='__main__':unittest.main()
