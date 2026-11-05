"""Regression checks for the reviewed terminal cut and vanished crossing tiles."""
import unittest
import build_mpr_transport_cleanup as cleanup
from shapely.geometry import LineString,Point,box
from shapely.ops import unary_union

class TransportCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=cleanup.revision.decode(cleanup.revision.read(cleanup.CURRENT/'layout.json'))
        cls.after,cls.audit=cleanup.revised_layout(cls.before)

    def test_vanished_component_still_selects_tile_by_old_bounds(self):
        # A retained crossing at the top of the tile shrinks new bounds away
        # from a removed lower crossing. Testing new bounds alone misses it.
        roles={'Concrete':([(10,10,0),(20,10,0),(20,20,0)],[(0,1,2)])}
        impact=box(30,-290,58,-270)
        self.assertFalse(cleanup.revision.geometry_intersects_impact(roles,None,impact))
        old={'bounds_m':[[10,58],[-295,20],[0,1]]}
        self.assertTrue(cleanup.revision.geometry_intersects_impact(roles,old,impact))
        self.assertFalse(cleanup.revision.geometry_intersects_impact(roles,old,box(-100,-200,-90,-190)))

    def test_only_reviewed_rail_sources_change(self):
        before={r['id']:r for r in self.before['rail_centerlines']}
        after={r['id']:r for r in self.after['rail_centerlines']}
        self.assertEqual(set(before)-set(after),cleanup.REMOVED_RAIL_IDS)
        for identity,record in after.items():
            if identity not in cleanup.TRIMMED_RAIL_IDS:self.assertEqual(record,before[identity])
            else:
                wanted=LineString(before[identity]['points_m']).difference(cleanup.TAIL_MASK)
                self.assertTrue(LineString(record['points_m']).equals_exact(wanted,1e-10))
                self.assertAlmostEqual(record['points_m'][0][0],510.)
                self.assertEqual(record['source_points_m'],before[identity]['source_points_m'])

    def test_all_three_terminal_road_stubs_removed(self):
        before={r['id']:r for r in self.before['road_centerlines']}
        after={r['id']:r for r in self.after['road_centerlines']}
        self.assertEqual(set(before)-set(after),cleanup.REMOVED_ROAD_IDS)
        for identity,record in after.items():
            if identity not in cleanup.TRIMMED_ROAD_IDS:self.assertEqual(record,before[identity])
        self.assertLess(self.after['roads'].intersection(cleanup.TAIL_MASK).area,1e-8)
        self.assertLess(self.before['roads'].symmetric_difference(self.after['roads']).difference(cleanup.TAIL_MASK).area,1e-8)

    def test_no_rail_road_crossing_survives_in_removed_tail(self):
        deck,ramps=cleanup.crossing_surfaces(self.after)
        self.assertLess(deck.intersection(cleanup.TAIL_MASK).area,1e-8)
        self.assertLess(ramps.intersection(cleanup.TAIL_MASK).area,1e-8)
        self.assertEqual(self.audit['removed_crossing_ids'],['Crossing_00','Crossing_01','Crossing_03','Crossing_06'])
        for item in self.after['crossings']:self.assertFalse(cleanup.TAIL_MASK.covers(Point(item['point_m'])))

    def test_existing_warehouse_environment_layout_is_preserved(self):
        for key in ['frame','water','source_buildings','building_protection','source_road_hatches']:
            self.assertEqual(cleanup.revision.encode(self.before[key]),cleanup.revision.encode(self.after[key]))
        for key in ['curbs','white_edges']:
            self.assertLess(self.before[key].symmetric_difference(self.after[key]).difference(cleanup.TAIL_MASK.buffer(1.00001)).area,1e-8)
        self.assertLess(self.before['rail_corridor'].symmetric_difference(self.after['rail_corridor']).difference(cleanup.TAIL_MASK.buffer(8.00001)).area,1e-8)

    def test_tile_selection_excludes_unrelated_meshes(self):
        for name in ['SM_MPRR_Roads_0_-2','SM_MPRR_CrossingRamp_-1_-3','SM_MPRR_Rail_3_-1_Sleepers']:
            self.assertTrue(cleanup.affected_name(name),name)
        for name in ['SM_MPRR_Roads_0_-1','SM_MPRR_Rail_0_-2_Rails','SM_MPRR_RailCorridor_-1_-3','SM_MPRR_Terrain_3_-2','SM_MPR_Site_Roads_0_-2']:
            self.assertFalse(cleanup.affected_name(name),name)

if __name__=='__main__':unittest.main(verbosity=2)
