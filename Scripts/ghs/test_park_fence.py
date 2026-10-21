"""Perimeter continuity, real gate clearances and curved-boundary regressions."""
import math
import unittest

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from park_curves import rounded_path
from park_fence import build_fence


class Capture:
    def __init__(self):
        self.boxes, self.meshes, self.ribbons = [], [], []
        self.api = dict(box=self.box,mesh=self.mesh,ribbon=self.ribbon,counts={})

    def box(self,role,center,size,angle=0):
        self.boxes.append((role,center,size,angle))

    def mesh(self,role,vertices,faces):
        self.meshes.append((role,vertices,faces))

    def ribbon(self,role,path,width,z):
        self.ribbons.append((role,path,width,z))

    def footprint(self,item):
        _,(x,y,_),(w,d,_),angle=item
        c,s=math.cos(angle),math.sin(angle)
        return Polygon([(x+dx*c-dy*s,y+dx*s+dy*c) for dx,dy in
                        ((-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2))])


class FenceTests(unittest.TestCase):
    boundary=[(0,0),(100,0),(100,60),(0,60),(0,0)]
    gates=[dict(name='south',geometry=box(24,-2,36,2)),
           dict(name='north',geometry=box(64,58,76,62))]

    def test_two_12m_gates_are_the_only_boundary_gaps(self):
        capture=Capture()
        result=build_fence(capture.api,self.boundary,self.gates)
        expected=LineString(self.boundary).difference(unary_union([g['geometry'] for g in self.gates]))
        actual=unary_union([LineString(path) for _,path,_,_ in capture.ribbons])
        self.assertAlmostEqual(actual.symmetric_difference(expected).length,0)
        self.assertEqual(len(result['portals']),2)
        self.assertAlmostEqual(result['gap_total_m'],24)
        self.assertAlmostEqual(result['fence_m'],296)
        self.assertTrue(result['continuous_except_named_gates'])

    def test_gate_columns_and_caps_preserve_full_12m_clearance(self):
        capture=Capture()
        result=build_fence(capture.api,self.boundary,self.gates)
        corridor=unary_union([g['geometry'] for g in self.gates])
        caps=[capture.footprint(item) for item in capture.boxes if item[0]=='Blue']
        self.assertEqual(len(caps),4)
        for item in capture.boxes:
            if item[0] in ('Buildings','Blue'):
                self.assertLess(capture.footprint(item).intersection(corridor).area,1e-8)
        for index,portal in enumerate(result['portals']):
            actual=caps[index*2].distance(caps[index*2+1])
            self.assertGreaterEqual(actual,12-1e-8)
            self.assertAlmostEqual(portal['clear_width_m'],actual)

    def test_gate_crossing_closed_path_seam_is_one_opening(self):
        capture=Capture()
        gate=[dict(name='seam',geometry=box(-6,-6,6,6))]
        result=build_fence(capture.api,self.boundary,gate)
        self.assertEqual(len(result['portals']),1)
        self.assertAlmostEqual(result['gap_total_m'],12)
        expected=LineString(self.boundary).difference(gate[0]['geometry'])
        actual=unary_union([LineString(p) for _,p,_,_ in capture.ribbons])
        self.assertAlmostEqual(actual.symmetric_difference(expected).length,0)

    def test_every_rail_and_bar_follows_rounded_boundary(self):
        boundary=rounded_path([(0,0),(100,0),(100,60),(0,60)],12,closed=True,max_step=.8)
        line=LineString(boundary)
        capture=Capture()
        gates=[dict(name='corner',geometry=box(-5,-5,13,13)),self.gates[1]]
        build_fence(capture.api,boundary,gates)
        corridor=unary_union([g['geometry'] for g in gates])
        for role,center,size,angle in capture.boxes:
            self.assertLess(line.distance(Point(center[:2])),1e-7)
            if role in ('Buildings','Blue'):
                item=(role,center,size,angle)
                self.assertLess(capture.footprint(item).intersection(corridor).area,1e-8)
            if role=='Fence' and size[0]>size[2]:
                # All horizontal rail axes are sampled-boundary segments,
                # without extrapolating into openings or through the corner.
                x,y,_=center
                dx,dy=math.cos(angle)*size[0]/2,math.sin(angle)*size[0]/2
                rail=LineString([(x-dx,y-dy),(x+dx,y+dy)])
                self.assertLess(rail.difference(line.buffer(1e-7)).length,1e-6)
                self.assertLess(rail.intersection(corridor).length,1e-7)
        for _,vertices,_ in capture.meshes:
            center=tuple(sum(p[i] for p in vertices)/len(vertices) for i in (0,1))
            self.assertLess(line.distance(Point(center)),1e-7)
            self.assertFalse(corridor.contains(Point(center)))

    def test_closed_fence_has_no_duplicate_seam_post(self):
        capture=Capture()
        result=build_fence(capture.api,self.boundary,[])
        posts=[tuple(round(value,7) for value in center[:2])
               for role,center,size,_ in capture.boxes if role=='Fence' and size[2]>2]
        self.assertEqual(len(posts),len(set(posts)))
        self.assertEqual(result['gap_total_m'],0)
        self.assertEqual(result['fence_m'],320)
        path=capture.ribbons[0][1]
        first=(path[1][0]-path[0][0],path[1][1]-path[0][1])
        last=(path[-1][0]-path[-2][0],path[-1][1]-path[-2][1])
        self.assertAlmostEqual(first[0]*last[1]-first[1]*last[0],0)
        self.assertGreater(first[0]*last[0]+first[1]*last[1],0)

    def test_overlapping_gates_rejected_before_geometry_is_emitted(self):
        capture=Capture()
        gates=[self.gates[0],dict(name='overlap',geometry=box(30,-2,42,2))]
        with self.assertRaises(ValueError):
            build_fence(capture.api,self.boundary,gates)
        self.assertEqual(capture.boxes+capture.meshes+capture.ribbons,[])

    def test_multi_crossing_corridor_rejected_before_geometry_is_emitted(self):
        capture=Capture()
        with self.assertRaises(ValueError):
            build_fence(capture.api,self.boundary,[dict(name='crosses_twice',geometry=box(24,-2,36,62))])
        self.assertEqual(capture.boxes+capture.meshes+capture.ribbons,[])

    def test_repeated_boundary_vertex_does_not_emit_zero_length_rail(self):
        capture=Capture()
        boundary=self.boundary[:2]+[self.boundary[1]]+self.boundary[2:]
        build_fence(capture.api,boundary,self.gates)
        for role,_,size,_ in capture.boxes:
            if role=='Fence' and size[2]<.1:
                self.assertGreater(size[0],.01)

    def test_strip_faces_do_not_duplicate_reversed_polygons(self):
        capture=Capture()
        build_fence(capture.api,self.boundary,self.gates)
        self.assertTrue(capture.meshes)
        for _,vertices,faces in capture.meshes:
            self.assertEqual(len(faces),1)
            self.assertEqual(len(set(faces[0])),4)
            self.assertEqual(len(vertices),4)


if __name__=='__main__':
    unittest.main()
