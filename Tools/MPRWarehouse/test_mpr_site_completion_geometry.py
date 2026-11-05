"""Actual-layout regressions: no UE/Blender, package writes or scene changes."""
from pathlib import Path
import unittest
import json
import hashlib
import mpr_site_completion_geometry as site
from shapely.geometry import LineString, Point
from shapely.ops import unary_union


class SiteCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=site.build_plan()
        cls.protected={k:site.from_polygons(v) for k,v in cls.plan['protected_geometry'].items()}
        cls.paving=unary_union([site.from_polygons(s['polygons']) for s in cls.plan['surfaces'] if s['role']!='MPRR_CampusGreen'])
        cls.raised=unary_union([LineString(l['points_m']).buffer(l['width_m']/2,cap_style=2)
                               for l in cls.plan['linear_features'] if l['height_m']>0])

    def test_latest_transport_source_and_existing_level_are_explicit(self):
        self.assertIn(site.SOURCE+'/transport_revision_20261105/layout.json',self.plan['source_hashes'])
        self.assertEqual(self.plan['map'],'/Game/Maps/MPR_CAD_Warehouse_B50B57')
        for p,expected in self.plan['source_hashes'].items():
            self.assertEqual(site.digest(site.ROOT/p),expected,p)

    def test_paving_preserves_road_building_and_rail_boundaries(self):
        for name in ('roads','main','rail_corridor'):
            self.assertLess(self.paving.intersection(self.protected[name]).area,.001,name)
        self.assertGreaterEqual(self.paving.distance(self.protected['roads']),site.ROAD_CLEARANCE-.00001)

    def test_work_aprons_are_continuous_in_front_of_docks(self):
        for y in (-106,90):
            line=LineString([(-155,y),(130,y)])
            self.assertLess(line.difference(self.paving.buffer(.00001)).length,.001)

    def test_no_new_raised_obstacle_in_operating_areas_or_parking_mouths(self):
        for name in ('operating_area','parking_mouths'):
            self.assertLess(self.raised.intersection(self.protected[name]).area,.001,name)

    def test_markings_stay_on_pavement_and_curbs_are_seated_in_landscape(self):
        green=unary_union([site.from_polygons(s['polygons']) for s in self.plan['surfaces'] if s['role']=='MPRR_CampusGreen'])
        for feature in self.plan['linear_features']:
            footprint=LineString(feature['points_m']).buffer(feature['width_m']/2,cap_style=2)
            if feature['height_m']==0:
                self.assertLess(footprint.difference(self.paving).area,.0001,feature['id'])
            if feature['id'].startswith('LandscapeCurb'):
                self.assertLess(footprint.difference(green).area,.0001,feature['id'])
                self.assertLessEqual(feature['offset_m'],.045)
                self.assertAlmostEqual(feature['offset_m']+feature['height_m'],.235)

    def test_plan_is_reproducible_from_identical_sources(self):
        self.assertEqual(self.plan,site.build_plan())

    def test_parking_bays_keep_existing_car_centres_and_open_mouths(self):
        self.assertEqual(len(self.plan['car_bays']),19)
        for bay in self.plan['car_bays']:
            self.assertTrue(self.paving.covers(Point(bay['centre_m'])),bay['id'])
            mouth=site.from_polygons(bay['mouth_clearance'])
            self.assertLess(self.raised.intersection(mouth).area,.0001,bay['id'])

    def test_parking_asphalt_covers_all_existing_cars_and_bay_markings(self):
        parking=site.from_polygons(next(s for s in self.plan['surfaces']
                                        if s['role']=='MPRSC_ParkingAsphalt')['polygons'])
        self.assertEqual(self.plan['audit']['car_parking_counts'],{'west':18,'east':1})
        self.assertGreater(parking.area,600)
        for bay in self.plan['car_bays']:
            footprint=site.from_polygons(bay['footprint'])
            self.assertLess(footprint.difference(parking).area,.00001,bay['id'])
        bay_lines=[f for f in self.plan['linear_features'] if f['id'].startswith('CarBay_')]
        self.assertEqual(len(bay_lines),19)
        for feature in bay_lines:
            mark=LineString(feature['points_m']).buffer(feature['width_m']/2,cap_style=2)
            self.assertLess(mark.difference(parking).area,.00001,feature['id'])
        for feature in self.plan['linear_features']:
            if feature['id'].startswith('WheelStop_'):
                stop=LineString(feature['points_m']).buffer(feature['width_m']/2,cap_style=2)
                self.assertLess(stop.difference(parking).area,.00001,feature['id'])

    def test_parking_is_a_flush_partition_without_overlapping_surfaces(self):
        surfaces={s['role']:site.from_polygons(s['polygons']) for s in self.plan['surfaces']}
        self.assertEqual(len(surfaces),4)
        for i,(name,geometry) in enumerate(surfaces.items()):
            for other,footprint in list(surfaces.items())[i+1:]:
                self.assertLess(geometry.intersection(footprint).area,.0001,name+' / '+other)
        self.assertAlmostEqual(self.paving.area,self.plan['audit']['paving_area_m2'],places=3)
        parking=next(s for s in self.plan['surfaces'] if s['role']=='MPRSC_ParkingAsphalt')
        concrete=next(s for s in self.plan['surfaces'] if s['role']=='MPR3_Concrete')
        self.assertEqual(parking['offset_m'],concrete['offset_m'])
        for name in ('roads','main','rail_corridor','operating_area'):
            self.assertLess(surfaces['MPRSC_ParkingAsphalt'].intersection(self.protected[name]).area,.0001,name)

    def test_car_markings_are_above_actual_parking_triangles(self):
        parking=next(s for s in self.plan['surfaces'] if s['role']=='MPRSC_ParkingAsphalt')
        triangles=parking['triangles_m']
        shapes=[site.Polygon([v[:2] for v in t]) for t in triangles]
        index=site.shapely.STRtree(shapes)
        for feature in self.plan['linear_features']:
            if not feature['id'].startswith('CarBay_'):
                continue
            for x,y,z in feature['points_m']:
                hits=index.query(Point(x,y),predicate='intersects')
                self.assertGreater(len(hits),0,feature['id'])
                a,b,c=triangles[int(hits[0])]
                ux,uy,vx,vy=b[0]-a[0],b[1]-a[1],c[0]-a[0],c[1]-a[1]
                dx,dy=x-a[0],y-a[1]
                determinant=ux*vy-uy*vx
                s,t=(dx*vy-dy*vx)/determinant,(ux*dy-uy*dx)/determinant
                top=a[2]+s*(b[2]-a[2])+t*(c[2]-a[2])
                self.assertAlmostEqual(z-top,.022,places=5,msg=feature['id'])

    def test_parking_material_split_preserves_accepted_positions_and_features(self):
        # Freeze the already applied round-two coordinates. A material partition
        # may not silently regenerate trees, vehicles, curbs or painted guides.
        frozen={'tree_relocations':'abceee3a798f3a9501dfb93b80435fbd374b98f8e12982d44f5f664d9567cf4b',
                'linear_features':'410749f58550387d11ea7b6f8318b1629d8ff18bd2ec83fb92e9ed55f14578a4',
                'vehicle_instances':'9b40f19369a240e0efb05046725e0e18d11c4f88ede84db17cf2fe71f1f09b7e',
                'protected_geometry':'854b47a3a1e814ce57831a93a7765520ce077b1ba6b0cb2b9896237e99ee4d8c'}
        for key,expected in frozen.items():
            actual=hashlib.sha256(json.dumps(self.plan[key],sort_keys=True,separators=(',',':')).encode()).hexdigest()
            self.assertEqual(actual,expected,key)

    def test_vehicle_positions_and_source_trees_are_never_reassigned(self):
        self.assertEqual(self.plan['audit']['vehicles_repositioned'],0)
        self.assertEqual(self.plan['audit']['source_trees_repositioned'],0)
        data=json.loads((site.ROOT/site.SOURCE/'manifest.json').read_text(encoding='utf8'))
        for row in self.plan['vehicle_instances']:
            old=data['instances'][row['mesh']][row['instance_index']]
            self.assertEqual(row['position_m'],old['position_m'])
        trees=data['instances']['SM_MPR4_Tree_Oak']
        moved={m['original_instance_index'] for m in self.plan['tree_relocations']+self.plan['tree_removals']}
        for index in moved:
            self.assertEqual(trees[index]['provenance'],'campus_green_row')
        fixed=[site.Point(t['position_m'][:2]).buffer(t['crown_radius_m']+site.TREE_MARGIN,quad_segs=12)
               for i,t in enumerate(trees) if i not in moved]
        for move in self.plan['tree_relocations']:
            c=Point(move['to_position_m'][:2]).buffer(move['crown_radius_m']+site.TREE_MARGIN,quad_segs=12)
            self.assertLess(c.intersection(self.paving).area,.0001)
            self.assertLess(c.intersection(self.protected['roads']).area,.0001)
            self.assertLess(c.intersection(self.protected['main']).area,.0001)
            self.assertFalse(any(c.intersects(other) for other in fixed))
            fixed.append(c)

    def test_elevation_follows_existing_terrain_instead_of_flattening_edge(self):
        triangles=self.plan['terrain_triangles_m']
        heights=[v[2] for t in triangles for v in t]
        self.assertGreater(max(heights)-min(heights),.10)
        for s in self.plan['surfaces']:
            self.assertEqual(s['elevation_mode'],'existing_terrain')
            self.assertIn('offset_m',s)
            for p in s['polygons']:
                self.assertEqual(p['outer'][0],p['outer'][-1])
            triangles=unary_union([site.Polygon([v[:2] for v in t]) for t in s['triangles_m']])
            expected=site.from_polygons(s['polygons'])
            self.assertLess(triangles.symmetric_difference(expected).area,.02,s['id'])


if __name__=='__main__':
    unittest.main()
