"""Reload only source materials whose automatic HISM flags were superseded."""
import hashlib
import json
import re
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test')
report=json.loads((root/'Saved/GHS_InstanceMaterials.json').read_text())
assert report['success']
logged=set(re.findall(r'Material (/Game/VideoDigitalTwin/Materials/\S+) needed to have new flag set bUsedWithInstancedStaticMeshes',
    (root/'Saved/Logs/AGV_Editor.log').read_text(encoding='utf-8',errors='replace')))
paths=sorted(report['copies'])
assert set(paths).issubset(logged)
files={p:root/'Content'/((p.split('.')[0].removeprefix('/Game/'))+'.uasset') for p in paths}
before={p:hashlib.sha256(f.read_bytes()).hexdigest() for p,f in files.items()}
packages=[unreal.EditorAssetLibrary.load_asset(p.split('.')[0]).get_outermost() for p in paths]
result=unreal.EditorLoadingAndSavingUtils.reload_packages(packages,unreal.ReloadPackagesInteractionMode.ASSUME_POSITIVE)
assert result[0],str(result)
assert before=={p:hashlib.sha256(f.read_bytes()).hexdigest() for p,f in files.items()}
(root/'Saved/GHS_SourceMaterialPreservation.json').write_text(json.dumps(dict(success=True,reloaded=paths,source_sha256=before,source_files_written=False),indent=2))
