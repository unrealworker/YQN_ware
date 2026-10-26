"""Constant-speed replay acceptance independent of Unreal."""
import importlib.util
import math
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'replay_motion_profile.py'
spec = importlib.util.spec_from_file_location('replay_motion_profile', MODULE)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def segment_distance(point, a, b):
    delta = [y-x for x,y in zip(a,b)]
    length_squared = sum(v*v for v in delta)
    fraction = max(0.,min(1.,sum((p-x)*d for p,x,d in zip(point,a,delta))/length_squared)) if length_squared else 0.
    return math.dist(point,[x+fraction*d for x,d in zip(a,delta)])


class RouteProfileTests(unittest.TestCase):
    def build(self, path, speed=3.2, **kwargs):
        return profile.build_route_profile(path,speed,**kwargs)

    def assert_constant_speed(self, rows, path, speed):
        length=sum(math.dist(a[:3],b[:3]) for a,b in zip(path,path[1:]))
        self.assertAlmostEqual(rows[-1][0],length/speed,places=11)
        self.assertEqual(rows[0][0],0.)
        self.assertEqual(rows[0][1],tuple(path[0][:3]))
        self.assertEqual(rows[-1][1],tuple(path[-1][:3]))
        for a,b in zip(rows,rows[1:]):
            self.assertGreater(b[0],a[0])
            self.assertAlmostEqual(math.dist(a[1],b[1])/(b[0]-a[0]),speed,places=8)
            self.assertLess(abs(b[2]-a[2]),180.)

    def test_turn_does_not_slow_down_or_change_the_validated_path(self):
        path=[(0,0,0),(5,0,0),(6,0,0),(6.2,.2,0),(6.2,1,0),(6.2,6,0)]
        rows=self.build(path)
        self.assert_constant_speed(rows,path,3.2)
        for _,point,_ in rows:
            self.assertLess(min(segment_distance(point,a,b) for a,b in zip(path,path[1:])),1e-8)
        for point in path:
            self.assertLess(min(segment_distance(point,a[1],b[1]) for a,b in zip(rows,rows[1:])),1e-8)

    def test_long_straight_is_two_keys_at_original_speed(self):
        path=[(i*.1,0,0) for i in range(1201)]
        rows=self.build(path,3.)
        self.assertEqual(len(rows),2)
        self.assert_constant_speed(rows,path,3.)
        self.assertAlmostEqual(rows[-1][0],40.)

    def test_three_dimensional_distance_controls_time(self):
        path=[(0,0,0),(3,0,4),(3,12,9)]
        rows=self.build(path,2.6)
        self.assert_constant_speed(rows,path,2.6)
        self.assertAlmostEqual(rows[-1][0],18/2.6)

    def test_heading_is_shape_preserving_and_c1_at_internal_waypoints(self):
        # Dense sampling approximates the same continuous heading on either
        # side of each key; every curve keeps the exact supplied heading.
        path=[(0,0,0,0),(1,0,0,30),(2,0,0,80),(3,0,0,90)]
        rows=self.build(path,1.,sample_hz=1000.)
        self.assert_constant_speed(rows,path,1.)
        self.assertTrue(all(b[2]>=a[2]-1e-12 for a,b in zip(rows,rows[1:])))
        for target in (1.,2.):
            i=next(i for i,row in enumerate(rows) if row[0]==target)
            before,at,after=rows[i-1:i+2]
            left=(at[2]-before[2])/(at[0]-before[0])
            right=(after[2]-at[2])/(after[0]-at[0])
            # Export-safe samples are at least 1ms apart; one-sided secants
            # converge to the same C1 derivative within this sampling error.
            self.assertLess(abs(left-right),.01*max(abs(left),abs(right)))
            self.assertGreater(abs(left),10.,'A turn must not ease to zero at every path key')

    def test_short_sharp_turn_keeps_duration_and_samples_heading(self):
        path=[(0,0,0,0),(.001,0,0,90),(.001,.001,0,90)]
        rows=self.build(path)
        self.assert_constant_speed(rows,path,3.2)
        self.assertEqual(len(rows),3,'Original sub-millisecond corners stay exact without artificial microsecond samples')
        self.assertEqual(rows[1][1],tuple(path[1][:3]))
        self.assertTrue(all(b[2]>=a[2] for a,b in zip(rows,rows[1:])))

    def test_wrap_reverse_and_multiple_revolutions_keep_runtime_direction(self):
        path=[(0,0,0,170),(5,0,0,179),(10,0,0,-170)]
        rows=self.build(path)
        self.assert_constant_speed(rows,path,3.2)
        self.assertAlmostEqual(rows[-1][2],190.)
        self.assertTrue(all(b[2]>=a[2] for a,b in zip(rows,rows[1:])))
        reverse=[(10,0,0),(5,0,0),(0,0,0)]
        rows=self.build(reverse)
        self.assert_constant_speed(rows,reverse,3.2)
        self.assertTrue(all(abs(math.remainder(row[2]-180,360))<1e-9 for row in rows))
        path=[(i,0,0,i*90) for i in range(9)]
        rows=self.build(path)
        self.assert_constant_speed(rows,path,3.2)
        self.assertAlmostEqual(rows[-1][2]-rows[0][2],720.)
        for a,b in zip(rows,rows[1:]):
            runtime_mid=a[2]+math.remainder(b[2]-a[2],360)*.5
            self.assertAlmostEqual(runtime_mid,(a[2]+b[2])*.5)

    def test_duplicates_do_not_add_time_and_stationary_turn_is_rejected(self):
        path=[(0,0,0,0),(0,0,0,360),(.001,0,0,0)]
        rows=self.build(path)
        self.assert_constant_speed(rows,path,3.2)
        with self.assertRaisesRegex(ValueError,'[Ss]tationary'):
            self.build([(0,0,0,0),(0,0,0,90),(.001,0,0,90)])

    def test_output_is_deterministic_and_rejects_invalid_inputs(self):
        path=[(0,0,0),(5,0,0),(5,5,0)]
        self.assertEqual(self.build(path),self.build(path))
        for speed in (0,-1,math.nan,math.inf):
            with self.assertRaises(ValueError):self.build(path,speed)
        with self.assertRaises(ValueError):self.build([])
        with self.assertRaises(ValueError):self.build([(0,0,0),(math.nan,0,0)])

    def test_symmetric_steering_blend_reduces_circle_entry_rate_steps(self):
        radius=.85
        count=math.ceil(math.pi*radius/2/.10)
        path=[(-3.,0.,0.,0.),(-.1,0.,0.,0.),(0.,0.,0.,0.)]
        for i in range(1,count+1):
            angle=math.pi*.5*i/count
            path.append((radius*math.sin(angle),radius*(1-math.cos(angle)),0.,math.degrees(angle)))
        path.extend([(radius,radius+.1,0.,90.),(radius,radius+3.,0.,90.)])
        baseline=self.build(path,steering_blend_seconds=0.)
        blended=self.build(path,steering_blend_seconds=.30)
        self.assert_constant_speed(blended,path,3.2)
        self.assertEqual(blended[-1][0],baseline[-1][0])
        self.assertEqual(blended[0][2],baseline[0][2])
        self.assertEqual(blended[-1][2],baseline[-1][2])
        def largest_rate_step(rows):
            rates=[(b[2]-a[2])/(b[0]-a[0]) for a,b in zip(rows,rows[1:])]
            return max(abs(b-a) for a,b in zip(rates,rates[1:]))
        self.assertLess(largest_rate_step(blended),largest_rate_step(baseline)*.4)
        self.assertTrue(any(row[0]<3/3.2 and row[2]>.1 for row in blended),'The turn should begin gently before the circular arc')

    def test_blend_integrates_linear_heading_exactly_and_keeps_endpoints(self):
        path=[(0,0,0,0),(1,0,0,0),(2,0,0,90),(3,0,0,90)]
        rows=self.build(path,1.,steering_blend_seconds=.30)
        self.assert_constant_speed(rows,path,1.)
        self.assertAlmostEqual(next(row[2] for row in rows if row[0]==1.),3.375)
        self.assertAlmostEqual(next(row[2] for row in rows if row[0]==2.),86.625)
        self.assertEqual(rows[0][2],0.)
        self.assertEqual(rows[-1][2],90.)
        for invalid in (-1.,math.nan,math.inf):
            with self.assertRaises(ValueError):self.build(path,steering_blend_seconds=invalid)

    def test_window_knots_near_path_corners_do_not_create_tiny_export_intervals(self):
        # Window edges nearly coincide with these real corners. Their exact
        # position/time must win over the optional extra steering knots.
        path=[(0,0,0,0),(.15001,0,0,30),(.15001,.14999,0,60),(0,.14999,0,90)]
        rows=self.build(path,1.)
        self.assert_constant_speed(rows,path,1.)
        self.assertGreaterEqual(min(b[0]-a[0] for a,b in zip(rows,rows[1:])),.001)
        for corner in path:
            self.assertTrue(any(math.dist(corner[:3],row[1])<1e-12 for row in rows))
        # Match the timeline's existing seconds/cm precision at an absolute
        # replay time, without changing the exporter or its merge threshold.
        exported=[(round(1000.123456+row[0],6),tuple(round(v*100,6)/100 for v in row[1])) for row in rows]
        for a,b in zip(exported,exported[1:]):
            self.assertLess(abs(math.dist(a[1],b[1])/(b[0]-a[0])-1.),.002)


if __name__=='__main__':
    unittest.main()
