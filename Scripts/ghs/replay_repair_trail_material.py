"""Build replay-only flowing blue dashes and a clock-controlled derivative of the existing rings."""
import hashlib,json,shutil,sys
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test')
PATH='/Game/GHSOrderReplay/Materials/M_ReplayTrail'
RIPPLE_PATH='/Game/GHSOrderReplay/Materials/M_ReplayGroundRipple'
ML=unreal.MaterialEditingLibrary
LIB=unreal.EditorAssetLibrary
PALETTE=['#356BFA']*5


def build_material(path,domain=unreal.MaterialDomain.MD_SURFACE):
    material=LIB.load_asset(path) if LIB.does_asset_exist(path) else None
    if material:ML.delete_all_material_expressions(material)
    else:material=unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        path.rsplit('/',1)[1],path.rsplit('/',1)[0],unreal.Material,unreal.MaterialFactoryNew())
    assert material,path
    material.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property('material_domain',domain)
    material.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property('two_sided',True)
    return material


def node(material,cls,x=0,y=0,**props):
    value=ML.create_material_expression(material,cls,x,y)
    for key,item in props.items():value.set_editor_property(key,item)
    return value


def connect(source,target,pin):
    assert ML.connect_material_expressions(source,'',target,pin),(source.get_name(),pin)


def custom(material,code,names,kind=unreal.CustomMaterialOutputType.CMOT_FLOAT4):
    inputs=[]
    for name in names:
        entry=unreal.CustomInput();entry.set_editor_property('input_name',name);inputs.append(entry)
    return node(material,unreal.MaterialExpressionCustom,200,0,inputs=inputs,output_type=kind,code=code)


