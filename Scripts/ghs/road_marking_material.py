"""Create the two owned, opaque lane material variants with view-dependent coverage."""
import unreal

ML=unreal.MaterialEditingLibrary
LIB=unreal.EditorAssetLibrary
# Clip-space derivative of a horizontal 2-D half width normal to the projected lane.
PROJECTION="""
float w = length(Edge);
if(w<0.001) return 1;
float2 e=Edge/w;
float4 P=mul(float4(POSITION,1),MATRIX);
float4 T=mul(float4(-e.y,e.x,0,0),MATRIX);
float4 E=mul(float4(Edge*2,0,0),MATRIX);
float2 t=(T.xy-T.w*P.xy/max(P.w,1.0))*View.ViewSizeAndInvSize.xy;
float2 h=(E.xy-E.w*P.xy/max(P.w,1.0))*View.ViewSizeAndInvSize.xy/(2*max(P.w,1.0));
float width=abs(dot(h,float2(-t.y,t.x)))/max(length(t),1e-8);
return clamp(1.15/max(width,.001),1, min(7,1+45/w));
"""


def build(source,destination,channel,version,owner):
    saved=LIB.does_asset_exist(destination)
    mat=LIB.load_asset(destination) if saved else LIB.duplicate_asset(source,destination)
    if saved and LIB.get_metadata_tag(mat,owner)==version:
        return mat
    assert not saved or not LIB.get_metadata_tag(mat,owner),destination

    def node(cls,**properties):
        n=ML.create_material_expression(mat,cls)
        for k,v in properties.items():n.set_editor_property(k,v)
        return n
    def connect(a,b,pin):
        assert ML.connect_material_expressions(a,'',b,pin),pin
    def hlsl(code,inputs,kind):
        pins=[]
        for name,_ in inputs:
            pin=unreal.CustomInput();pin.set_editor_property('input_name',name);pins.append(pin)
        n=node(unreal.MaterialExpressionCustom,code=code,inputs=pins,output_type=kind)
        for name,value in inputs:connect(value,n,name)
        return n
    scalar=unreal.CustomMaterialOutputType.CMOT_FLOAT1
    rgb=unreal.CustomMaterialOutputType.CMOT_FLOAT3
    # With camera-relative world position UE also computes the previous-frame position
    # in its previous translated coordinate system for the velocity material shader.
    position=node(unreal.MaterialExpressionWorldPosition,
                  world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_CAMERA_RELATIVE_NO_OFFSETS)
    uv=node(unreal.MaterialExpressionTextureCoordinate,coordinate_index=channel)
    def factor(matrix):
        code=PROJECTION.replace('POSITION','Position').replace('MATRIX',matrix)
        return hlsl(code,[('Edge',uv),('Position',position)],scalar)
    current=factor('ResolvedView.TranslatedWorldToClip')
    previous=factor('ResolvedView.PrevTranslatedWorldToClip')
    switch=node(unreal.MaterialExpressionPreviousFrameSwitch)
    connect(current,switch,'Current Frame');connect(previous,switch,'Previous Frame')
    offset=hlsl('return float3(Edge*(Scale-1),0);',[('Edge',uv),('Scale',switch)],rgb)
    assert unreal.GHSVisualMaterialLibrary.connect_world_position_offset(mat,offset)
    mat.set_editor_property('max_world_position_offset_displacement',45.)
    interp=node(unreal.MaterialExpressionVertexInterpolator)
    connect(current,interp,'')
    road=LIB.load_asset('/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_ContextRoads')
    tint=ML.get_material_default_vector_parameter_value(road,'SurfaceTint')
    base=node(unreal.MaterialExpressionConstant3Vector,constant=tint)
    paint=ML.get_material_property_input_node(mat,unreal.MaterialProperty.MP_BASE_COLOR)
    # Preserve the terminal's existing vertex-colour fade into the surrounding ground.
    if 'ContextTransition' in source:
        ground=node(unreal.MaterialExpressionVectorParameter,parameter_name='ContextGroundTint',
                    default_value=ML.get_material_default_vector_parameter_value(mat,'ContextGroundTint'))
        lerp=node(unreal.MaterialExpressionLinearInterpolate)
        connect(base,lerp,'A');connect(ground,lerp,'B')
        alpha=node(unreal.MaterialExpressionVertexColor)
        assert ML.connect_material_expressions(alpha,'R',lerp,'Alpha')
        base=lerp
    color=hlsl('return lerp(Road,Paint,pow(max(Scale,1),-1.35));',[('Road',base),('Paint',paint),('Scale',interp)],rgb)
    assert ML.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR)
    ML.recompile_material(mat)
    LIB.set_metadata_tag(mat,owner,version)
    assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
    return mat
