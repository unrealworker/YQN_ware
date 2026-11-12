"""Archive native JSON observations and reproduce the audit without Saved/.

Stores measured geometry, scene identity and hashes, never .umap backups,
assets, logs or runtime caches. Gzip payloads preserve original byte hashes.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'SourceAssets/MPR/rack_clearance_20261112/evidence'
MANIFEST = OUT/'manifest.json'
USE_ARCHIVE = False
INPUTS = {
    'Saved/MPR/optimization_20261112/baseline.json.gz': 'baseline.json.gz',
    'Saved/MPR/optimization_20261112/native_mesh_bounds.json': 'native_mesh_bounds.json.gz',
    'Saved/MPR/optimization_20261112/wall_solid_boxes.json': 'wall_solid_boxes.json.gz',
    'Saved/MPR/optimization_20261112/original_package_hashes.json': 'original_package_hashes.json.gz',
    'Saved/MPR/optimization_20261112/preserved_configuration.json': 'preserved_configuration.json.gz',
    'Saved/MPR/interior_cad_20261112/interior_truth/pedestrian_openings.json': 'pedestrian_openings.json.gz',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bytes(path, *, archived=None):
    path = Path(path).resolve()
    relative = path.relative_to(ROOT.resolve()).as_posix()
    if archived is None:
        archived = USE_ARCHIVE
    if path.is_file() and not (archived and relative in INPUTS):
        return path.read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding='utf8'))
    entry = manifest['inputs'][relative]
    source = (OUT/entry['archive']).resolve()
    assert source.is_relative_to(OUT.resolve())
    compressed = source.read_bytes()
    assert digest(compressed) == entry['archive_sha256'], source
    payload = gzip.decompress(compressed) if entry['encoding'] == 'gzip' else compressed
    assert digest(payload) == entry['original_sha256'] and len(payload) == entry['original_bytes'], relative
    return payload


def archive():
    OUT.mkdir(parents=True, exist_ok=True)
    entries = {}
    for relative, filename in INPUTS.items():
        raw = (ROOT/relative).read_bytes()
        encoding = 'identity' if relative.endswith('.gz') else 'gzip'
        packed = raw if encoding == 'identity' else gzip.compress(raw, compresslevel=9, mtime=0)
        destination = OUT/filename
        if destination.exists():
            assert destination.read_bytes() == packed, 'Refuse replacing different native evidence: '+relative
        else:
            destination.write_bytes(packed)
        entries[relative] = dict(archive=filename, encoding=encoding, original_bytes=len(raw),
            archive_bytes=len(packed), original_sha256=digest(raw), archive_sha256=digest(packed))
    result = dict(schema_version=1, purpose='Native geometry and preservation evidence for reproducible MPR whole-row clearance',
        map='/Game/Maps/MPR_CAD_Warehouse_B50B57',
        original_map_sha256='1af91bb69aeb9643a14b33dad7239f8d300c8e29318a85b48e84737d0c5ecf23',
        source_dxf_sha256='c316aafe183162c5bef636885b59cc1000c3eecf50d8be645490b4716c6af863',
        excluded=['map/asset binaries', 'runtime captures', 'logs', 'temporary caches'], inputs=entries)
    MANIFEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    for relative in INPUTS:
        assert read_bytes(ROOT/relative, archived=True) == (ROOT/relative).read_bytes()
    print(json.dumps(dict(success=True, inputs=len(entries), total_archive_bytes=sum(e['archive_bytes'] for e in entries.values())), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', action='store_true', required=True)
    parser.parse_args()
    archive()
