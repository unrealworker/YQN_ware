"""Tests for conservative CAD-to-WMS inventory bindings."""
import importlib.util
from pathlib import Path
import unittest
import tempfile

MODULE = Path(__file__).with_name('build_bindings.py')

class BindingTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('bindings', MODULE)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def rack(self, row='R02', bay='15', kind='A', passing=False):
        return dict(instance_id='CAD_ABC', source_handles=['ABC'], row_code=row,
                    bay_sequence=bay, spec_type=kind, pass_variant=passing,
                    rotation_deg=0.0, position_m=[1,2], mapping_key='A:0:3.7138')

    def identity_fixture(self, source_row='S06', source_bay='13'):
        def make(cid,row,bay,y,passing):
            return dict(self.rack(row,str(bay),'B',passing),instance_id=cid,
                        source_handles=[cid.removeprefix('CAD_')],
                        physical_center_m=[10,y],position_m=[10,y])
        target=make('CAD_MID',source_row,source_bay,0,True)
        left=make('CAD_LEFT','SR06',12,-3.70975,False)
        right=make('CAD_RIGHT','SR06',14,3.70975,False)
        rows=[target,left,right]
        attrs={r['source_handles'][-1]:dict(attributes=dict(BLOCK_CODE=r['row_code'],SEQ=r['bay_sequence'])) for r in rows}
        return target,rows,attrs

    def test_special_pass_requires_bilateral_cad_evidence(self):
        target,rows,attrs=self.identity_fixture()
        resolved,evidence,reason=self.m.resolve_rack_identity(target,rows,attrs)
        self.assertEqual((resolved['row_code'],resolved['bay_sequence']),('SR06','13'))
        self.assertEqual((target['row_code'],target['bay_sequence']),('S06','13'))
        self.assertEqual([n['cadId'] for n in evidence['neighbors']],['CAD_LEFT','CAD_RIGHT'])
        self.assertEqual(reason,'')

    def test_direct_pass_bad_bay_is_corrected_only_by_bracketing_neighbors(self):
        target,rows,attrs=self.identity_fixture('R31','15')
        for r in rows:
            r['spec_type']='A'
            if r is not target:r['row_code']='R31';attrs[r['source_handles'][-1]]['attributes']['BLOCK_CODE']='R31'
        resolved,evidence,reason=self.m.resolve_rack_identity(target,rows,attrs)
        self.assertEqual(resolved['bay_sequence'],'13')
        self.assertEqual(evidence['originalBay'],'15')
        self.assertEqual(evidence['resolvedBay'],'13')

    def test_special_pass_rejects_one_side_wrong_family_offset_or_tie(self):
        for change in ('one_side','wrong_family','offset','tie','wrong_spec','wrong_direction','not_pass'):
            with self.subTest(change=change):
                target,rows,attrs=self.identity_fixture()
                if change=='one_side':rows.pop()
                elif change=='wrong_family':target['row_code']='S05';attrs['MID']['attributes']['BLOCK_CODE']='S05'
                elif change=='offset':rows[2]['physical_center_m']=[10,4.2]
                elif change=='tie':rows.append(dict(rows[2],instance_id='CAD_OTHER',source_handles=['OTHER']));attrs['OTHER']=attrs['RIGHT']
                elif change=='wrong_spec':rows[2]['spec_type']='A'
                elif change=='wrong_direction':rows[2]['rotation_deg']=180
                elif change=='not_pass':target['pass_variant']=False
                self.assertIsNone(self.m.resolve_rack_identity(target,rows,attrs)[0])

    def test_identity_rejects_changed_original_or_neighbor_attributes(self):
        target,rows,attrs=self.identity_fixture()
        attrs['MID']['attributes']['SEQ']='99'
        self.assertIsNone(self.m.resolve_rack_identity(target,rows,attrs)[0])
        target,rows,attrs=self.identity_fixture();attrs['RIGHT']['attributes']['BLOCK_CODE']='SR05'
        self.assertIsNone(self.m.resolve_rack_identity(target,rows,attrs)[0])

    def test_placeholder_does_not_inherit_a_nearby_business_row(self):
        target,rows,attrs=self.identity_fixture('A_A_000','1')
        self.assertIsNone(self.m.resolve_rack_identity(target,rows,attrs)[0])

    def test_numeric_width_matching_keeps_separator_families_and_raw_code(self):
        current=dict(location_code='GHS-SR-02-073-01',location_id='1')
        old=dict(location_code='GHS-SR02-73-01',location_id='2')
        lookup=self.m.numeric_code_index({current['location_code']:[current],old['location_code']:[old]})
        self.assertEqual(lookup[self.m.numeric_code_key('GHS-SR-02-73-01')],[current])
        self.assertEqual(current['location_code'],'GHS-SR-02-073-01')
        self.assertIsNone(self.m.numeric_code_key(old['location_code']))
        self.assertIsNone(self.m.numeric_code_key('SR02-73-01'))
        self.assertIsNone(self.m.numeric_code_key('R02-73-01'))

    def test_multiple_same_family_numeric_codes_remain_ambiguous(self):
        a=dict(location_code='GHS-SR-02-073-01',location_id='1')
        b=dict(location_code='GHS-SR-02-73-01',location_id='2')
        lookup=self.m.numeric_code_index({a['location_code']:[a],b['location_code']:[b]})
        self.assertEqual(len(lookup[self.m.numeric_code_key(b['location_code'])]),2)

    def test_sequence_conflicts_use_actual_centers_and_only_reject_inversion_endpoints(self):
        def row(cid,bay,y,origin):
            return dict(self.rack('R40',str(bay)),instance_id=cid,position_m=[10,y],physical_origin_m=[10,origin])
        racks=[row('CAD_12',12,2,0),row('CAD_13',13,9,7.5),row('CAD_14',14,5.75,7.6),row('CAD_15',15,13,11)]
        bad=self.m.sequence_conflicts(racks)
        self.assertEqual(bad,{'CAD_13','CAD_14'})
        self.assertEqual(self.m.increasing_sequence_rows([r for r in racks if r['instance_id'] not in bad]),{'R40'})

    def test_sequence_conflicts_do_not_invent_an_order_for_duplicate_bay_numbers(self):
        a=dict(self.rack(),instance_id='CAD_A',position_m=[1,20])
        b=dict(a,instance_id='CAD_B',position_m=[1,10])
        self.assertEqual(self.m.sequence_conflicts([a,b]),set())

    def test_complete_code_does_not_normalize_stale_alias(self):
        rack=self.rack()
        self.assertEqual(self.m.expected_code(rack, 1, 1, 1), 'GHS-R02-43-01')
        self.assertNotEqual(self.m.expected_code(rack, 1, 1, 1), 'R02-43-01')

    def test_sr_spelling_is_preserved(self):
        self.assertEqual(self.m.expected_code(self.rack('SR02', '1', 'B'),1,3,1), 'GHS-SR-02-03-01')

    def test_placeholders_and_alternate_rows_rejected(self):
        for row in ('A_A_000','S01','TMP','R0','R02x'):
            self.assertIsNone(self.m.expected_code(self.rack(row),1,1,1))

    def test_pass_levels_resolve_by_height_not_local_index(self):
        canonical=[{'level':i+1,'base_z_m':z} for i,z in enumerate((0,2.3114,4.6228,6.9342))]
        self.assertEqual(self.m.physical_level(4.6228, canonical),3)
        self.assertEqual(self.m.physical_level(6.9342, canonical),4)
        self.assertIsNone(self.m.physical_level(4.7, canonical))

    def test_crosscheck_rejects_bad_bay_layer_and_wrong_warehouse(self):
        r=self.rack(); loc=dict(warehouse_id='108',warehouse_code='GHS_CA_US',warehouse_area_id='450',horizontal_num='15',location_layer='3')
        self.assertIsNone(self.m.crosscheck_location(loc,r,3))
        for key,value in [('horizontal_num','14'),('location_layer','1'),('warehouse_id','109'),('warehouse_code','MPR'),('warehouse_area_id','454')]:
            with self.subTest(key=key):
                self.assertIsNotNone(self.m.crosscheck_location(dict(loc,**{key:value}),r,3))

    def test_sr_requires_its_own_warehouse_area(self):
        r=self.rack('SR02'); loc=dict(warehouse_id='108',warehouse_code='GHS_CA_US',warehouse_area_id='454',horizontal_num='15',location_layer='3')
        self.assertIsNone(self.m.crosscheck_location(loc,r,3))
        self.assertEqual(self.m.crosscheck_location(dict(loc,warehouse_area_id='450'),r,3),'warehouse_area_mismatch')

    def test_numbering_direction_requires_positive_cad_progression(self):
        def row(bay,y): return dict(self.rack(bay=str(bay)),physical_origin_m=[10,y],position_m=[10,y])
        self.assertEqual(self.m.increasing_sequence_rows([row(1,20),row(2,24)]),{'R02'})
        self.assertEqual(self.m.increasing_sequence_rows([row(1,24),row(2,20)]),set())
        self.assertEqual(self.m.increasing_sequence_rows([row(1,20)]),set())
        self.assertEqual(self.m.increasing_sequence_rows([row(1,20),row(2,20)]),set())

    def test_transform_contract_preserves_authored_rotation_and_scale(self):
        instance=dict(id='CAD_A',position_m=[10,20,0])
        authored=dict(instance,rotation_deg=90,scale=[1,1,1])
        capacity=dict(source_mesh='Rack',mesh='Rack_Capacity')
        contract=self.m.transform_contract(instance,'Rack',authored,capacity)
        self.assertEqual(contract['expectedWorldRotationDeg'],[0,-90,0])
        self.assertEqual(contract['expectedWorldScale'],[1,1,1])
        self.assertEqual(contract['expectedMesh'],'Rack_Capacity')
        self.assertIsNone(self.m.transform_contract(dict(instance,position_m=[10,21,0]),'Rack',authored,capacity))
        self.assertIsNone(self.m.transform_contract(instance,'Rack',dict(authored,scale=[1,float('nan'),1]),capacity))
        self.assertIsNone(self.m.transform_contract(instance,'Rack',authored,dict(capacity,source_mesh='Other')))
        self.assertIsNone(self.m.transform_contract(instance,'Rack',authored,dict(capacity,mesh='Rack_Occ70')))

    def test_authored_identity_conflict_never_picks_last_placement(self):
        original=dict(id='CAD_A',position_m=[1,2,0],rotation_deg=90,scale=[1,1,1])
        groups=[dict(mesh='Rack',instances=[original,dict(original,rotation_deg=270)])]
        self.assertNotIn('CAD_A',self.m.authored_placements(groups)['Rack'])
        groups=[dict(mesh='Rack',instances=[original,dict(original)])]
        self.assertEqual(self.m.authored_placements(groups)['Rack']['CAD_A'],original)

    def test_duplicate_location_and_duplicate_target_are_rejected(self):
        rows=[dict(cadId='A',level=1,column=1,locationId='1'),dict(cadId='B',level=1,column=1,locationId='1'),dict(cadId='C',level=1,column=1,locationId='2')]
        good,rejected=self.m.reject_ambiguous(rows)
        self.assertEqual([x['locationId'] for x in good],['2'])
        self.assertEqual(len(rejected),2)
        rows=[dict(cadId='A',level=1,column=1,locationId='1'),dict(cadId='A',level=1,column=1,locationId='2')]
        self.assertEqual(self.m.reject_ambiguous(rows)[0],[])

    def test_same_stock_rows_do_not_create_duplicate_locations(self):
        rows=[dict(warehouse_id='108',warehouse_code='GHS_CA_US',location_id='001',location_code='GHS-R02-43-01',inventory_item_id='a',quantity='1'),dict(warehouse_id='108',warehouse_code='GHS_CA_US',location_id='001',location_code='GHS-R02-43-01',inventory_item_id='b',quantity='2')]
        self.assertEqual(len(self.m.index_locations(rows)['GHS-R02-43-01']),1)

    def test_occ70_alias_is_not_a_second_physical_location(self):
        src=dict(mesh='Rack',instances=[dict(id='CAD_A',position_m=[0,1,2])])
        alias=dict(mesh='Rack_Occ70',instances=[dict(id='CAD_A',position_m=[0,1,2])])
        self.assertEqual(self.m.canonical_scene_groups(dict(groups=[src,alias])),[src])
        alias['instances'][0]['position_m']=[10,1,2]
        with self.assertRaises(ValueError):self.m.canonical_scene_groups(dict(groups=[src,alias]))

    def test_dxf_attributes_are_bound_to_their_actual_insert_handle(self):
        pairs=[('0','INSERT'),('5','ABC'),('2','RACK_42D_144B'),('10','10'),('20','20'),
               ('0','ATTRIB'),('2','BLOCK_CODE'),('1','R02'),('0','ATTRIB'),('2','SEQ'),('1','15'),
               ('0','SEQEND'),('0','INSERT'),('5','DEF'),('2','FL_PALLET'),('0','ATTRIB'),
               ('2','ZONE_CODE'),('1','A01'),('0','SEQEND'),('0','EOF')]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.dxf'
            path.write_text(''.join(k+'\n'+v+'\n' for k,v in pairs),encoding='utf8')
            result=self.m.dxf_insert_attributes(path)
        self.assertEqual(result['ABC']['attributes'],{'BLOCK_CODE':'R02','SEQ':'15'})
        self.assertEqual(result['ABC']['position'],[10,20,0])
        self.assertEqual(result['DEF']['attributes'],{'ZONE_CODE':'A01'})

    def test_repeated_location_cannot_change_identity_between_stock_rows(self):
        row=dict(warehouse_id='108',warehouse_code='GHS_CA_US',location_id='001',location_code='A')
        with self.assertRaises(ValueError):self.m.index_locations([row,dict(row,location_code='B')])

if __name__=='__main__':unittest.main()
