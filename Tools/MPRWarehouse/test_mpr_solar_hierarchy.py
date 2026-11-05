"""CPU-only fail-closed checks for the solar import source contract."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import mpr_solar_hierarchy as solar


class SolarSourceContract(unittest.TestCase):
    def test_reviewed_sources_are_complete(self):
        manifest, report = solar.source_contract()
        self.assertEqual(len(report['checked_source_files']), 16)
        self.assertEqual(sum(row['lod_triangles'][0] for row in manifest['meshes']), 80320)
        self.assertTrue(all(solar.mesh_path(row).startswith(solar.DEST + '/Meshes/') for row in manifest['meshes']))

    def rejected_manifest(self, change, message):
        original_read = solar.read
        path = (solar.ROOT / solar.SOURCE / 'manifest.json').resolve()
        changed = deepcopy(original_read(path))
        change(changed)

        def reader(candidate):
            return changed if Path(candidate).resolve() == path else original_read(candidate)

        with patch.object(solar, 'read', reader):
            with self.assertRaisesRegex(RuntimeError, message):
                solar.source_contract()

    def test_cannot_retarget_another_map(self):
        self.rejected_manifest(lambda m: m.update(map='/Game/Maps/Other'), 'another map or namespace')

    def test_cannot_import_a_file_outside_reviewed_solar_folder(self):
        self.rejected_manifest(lambda m: m['meshes'][0].update(fbx='SourceAssets/MPR/Other.fbx'), 'FBX source/hash mismatch')

    def test_changed_fbx_is_rejected(self):
        self.rejected_manifest(lambda m: m['meshes'][0].update(sha256='0' * 64), 'FBX source/hash mismatch')

    def test_material_roles_cannot_silently_swap(self):
        self.rejected_manifest(lambda m: m['meshes'][0].update(lod_material_roles=[list(reversed(solar.ROLES))] * 3),
                               'LOD material role contract changed')

    def test_partial_bank_set_is_rejected(self):
        self.rejected_manifest(lambda m: m['meshes'].pop(), 'exactly five bank meshes')


if __name__ == '__main__':
    unittest.main()
