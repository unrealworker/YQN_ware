"""Context continuations must never extend an internal CAD junction."""
import json
from pathlib import Path
import unittest

from context_road_ends import classify_context_road_ends

ROOT = Path(__file__).resolve().parents[2]


class ContextRoadEndsTest(unittest.TestCase):
    def test_current_site_keeps_six_external_ends(self):
        routes = json.loads((ROOT/'SourceAssets/GHS/Traffic/routes.json').read_text(encoding='utf-8'))
        cad = json.loads((ROOT/'SourceAssets/GHS/Park/cad_layout.json').read_text(encoding='utf-8'))
        result = classify_context_road_ends(routes['roads'], cad['roads'])
        self.assertEqual({(r['road_id'], r['side']) for r in result['external']}, {
            ('glen','start'), ('glen','end'), ('i15_0','start'),
            ('i15_0','end'), ('i15_1','start'), ('i15_1','end')})
        self.assertEqual({(r['road_id'], r['side']) for r in result['internal']}, {
            ('sycamore_south','end'), ('sycamore_north','start')})
        for row in result['internal']:
            self.assertEqual(set(row['cad_incidents']), {'15ee','17a8','18f8','1dc8'})

    def test_shared_route_endpoint_is_internal_without_cad(self):
        roads = [dict(id='a',path_uv_m=[[0,0],[10,0]],extend_end=True),
                 dict(id='b',path_uv_m=[[10,0],[10,10]],extend_start=True)]
        result = classify_context_road_ends(roads)
        self.assertEqual(len(result['internal']), 2)
        self.assertFalse(result['external'])

    def test_cad_endpoint_continuation_is_internal(self):
        roads = [dict(id='a',path_uv_m=[[0,0],[10,0]],extend_end=True)]
        cad = [dict(handle='original',points_uv_m=[[0,0],[10,0]]),
               dict(handle='continuation',points_uv_m=[[10,0],[20,0]])]
        self.assertEqual(len(classify_context_road_ends(roads,cad)['internal']),1)

    def test_unconnected_requested_end_is_retained(self):
        roads = [dict(id='a',path_uv_m=[[0,0],[10,0]],extend_end=True)]
        self.assertEqual(len(classify_context_road_ends(roads)['external']),1)


if __name__ == '__main__':
    unittest.main()
