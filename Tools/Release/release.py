"""Versioned Win64 cumulative patches. Run with Python 3.11+ on Windows.

All build output stays under Deployment/Saved. Never installs or stops a service.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from iostore_globals import verify_compatible_globals

ROOT = Path(__file__).resolve().parents[2]
CATALOG = Path(__file__).with_name('releases.json')
DEFAULT_ENGINE = Path('C:/UE/UE_5.8')
BASES = ROOT / 'Deployment/Releases'
PATCHES = ROOT / 'Deployment/Patches'
MAPS = ['/Game/Maps/GHS_WarehousePortal',
        '/Game/Maps/GHS_GlobalWarehouse',
        '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory',
        '/Game/Maps/MPR_CAD_Warehouse_B50B57']
PAKS = 'Test/Content/Paks/'
GLOBAL_PAIR = (PAKS + 'global.utoc', PAKS + 'global.ucas')


def fail(message):
    raise RuntimeError(message)


def version(value):
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise argparse.ArgumentTypeError('Use major.minor.patch, for example 1.0.1')
    return value


def version_key(value):
    return tuple(map(int, version(value).split('.')))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def now():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, encoding='utf-8').strip()


def commit(value=None):
    return git('rev-parse', '--verify', (value or 'HEAD') + '^{commit}')


def engine_info(engine):
    path = engine / 'Engine/Build/Build.version'
    data = read_json(path)
    return {'engineVersion': '.'.join(str(data[x]) for x in ('MajorVersion', 'MinorVersion', 'PatchVersion')),
            'engineBuildSHA256': sha(path), 'engineChangelist': data['Changelist']}


def runtime_path(relative):
    return (not relative.startswith('.warehouse-patch/')
            and relative not in ('warehouse-version.json', '运行说明.txt')
            and not relative.startswith('Manifest_'))


def inventory(directory):
    result = []
    pending = [directory]
    while pending:
        path = pending.pop()
        attributes = path.stat(follow_symlinks=False)
        if path.is_symlink() or getattr(attributes, 'st_file_attributes', 0) & 0x400:
            fail('Links are not allowed in a release: ' + str(path))
        if path.is_dir():
            pending.extend(path.iterdir())
        elif path.is_file():
            relative = path.relative_to(directory).as_posix()
            if runtime_path(relative):
                result.append({'path': relative, 'size': path.stat().st_size, 'sha256': sha(path)})
    return sorted(result, key=lambda item: item['path'])


def verify_files(directory, entries):
    for item in entries:
        path = directory / item['path']
        if not path.is_file() or path.stat().st_size != item['size'] or sha(path) != item['sha256']:
            fail('Release file differs: ' + str(path))


def verify_baseline(directory, entries):
    actual = inventory(directory)
    if actual != sorted(entries, key=lambda item: item['path']):
        fail('Baseline contents changed (including extra/missing files): ' + str(directory))
    if any(re.search(r'_P\.(pak|utoc|ucas|sig)$', item['path'], re.I) for item in actual):
        fail('A cumulative patch must be based only on the original full release')


def run(arguments, log):
    log.parent.mkdir(parents=True, exist_ok=True)
    print('Running ' + str(arguments[0]) + '; log: ' + str(log), flush=True)
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run([str(x) for x in arguments], cwd=ROOT,
                                stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        fail(f'Command failed ({result.returncode}); inspect {log}')


def catalog():
    return read_json(CATALOG)


def record(entry):
    data = catalog()
    if any(row['version'] == entry['version'] for row in data['releases']):
        fail('Version already recorded: ' + entry['version'])
    data['releases'].append(entry)
    write_json(CATALOG, data)


def register_base(args):
    package = Path(args.package).resolve(strict=True)
    destination = BASES / args.version
    if destination.exists() or any(x['version'] == args.version for x in catalog()['releases']):
        fail('A registered baseline/version is immutable; choose a new version')
    files = inventory(package)
    names = {x['path'] for x in files}
    for required in ('TestGame.exe', 'Test/Binaries/Win64/TestGame-Win64-Shipping.exe',
                     PAKS + 'Test-Windows.pak', PAKS + 'Test-Windows.utoc', PAKS + 'Test-Windows.ucas'):
        if required not in names:
            fail('Not a full Windows package: missing ' + required)
    if any(re.search(r'_P\.(pak|utoc|ucas)$', x) for x in names):
        fail('Register a clean full release, not an installation with patches')
    source_commit = commit(args.source_commit)
    temporary = destination.with_name(destination.name + '.incomplete')
    temporary.mkdir(parents=True, exist_ok=False)
    for item in files:
        target = temporary / 'package' / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(package / item['path'], target)
    verify_files(temporary / 'package', files)
    native = temporary / 'Windows'
    native.mkdir()
    for path in (temporary / 'package' / PAKS).iterdir():
        if path.is_file():
            shutil.copy2(path, native / path.name)
    log = ROOT / 'Saved/Packaging/Versioning' / ('Register-' + args.version + '.log')
    extract = temporary / 'registry-extract'
    run([args.engine / 'Engine/Binaries/Win64/UnrealPak.exe',
         native / 'Test-Windows.pak', '-Extract', extract, '-Filter=*AssetRegistry.bin'], log)
    registries = list(extract.rglob('AssetRegistry.bin'))
    if len(registries) != 1:
        fail('Expected exactly one original runtime AssetRegistry.bin in the baseline pak')
    shutil.copy2(registries[0], native / 'AssetRegistry.bin')
    metadata = {'schemaVersion': 1, 'kind': 'full-baseline', 'project': 'Test',
                'version': args.version, 'platform': 'Win64', 'configuration': 'Shipping',
                **engine_info(args.engine), 'sourceCommit': source_commit,
                'createdAt': now(), 'files': files, 'nativeFiles': inventory(native),
                'registryProvenance': 'Extracted from this exact original package; no newer cook metadata used'}
    write_json(temporary / 'baseline.json', metadata)
    temporary.rename(destination)
    record({'version': args.version, 'kind': 'full-baseline', 'status': 'registered',
            'sourceCommit': source_commit, 'baselineManifestSHA256': sha(destination / 'baseline.json'),
            'artifact': destination.relative_to(ROOT).as_posix(), 'notes': args.notes})
    print('Registered immutable baseline: ' + str(destination))


def select_patch_files(windows_stage, base, baseline, engine):
    staged_files = {x['path']: x for x in inventory(windows_stage)}
    base_files = {x['path']: x for x in baseline['files']}
    if any(name not in staged_files or name not in base_files for name in GLOBAL_PAIR):
        fail('Missing global IoStore file in the staged build or baseline')
    new_globals = any(staged_files[name]['sha256'] != base_files[name]['sha256'] for name in GLOBAL_PAIR)
    if new_globals:
        verify_compatible_globals(base / 'package' / PAKS, windows_stage / PAKS, engine)

    selected = []
    for name, item in staged_files.items():
        if name in GLOBAL_PAIR:
            if new_globals:
                selected.append(item)
        elif name.startswith(PAKS):
            if re.fullmatch(r'Test-Windows_0_P\.(pak|utoc|ucas|sig)', name[len(PAKS):]):
                selected.append(item)
            elif name in base_files and item['sha256'] != base_files[name]['sha256']:
                fail('Non-patch container changed; a new full baseline is required: ' + name)
            elif name not in base_files:
                fail('Unexpected container; review chunk/split-container support: ' + name)
        elif name not in base_files or item['sha256'] != base_files[name]['sha256']:
            selected.append(item)
    for name in base_files:
        if not name.startswith(PAKS) and name not in staged_files:
            fail('Removing a baseline loose file requires a new full baseline: ' + name)
    selected_names = {x['path'] for x in selected}
    for extension in ('pak', 'utoc', 'ucas'):
        if PAKS + 'Test-Windows_0_P.' + extension not in selected_names:
            fail('Missing native patch container: ' + extension)
    return selected, (2 if new_globals else 1)


def build_patch(args):
    data = catalog()
    if any(row['version'] == args.version for row in data['releases']):
        fail('Version is already recorded; published artifacts must never be overwritten')
    if version_key(args.version) <= version_key(args.base):
        fail('Patch version must be newer than the baseline')
    if version_key(args.version)[0] != version_key(args.base)[0]:
        fail('A major version change requires a new full baseline')
    previous = [version_key(x['version']) for x in data['releases']]
    if previous and version_key(args.version) <= max(previous):
        fail('Version must increase monotonically')
    base = BASES / args.base
    baseline = read_json(base / 'baseline.json')
    record_base = next((x for x in data['releases'] if x['version'] == args.base), None)
    if not record_base or sha(base / 'baseline.json') != record_base['baselineManifestSHA256']:
        fail('Baseline manifest does not match the registered release')
    if engine_info(args.engine) != {key: baseline[key] for key in engine_info(args.engine)}:
        fail('Engine build changed; create and verify a new full baseline')
    verify_baseline(base / 'package', baseline['files'])
    verify_baseline(base / 'Windows', baseline['nativeFiles'])
    output = PATCHES / args.version
    stage = ROOT / 'Saved/PatchStaging' / args.version
    logs = ROOT / 'Saved/Packaging/Versioning' / args.version
    if output.exists() or stage.exists():
        fail('Version output/staging already exists; inspect the failed run before retrying')
    source_commit = commit(args.source_commit)
    dirty = git('status', '--porcelain', '--untracked-files=no')
    uat = args.engine / 'Engine/Build/BatchFiles/RunUAT.bat'
    common = ['BuildCookRun', '-project=' + str(ROOT / 'Test.uproject'), '-noP4',
              '-platform=Win64', '-target=TestGame', '-clientconfig=Shipping',
              '-unattended', '-utf8output', '-nodebuginfo']
    if args.reuse_cooked_from:
        # Explicit migration of an already verified staged build. Zen data must
        # still exist locally; this is not a portable cooked-data snapshot.
        reference = Path(args.reuse_cooked_from).resolve(strict=True)
        staged = ROOT / 'Saved/StagedBuilds/Windows'
        verify_files(staged, inventory(reference))
    else:
        # UE rejects -iterate together with -basedonreleaseversion. Keep the
        # incremental compile/cook and native patch stage as separate commands.
        run([uat, *common, '-build', '-cook', '-iterate', '-map=' + '+'.join(MAPS)], logs / 'Cook.log')
    run([uat, *common, '-skipbuild', '-nocompileeditor', '-skipcook', '-stage', '-pak', '-iostore', '-compressed', '-prereqs',
         '-generatepatch', '-basedonreleaseversion=' + args.base,
         '-basedonreleaseversionroot=' + str(BASES), '-stagingdirectory=' + str(stage)], logs / 'Patch.log')
    windows_stage = stage / 'Windows'
    if not (windows_stage / 'TestGame.exe').is_file():
        fail('Expected UAT Windows staging directory: ' + str(windows_stage))
    selected, schema_version = select_patch_files(windows_stage, base, baseline, args.engine)
    output.mkdir(parents=True)
    for item in selected:
        target = output / 'payload' / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(windows_stage / item['path'], target)
    verify_files(output / 'payload', selected)
    manifest = {'schemaVersion': schema_version, 'kind': 'cumulative-patch', 'project': 'Test',
                'baseVersion': args.base, 'version': args.version, **engine_info(args.engine),
                'sourceCommit': source_commit, 'sourceTrackedChanges': dirty,
                'createdAt': now(), 'notes': args.notes, 'baseFiles': baseline['files'],
                'files': selected, 'payloadBytes': sum(x['size'] for x in selected),
                'baselineManifestSHA256': sha(base / 'baseline.json')}
    write_json(output / 'patch.json', manifest)
    shutil.copy2(Path(__file__).with_name('Apply-WarehousePatch.ps1'), output)
    (output / '安装说明.txt').write_text(
        f'YQN 仓库 {args.version} 累计补丁（基线 {args.base}）\n\n'
        '先停止目标程序和像素流实例，再在 PowerShell 中执行：\n'
        '.\\Apply-WarehousePatch.ps1 -PatchDirectory . -InstallDirectory "完整程序目录" -CheckOnly\n'
        '.\\Apply-WarehousePatch.ps1 -PatchDirectory . -InstallDirectory "完整程序目录"\n\n'
        '回退至基线：.\\Apply-WarehousePatch.ps1 -Rollback -InstallDirectory "完整程序目录"\n'
        '不要手工复制容器。安装器核验基线与补丁，替换旧累计补丁并保存回退备份。\n'
        '本补丁不能独立运行；安装成功后重新启动服务，观看者重新进入页面。\n', encoding='utf-8-sig')
    archive = PATCHES / f'YQN-Warehouse-{args.base}-to-{args.version}-Win64-Patch.zip'
    if archive.exists():
        fail('ZIP already exists')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                bundle.write(path, 'YQN-Warehouse-' + args.version + '-Patch/' + path.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            fail('ZIP CRC verification failed')
        for path in output.rglob('*'):
            if path.is_file():
                member = 'YQN-Warehouse-' + args.version + '-Patch/' + path.relative_to(output).as_posix()
                if hashlib.sha256(bundle.read(member)).hexdigest() != sha(path):
                    fail('ZIP content verification failed: ' + member)
    record({'version': args.version, 'kind': 'cumulative-patch', 'status': 'built',
            'baseVersion': args.base, 'sourceCommit': source_commit, 'notes': args.notes,
            'artifact': archive.relative_to(ROOT).as_posix(), 'sha256': sha(archive),
            'bytes': archive.stat().st_size, 'payloadBytes': manifest['payloadBytes']})
    print(f'Patch ready: {archive}\nPayload: {manifest["payloadBytes"]:,} bytes; ZIP: {archive.stat().st_size:,} bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, default=DEFAULT_ENGINE)
    actions = parser.add_subparsers(dest='action', required=True)
    base = actions.add_parser('register-base', help='Preserve an existing full package without rebuilding it')
    base.add_argument('--version', type=version, required=True)
    base.add_argument('--package', required=True)
    base.add_argument('--source-commit', required=True)
    base.add_argument('--notes', required=True)
    patch = actions.add_parser('build-patch', help='Incrementally cook, then generate a cumulative native UE patch')
    patch.add_argument('--version', type=version, required=True)
    patch.add_argument('--base', type=version, required=True)
    patch.add_argument('--notes', required=True)
    patch.add_argument('--source-commit')
    patch.add_argument('--reuse-cooked-from', help='Explicitly reuse a package matching the current staging files')
    args = parser.parse_args()
    if git('branch', '--show-current') != 'master':
        fail('Project releases must be built on master')
    (register_base if args.action == 'register-base' else build_patch)(args)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
