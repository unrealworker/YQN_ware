"""Final visual correction of only two newly created private supply meshes."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import mpr_private_mesh_import as importer
import rebuild_preservation as guard
import unreal as u

assert '-own' in u.SystemLibrary.get_command_line().lower()
assert not u.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not u.EditorLoadingAndSavingUtils.get_dirty_content_packages()
before=guard.content_hashes(ROOT)
manifest=json.loads((ROOT/'SourceAssets/MPR/conveyor_audit_20261107/MPR_CADConveyorAudit.json').read_text(encoding='utf8'))
names={'SM_MPR_CADSupplyBelt_2CCF62','SM_MPR_CADSupplyBelt_2CCF66'}
changed=[]
for row in manifest['meshes']:
    if row['name'] not in names:continue
    mesh=importer.import_mesh(u,row,'/Game/MPRWarehouse/ConveyorAudit20261107/Meshes',replace=True)
    assert u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
    changed.append('Content/MPRWarehouse/ConveyorAudit20261107/Meshes/'+row['name']+'.uasset')
after=guard.content_hashes(ROOT)
assert len(changed)==2 and set(before)==set(after)
assert all(after[p]==h for p,h in before.items() if p not in changed)
out=ROOT/'Saved/MPR/full_workflow_20261107/conveyor_application/guard_reimport_report.json'
out.write_text(json.dumps(dict(success=True,changed={p:after[p] for p in changed},map_unchanged=True),indent=2),encoding='utf8')
