"""Blender geometry regression for the two Glen road continuation joints.

Run in background Blender; -- --baseline intentionally checks the old mesh
and must fail the lane-opening test. Without that flag check the new asset.
"""
from pathlib import Path
import json
import math
import sys
import unittest

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'Saved/ParkRefinement/python_deps'))
from shapely.geometry import Polygon
from shapely.ops import unary_union

ORIGIN = (239.33385, 60.24019)
SOURCE = ROOT / 'SourceAssets/GHS/Park/GHS_Park_Source.blend'
OUTPUT = ROOT / 'SourceAssets/GHS/RoadEndcaps/GHS_RoadEndcaps.blend'


def load_object(path, name):
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        assert name in source.objects, (path, name)
        target.objects = [name]
    return target.objects[0]


def frame(end):
    a, b = end['old_end_uv_m'], end['new_end_uv_m']
    size = math.dist(a, b)
    return a, ((b[0]-a[0])/size, (b[1]-a[1])/size)


def rectangle(end, start, stop, left, right):
    p, t = frame(end)
    return Polygon([(p[0]+t[0]*d-t[1]*side, p[1]+t[1]*d+t[0]*side)
                    for d, side in [(start,left),(stop,left),(stop,right),(start,right)]])


def top_in_window(obj, end, z):
    window = rectangle(end, -4, 4, -12, 12)
    pieces = []
    for face in obj.data.polygons:
        points = [obj.data.vertices[i].co for i in face.vertices]
        if not all(abs(v.z-z)<1e-6 for v in points):
            continue
        polygon = Polygon([(v.x+ORIGIN[0], -v.y+ORIGIN[1]) for v in points])
        if polygon.is_valid and polygon.area > 1e-10 and polygon.intersects(window):
            pieces.append(polygon.intersection(window))
    return unary_union(pieces)


class GlenEndcapsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ends = [e for e in json.loads((ROOT/'SourceAssets/GHS/ContextTransition/context_transition.json')
            .read_text(encoding='utf-8'))['roads'] if e['road_id']=='glen']
        assert {e['side'] for e in cls.ends} == {'start', 'end'}
        cls.original = load_object(SOURCE, 'SM_GHSPark_Curbs')
        cls.revised = cls.original if '--baseline' in sys.argv else load_object(OUTPUT, 'SM_GHSRoadEndcaps_Curbs')
        cls.original_tops = {(e['side'], z):top_in_window(cls.original,e,z) for e in cls.ends for z in (.10,.19)}
        cls.revised_tops = {(e['side'], z):top_in_window(cls.revised,e,z) for e in cls.ends for z in (.10,.19)}
        road=load_object(SOURCE,'SM_GHSPark_ContextRoads')
        extension=load_object(ROOT/'SourceAssets/GHS/ContextTransition/GHS_ContextTransition.blend',
                              'SM_GHSContextTransition_ContextRoads')
        cls.road_tops={e['side']:unary_union([top_in_window(road,e,.015),top_in_window(extension,e,.018)])
                       for e in cls.ends}

    def test_both_extended_carriageways_have_no_transverse_curb_or_sidewalk(self):
        for end in self.ends:
            for z in (.10,.19):
                with self.subTest(end=end['side'], elevation=z):
                    lane = rectangle(end,-.08,1.90,-9.49,9.49)
                    overlap = self.revised_tops[(end['side'],z)].intersection(lane).area
                    self.assertLess(overlap, 0.0001, 'Raised white endcap still crosses the 19m Glen carriageway')

    def test_side_curbs_and_sidewalks_remain_at_both_joints(self):
        for end in self.ends:
            for z in (.10,.19):
                before = self.original_tops[(end['side'],z)]
                after = self.revised_tops[(end['side'],z)]
                for side in (-1,1):
                    shoulder = rectangle(end,-3.5,1.9,*sorted([side*9.51,side*11.5]))
                    with self.subTest(end=end['side'], elevation=z, side=side):
                        original_area = before.intersection(shoulder).area
                        self.assertGreater(original_area,.5)
                        self.assertLess(before.symmetric_difference(after).intersection(shoulder).area,.0001)

    def test_asphalt_remains_continuous_across_each_original_and_extended_joint(self):
        for end in self.ends:
            with self.subTest(end=end['side']):
                lane=rectangle(end,-1.,2.,-9.45,9.45)
                self.assertLess(lane.difference(self.road_tops[end['side']]).area,.0001)
                self.assertAlmostEqual(end['height_m'],.018)

    def test_full_rebuild_opening_rule_matches_the_scoped_mesh(self):
        sys.path.insert(0,str(ROOT/'Scripts/ghs'))
        from road_endcaps import open_glen_endcaps
        roads=json.loads((ROOT/'SourceAssets/GHS/Traffic/routes.json').read_text(encoding='utf-8'))['roads']
        for end in self.ends:
            for z in (.10,.19):
                with self.subTest(end=end['side'],elevation=z):
                    expected=open_glen_endcaps(self.original_tops[(end['side'],z)],roads)
                    actual=self.revised_tops[(end['side'],z)]
                    self.assertLess(expected.symmetric_difference(actual).area,.0001)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GlenEndcapsTests))
    if not result.wasSuccessful():
        raise AssertionError('Glen road-end geometry checks failed')