def output_rgba(material,expression,masked=False):
    rgb=node(material,unreal.MaterialExpressionComponentMask,600,0,r=True,g=True,b=True,a=False)
    alpha=node(material,unreal.MaterialExpressionComponentMask,600,160,r=False,g=False,b=False,a=True)
    connect(expression,rgb,'');connect(expression,alpha,'')
    assert ML.connect_material_property(rgb,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if masked:
        # Shared outgoing/return paths must not accumulate translucency brightness.
        # A depth-writing, temporally dithered mask retains their soft light coverage.
        dither=node(material,unreal.MaterialExpressionMaterialFunctionCall,850,160)
        function=LIB.load_asset('/Engine/Functions/Engine_MaterialFunctions02/Utility/DitherTemporalAA')
        assert function and dither.set_material_function(function)
        names=ML.get_material_expression_input_names(dither)
        alpha_pin=next(name for name in names if 'Alpha' in name)
        connect(alpha,dither,alpha_pin)
        assert ML.connect_material_property(dither,'',unreal.MaterialProperty.MP_OPACITY_MASK)
    else:
        assert ML.connect_material_property(alpha,'',unreal.MaterialProperty.MP_OPACITY)


def params(material):
    uv=node(material,unreal.MaterialExpressionTextureCoordinate,-700,0)
    clock=node(material,unreal.MaterialExpressionScalarParameter,-700,120,parameter_name='ReplayTime',default_value=0.)
    tint=node(material,unreal.MaterialExpressionVectorParameter,-700,-180,parameter_name='Tint',
              default_value=unreal.LinearColor(.035601315,.147027266,.955973353,1.))
    return uv,clock,tint


def finish(material,version):
    ML.recompile_material(material)
    stats=ML.get_statistics(material)
    statistics={name:stats.get_editor_property(name) for name in (
        'num_vertex_shader_instructions','num_pixel_shader_instructions','num_interpolator_scalars','num_samplers')}
    LIB.set_metadata_tag(material,'GHS.Replay.FXVersion',version)
    assert LIB.save_loaded_asset(material,only_if_is_dirty=False)
    return statistics


def build_trail_material():
    material=build_material(PATH)
    material.set_editor_property('blend_mode',unreal.BlendMode.BLEND_MASKED)
    material.set_editor_property('opacity_mask_clip_value',.333)
    material.set_editor_property('used_with_instanced_static_meshes',True)
    uv,clock,tint=params(material)
    distance=[];data=[]
    for index in range(9):
        value=node(material,unreal.MaterialExpressionPerInstanceCustomData,-1100,260+index*160,
                   data_index=index,const_default_value=9. if index in (4,5) else -1. if index==6 else 0.)
        data.append(value)
        if index<2 or index>=6:
            interp=node(material,unreal.MaterialExpressionVertexInterpolator,-700,260+index*160)
            connect(value,interp,'VS');distance.append(interp)
    active_leg=node(material,unreal.MaterialExpressionScalarParameter,-700,1150,parameter_name='ActiveLegId',default_value=-1.)
    remaining_from=node(material,unreal.MaterialExpressionScalarParameter,-700,1300,parameter_name='RemainingFromMeters',default_value=0.)
    signal=custom(material,'''float d = RouteStart + UV.x * PhaseDelta;
float progress = ProgressStart + UV.x * ProgressDelta;
float active = (ActiveLeg >= 0.0 && abs(RouteLeg - ActiveLeg) < 0.25) ? 1.0 : 0.0;
// Clip in absolute route distance: paused frames remain fixed and seeks are reversible.
float remaining = saturate((progress - RemainingFrom) / 0.06);
// A 2.25 m capsule followed by a real 0.75 m gap, measured along the directed leg.
// Advect coverage and its blue gradient together; no white hotspot or continuous underlay.
// 1.2 * 10000 / 3 is integral, matching the runtime replay-clock wrap.
float phase = (frac((d - ReplayClock * 1.2) / 3.0 + 0.5) - 0.5) * 3.0;
float across = (UV.y - 0.5) * 0.18;
float2 cap = float2(max(abs(phase) - 1.035, 0.0), across);
float sdf = length(cap) - 0.09;
float aa = clamp(fwidth(sdf), 0.008, 0.045);
float dash = 1.0 - smoothstep(-aa, aa, sdf);
// A pale, transparent blue tail leads into the theme-blue forward cap.
// Keep the opacity fade in the rear third so the visible dash stays longer than the gap.
float gradient = saturate((phase + 1.125) / 2.25);
// Linear RGB ratios map the project Tint to sRGB #8BB9FF at the tail.
float3 tailBlue = saturate(Tint * float3(7.2520595, 3.2997277, 1.0460543));
float3 blue = lerp(tailBlue, Tint, smoothstep(0.0, 0.86, gradient));
float tailCoverage = smoothstep(0.0, 0.35, gradient);
return float4(blue * 1.45, dash * tailCoverage * active * remaining);''',
                  ['UV','ReplayClock','RouteStart','PhaseDelta','Tint','RouteLeg','ProgressStart','ProgressDelta','ActiveLeg','RemainingFrom'])
    for source,pin in [(uv,'UV'),(clock,'ReplayClock'),(distance[0],'RouteStart'),(distance[1],'PhaseDelta'),(tint,'Tint'),
                       (distance[2],'RouteLeg'),(distance[3],'ProgressStart'),(distance[4],'ProgressDelta'),(active_leg,'ActiveLeg'),(remaining_from,'RemainingFrom')]:
        connect(source,signal,pin)
    output_rgba(material,signal,masked=True)
    # Miter the two end cross-sections of every plane so neighboring curve chords
    # form one continuous ribbon, rather than a chain of overlapping rectangles.
    tangent=node(material,unreal.MaterialExpressionConstant3Vector,-900,900,constant=unreal.LinearColor(1,0,0,0))
    transform=node(material,unreal.MaterialExpressionTransform,-600,900,
                   transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_INSTANCE,
                   transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    connect(tangent,transform,'')
    offset=custom(material,'''float3 d = normalize(Direction);
float side = 2.0 * UV.y - 1.0;
return side * (d * lerp(StartShear, EndShear, UV.x) + float3(-d.y, d.x, 0) * (lerp(StartWidth, EndWidth, UV.x) - 9.0));''',
                  ['UV','StartShear','EndShear','StartWidth','EndWidth','Direction'],unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    for source,pin in [(uv,'UV'),(data[2],'StartShear'),(data[3],'EndShear'),(data[4],'StartWidth'),(data[5],'EndWidth'),(transform,'Direction')]:connect(source,offset,pin)
    # UE 5.4 hides this material output from Python; use the existing scoped native bridge.
    assert unreal.GHSVisualMaterialLibrary.connect_world_position_offset(material,offset)
    assert unreal.GHSVisualMaterialLibrary.has_world_position_offset(material)
    result=finish(material,'theme-blue-fading-long-dashes-v10')
    result['custom_data_indices']=[v.get_editor_property('data_index') for v in data]
    result['vertex_interpolators']=len(distance)
    return result


def build_ripple_material():
    sys.path.insert(0,str(ROOT/'Scripts/ghs'))
    from replay_ripple_shader import REPLAY_RIPPLE_HLSL
    material=build_material(RIPPLE_PATH,unreal.MaterialDomain.MD_DEFERRED_DECAL)
    uv,clock,tint=params(material)
    phase=node(material,unreal.MaterialExpressionScalarParameter,-700,300,parameter_name='Phase',default_value=0.)
    signal=custom(material,REPLAY_RIPPLE_HLSL,['UV','T','Tint','Phase'])
    for source,pin in [(uv,'UV'),(clock,'T'),(tint,'Tint'),(phase,'Phase')]:connect(source,signal,pin)
    rgb=node(material,unreal.MaterialExpressionComponentMask,600,0,r=True,g=True,b=True,a=False)
    alpha=node(material,unreal.MaterialExpressionComponentMask,600,200,r=False,g=False,b=False,a=True)
    connect(signal,rgb,'');connect(signal,alpha,'')
    assert ML.connect_material_property(rgb,'',unreal.MaterialProperty.MP_BASE_COLOR)
    assert ML.connect_material_property(alpha,'',unreal.MaterialProperty.MP_OPACITY)
    strength=node(material,unreal.MaterialExpressionScalarParameter,600,-180,parameter_name='RippleEmission',default_value=.55)
    emission=node(material,unreal.MaterialExpressionMultiply,850,0)
    connect(rgb,emission,'A');connect(strength,emission,'B')
    assert ML.connect_material_property(emission,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    LIB.set_metadata_tag(material,'GHS.Replay.ReusedShader','Derived from Scripts/video_reference/agv_fx_shader.py:RINGS_HLSL; replay-only coverage and blue palette')
    return finish(material,'theme-blue-visible-diffusion-v2')


def repair():
    assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower(), 'Use the isolated commandlet'
    sha=lambda file:hashlib.sha256(file.read_bytes()).hexdigest()
    targets={ROOT/(p.replace('/Game/','Content/')+'.uasset') for p in [PATH,RIPPLE_PATH]}
    map_file=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
    data_file=ROOT/'Content/GHSTwinUI/data/order-replay.json'
    sources=[map_file,data_file,ROOT/'Scripts/video_reference/agv_fx_shader.py']
    sources+=list((ROOT/'Content/GHSNormalWarehouse/FX').rglob('*.uasset'))
    sources+=list((ROOT/'Content/VideoDigitalTwin/FX').rglob('*.uasset'))
    originals={str(p.relative_to(ROOT)):sha(p) for p in sources}
    other={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'Content/GHSOrderReplay').rglob('*.uasset') if p not in targets}
    out=ROOT/'Saved/OrderReplay/TrailMaterial';out.mkdir(parents=True,exist_ok=True)
    for target in targets:
        backup=out/(target.stem+'.before-remaining-route.uasset')
        if target.exists() and not backup.exists():shutil.copy2(target,backup)
    trail_stats=build_trail_material();ripple_stats=build_ripple_material()
    assert all(sha(ROOT/p)==value for p,value in originals.items()),'Protected source changed'
    assert all(sha(ROOT/p)==value for p,value in other.items()),'Unrelated replay asset changed'
    unreal.SystemLibrary.collect_garbage()
    nodes={}
    for path in [PATH,RIPPLE_PATH]:
        material=LIB.load_asset(path)
        # Deleted editor expressions may remain as orphan subobjects after rebuilding;
        # inspect connected pixel nodes, not every UObject ever owned by the material.
        coverage=unreal.MaterialProperty.MP_OPACITY_MASK if path==PATH else unreal.MaterialProperty.MP_OPACITY
        pending=[ML.get_material_property_input_node(material,p) for p in [unreal.MaterialProperty.MP_EMISSIVE_COLOR,coverage]]
        nodes[path]=[];seen=set()
        while pending:
            value=pending.pop()
            if value is None or value.get_path_name() in seen:continue
            seen.add(value.get_path_name());nodes[path].append(value)
            pending.extend(n for n in ML.get_inputs_for_material_expression(material,value) if n)
        assert not any(isinstance(o,unreal.MaterialExpressionTime) for o in nodes[path]),'Wall clock would break pause/seek'
        assert ML.get_material_property_input_node(material,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        assert ML.get_material_property_input_node(material,coverage)
        assert {str(o.get_editor_property('parameter_name')) for o in nodes[path] if isinstance(o,unreal.MaterialExpressionScalarParameter)} >= {'ReplayTime'}
    indices=trail_stats['custom_data_indices']
    assert sorted(indices)==list(range(9)),indices
    assert trail_stats['vertex_interpolators']==5
    report=dict(success=True,trail=PATH,ripple=RIPPLE_PATH,palette=PALETTE,clock='ReplayTime',wall_clock_nodes=0,
                fixed_trails=5,fixed_ground_ripples=5,custom_data_indices=indices,vertex_interpolators=5,
                width_cm=18,wavelength_m=3.,dash_length_m=2.25,gap_length_m=.75,flow_speed_mps=1.2,
                opacity_range=[0.,1.],core_coverage=1.,dither_region='Rear 35 percent fade and antialiased capsule edges',emission_range=[1.45,1.45],
                trail_pattern='Long round blue dashes with fading pale-blue tails; transparent gaps; no white highlight',
                dash_gradient_srgb=['#8BB9FF','#356BFA'],gradient_direction='Transparent pale tail to theme-blue forward cap',
                phase_source='Per-leg route metric; custom data 0=start, 1=phase delta',
                remaining_clip=dict(active_leg='ActiveLegId',distance='RemainingFromMeters',custom_data='6 leg id, 7 progress start metres, 8 progress delta metres',front_soft_edge_cm=6),
                trail_blending='Masked with engine DitherTemporalAA soft coverage and depth writing; no alpha accumulation',
                ripple_radius_cm=165,ripple_depth_cm=6,reused_shader='REPLAY_RIPPLE_HLSL derived from RINGS_HLSL',
                ripple_gradient_srgb=['#8BB9FF','#356BFA'],ripple_core_width_cm=5.28,ripple_emission=.55,
                statistics=dict(trail=trail_stats,ripple=ripple_stats),protected_hashes=originals,
                protected_sources_unchanged=True,other_replay_assets_unchanged=len(other),
                material_sha256={p.stem:sha(p) for p in targets})
    (ROOT/'Saved/OrderReplay/trail_material_repair.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    unreal.log('ORDER_REPLAY_REMAINING_ROUTE_FX_BUILT '+json.dumps(report))


if __name__=='__main__':repair()
