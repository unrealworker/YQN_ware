"""Pure preflight/reload/FBX-color regressions; never import bpy or unreal."""
import ast
from collections import defaultdict
from copy import deepcopy
from itertools import product
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
import numpy as np
import shapely
from shapely.geometry import box,Point,LineString,GeometryCollection,shape,mapping
from shapely.ops import unary_union
import extension_preservation as guard


def helpers(filename,names,**values):
    path=ROOT/'Tools/MPRWarehouse'/filename
    tree=ast.parse(path.read_text(encoding='utf-8'))
    selected=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef)
                             and n.name in names],type_ignores=[])
    scope=dict(guard=guard,Path=Path,re=re,np=np,shapely=shapely,
               defaultdict=defaultdict,product=product,
               Point=Point,LineString=LineString,GeometryCollection=GeometryCollection,
               shape=shape,unary_union=unary_union,
               POSITION_TOLERANCE_M=.002,COLOR_TOLERANCE=.00002,**values)
    exec(compile(selected,str(path),'exec'),scope)
    return scope


class ImportPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.functions=helpers('import_mpr_extension.py',
            {'require','validate_manifest','assert_generated_actor_types'},
            ROOT=root,SRC=root/'SourceAssets/MPR/extension_b50b57',DEST=guard.EXTENSION_NAMESPACE)
        self.before=dict(actors=[],asset_hashes={})
        self.manifest=dict(extension_namespace=guard.EXTENSION_NAMESPACE,
            read_only_inputs_unchanged=True,meshes=[],allowed_replacements=[],instances={})
        for i,old in enumerate(sorted(guard.TERMINAL_MESHES)):
            package=old.split('.')[0]
            self.before['asset_hashes'][package]={'old.uasset':'frozen'}
            self.before['actors'].append(dict(guid=str(i),label=package.rsplit('/',1)[1].removeprefix('SM_'),
                folder='MPR/ReferenceV4/Site',tags=['mpr-reference-exterior-v4'],
                components=[dict(name='StaticMeshComponent0',mesh=old,
                    **{'class':'/Script/Engine.StaticMeshComponent'})],
                **{'class':'/Script/Engine.StaticMeshActor'}))
            name='SM_MPRE_Join'+str(i)
            self.manifest['meshes'].append(dict(name=name,material_roles=['MPR4_TerminalAsphalt'],
                replacement_only=True,fbx='SourceAssets/MPR/extension_b50b57/'+name+'.fbx'))
            self.manifest['allowed_replacements'].append(dict(old_mesh=old,new_mesh=name))

    def validate(self):
        return self.functions['validate_manifest'](self.manifest,self.before)

    def test_valid_plan_resolves_exact_three_baseline_components(self):
        _,_,plan=self.validate()
        self.assertEqual({p['actor_guid'] for p in plan},{'0','1','2'})
        self.assertEqual({p['old_mesh'] for p in plan},guard.TERMINAL_MESHES)

    def test_replacement_must_not_also_spawn_as_a_new_actor(self):
        self.manifest['meshes'][0]['replacement_only']=False
        with self.assertRaisesRegex(guard.PreservationError,'replacement_only'):
            self.validate()

    def test_duplicate_terminal_authorization_cannot_hide_a_missing_slot(self):
        self.manifest['allowed_replacements'][1]=deepcopy(self.manifest['allowed_replacements'][0])
        with self.assertRaisesRegex(guard.PreservationError,'three authorized'):
            self.validate()

    def test_source_and_destination_escape_fail_before_import(self):
        self.manifest['meshes'][0]['fbx']='SourceAssets/MPR/reference_v4/old.fbx'
        with self.assertRaisesRegex(guard.PreservationError,'outside extension source'):
            self.validate()
        self.manifest['meshes'][0]['name']='SM_MPRE_Bad/../../Other'
        with self.assertRaisesRegex(guard.PreservationError,'Invalid extension mesh name'):
            self.validate()

    def test_unregistered_reuse_and_fog_actor_are_rejected(self):
        self.manifest['instances']={'Tree':[]}
        self.manifest['reused_meshes']={'Tree':'/Game/UnknownTree.UnknownTree'}
        with self.assertRaisesRegex(guard.PreservationError,'lacks baseline hashes'):
            self.validate()
        after=deepcopy(self.before)
        after['actors'].append(dict(guid='fog',**{'class':'/Script/Engine.ExponentialHeightFog'}))
        with self.assertRaisesRegex(guard.PreservationError,'scene controller'):
            self.functions['assert_generated_actor_types'](self.before,after)


