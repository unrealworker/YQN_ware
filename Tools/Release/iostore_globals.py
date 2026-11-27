"""Validate additive ScriptObjects changes in this project's Win64 UE 5.8 IoStore globals."""
import ctypes
from pathlib import Path
import struct


DEFAULT_ENGINE = Path('C:/UE/UE_5.8')
HEADER = struct.Struct('<16s10IQ16sIIQ48s')
OBJECT = struct.Struct('<IIQQQ')  # FScriptObjectEntry from AsyncLoading2.h
BLOCK_SIZE = 65536
NULL_INDEX = (1 << 64) - 1


def _require(condition, message):
    if not condition:
        raise RuntimeError('Incompatible IoStore global container: ' + message)


def _io_hash(data, engine):
    # UE's FIoHash is the first 20 bytes of BLAKE3. Use the same implementation as UBT.
    library = ctypes.CDLL(str((engine / 'Engine/Binaries/DotNET/UnrealBuildTool'
                               '/runtimes/win-x64/native/blake3_dotnet.dll').resolve()))
    digest = ctypes.create_string_buffer(32)
    library.blake3_hash.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p)
    library.blake3_hash.restype = None
    library.blake3_hash(data, len(data), digest)
    return digest.raw[:20]


def _script_chunk(directory, engine):
    toc = (directory / 'global.utoc').read_bytes()
    data = (directory / 'global.ucas').read_bytes()
    _require(len(toc) >= 194, 'truncated TOC')
    header = HEADER.unpack_from(toc)
    blocks = header[4]
    # TOC v8, a single uncompressed/unsigned ScriptObjects chunk in one partition.
    expected = (b'-==-' * 4, 8, HEADER.size, 1, blocks, 12, 0, 32, BLOCK_SIZE,
                0, 1, NULL_INDEX, bytes(16), 0, 1, NULL_INDEX, bytes(48))
    _require(header == expected and len(toc) == 170 + 12 * blocks + 24, 'unsupported TOC layout')
    _require(toc[144:161] == bytes(11) + b'\x05' + bytes(5) and
             toc[166:170] == b'\xff' * 4, 'expected ScriptObjects at offset zero')
    size = int.from_bytes(toc[161:166], 'big')
    _require(size > 0 and blocks == (size + BLOCK_SIZE - 1) // BLOCK_SIZE and
             len(data) == (size + 15) // 16 * 16, 'UCAS/TOC length mismatch')
    for i in range(blocks):
        offset = i * BLOCK_SIZE
        length = min(BLOCK_SIZE, size - offset).to_bytes(3, 'little')
        expected_block = offset.to_bytes(5, 'little') + length + length + b'\x00'
        start = 170 + 12 * i
        _require(toc[start:start + 12] == expected_block, 'unexpected block offset, length or codec')
    chunk = data[:size]
    _require(toc[-24:] == _io_hash(chunk, engine) + bytes(4), 'ScriptObjects chunk hash/flags mismatch')
    return chunk


def _objects(data):
    _require(len(data) >= 16, 'truncated name batch')
    count, string_bytes, hash_version = struct.unpack_from('<IIQ', data)
    _require(count > 0 and hash_version == 0xC1640000, 'unsupported name batch')
    headers = 16 + count * 8
    cursor = headers + count * 2
    end = cursor + string_bytes
    _require(end + 4 <= len(data), 'truncated name data')
    names = []
    for i in range(count):
        header = struct.unpack_from('>H', data, headers + 2 * i)[0]
        wide = bool(header & 0x8000)
        if wide:
            cursor += cursor % 2
        length = (header & 0x7fff) * (2 if wide else 1)
        _require(length and cursor + length <= end, 'invalid name length')
        name = data[cursor:cursor + length].decode('utf-16-le' if wide else 'utf-8')
        name_hash = struct.unpack_from('<Q', data, 16 + i * 8)[0]
        names.append((name, name_hash))
        cursor += length
    _require(cursor == end, 'unconsumed name bytes')
    object_count, = struct.unpack_from('<I', data, end)
    _require(len(data) == end + 4 + object_count * OBJECT.size, 'invalid object table size')
    entries = {}
    references = set()
    for mapped, number, global_id, outer, cdo_class in OBJECT.iter_unpack(memoryview(data)[end + 4:]):
        name_index = mapped & 0x3fffffff
        _require(mapped >> 30 == 2 and name_index < len(names), 'invalid global mapped name')
        _require(global_id >> 62 == 1 and global_id not in entries, 'invalid or duplicate script object ID')
        entries[global_id] = (names[name_index], number, outer, cdo_class)
        references.update((outer, cdo_class))
    _require(references.difference(entries) <= {NULL_INDEX}, 'unresolved outer or class index')
    return entries


def verify_compatible_globals(base_dir: Path, stage_dir: Path, engine: Path = DEFAULT_ENGINE) -> None:
    """Old FPackageObjectIndex IDs must resolve to the same name, outer and class after the update."""
    base = _objects(_script_chunk(base_dir, engine))
    staged = _objects(_script_chunk(stage_dir, engine))
    for object_id, entry in base.items():
        _require(staged.get(object_id) == entry, f'old script object changed or missing: {entry[0][0]}')
