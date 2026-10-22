"""Road traffic must stay on the CAD pavement, including the I-15 flyover."""
import math
import unittest
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'Saved/ParkRefinement/python_deps'))
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union


class TrafficRoutesTest(unittest.TestCase):
    def test_road_contract(self):
        from traffic_routes import build_routes
        result = build_routes()
        self.assertEqual(len(result['roads']), 5)  # Sycamore has two CAD carriageways.
        self.assertEqual(len(result['routes']), 6)
        self.assertEqual(len({r['corridor'] for r in result['roads']}), 4)
        by_id = {r['id']: r for r in result['roads']}
        for route in result['routes']:
            road = by_id[route['road_id']]
            pavement = LineString(road['extended_path_uv_m']).buffer(road['width_m']/2+.05)
            for point in route['points_uvz_m']:
                self.assertTrue(pavement.contains(Point(point[:2])), route['id'])
            self.assertGreater(route['length_m'], 450)
            self.assertGreater(route['max_speed_cm_s'], 700)
        highways = [r for r in result['routes'] if r['corridor'].startswith('I15')]
        self.assertEqual(len(highways), 2)
        for road in highways:
            self.assertGreater(max(p[2] for p in road['points_uvz_m']), 6)
            self.assertLess(road['points_uvz_m'][0][2], .1)

    def test_extensions_only_at_external_ends(self):
        from traffic_routes import build_routes
        for road in build_routes()['roads']:
            if road['corridor']=='Sycamore':
                self.assertEqual(sum([road['extend_start'], road['extend_end']]), 1)
            for side, enabled in [(0,road['extend_start']),(-1,road['extend_end'])]:
                expected = 65 if enabled else 0
                self.assertAlmostEqual(math.dist(road['path_uv_m'][side], road['extended_path_uv_m'][side]), expected, places=3)

    def test_sycamore_opposing_trucks_never_share_the_cad_terminal_join(self):
        from traffic_routes import build_routes
        result=build_routes()
        routes=[r for r in result['routes'] if r['corridor']=='Sycamore']
        self.assertEqual(len(routes),2)
        south,north=[LineString(r['points_uvz_m']) for r in routes]
        self.assertTrue(south.intersection(north).is_empty,
                        'Opposite traffic must retire before the shared CAD endpoint')

        def swept_truck(route):
            # Largest reused vehicle is 14.904m x 3m. Sweep a conservative
            # 15m x3m rectangle, including both full end-of-route overhangs.
            points=route['points_uvz_m'];rectangles=[]
            for i,p in enumerate(points):
                before,after=points[max(0,i-1)],points[min(len(points)-1,i+1)]
                dx,dy=after[0]-before[0],after[1]-before[1]
                length=math.hypot(dx,dy);dx/=length;dy/=length
                rectangles.append(Polygon([(p[0]+dx*x-dy*y,p[1]+dy*x+dx*y)
                    for x,y in [(-7.5,-1.5),(7.5,-1.5),(7.5,1.5),(-7.5,1.5)]]))
            return unary_union(rectangles)
        envelopes=[swept_truck(route) for route in routes]
        self.assertGreater(envelopes[0].distance(envelopes[1]),8.,
                           'Opposing closed trucks need continuous body clearance')


if __name__ == '__main__':
    unittest.main()
