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
OUT=ROOT/'Saved/RoofTraffic'
DEST='/Game/GHSZcoolSmartFactory/Roof/Dissolve'
LIB=unreal.EditorAssetLibrary
ML=unreal.MaterialEditingLibrary
VERSION='center-out-0.5s-v1'
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
    target=f'{DEST}/M_Dissolve_{source_name}'
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
        return {'source':source,'target':target,'source_sha256':fingerprint,'reused':True}
    material=LIB.duplicate_asset(source,target)
    assert material is not None,target
    material.set_editor_property('blend_mode',unreal.BlendMode.BLEND_MASKED)
    material.set_editor_property('opacity_mask_clip_value',.5)
    # A narrow, lightly irregular front moves symmetrically out from center.
    # Clip testing uses opaque masked rendering: no translucent sorting and no
    # permanent translucent overdraw after the 0.5 second transition.
    world=expression(material,unreal.MaterialExpressionWorldPosition,-1000,300)
    center=expression(material,unreal.MaterialExpressionVectorParameter,-1000,460,
        parameter_name='RoofCenter',default_value=unreal.LinearColor(0,0,0,0))
    axis=expression(material,unreal.MaterialExpressionVectorParameter,-1000,620,
        parameter_name='RoofAxisInvExtent',default_value=unreal.LinearColor(1,0,0,1/23312.))
    progress=expression(material,unreal.MaterialExpressionScalarParameter,-1000,780,
        parameter_name='RoofOpenProgress',default_value=0.)
    cut=expression(material,unreal.MaterialExpressionCustom,-700,300,
        description='Roof center-out pale blue dissolve',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT2,
        inputs=[custom_input(name) for name in ('Position','Center','Axis','Progress')],
        code='''float3 p=Position-Center;
float u=abs(dot(p,Axis.xyz))*Axis.w;
float grain=(sin(p.x*0.027+p.y*0.019)*sin(p.y*0.043+p.z*0.021))*0.006;
float field=u+grain;
float front=saturate(Progress)*1.08-0.04;
float keep=step(front,field);
float edge=saturate(1.0-abs(field-front)/0.035)*keep;
return float2(keep,edge);''')
    connect(world,'',cut,'Position')
    connect(center,'',cut,'Center')
    # UE5.4 VectorParameter exposes RGB and A separately, not a named RGBA pin.
    rgba=expression(material,unreal.MaterialExpressionAppendVector,-800,650)
    connect(axis,'',rgba,'A');connect(axis,'A',rgba,'B')
    connect(rgba,'',cut,'Axis')
    connect(progress,'',cut,'Progress')
    mask=expression(material,unreal.MaterialExpressionComponentMask,-420,300,r=True,g=False,b=False,a=False)
    edge=expression(material,unreal.MaterialExpressionComponentMask,-420,450,r=False,g=True,b=False,a=False)
    connect(cut,'',mask,'');connect(cut,'',edge,'')
    property_input(material,mask,'',unreal.MaterialProperty.MP_OPACITY_MASK)
    old_base=ML.get_material_property_input_node(material,unreal.MaterialProperty.MP_BASE_COLOR)
    old_base_output=ML.get_material_property_input_node_output_name(material,unreal.MaterialProperty.MP_BASE_COLOR)
    assert old_base is not None,source
    blue=expression(material,unreal.MaterialExpressionConstant3Vector,-430,630,
        constant=unreal.LinearColor(.30,.70,1.,1.))
    tint=expression(material,unreal.MaterialExpressionLinearInterpolate,-100,100)
    connect(old_base,old_base_output,tint,'A');connect(blue,'',tint,'B');connect(edge,'',tint,'Alpha')
    property_input(material,tint,'',unreal.MaterialProperty.MP_BASE_COLOR)
    glow=expression(material,unreal.MaterialExpressionMultiply,-100,450)
    connect(blue,'',glow,'A');connect(edge,'',glow,'B')
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
    assert LIB.save_loaded_asset(material,only_if_is_dirty=False)
    return {'source':source,'target':target,'source_sha256':fingerprint,'reused':False,
            'expression_count':ML.get_num_material_expressions(material)}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report={'success':False,'variants':[],'version':VERSION,'duration_seconds':.5,
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
