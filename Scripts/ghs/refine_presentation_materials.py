"""Deep-blue lit storage surfaces; keep architectural and AGV effects separate."""
import json,sys,importlib
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
style=json.loads((ROOT/'SourceAssets/GHS/Presentation/material_style.json').read_text())
ml=unreal.MaterialEditingLibrary;lib=unreal.EditorAssetLibrary
def scalar(mat,name,value):
    n=ml.create_material_expression(mat,unreal.MaterialExpressionScalarParameter)
    n.set_editor_property('parameter_name',name);n.set_editor_property('default_value',float(value));return n
def plug(n,p):assert ml.connect_material_property(n,'',p)
for name,item in style.items():
    mat=lib.load_asset('/Game/GHSDigitalTwin/Materials/Instanced/M_GHS_'+name);assert isinstance(mat,unreal.Material)
    # UE 5.4 deletes from the array being iterated; a single call may skip
    # expressions and leave stale duplicate parameter defaults behind.
    while ml.get_num_material_expressions(mat):
        count=ml.get_num_material_expressions(mat)
        ml.delete_all_material_expressions(mat)
        assert ml.get_num_material_expressions(mat)<count,('Expression cleanup stalled',name,count)
    mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    mat.set_editor_property('used_with_instanced_static_meshes',True)
    mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT if 'opacity' in item else unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided','opacity' in item)
    c=ml.create_material_expression(mat,unreal.MaterialExpressionVectorParameter)
    c.set_editor_property('parameter_name','SurfaceTint');c.set_editor_property('default_value',unreal.LinearColor(*item['base_color'],1.0))
    plug(c,unreal.MaterialProperty.MP_BASE_COLOR)
    plug(scalar(mat,'Roughness',item['roughness']),unreal.MaterialProperty.MP_ROUGHNESS)
    plug(scalar(mat,'Metallic',item['metallic']),unreal.MaterialProperty.MP_METALLIC)
    plug(scalar(mat,'Specular',.22),unreal.MaterialProperty.MP_SPECULAR)
    if item.get('emission'):
        strength=scalar(mat,'EdgeGlow',item['emission'])
        mul=ml.create_material_expression(mat,unreal.MaterialExpressionMultiply)
        assert ml.connect_material_expressions(c,'',mul,'A') and ml.connect_material_expressions(strength,'',mul,'B')
        plug(mul,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if 'opacity' in item:plug(scalar(mat,'EnvelopeOpacity',item['opacity']),unreal.MaterialProperty.MP_OPACITY)
    ml.recompile_material(mat)
    tint=ml.get_material_default_vector_parameter_value(mat,'SurfaceTint')
    assert max(abs(a-b) for a,b in zip([tint.r,tint.g,tint.b],item['base_color']))<1e-5,(name,'SurfaceTint cache')
    for param,value in [('Roughness',item['roughness']),('Metallic',item['metallic']),('Specular',.22)]:
        assert abs(ml.get_material_default_scalar_parameter_value(mat,param)-value)<1e-5,(name,param)
    assert ml.get_num_material_expressions(mat)==4+(2 if item.get('emission') else 0)+(1 if 'opacity' in item else 0)
    assert lib.save_loaded_asset(mat,only_if_is_dirty=False)
import uniform_lighting
importlib.reload(uniform_lighting)
settings=uniform_lighting.configure()
assert unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
(ROOT/'Saved/GHS_PresentationMaterials.json').write_text(json.dumps(dict(success=True,materials=style,lighting=settings),indent=2))
