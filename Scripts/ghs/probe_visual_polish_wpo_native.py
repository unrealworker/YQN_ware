"""Read native reflected WPO field names. No asset or scene mutation."""
import json
from pathlib import Path
import unreal

path='/Game/GHSZcoolSmartFactory/VisualPolish/M_VisualPolish_Landscape'
mat=unreal.load_asset(path)
assert mat
report={'material':path,'mutated':False,'editor_only_data':[]}
for obj in unreal.ObjectIterator():
    if obj.get_outer()!=mat or obj.get_class().get_name()!='MaterialEditorOnlyData':continue
    row={'path':obj.get_path_name()}
    try:
        entry=obj.get_editor_property('WorldPositionOffset')
        row['wpo_native_field_read']=True
        row['struct_type']=type(entry).__name__
        row['fields']={}
        for name in ('Expression','OutputIndex','Mask','MaskR','MaskG','MaskB','MaskA','UseConstant'):
            try:
                value=entry.get_editor_property(name)
                row['fields'][name]=value.get_path_name() if hasattr(value,'get_path_name') else value if isinstance(value,(str,int,float,bool,type(None))) else str(value)
            except Exception as error:row['fields'][name]={'error':str(error)}
    except Exception as error:row['error']=str(error)
    report['editor_only_data'].append(row)
out=Path('D:/UEPro/Test/Saved/VisualPolish/wpo_native_probe.json')
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
unreal.log('GHS_VISUAL_POLISH_WPO_NATIVE_PROBED')
