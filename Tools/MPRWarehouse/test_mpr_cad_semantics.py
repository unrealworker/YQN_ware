"""Regression checks against independently extracted original CAD arc geometry."""
import json
import math
import pathlib
import unittest
from mpr_cad_semantics import planar_handedness, reflected_mesh_roles, turn_requires_reflection,covered_drive_detail

ROOT = pathlib.Path(__file__).resolve().parents[2]


class CADSemanticsTests(unittest.TestCase):
    def test_mirrored_basis_keeps_reflection(self):
        self.assertEqual(planar_handedness((0, -1), (-1, 0)), -1)
        self.assertEqual(planar_handedness((0, -1), (1, 0)), 1)
        with self.assertRaises(ValueError):
            planar_handedness((1, 0), (2, 0))

    def test_reflected_deck_still_faces_up(self):
        roles = {'Rubber': [[(0, 0, 1), (2, 0, 1), (2, 1, 1), (0, 1, 1)], [(0, 1, 2, 3)]]}
        vertices, faces = reflected_mesh_roles(roles)['Rubber']
        a, b, c = [vertices[i] for i in faces[0][:3]]
        self.assertGreater((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]), 0)
        self.assertEqual(roles['Rubber'][0][2], (2, 1, 1))

    def test_drive_merge_requires_complete_existing_span(self):
        drive=dict(block='*U258',position_m=[0,.06],size_m=[2,1.55],rotation_deg=0,source_handles=['drive'])
        main=dict(position_m=[0,0],size_m=[1.26,4],rotation_deg=-90,source_handles=['main'])
        self.assertIsNotNone(covered_drive_detail(drive,[main]))
        main['position_m']=[3,0]
        self.assertIsNone(covered_drive_detail(drive,[main]))

    def test_four_turn_placements_match_original_cad(self):
        original = json.loads((ROOT/'SourceAssets/MPR/conveyor_repair_20261106/u33_actual_cad_arcs.json').read_text(encoding='utf-8'))
        layout = json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf-8'))
        placements = {v['source_handles'][0]: v for v in layout['equipment'] if v['block']=='*U33'}
        reference = placements[original[0]['handle']]
        def rotate(p, angle):
            c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            return c*p[0]-s*p[1], s*p[0]+c*p[1]
        for target in original:
            placement = placements[target['handle']]
            actual = {a['handle']: a for a in target['arcs']}
            for arc in original[0]['arcs']:
                for key in ('center_m', 'start_m', 'end_m'):
                    local = rotate([arc[key][k]-reference['position_m'][k] for k in (0, 1)], -reference['rotation_deg'])
                    if turn_requires_reflection(reference, placement):
                        local = local[0], -local[1]
                    turned = rotate(local, placement['rotation_deg'])
                    predicted = [turned[k]+placement['position_m'][k] for k in (0, 1)]
                    self.assertLess(math.dist(predicted, actual[arc['handle']][key]), 0.00003,
                                    (target['handle'], arc['handle'], key))


if __name__ == '__main__':
    unittest.main()
