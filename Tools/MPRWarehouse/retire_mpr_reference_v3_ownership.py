"""Retire only unused task-created V3 experiment packages from the catalog.

Files remain on disk for local recovery; no UE package or map is modified.
Recursive saved-map package dependencies must contain no V3 reference.
"""
from pathlib import Path
import sys,json,shutil,hashlib
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_scene_ownership import verify_owned_scene
verify_owned_scene(ROOT)
registry=u.AssetRegistryHelpers.get_asset_registry();registry.search_all_assets(synchronous_search=True)
options=u.AssetRegistryDependencyOptions(include_soft_package_references=True,include_hard_package_references=True,include_searchable_names=False,include_soft_management_references=True,include_hard_management_references=True)
seen=set();pending=['/Game/Maps/MPR_CAD_Warehouse']
while pending:
    name=pending.pop()
    if name in seen:continue
    seen.add(name)
    for dependency in registry.get_dependencies(name,options):
        path=str(dependency)
        if path.startswith('/Game/') and path not in seen:pending.append(path)
assert not [p for p in seen if p.startswith('/Game/MPRWarehouse/ReferenceV3/')]
file=ROOT/'SourceAssets/MPR/scene_ownership.json';before=file.read_bytes();data=json.loads(before)
retired=[row for row in data['packages'] if row['package'].startswith('/Game/MPRWarehouse/ReferenceV3/')]
out=ROOT/'Saved/MPR/reference_v3_retired_ownership.json'
out.write_text(json.dumps(dict(before_sha256=hashlib.sha256(before).hexdigest(),retired=retired),indent=2),encoding='utf8')
data['packages']=[r for r in data['packages'] if r not in retired]
file.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
verify_owned_scene(ROOT)
report=dict(success=True,retired_unused_packages=len(retired),deleted_files=0,recursive_map_dependencies=sorted(seen),v3_dependencies=0)
(ROOT/'SourceAssets/MPR/reference_v4/validation/package_dependencies.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('MPR_REFERENCE_V3_RETIRED',len(retired))
