"""Read-only native-editor baseline before the additive B50B57 import."""
import json, sys, traceback
from pathlib import Path
import unreal as u

ROOT = Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir()))
sys.path.insert(0, str(ROOT/'Tools/MPRWarehouse'))
import extension_preservation as guard
OUT = ROOT/'Saved/MPR/extension_20261104'
OUT.mkdir(parents=True, exist_ok=True)
try:
    roots = ['/Game/MPRWarehouse/ReferenceV4/Props/Meshes/SM_MPR4_Tree_Oak',
             '/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup']
    roots += ['/Game/MPRWarehouse/ReferenceV4/Materials/'+p.stem
              for p in (ROOT/'Content/MPRWarehouse/ReferenceV4/Materials').glob('*.uasset')]
    frozen = [p.relative_to(ROOT).as_posix() for p in
              (ROOT/'SourceAssets/MPR/reference_v4').rglob('*')
              if p.is_file() and p.suffix in ('.json', '.fbx')]
    before = guard.capture_editor_snapshot(u, project_root=ROOT,
                  additional_packages=roots, frozen_paths=frozen)
    guard.assert_clean_baseline(before)
    (OUT/'baseline.json').write_text(json.dumps(before, ensure_ascii=False), encoding='utf-8')
    report = dict(success=True, actors=len(before['actors']),
                  dependencies=len(before['asset_hashes']), frozen_files=len(frozen),
                  map_sha256=before['map_file_sha256'])
except Exception:
    report = dict(success=False, error=traceback.format_exc())
    u.log_error(report['error'])
(OUT/'baseline_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('MPRE_BASELINE', report)
