"""Preflight regressions that prevent generating patches against a polluted base."""
import tempfile
import unittest
from pathlib import Path
import shutil
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


class PayloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name) / 'release'
        self.stage = Path(temporary.name) / 'stage'
        package = self.base / 'package'
        paks = package / release.PAKS
        paks.mkdir(parents=True)
        for name in ('global.utoc', 'global.ucas', 'Test-Windows.ucas'):
            (paks / name).write_bytes(name.encode())
        self.manifest = {'files': release.inventory(package)}
        shutil.copytree(package, self.stage)
        self.paks = self.stage / release.PAKS
        for extension in ('pak', 'utoc', 'ucas'):
            (self.paks / ('Test-Windows_0_P.' + extension)).write_bytes(b'overlay')

    def select(self):
        files, schema = release.select_patch_files(self.stage, self.base, self.manifest, release.DEFAULT_ENGINE)
        return {x['path'] for x in files}, schema

    def test_unchanged_globals_keep_original_schema(self):
        files, schema = self.select()
        self.assertEqual(schema, 1)
        self.assertTrue(files.isdisjoint(release.GLOBAL_PAIR))

    def test_even_one_changed_global_requires_compatibility_and_both_files(self):
        (self.paks / 'global.utoc').write_bytes(b'updated')
        with patch.object(release, 'verify_compatible_globals') as check:
            files, schema = self.select()
            check.assert_called_once_with(self.base / 'package' / release.PAKS, self.paks, release.DEFAULT_ENGINE)
            self.assertEqual(schema, 2)
            self.assertTrue(files.issuperset(release.GLOBAL_PAIR))
            check.side_effect = RuntimeError('incompatible')
            with self.assertRaisesRegex(RuntimeError, 'incompatible'):
                self.select()

    def test_changed_main_container_remains_protected(self):
        (self.paks / 'Test-Windows.ucas').write_bytes(b'changed main container')
        with self.assertRaisesRegex(RuntimeError, 'Non-patch container changed'):
            self.select()


if __name__ == '__main__':
    unittest.main()
