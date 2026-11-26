"""Regressions for mirrored CAD passes and shared ground-zone identifiers."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bind_cad24


class Cad24Bindings(unittest.TestCase):
    def test_pass_columns_continue_along_the_business_row(self):
        def rack(bay, yaw):
            return dict(id=str(bay), position_m=[0, 3.8*bay], rotation_deg=yaw)
        rows = {'R17': {1:rack(1,90), 2:rack(2,270), 3:rack(3,90)}}
        self.assertEqual(bind_cad24.column_directions(rows), {'1':1, '2':-1, '3':1})

    def test_explicit_cad_underpass_range_has_no_implicit_twelfth_level(self):
        attrs = {'BEAM_CODE_01':'L1~L6:underpass', 'BEAM_CODE_02':'L7~L11:p27b'}
        levels = bind_cad24.cad_levels(attrs)
        self.assertEqual(list(levels), list(range(1,12)))
        self.assertEqual(list(levels.values()), ['underpass']*6+['p27b']*5)

    def test_full_zone_code_does_not_assign_same_stock_to_each_pallet(self):
        pallets, source, workbook, instances = [], {}, {}, []
        for seq in (1,2):
            attrs = dict(SEQ=str(seq),ZONE_CODE='GHS-G01-01')
            cid = f'CAD_24_{seq}'
            pallets.append(dict(id=cid,attrs=attrs,rotation_deg=0,position_m=[seq,0]))
            source[str(seq)] = dict(attributes=attrs,position=[seq,0,0])
            workbook['GHS-G01-01',seq] = dict(cd_x=seq,cd_y=0)
            instances.append(dict(id=cid,position_m=[seq,0,0],rotation_deg=90))
        groups = [dict(mesh='SM_GHS_Presentation_CargoLow',instances=instances)]
        mapped, reasons = bind_cad24.floor_bindings(pallets,source,workbook,groups,{'GHS-G01-01':[{}]})
        self.assertFalse(mapped)
        self.assertEqual(reasons['floor_zone_shared_by_pallets'],2)

    def test_wall_empty_bay_field_requires_matching_both_other_indices(self):
        loc = dict(warehouse_id='108',warehouse_code='GHS_CA_US',warehouse_area_id='519',
                   location_layer='4',horizontal_num='',location_row='135',location_col='1')
        self.assertTrue(bind_cad24.metadata_matches(loc,'WALL01','WALL',45,135,4))
        self.assertFalse(bind_cad24.metadata_matches(loc,'WALL01','WALL',45,134,4))
        self.assertFalse(bind_cad24.metadata_matches(loc,'WALL02','WALL',45,135,4))
