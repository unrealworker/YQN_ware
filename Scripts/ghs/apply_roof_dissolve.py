"""Create private masked roof variants; never edit original materials or level.

Run in UE Python (live dispatcher or commandlet). Each variant duplicates the
source graph, retaining its original shading and the user's glass skylight.
The runtime component restores the exact original material objects on reset.
"""
import hashlib
import json
from pathlib import Path
import traceback
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/RoofScan'
DEST='/Game/GHSZcoolSmartFactory/Roof/ScanReveal'
LIB=unreal.EditorAssetLibrary
ML=unreal.MaterialEditingLibrary
VERSION='scan-reveal-v2'
SHADER=(ROOT/'Scripts/ghs/roof_scan_shader.hlsl').read_text(encoding='utf8')
SHADER_HASH=hashlib.sha256(SHADER.encode('utf8')).hexdigest()
SOURCES=[f'/Game/GHSZcoolSmartFactory/Roof/Materials/M_GHSRoof_{role}'
         for role in ('Roof','Seams','Blue','Skylight','Detail')]
SOURCES.append('/Game/GHSZcoolSmartFactory/OfficeFacade/Materials/M_GHSFacade_Glass')

def sha_asset(path):
    return hashlib.sha256((ROOT/'Content'/(path.removeprefix('/Game/')+'.uasset')).read_bytes()).hexdigest()

def expression(mat,cls,x=0,y=0,**properties):
    node=ML.create_material_expression(mat,cls,x,y)
    for name,value in properties.items():node.set_editor_property(name,value)
    return node

def connect(a,out,b,pin):
    assert ML.connect_material_expressions(a,out,b,pin),(a,b,pin)

def property_input(mat,node,out,prop):
    assert ML.connect_material_property(node,out,prop),(node,prop)

def custom_input(name):
    value=unreal.CustomInput()
    value.set_editor_property('input_name',name)
    return value

