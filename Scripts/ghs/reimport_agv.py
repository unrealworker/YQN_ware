"""Reimport only the corrected GHS AGV using the same validated import settings."""
import json
from pathlib import Path
root=Path(r'D:\UEPro\Test')
old_report=json.loads((root/'Saved/GHS_AssetImport.json').read_text(encoding='utf-8'))
source=(root/'Scripts/ghs/prepare_ue_assets.py').read_text(encoding='utf-8')
changes={"['kuka_agv','charger','cad_architecture']":"['kuka_agv']",
         "['SM_VR_RackBay','SM_VR_PalletCargo','SM_VR_Conveyor']":"[]",
         "'Saved/GHS_AssetImport.json'":"'Saved/GHS_AGVReimport.json'"}
for original,replacement in changes.items():
    assert source.count(original)==1,original
    source=source.replace(original,replacement)
exec(compile(source,'ghs_agv_reimport.py','exec'),{})
new_report=json.loads((root/'Saved/GHS_AGVReimport.json').read_text(encoding='utf-8'))
assert new_report['success'] and len(new_report['meshes'])==1
updated=new_report['meshes'][0]
old_report['meshes']=[updated if entry['name']==updated['name'] else entry for entry in old_report['meshes']]
old_report['agv_turntable_clearance_fixed']=True
(root/'Saved/GHS_AssetImport.json').write_text(json.dumps(old_report,indent=2),encoding='utf-8')