class SavedSceneTests(unittest.TestCase):
    def test_same_new_guid_with_lost_hism_instances_fails_save_and_reload(self):
        original=dict(actors=[dict(guid='new-trees',components=[dict(instance_count=2,
            instance_transforms=[[0,0,0],[1,1,1]])])],asset_hashes={})
        cleared=deepcopy(original)
        cleared['actors'][0]['components'][0]['instance_transforms']=[]
        for filename,args in [('import_mpr_extension.py',('Save',)),('validate_mpr_extension.py',())]:
            fn=helpers(filename,{'require','assert_snapshot_content_equal'})
            with self.subTest(filename=filename),self.assertRaisesRegex(guard.PreservationError,'instance state'):
                fn['assert_snapshot_content_equal'](original,cleared,*args)

    def test_new_package_reimport_fails_reload_check(self):
        fn=helpers('validate_mpr_extension.py',{'require','assert_snapshot_content_equal'})
        original=dict(actors=[],asset_hashes={'new':{'file':'original'}})
        changed=deepcopy(original);changed['asset_hashes']['new']['file']='new bytes'
        with self.assertRaisesRegex(guard.PreservationError,'package set/bytes'):
            fn['assert_snapshot_content_equal'](original,changed)


class RegistrySynchronizationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.events=[];self.ready=False
        self.package=guard.EXTENSION_NAMESPACE+'/Meshes/SM_MPRE_New'
        path=self.root/'Content/MPRWarehouse/ExtensionB50B57/Meshes/SM_MPRE_New.uasset'
        path.parent.mkdir(parents=True);path.write_bytes(b'saved-new-package')
        def wait():
            self.events.append(('wait',));self.ready=True
        registry=SimpleNamespace(
            scan_modified_asset_files=lambda files:self.events.append(('files',files)),
            scan_paths_synchronous=lambda paths,force:self.events.append(('paths',paths,force)),
            wait_for_completion=wait,
            get_dependencies=lambda package,options: [] if self.ready else None)
        self.registry=registry
        u=SimpleNamespace(AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda:registry),
                          AssetRegistryDependencyOptions=lambda **kwargs:kwargs)
        self.functions=helpers('import_mpr_extension.py',{'require','synchronize_new_package_registry'},
                               ROOT=self.root,DEST=guard.EXTENSION_NAMESPACE,u=u)

    def test_saved_new_files_scan_then_wait_before_dependency_check(self):
        result=self.functions['synchronize_new_package_registry']([self.package])
        self.assertEqual([e[0] for e in self.events],['files','paths','wait'])
        self.assertEqual(self.events[1],('paths',[guard.EXTENSION_NAMESPACE],True))
        self.assertEqual(result['dependency_counts'],{self.package:0})
        self.assertTrue(result['wait_for_completion'])

    def test_missing_node_after_scan_still_fails_closed(self):
        self.registry.get_dependencies=lambda package,options:None
        with self.assertRaisesRegex(guard.PreservationError,'unavailable after synchronous registry scan: '+self.package):
            self.functions['synchronize_new_package_registry']([self.package])

    def test_refresh_rejects_old_namespace_or_unsaved_new_package(self):
        for package in ['/Game/MPRWarehouse/ReferenceV4/Old',self.package+'Missing']:
            with self.subTest(package=package),self.assertRaises(guard.PreservationError):
                self.functions['synchronize_new_package_registry']([package])
        self.assertEqual(self.events,[])


