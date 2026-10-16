"""Keep reference-model lettering, central disk and cables at useful distances."""
import json
from pathlib import Path
import unreal
unreal.load_module('StaticMeshEditor')
sub=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
report=[]
for name in ['SM_GHS_KukaLowProfileAGV','SM_GHS_WallCharger']:
    mesh=unreal.EditorAssetLibrary.load_asset('/Game/GHSDigitalTwin/Meshes/'+name)
    assert sub.set_lod_screen_sizes(mesh,[1,.12,.04,.012])
    assert sub.get_lod_count(mesh)==4
    assert unreal.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
    report.append(dict(mesh=name,screen_sizes=list(sub.get_lod_screen_sizes(mesh))))
Path(r'D:\UEPro\Test\Saved\GHS_EquipmentLODRefinement.json').write_text(json.dumps(dict(success=True,meshes=report)))