def create(source):
    source_name=source.rsplit('/',1)[1]
    target=f'{DEST}/M_Scan_{source_name}'
    original=LIB.load_asset(source)
    assert isinstance(original,unreal.Material),source
    fingerprint=sha_asset(source)
    # A failed first import may leave only an unsaved duplicate in memory.
    if LIB.does_asset_exist(target) and not (ROOT/'Content'/(target.removeprefix('/Game/')+'.uasset')).exists():
        partial=LIB.load_asset(target)
        assert not LIB.get_metadata_tag(partial,'GHS.RoofDissolve.Version'),target
        assert LIB.delete_asset(target),target
    if LIB.does_asset_exist(target):
        material=LIB.load_asset(target)
        assert LIB.get_metadata_tag(material,'GHS.RoofDissolve.Version')==VERSION,('Unrecognized existing target',target)
        assert LIB.get_metadata_tag(material,'GHS.RoofDissolve.SourceHash')==fingerprint,('Source changed; regenerate reviewed variant',source)
        assert material.get_editor_property('blend_mode')==unreal.BlendMode.BLEND_MASKED
        if LIB.get_metadata_tag(material,'GHS.RoofScan.ShaderHash')!=SHADER_HASH:
            nodes=[n for n in unreal.ObjectIterator(unreal.MaterialExpressionCustom)
                   if n.get_outer()==material and n.get_editor_property('description')=='Roof architectural scan reveal']
            assert len(nodes)==1,('Expected owned scan node',target,len(nodes))
            nodes[0].set_editor_property('code',SHADER)
            ML.recompile_material(material)
            LIB.set_metadata_tag(material,'GHS.RoofScan.ShaderHash',SHADER_HASH)
            assert LIB.save_loaded_asset(material,only_if_is_dirty=False)
        return {'source':source,'target':target,'source_sha256':fingerprint,'reused':True}
    material=LIB.duplicate_asset(source,target)
    assert material is not None,target
    material.set_editor_property('blend_mode',unreal.BlendMode.BLEND_MASKED)
    material.set_editor_property('opacity_mask_clip_value',.5)
    # Private masked variants preserve original source shading. Fractional coverage
    # is temporally antialiased only at the scan edge and short grid afterglow.
    world=expression(material,unreal.MaterialExpressionWorldPosition,-1000,300)
    center=expression(material,unreal.MaterialExpressionVectorParameter,-1000,460,
        parameter_name='RoofCenter',default_value=unreal.LinearColor(0,0,0,0))
    axis=expression(material,unreal.MaterialExpressionVectorParameter,-1000,620,
        parameter_name='RoofAxisInvExtent',default_value=unreal.LinearColor(1,0,0,1/23312.))
    progress=expression(material,unreal.MaterialExpressionScalarParameter,-1000,780,
        parameter_name='RoofOpenProgress',default_value=0.)
    cut=expression(material,unreal.MaterialExpressionCustom,-700,300,
        description='Roof architectural scan reveal',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT4,
        inputs=[custom_input(name) for name in ('Position','Center','Axis','Progress')],
        code=SHADER)
    connect(world,'',cut,'Position')
    connect(center,'',cut,'Center')
    # UE5.4 VectorParameter exposes RGB and A separately, not a named RGBA pin.
    rgba=expression(material,unreal.MaterialExpressionAppendVector,-800,650)
    connect(axis,'',rgba,'A');connect(axis,'A',rgba,'B')
    connect(rgba,'',cut,'Axis')
    connect(progress,'',cut,'Progress')
    mask=expression(material,unreal.MaterialExpressionComponentMask,-420,300,r=True,g=False,b=False,a=False)
    edge=expression(material,unreal.MaterialExpressionComponentMask,-420,450,r=False,g=True,b=False,a=False)
    core=expression(material,unreal.MaterialExpressionComponentMask,-420,820,r=False,g=False,b=True,a=False)
    trail=expression(material,unreal.MaterialExpressionComponentMask,-420,980,r=False,g=False,b=False,a=True)
    connect(cut,'',mask,'');connect(cut,'',edge,'')
    connect(cut,'',core,'');connect(cut,'',trail,'')
    dither=expression(material,unreal.MaterialExpressionMaterialFunctionCall,-200,300,
        material_function=LIB.load_asset('/Engine/Functions/Engine_MaterialFunctions02/Utility/DitherTemporalAA'))
    connect(mask,'',dither,'Alpha Threshold')
    property_input(material,dither,'',unreal.MaterialProperty.MP_OPACITY_MASK)
    old_base=ML.get_material_property_input_node(material,unreal.MaterialProperty.MP_BASE_COLOR)
    old_base_output=ML.get_material_property_input_node_output_name(material,unreal.MaterialProperty.MP_BASE_COLOR)
    assert old_base is not None,source
    blue=expression(material,unreal.MaterialExpressionConstant3Vector,-430,630,
        constant=unreal.LinearColor(.27,.65,.95,1.))
    tint=expression(material,unreal.MaterialExpressionLinearInterpolate,-100,100)
    connect(old_base,old_base_output,tint,'A');connect(blue,'',tint,'B');connect(edge,'',tint,'Alpha')
    property_input(material,tint,'',unreal.MaterialProperty.MP_BASE_COLOR)
    white=expression(material,unreal.MaterialExpressionConstant3Vector,-200,820,
        constant=unreal.LinearColor(1.5,2.8,3.6,1.))
    leading=expression(material,unreal.MaterialExpressionMultiply,0,820)
    connect(white,'',leading,'A');connect(core,'',leading,'B')
    trailing=expression(material,unreal.MaterialExpressionMultiply,0,980)
    connect(blue,'',trailing,'A');connect(trail,'',trailing,'B')
    glow=expression(material,unreal.MaterialExpressionAdd,180,820)
    connect(leading,'',glow,'A');connect(trailing,'',glow,'B')
    old_emissive=ML.get_material_property_input_node(material,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if old_emissive:
        output=ML.get_material_property_input_node_output_name(material,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        add=expression(material,unreal.MaterialExpressionAdd,140,450)
        connect(old_emissive,output,add,'A');connect(glow,'',add,'B');glow=add
    property_input(material,glow,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    ML.recompile_material(material)
    LIB.set_metadata_tag(material,'GHS.RoofDissolve.Version',VERSION)
    LIB.set_metadata_tag(material,'GHS.RoofDissolve.SourceHash',fingerprint)
    LIB.set_metadata_tag(material,'GHS.RoofDissolve.Source',source)
    LIB.set_metadata_tag(material,'GHS.RoofScan.ShaderHash',SHADER_HASH)
    assert LIB.save_loaded_asset(material,only_if_is_dirty=False)
    return {'source':source,'target':target,'source_sha256':fingerprint,'reused':False,
            'expression_count':ML.get_num_material_expressions(material)}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report={'success':False,'variants':[],'version':VERSION,'manual_seconds':.8,'navigation_seconds':.5,'restore_seconds':.55,
            'shader_sha256':SHADER_HASH,
            'map_modified':False,'original_materials_modified':False}
    protected={path:sha_asset(path) for path in SOURCES}
    dirty={p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
    try:
        assert not any(path in dirty for path in SOURCES),'Source material has unsaved edits; inspect before cloning'
        LIB.make_directory(DEST)
        for source in SOURCES:report['variants'].append(create(source))
        assert protected=={path:sha_asset(path) for path in SOURCES},'Original material changed'
        report['success']=True
    except Exception:
        report['error']=traceback.format_exc();unreal.log_error(report['error'])
    (OUT/'roof_dissolve_apply.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert report['success'],report.get('error')
    unreal.log('GHS_ROOF_DISSOLVE_MATERIALS_READY')

main()
