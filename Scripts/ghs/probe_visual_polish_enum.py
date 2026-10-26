import json
from pathlib import Path
import unreal
out={'names': [n for n in dir(unreal.MaterialProperty) if not n.startswith('_')]}
try:
    value=unreal.MaterialProperty(13)
    out['numeric']=str(value)
except Exception as exc:out['numeric_error']=str(exc)
for candidate in (12, 'MP_WorldPositionOffset'):
    try:out['cast_'+str(candidate)]=str(unreal.MaterialProperty.cast(candidate))
    except Exception as exc:out['cast_'+str(candidate)]=str(exc)
out['enum_methods']=[name for name in dir(unreal.MaterialProperty.static_enum()) if not name.startswith('_')]
mat=unreal.load_asset('/Game/GHSZcoolSmartFactory/VisualPolish/M_VisualPolish_Landscape')
if mat:
    try:
        expression=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector)
        out['connect_numeric']=unreal.MaterialEditingLibrary.connect_material_property(expression,'',12)
        unreal.MaterialEditingLibrary.delete_material_expression(mat,expression)
    except Exception as exc:out['connect_numeric_error']=str(exc)
    try:out['editor_only']=str(mat.get_editor_property('editor_only_data'))
    except Exception as exc:out['editor_only_error']=str(exc)
    out['children']=[]
    for obj in unreal.ObjectIterator():
        if obj.get_outer()!=mat: continue
        row={'path':obj.get_path_name(),'class':obj.get_class().get_name()}
        if 'EditorOnlyData' in row['class']:
            try:row['wpo']=str(obj.get_editor_property('world_position_offset'))
            except Exception as exc:row['error']=str(exc)
        out['children'].append(row)
Path('D:/UEPro/Test/Saved/VisualPolish/enum_probe.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
