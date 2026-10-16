"""Retry the unsaved V2 attempt after Blueprint component reconstruction repair."""
import sys,json
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import apply_refinement_v2 as apply
prior=apply.read(apply.REPORT)
assert not prior['success'] and not prior['maps'],'Never discard a saved or completed revision'
for relative,entry in prior['changed_files'].items():assert apply.sha(ROOT/relative)==entry['before_sha256'],relative
current=apply.snapshot(apply.labels());before=apply.read(prior['preserved_snapshots'][apply.MAPS[0]])
allowed=set(prior['revision']['changed_groups'])|set(prior['revision']['retired_groups'])
for label,state in before.items():
    if label not in allowed:assert current[label]==state,'Unrelated edit appeared: '+label
apply.write(ROOT/'Saved/GHS_RefinementV2LiveDiagnostic.json',{k:v for k,v in current.items() if k.startswith('GHS_CAD_Wall')})
assert apply.levels.load_level(apply.MAPS[1])
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
destination=ROOT/'SourceAssets/GHS/RefinementV2/unsaved_attempt_before_component_fix.json'
assert not destination.exists()
apply.REPORT.rename(destination)
apply.run()
