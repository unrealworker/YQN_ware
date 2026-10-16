import json
from pathlib import Path
import unreal
result={}
for name in ['SM_GHS_Shared_PalletCargo','SM_GHS_Shared_RackBay','SM_GHS_Presentation_CargoLow']:
    mesh=unreal.load_asset('/Game/GHSDigitalTwin/Meshes/'+name)
    if mesh:
        b=mesh.get_bounds()
        result[name]=dict(origin=[b.origin.x,b.origin.y,b.origin.z],extent=[b.box_extent.x,b.box_extent.y,b.box_extent.z],build_settings=str(unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).get_lod_build_settings(mesh,0)))
Path(r'D:\UEPro\Test\Saved\GHS_PresentationBounds.json').write_text(json.dumps(result,indent=2))
