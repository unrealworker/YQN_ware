import json
from pathlib import Path
import unreal
names=['DecalActor','DecalComponent','CustomInput','CustomMaterialOutputType','MaterialDomain','MaterialExpressionCustom','MaterialExpressionTime','MaterialExpressionDecalColor']
result={n: str(getattr(unreal,n,None).__doc__) for n in names}
result['attach']=unreal.Actor.attach_to_actor.__doc__
result['material_params']=unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value.__doc__
result['stats']=unreal.MaterialEditingLibrary.get_statistics.__doc__
result['time_fields']=str(unreal.MaterialExpressionTime.__doc__)
result['custom_enums']=[x for x in dir(unreal.CustomMaterialOutputType) if x.isupper()]
result['domain_enums']=[x for x in dir(unreal.MaterialDomain) if x.isupper()]
result['material_properties']=str(unreal.Material.__doc__)
Path(r'D:\UEPro\Test\Saved\AGVFX_APIs.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
