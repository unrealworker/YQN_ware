"""Validate serialized assets in a fresh UE process with no editor cache."""
import json
from pathlib import Path
import unreal
root=Path(r"D:\UEPro\Test")
script=(root/"Scripts/verify_warehouse_editor.py").read_text(encoding="utf-8").replace('report_path.write_text(json.dumps(report,indent=2), encoding="utf-8")','pass')
exec(compile(script.split('\nwh_views =')[0],"verify_warehouse_editor.py","exec"),globals())
report["fresh_process"] = True
for r in registry:
    assert "TwinId="+r["id"] in [str(t) for t in by_label[r["id"]].tags],r["id"]
report["twin_tags_match_registry"] = True
(root/"Saved/Warehouse_SavedAssetVerification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
unreal.log("WAREHOUSE_FRESH_PROCESS_VERIFIED")
