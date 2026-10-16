"""Force material-slot serialization; direct property edits do not dirty meshes."""
import json
from pathlib import Path
import unreal
root=Path(r"D:\UEPro\Test")
lib=unreal.EditorAssetLibrary
records=[]
for manifest in ["architecture.json","vehicles.json","vegetation.json","site_details.json"]:
    for item in json.loads((root/"SourceAssets/LogisticsWarehouse"/manifest).read_text())["meshes"]:
        mesh=lib.load_asset("/Game/LogisticsWarehouse/Meshes/"+item["name"])
        slots=mesh.get_editor_property("static_materials")
        for i,slot in enumerate(slots):
            name=str(slot.get_editor_property("imported_material_slot_name"))
            mat=lib.load_asset("/Game/LogisticsWarehouse/Materials/"+name)
            assert mat,name
            slot.set_editor_property("material_interface",mat)
            slots[i]=slot
        mesh.set_editor_property("static_materials",slots)
        assert lib.save_loaded_asset(mesh,only_if_is_dirty=False)
        records.append(item["name"])
(root/"Saved/Warehouse_MaterialPersistence.json").write_text(json.dumps({"saved":records},indent=2))
