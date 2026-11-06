"""CPU checks for solar grouping, exclusion retention and fail-closed import."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import mpr_solar_units as solar


class SolarUnits(unittest.TestCase):
    def test_sources_and_covered_cells(self):
        manifest,_=solar.source_contract()
        units=solar.read(solar.ROOT/solar.SOURCE/'unit_layout.json')
        old=solar.read(solar.ROOT/manifest['original_layout'])
        seen=set()
        for bank,rows in units.items():
            for row in rows:
                x,y,xx,yy=row['original_grid']
                block=old['blocks'][bank][row['block_index']]
                bx,by,bxx,byy=block['grid']
                self.assertTrue(bx<=x<xx<=bxx and by<=y<yy<=byy)
                keys={(i,j)for i in range(x,xx)for j in range(y,yy)}
                self.assertFalse(seen&keys)
                seen.update(keys)
        wanted={(i,j)for blocks in old['blocks'].values()for b in blocks
                for i in range(b['grid'][0],b['grid'][2])for j in range(b['grid'][1],b['grid'][3])}
        self.assertEqual(seen,wanted)
        self.assertEqual(len(seen),5636)
        self.assertEqual(sum(map(len,units.values())),905)

    def reject(self,mutate,message):
        read=solar.read
        target=solar.ROOT/solar.SOURCE/'manifest.json'
        wrong=deepcopy(read(target))
        mutate(wrong)
        def fake(path):return wrong if Path(path).resolve()==target.resolve()else read(path)
        with patch.object(solar,'read',fake),self.assertRaisesRegex(RuntimeError,message):
            solar.source_contract()

    def test_another_map_rejected(self):
        self.reject(lambda m:m.update(map='/Game/Maps/Other'),'wrong solar unit target')

    def test_changed_palette_rejected(self):
        self.reject(lambda m:m['materials']['MPRH_SolarCells'].update(base_color=[1,1,1]),'existing final solar palette changed')

    def test_cross_bank_scope_rejected(self):
        self.reject(lambda m:m['meshes'].pop(),'unexpected solar banks')

    def test_wrong_fbx_hash_rejected(self):
        self.reject(lambda m:m['meshes'][0].update(sha256='0'*64),'unit FBX/hash mismatch')

    def test_source_path_escape_rejected(self):
        self.reject(lambda m:m['meshes'][0].update(fbx='SourceAssets/Other.fbx'),'unit FBX/hash mismatch')


if __name__=='__main__':unittest.main()
