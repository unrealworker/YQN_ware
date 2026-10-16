"""Read graph values and material parameter metadata independently."""
import json
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test')
style=json.loads((root/'SourceAssets/GHS/Presentation/material_style.json').read_text())
ml=unreal.MaterialEditingLibrary
result={}
def color(c): return [c.r,c.g,c.b,c.a]
for name,item in style.items():
    mat=unreal.EditorAssetLibrary.load_asset('/Game/GHSDigitalTwin/Materials/Instanced/M_GHS_'+name)
    node=ml.get_material_property_input_node(mat,unreal.MaterialProperty.MP_BASE_COLOR)
    result[name]=dict(node=node.get_path_name(),graph=color(node.get_editor_property('default_value')),cached=color(ml.get_material_default_vector_parameter_value(mat,'SurfaceTint')))
(root/'Saved/GHS_PresentationMaterialDiagnostic.json').write_text(json.dumps(result,indent=2))
