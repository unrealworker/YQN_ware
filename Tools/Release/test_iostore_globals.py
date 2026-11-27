import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import iostore_globals as globals_io


FIRST = (1 << 62) + 1
SECOND = FIRST + 1
NULL = (1 << 64) - 1


def fixture_hash(data, engine=None):
    return hashlib.sha256(data).digest()[:20]


def write_global(directory, entries):
    # One name per object keeps the name-index renumbering observable when reordering entries.
    names = [name.encode('ascii') for _, name, _ in entries]
    packed_names = (struct.pack('<IIQ', len(names), sum(map(len, names)), 0xC1640000) +
                    b''.join(hashlib.sha256(name).digest()[:8] for name in names) +
                    b''.join(struct.pack('>H', len(name)) for name in names) + b''.join(names))
    objects = b''.join(struct.pack('<IIQQQ', (2 << 30) + i, 0, index, outer, NULL)
                       for i, (index, _, outer) in enumerate(entries))
    data = packed_names + struct.pack('<I', len(entries)) + objects
    size = len(data)
    header = struct.pack('<16s10IQ16sIIQ48s', b'-==-' * 4, 8, 144, 1, 1, 12, 0, 32, 65536,
                         0, 1, NULL, bytes(16), 0, 1, NULL, bytes(48))
    chunk = bytes(11) + b'\x05' + bytes(5) + size.to_bytes(5, 'big') + b'\xff' * 4
    block = bytes(5) + size.to_bytes(3, 'little') * 2 + bytes(1)
    (directory / 'global.utoc').write_bytes(header + chunk + block + fixture_hash(data) + bytes(4))
    (directory / 'global.ucas').write_bytes(data + bytes(-size % 16))


class GlobalCompatibilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name) / 'base'
        self.stage = Path(temporary.name) / 'stage'
        self.base.mkdir()
        self.stage.mkdir()
        write_global(self.base, [(FIRST, 'Root', NULL)])
        write_global(self.stage, [(SECOND, 'Child', FIRST), (FIRST, 'Root', NULL)])
        binding = patch.object(globals_io, '_io_hash', side_effect=fixture_hash)
        binding.start()
        self.addCleanup(binding.stop)

    def test_addition_with_reordered_names_and_objects(self):
        globals_io.verify_compatible_globals(self.base, self.stage)

    def test_removed_renamed_and_unresolved_objects(self):
        for entries in ([(SECOND, 'Root', NULL)], [(FIRST, 'NewName', NULL)],
                        [(FIRST, 'Root', SECOND)], [(FIRST, 'Root', NULL), (FIRST, 'Child', NULL)]):
            with self.subTest(entries=entries):
                write_global(self.stage, entries)
                with self.assertRaises(RuntimeError):
                    globals_io.verify_compatible_globals(self.base, self.stage)

    def test_toc_layout_and_data_integrity(self):
        for file, offset in (('global.utoc', 16), ('global.utoc', 155), ('global.utoc', 175),
                             ('global.utoc', -20), ('global.ucas', 20)):
            with self.subTest(file=file, offset=offset):
                write_global(self.stage, [(FIRST, 'Root', NULL)])
                path = self.stage / file
                data = bytearray(path.read_bytes())
                data[offset] ^= 1
                path.write_bytes(data)
                with self.assertRaises(RuntimeError):
                    globals_io.verify_compatible_globals(self.base, self.stage)
