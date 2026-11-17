"""Preflight regressions that prevent generating patches against a polluted base."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import release


class BaselineTests(unittest.TestCase):
    def test_original_container_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'Test-Windows.ucas'
            source.write_bytes(b'original release')
            manifest = release.inventory(root)
            source.write_bytes(b'a different build')
            with self.assertRaisesRegex(RuntimeError, 'Baseline contents changed'):
                release.verify_baseline(root, manifest)

    def test_unregistered_patch_cannot_silently_become_a_diff_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'Test-Windows.utoc').write_bytes(b'original release')
            manifest = release.inventory(root)
            (root / 'Test-Windows_0_P.utoc').write_bytes(b'unregistered previous patch')
            with self.assertRaisesRegex(RuntimeError, 'Baseline contents changed'):
                release.verify_baseline(root, manifest)

    def test_even_a_registered_overlay_is_not_a_full_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'Test-Windows_0_P.pak').write_bytes(b'previous patch')
            with self.assertRaisesRegex(RuntimeError, 'original full release'):
                release.verify_baseline(root, release.inventory(root))

    def test_existing_version_is_rejected_before_build_tools_run(self):
        class Args:
            version = '1.0.1'
        with patch.object(release, 'catalog', return_value={'releases': [{'version': '1.0.1'}]}), \
                patch.object(release, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'already recorded'):
                release.build_patch(Args())
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
