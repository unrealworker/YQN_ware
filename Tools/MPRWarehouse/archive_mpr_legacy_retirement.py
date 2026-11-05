"""Archive the completed legacy cleanup as an immutable historical event.

Only reads Saved evidence and writes the dedicated retirement archive. It does
not inspect today's map or Content bytes: later scene edits are separate work.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CACHE_REL = 'Saved/MPR/cleanup_20261105'
OUT_REL = 'SourceAssets/MPR/rebuild_b50b57/retirement_20261105'
EVIDENCE = (
    'legacy_audit.json',
    'legacy_predelete.json',
    'legacy_delete.json',
    'legacy_delete_progress.json',
    'backup_manifest.json',
    'legacy_audit_scene_snapshot.json',
    'legacy_predelete_scene_snapshot.json',
    'legacy_after_scene_snapshot.json',
    'after_cleanup/current_validation.json',
    'after_cleanup/current_snapshot.json',
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8')


def gzip_bytes(data):
    stream = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0) as zipped:
        zipped.write(data)
    result = stream.getvalue()
    require(gzip.decompress(result) == data, 'Compression roundtrip failed')
    return result


def write_immutable(path, data):
    if path.exists():
        require(path.read_bytes() == data, 'Refusing to overwrite different retirement evidence: ' + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def main(root=ROOT):
    cache, output = root / CACHE_REL, root / OUT_REL
    raw = {name: (cache / name).read_bytes() for name in EVIDENCE}
    records = {name: json.loads(data) for name, data in raw.items()}
    audit = records['legacy_audit.json']
    predelete = records['legacy_predelete.json']
    deletion = records['legacy_delete.json']
    progress = records['legacy_delete_progress.json']
    backup = records['backup_manifest.json']
    validated = records['after_cleanup/current_validation.json']
    for label, record in [('audit', audit), ('predelete', predelete), ('delete', deletion),
                          ('progress', progress), ('after_cleanup', validated)]:
        require(record['success'] is True, label + ' did not succeed')
    require(audit['eligible_for_review'] and predelete['eligible_for_review'], 'Audit was not eligible')
    require(deletion['phase'] == progress['phase'] == 'complete', 'Cleanup is incomplete')
    require(deletion['reviewed_audit_sha256'] == sha(raw['legacy_audit.json']) == validated['user_audit_sha256'], 'Audit chain mismatch')
    require(deletion['predelete_audit_sha256'] == sha(raw['legacy_predelete.json']), 'Predelete chain mismatch')
    require(deletion['backup_manifest_sha256'] == sha(raw['backup_manifest.json']), 'Backup chain mismatch')
    require(backup['audit_sha256'] == deletion['reviewed_audit_sha256'] and
            backup['predelete_sha256'] == deletion['predelete_audit_sha256'], 'Backup audit mismatch')
    require(validated['deletion_manifest_sha256'] == sha(raw['legacy_delete.json']), 'Validation deletion chain mismatch')
    require(audit['all_content_files'] == predelete['all_content_files'], 'Content changed between approved audits')
    expected = {name: spec for row in audit['deletable'] for name, spec in row['files'].items()}
    require(expected == backup['files'], 'Backup does not cover exactly the deletion files')
    require(set(expected) == set(deletion['deleted_files']) == set(progress['deleted_files']), 'Deleted file sets differ')
    require(set(row['package'] for row in audit['deletable']) == set(deletion['deleted_packages']), 'Deleted package sets differ')
    retained = {name: spec['sha256'] for name, spec in audit['all_content_files'].items() if name not in expected}
    require(retained == deletion['retained_content_hashes'], 'Retained byte verification differs')
    require({name: spec['sha256'] for name, spec in expected.items()} == deletion['deleted_file_hashes'], 'Deleted byte hashes differ')
    require(audit['candidate_count'] == 770 and deletion['deleted_package_count'] == 626 and
            deletion['retained_legacy_package_count'] == 144, 'Unexpected retirement scope')
    require(len(expected) == deletion['deleted_file_count'] == 626, 'Unexpected retired file count')
    for key in ['live_scene_unchanged', 'current_map_file_unchanged', 'retained_content_unchanged']:
        require(deletion[key] is True, 'Preservation failed: ' + key)
    original = raw['legacy_audit_scene_snapshot.json']
    require(original == raw['legacy_predelete_scene_snapshot.json'] == raw['legacy_after_scene_snapshot.json'],
            'Current user scene bytes changed across cleanup')
    require(sha(original) == audit['scene_snapshot_sha256'] == predelete['scene_snapshot_sha256'] ==
            deletion['after_scene_snapshot_sha256'] == validated['user_baseline_sha'], 'Snapshot hash chain mismatch')
    require(sha(raw['after_cleanup/current_snapshot.json']) == validated['snapshot_sha256'], 'Post-cleanup snapshot mismatch')
    require(audit['map_sha256'] == predelete['map_sha256'] == deletion['map_sha256'] ==
            validated['map_sha256'] == validated['user_baseline_map_sha256'], 'User map hash mismatch')
    require(deletion['scene_actor_count'] == validated['preservation']['actor_count'] ==
            validated['preservation']['unchanged_existing_actors'] == 905, 'Live actor preservation mismatch')
    require(not validated['missing_game_packages'] and not validated['transport_mesh_changes'] and
            validated['transport_patch_sha256'] is None, 'Evidence is not the standalone cleanup event')
    require(validated['retirement']['deleted_files'] == 626 and
            validated['retirement']['retained_content_files'] == len(retained), 'Post-cleanup inventory mismatch')
    require(validated['historical_migration_evidence_modified'] is False, 'Original migration evidence changed')
    files = {}
    for name, data in raw.items():
        archived_name = name + '.gz'
        compressed = gzip_bytes(data)
        write_immutable(output / archived_name, compressed)
        files[archived_name] = dict(sha256=sha(compressed), bytes=len(compressed),
            source=CACHE_REL + '/' + name, source_sha256=sha(data), source_bytes=len(data), compression='gzip')
    readme = (
        '# MPR 旧场景清理记录（2026-11-05）\n\n'
        '本目录只记录旧场景资源清理这一独立事件，不包含后续路网或交通修改。\n\n'
        '- 删除旧关卡 `/Game/Maps/MPR_CAD_Warehouse` 及其不再被其他资源引用的专属资源，共 626 个包、626 个文件。\n'
        '- 保留 144 个旧命名空间中的共享包；新版关卡的主仓、内部设备、模型和材质仍依赖它们。\n'
        '- 清理前后以用户当时已保存的新版关卡为基线：905 个 Actor 完全不变，全部 1843 个保留 Content 文件字节不变。原始重建报告中的 906 个 Actor 是历史基线，不用于覆盖用户修改。\n'
        '- 旧 `SourceAssets/MPR` 下的 Blender、FBX、布局和贴图源文件保留；当前重建和光伏工具仍复用这些构建依赖。\n'
        '- 原 `validation/` 和 `scene_ownership.json` 保持历史内容。本目录不更新它们。\n\n'
        '执行顺序为同步全项目引用审计、复核、文件备份与哈希校验、按引用先后删除、现场状态及所有保留资源校验。硬/软包引用和硬/软管理引用都参与保护闭包；动态源代码和配置引用另行审阅。\n\n'
        '`index.json` 记录每个 gzip 文件及解压后源文件的 SHA-256。三个 `legacy_*_scene_snapshot.json.gz` 的源文件字节完全相同；`after_cleanup/current_snapshot.json.gz` 是独立验证器的后验快照。备份实体只存于 `Saved/MPR/cleanup_20261105/backup`，不纳入版本库；这里只归档备份清单。\n\n'
        '清理时新版关卡 SHA-256：`' + deletion['map_sha256'] + '`。\n'
    ).encode('utf8')
    write_immutable(output / 'README.md', readme)
    files['README.md'] = dict(sha256=sha(readme), bytes=len(readme))
    index = dict(schema_version=1, success=True, event='MPR legacy retirement 2026-11-05',
        evidence_is_historical=True, contains_later_transport_changes=False,
        old_map=deletion['old_map'], preserved_map=deletion['current_map'], map_sha256=deletion['map_sha256'],
        candidate_packages=770, deleted_packages=626, deleted_files=626, retained_shared_legacy_packages=144,
        retained_content_files=len(retained), preserved_actors=905,
        preserved_scene_snapshot_sha256=sha(original),
        backup_files_included=False, source_models_deleted=False,
        original_validation_and_ownership_modified=False,
        execution_tool_sha256=deletion['tool_sha256'],
        archive_tool_sha256=sha(Path(__file__).read_bytes()), files=files)
    write_immutable(output / 'index.json', json_bytes(index))
    # Verify archive against the same immutable inputs after all output writes.
    for name, data in raw.items():
        require((cache / name).read_bytes() == data, 'Saved evidence changed while archiving: ' + name)
        require(gzip.decompress((output / (name + '.gz')).read_bytes()) == data, 'Archive roundtrip mismatch: ' + name)
    print(json.dumps(dict(success=True, archived_files=len(files) + 1, output=OUT_REL,
        deleted_packages=626, retained_shared_legacy_packages=144,
        bytes=sum(p.stat().st_size for p in output.rglob('*') if p.is_file())), ensure_ascii=False))
    return index


if __name__ == '__main__':
    main()
