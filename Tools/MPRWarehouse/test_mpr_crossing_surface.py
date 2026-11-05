"""Geometric clipping and live-target boundary regression tests."""
import unittest
import build_mpr_crossing_surface as build
import mpr_crossing_surface as patch
import numpy as np
from shapely.geometry import Polygon,box
from shapely.ops import unary_union

class CrossingSurfaceTests(unittest.TestCase):
    def test_sloped_triangle_preserves_plane_and_area(self):
        points=[(0,0,2),(10,0,7),(0,10,5)];mask=box(2,2,7,7)
        outside,inside=build.split_face(points,mask)
        for face in outside+inside:
            for x,y,z in face:self.assertAlmostEqual(z,2+.5*x+.3*y,places=10)
            self.assertGreater(np.cross(np.asarray(face[1])-face[0],np.asarray(face[2])-face[0])[2],0)
        union=unary_union([Polygon(np.asarray(p)[:,:2])for p in outside+inside])
        self.assertLess(union.symmetric_difference(Polygon(np.asarray(points)[:,:2])).area,1e-9)
        self.assertLess(unary_union([Polygon(np.asarray(p)[:,:2])for p in outside]).intersection(mask).area,1e-9)

    def test_vertical_sleeper_side_is_clipped_without_losing_outer_portion(self):
        points=[(0,0,0),(10,0,0),(10,0,1),(0,0,1)]
        outside,inside=build.split_face(points,box(4,-1,6,1))
        area=lambda faces:sum(Polygon([(p[0],p[2])for p in face]).area for face in faces)
        self.assertAlmostEqual(area(outside),8.);self.assertAlmostEqual(area(inside),2.)
        for face in outside+inside:self.assertLess(np.cross(np.asarray(face[1])-face[0],np.asarray(face[2])-face[0])[1],0)

    def test_scope_only_covers_f97_c08_crossing_and_excludes_cleared_ghost(self):
        layout,crossing,scope=build.plan()
        self.assertEqual(crossing['id'],'Crossing_04')
        self.assertLess(scope.difference(layout['roads'].buffer(.00021)).area,1e-8)
        self.assertFalse(scope.intersects(box(30,-296,58,-270)))
        self.assertTrue(all(not name.endswith('_Rails')for name in build.NAMES))

    def test_wrong_namespace_and_partial_application_fail_closed(self):
        mappings=[dict(name=str(i),old_mesh='/Game/Old/'+str(i),new_mesh='/Game/New/'+str(i))for i in range(2)]
        manifest=dict(mesh_mappings=mappings)
        snapshot=dict(map=patch.MAP,actors=[dict(guid=str(i),path='Level.'+str(i),**{'class':'/Script/Engine.StaticMeshActor'},
            components=[dict(name='Mesh',mesh=m['old_mesh'],**{'class':'/Script/Engine.StaticMeshComponent'})])for i,m in enumerate(mappings)])
        self.assertEqual(len(patch.plan_from_snapshot(snapshot,manifest)),2)
        snapshot['actors'][0]['components'][0]['mesh']=mappings[0]['new_mesh']
        with self.assertRaisesRegex(RuntimeError,'Partially applied'):patch.plan_from_snapshot(snapshot,manifest)
        snapshot['actors'][0]['components'][0]['mesh']='/Game/User/0'
        with self.assertRaisesRegex(RuntimeError,'Missing/duplicate'):patch.plan_from_snapshot(snapshot,manifest)

    def test_final_residual_faces_are_explicit_and_geometry_uv_color_remain_fixed(self):
        import hashlib
        import finish_mpr_crossing_material as final
        audit=build.transport.revision.read(build.OUT/'residual_material_validation.json')
        manifest=build.transport.revision.read(build.OUT/'manifest.json')
        row=next(r for r in manifest['meshes']if r['name']==final.NAME)
        faces=final.base.native(build.ROOT/row['fbx'],row['material_roles'])
        self.assertEqual(final.positions_hash(faces),audit['positions_faces_sha256'])
        changes=[i for i,(a,b)in enumerate(zip(audit['before_material_indices'],audit['after_material_indices']))if a!=b]
        self.assertEqual(changes,audit['selected_source_face_indices'])
        self.assertEqual(len(changes),115);self.assertIn(293,changes)
        self.assertEqual([row['material_roles'].index(role)for role,p,n in faces],audit['after_material_indices'])
        names,uv=final.base.native_attributes(build.ROOT/row['fbx'])
        self.assertEqual(names,row['material_roles'])
        self.assertEqual(hashlib.sha256(uv.tobytes()).hexdigest(),audit['uv_sha256'])
        self.assertEqual(hashlib.sha256(final.colors(build.ROOT/row['fbx']).tobytes()).hexdigest(),audit['edge_fade_colors_sha256'])

    def test_no_ballast_remains_under_the_approved_adjacent_ramp_faces(self):
        import shapely
        import approve_mpr_crossing_normals as native
        audit=build.transport.revision.read(build.OUT/'residual_ballast_validation.json')
        manifest=build.transport.revision.read(build.OUT/'manifest.json')
        rows={r['name']:r for r in manifest['meshes']}
        row=rows[audit['mesh_name']]
        self.assertEqual(build.transport.revision.sha(build.ROOT/row['fbx']),audit['final_fbx_sha256'])
        faces=build.read_faces(row)
        surface=unary_union([Polygon(np.asarray(p)[:,:2])for role,p in faces])
        material_audit=build.transport.revision.read(build.OUT/'residual_material_validation.json')
        ramp=rows[material_audit['mesh_name']]
        ramp_faces=native.native(build.ROOT/ramp['fbx'],ramp['material_roles'])
        actual_ramp=unary_union([Polygon(ramp_faces[i][1][:,:2])for i in material_audit['selected_source_face_indices']])
        self.assertLess(surface.intersection(actual_ramp.buffer(-.000001)).area,1e-9)
        self.assertEqual(len(faces),1955)
        self.assertEqual(audit['untouched_native_faces_exact'],1830)
        self.assertTrue(audit['untouched_faces_normals_uv_exact'])

if __name__=='__main__':unittest.main(verbosity=2)