class TransientEditorSpriteTests(unittest.TestCase):
    def setUp(self):
        self.compare=helpers('validate_mpr_extension.py',{'require','assert_snapshot_content_equal'})['assert_snapshot_content_equal']
        actor=dict(guid='new-tree',path='/Game/Map.Map:PersistentLevel.TreeGroup',label='New tree group',
                   **{'class':'/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup.BP_GHS_InstanceGroup_C'},
                   folder=guard.EXTENSION_FOLDER+'/Vegetation',tags=[guard.EXTENSION_TAG],components=[])
        actor['components']=[dict(name='BillboardComponent_2',**{'class':'/Script/Engine.BillboardComponent'},
            hidden_in_game=True,attach_parent=actor['path']+'.DefaultSceneRoot',transform=dict(scale=[.5,.5,.5])),
            dict(name='DefaultSceneRoot',**{'class':'/Script/Engine.SceneComponent'}),
            dict(name='HierarchicalInstancedStaticMesh',**{'class':'/Script/Engine.HierarchicalInstancedStaticMeshComponent'},
                 instance_count=2,instance_transforms=[[1.,2.,3.],[4.,5.,6.]])]
        self.saved=dict(actors=[actor],asset_hashes={})
        self.current=deepcopy(self.saved)
        self.current['actors'][0]['components'][0]['name']='BillboardComponent_1'

    def test_only_new_default_root_editor_sprite_name_is_normalized(self):
        raw=deepcopy(self.current)
        result=self.compare(self.saved,self.current,new_actor_guids=['new-tree'])
        self.assertEqual(result['actors'],self.saved['actors'])
        self.assertEqual(self.current,raw)
        self.assertEqual(len(result['transient_editor_billboard_names']),1)
        self.assertEqual(result['transient_editor_billboard_names'][0]['reloaded_name'],'BillboardComponent_1')

    def test_old_actor_or_other_class_folder_tag_cannot_use_exception(self):
        with self.assertRaisesRegex(guard.PreservationError,'instance state'):
            self.compare(self.saved,self.current)
        for field,value in [('class','/Script/Engine.Actor'),('folder','MPR/ReferenceV4'),('tags',[])]:
            saved,current=deepcopy(self.saved),deepcopy(self.current)
            saved['actors'][0][field]=current['actors'][0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(guard.PreservationError,'instance state'):
                self.compare(saved,current,new_actor_guids=['new-tree'])

    def test_visualization_field_changes_and_duplicate_sprites_still_fail(self):
        mutations=[lambda c:c.update(hidden_in_game=False),
                   lambda c:c['transform'].update(scale=[.51,.5,.5]),
                   lambda c:c.update(attach_parent='/Game/Other.Other:Root')]
        for mutate in mutations:
            current=deepcopy(self.current);mutate(current['actors'][0]['components'][0])
            with self.assertRaisesRegex(guard.PreservationError,'instance state'):
                self.compare(self.saved,current,new_actor_guids=['new-tree'])
        current=deepcopy(self.current)
        current['actors'][0]['components'].append(deepcopy(current['actors'][0]['components'][0]))
        with self.assertRaisesRegex(guard.PreservationError,'instance state'):
            self.compare(self.saved,current,new_actor_guids=['new-tree'])

    def test_hism_instance_loss_order_or_small_float_change_still_fail(self):
        for instances in [[],[[4.,5.,6.],[1.,2.,3.]],[[1.+1e-12,2.,3.],[4.,5.,6.]]]:
            current=deepcopy(self.current)
            current['actors'][0]['components'][2]['instance_transforms']=instances
            with self.subTest(instances=instances),self.assertRaisesRegex(guard.PreservationError,'instance state'):
                self.compare(self.saved,current,new_actor_guids=['new-tree'])


class FbxColorTests(unittest.TestCase):
    def setUp(self):
        self.functions=helpers('verify_mpr_extension_blender.py',
            {'color_samples','compare_color_samples','verify_fade_regions'})
        self.source=np.asarray([[.0009,0,0,0,0,0,1],
                                [2,0,0,.5,.5,.5,1],
                                [5,0,0,1,1,1,1]],dtype=float)

    def compare(self,current):
        return self.functions['compare_color_samples'](self.source,current)

    def test_fbx_reorder_and_sub_millimetre_threshold_crossing_pass(self):
        current=self.source[[2,0,1]].copy()
        current[1,0]=.0011
        report=self.compare(current)
        self.assertTrue(report['coordinate_color_multiset_equal'])
        self.assertEqual(report['neighbor_bucket_samples'],1)

    def test_real_terminal_edge_bucket_collision_keeps_actual_samples(self):
        # Captured from the saved Blender/FBX pair: the first two points merge
        # in a 2mm rounded bucket, then split again on FBX float conversion.
        xyz=[[-498.9809875488281,268.21270751953125,-1.093999981880188],
             [-498.97918701171875,268.2117919921875,-1.093999981880188],
             [-498.97900390625,268.2117919921875,-1.093999981880188]]
        actual=[[-498.98101806640625,268.2126770019531,-1.093999981880188],
                [-498.9792175292969,268.2117614746094,-1.093999981880188],
                [-498.9790344238281,268.2117614746094,-1.093999981880188]]
        self.source=np.repeat(np.asarray([p+[0,0,0,1] for p in xyz]),[2,2,3],axis=0)
        current=np.repeat(np.asarray([p+[0,0,0,1] for p in actual]),[2,2,3],axis=0)
        result=self.compare(current[::-1])
        self.assertLess(result['maximum_matched_axis_error_m'],.00004)
        self.assertEqual(result['maximum_matched_rgba_error'],0.)

    def test_capacity_matching_repairs_greedy_assignment_without_wider_tolerance(self):
        self.source=np.asarray([[x,0,0,0,0,0,1] for x in [0,.0025,.005]])
        current=np.asarray([[x,0,0,0,0,0,1] for x in [.0015,.0036,.004]])
        result=self.compare(current)
        self.assertGreater(result['capacity_augmentations'],0)
        self.assertLessEqual(result['maximum_matched_axis_error_m'],.002)

    def test_all_white_and_wrong_gamma_fail_even_with_color_layer_present(self):
        for rgb in [1.,.214041]:
            current=self.source.copy();current[1,3:6]=rgb
            with self.subTest(rgb=rgb),self.assertRaisesRegex(AssertionError,'distribution changed'):
                self.compare(current)

    def test_same_range_and_histogram_on_wrong_positions_fails(self):
        current=self.source.copy();current[:,3:]=current[::-1,3:]
        with self.assertRaisesRegex(AssertionError,'distribution changed'):
            self.compare(current)

    def test_duplicate_sample_count_changes_fail(self):
        self.source=np.vstack((self.source[0],self.source[0],self.source[1]))
        current=np.vstack((self.source[0],self.source[2],self.source[2]))
        with self.assertRaisesRegex(AssertionError,'distribution changed'):
            self.compare(current)

    def test_point_and_corner_attribute_domains_produce_equivalent_samples(self):
        class Loops:
            def __init__(self,indices):self.indices=indices
            def __len__(self):return len(self.indices)
            def foreach_get(self,name,output):output[:]=self.indices
        class Identity:
            def __matmul__(self,value):return value
        def obj(points,indices,colors,domain):
            attr=SimpleNamespace(domain=domain,data=[SimpleNamespace(color=c) for c in colors])
            mesh=SimpleNamespace(loops=Loops(indices),vertices=[SimpleNamespace(co=p) for p in points],
                                 color_attributes={'EdgeFade':attr})
            return SimpleNamespace(name='Road',data=mesh,matrix_world=Identity())
        a=obj([(0,0,0),(1,0,0)],[0,1,0],[(0,0,0,1),(1,1,1,1)],'POINT')
        b=obj([(0,0,0),(1,0,0),(0,0,0)],[0,1,2],[(0,0,0,1),(1,1,1,1),(0,0,0,1)],'CORNER')
        np.testing.assert_array_equal(self.functions['color_samples'](a),self.functions['color_samples'](b))

    def test_connection_fade_fails_but_exact_outer_tail_is_allowed(self):
        samples=np.asarray([[0,0,0,0,0,0,1],[20,0,0,.7,.7,.7,1]])
        args=(dict(name='Replacement',replacement_only=True),box(-10,-10,-5,5),
              box(-30,-30,30,30),{'connected':box(-1,-1,1,1)},box(19,-1,21,1))
        self.functions['verify_fade_regions'](samples,*args)
        samples[0,3]=.1
        with self.assertRaisesRegex(AssertionError,'connected band must be opaque'):
            self.functions['verify_fade_regions'](samples,*args)


class ReplacementSpatialTests(unittest.TestCase):
    def test_old_tree_overlap_is_retained_but_new_rail_building_overlap_fails(self):
        fn=helpers('verify_mpr_extension_blender.py',{'replacement_spatial_audit'})
        # The old road already intersects this crown. Only its original area
        # is exempt; a new bend continuing into the other protected patch fails.
        old_road=box(0,0,4,2)
        protect=shapely.union_all([box(1,1,3,3),box(5,0,7,2)])
        original=np.asarray([old_road],dtype=object)
        report=fn['replacement_spatial_audit'](original,protect,old_road)
        self.assertEqual(report['protected_new_overlap_m2'],0)
        invading=np.asarray([box(0,0,7,2)],dtype=object)
        with self.assertRaisesRegex(AssertionError,'protected building/tree/rail'):
            fn['replacement_spatial_audit'](invading,protect,old_road)


class MouthStitchTests(unittest.TestCase):
    def setUp(self):
        self.fn=helpers('verify_mpr_extension_blender.py',{'validated_mouth_stitches'})['validated_mouth_stitches']
        empty=mapping(GeometryCollection())
        self.originals=[dict(id='mouth',section_m=[[0,3],[0,5]])]
        self.audit=dict(completed_frame=mapping(box(0,0,10,10)),
            existing_buildings=empty,existing_tree_clearance=empty,existing_rails=empty,
            connections=[dict(id='mouth',status='connected')],road_audit={})
        self.set_patch(box(0,3.1,.1,4.9),.1)

    def set_patch(self,patch,depth):
        self.audit['mouth_stitches']=mapping(patch)
        self.audit['road_audit']['mouth_stitches']=[dict(id='mouth',geometry=mapping(patch),
            area_m2=patch.area,max_in_frame_m=depth)]

    def test_local_ten_centimetre_patch_passes_without_shrinking_frame(self):
        mask,_,report=self.fn(self.audit,self.originals)
        self.assertAlmostEqual(mask.area,.18)
        self.assertFalse(report['frame_wide_tolerance_added'])
        self.assertEqual(shape(self.audit['completed_frame']).bounds,(0,0,10,10))

    def test_thirteen_centimetre_or_wrong_mouth_patch_fails(self):
        self.set_patch(box(0,3.1,.13,4.9),.13)
        with self.assertRaisesRegex(AssertionError,'exceeds 12cm'):
            self.fn(self.audit,self.originals)
        self.set_patch(box(0,8,.1,9),.1)
        with self.assertRaisesRegex(AssertionError,'not local'):
            self.fn(self.audit,self.originals)

    def test_unrecorded_extra_patch_is_not_authorized_by_total_mask(self):
        self.audit['mouth_stitches']=mapping(unary_union([shape(self.audit['mouth_stitches']),box(0,8,.1,9)]))
        with self.assertRaisesRegex(AssertionError,'differs from per-mouth'):
            self.fn(self.audit,self.originals)

    def test_patch_never_exempts_existing_buildings_trees_or_rails(self):
        for key in ['existing_buildings','existing_tree_clearance','existing_rails']:
            self.audit[key]=mapping(box(.02,3.2,.08,3.4))
            with self.subTest(key=key),self.assertRaisesRegex(AssertionError,'immutable building/tree/rail'):
                self.fn(self.audit,self.originals)
            self.audit[key]=mapping(GeometryCollection())


if __name__=='__main__':unittest.main()
