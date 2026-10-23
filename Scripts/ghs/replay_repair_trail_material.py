"""Rebuild only the replay trail material; never import models or load/save a map."""
import hashlib,json,shutil
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test')
PATH='/Game/GHSOrderReplay/Materials/M_ReplayTrail'
ML=unreal.MaterialEditingLibrary
LIB=unreal.EditorAssetLibrary


def build_trail_material():
    material=LIB.load_asset(PATH)
    if material:ML.delete_all_material_expressions(material)
    else:material=unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'M_ReplayTrail','/Game/GHSOrderReplay/Materials',unreal.Material,unreal.MaterialFactoryNew())
    assert material,PATH
    material.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property('two_sided',True)
    material.set_editor_property('used_with_instanced_static_meshes',True)

    def node(cls,x,y,**props):
        value=ML.create_material_expression(material,cls,x,y)
        for key,item in props.items():value.set_editor_property(key,item)
        return value

    def connect(source,target,pin):
        assert ML.connect_material_expressions(source,'',target,pin),(source.get_name(),pin)

    color=node(unreal.MaterialExpressionConstant3Vector,-700,-200,constant=unreal.LinearColor(.015,.20,.9,1))
    assert ML.connect_material_property(color,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    uv=node(unreal.MaterialExpressionTextureCoordinate,-700,0)
    clock=node(unreal.MaterialExpressionScalarParameter,-700,120,parameter_name='ReplayTime',default_value=0.)
    distance=[]
    for index in range(2):
        data=node(unreal.MaterialExpressionPerInstanceCustomData,-1000,260+index*160,
                  data_index=index,const_default_value=0.)
        # ISM custom data is a vertex-stage input in UE 5.4; explicitly interpolate it.
        interp=node(unreal.MaterialExpressionVertexInterpolator,-700,260+index*160)
        connect(data,interp,'VS');distance.append(interp)
    inputs=[]
    for name in ['UV','ReplayClock','RouteStart','SegmentLength']:
        entry=unreal.CustomInput();entry.set_editor_property('input_name',name);inputs.append(entry)
    mask=node(unreal.MaterialExpressionCustom,-280,100,inputs=inputs,
              output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,
              description='Continuous route metres; 5m wavelength, 1.2m/s, replay-clock driven',
              code='''float distanceMeters = RouteStart + UV.x * SegmentLength;
float edge = smoothstep(0.0, 0.16, UV.y) * smoothstep(0.0, 0.16, 1.0 - UV.y);
float flow = 0.5 + 0.5 * cos((distanceMeters - ReplayClock * 1.2) * 6.28318530718 / 5.0);
return edge * (0.16 + 0.18 * flow * flow * flow);''')
    for source,pin in [(uv,'UV'),(clock,'ReplayClock'),(distance[0],'RouteStart'),(distance[1],'SegmentLength')]:
        connect(source,mask,pin)
    assert ML.connect_material_property(mask,'',unreal.MaterialProperty.MP_OPACITY)
    ML.recompile_material(material)
    # GetStatistics blocks until the active platform's material compilation completes.
    stats=ML.get_statistics(material)
    statistics={name:stats.get_editor_property(name) for name in (
        'num_vertex_shader_instructions','num_pixel_shader_instructions','num_interpolator_scalars','num_samplers')}
    LIB.set_metadata_tag(material,'GHS.Replay.TrailVersion','route-distance-5m-v1')
    assert LIB.save_loaded_asset(material,only_if_is_dirty=False)
    return statistics


def repair():
    assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower(), 'Use the isolated commandlet'
    map_file=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
    target=ROOT/'Content/GHSOrderReplay/Materials/M_ReplayTrail.uasset'
    out=ROOT/'Saved/OrderReplay/TrailMaterial';out.mkdir(parents=True,exist_ok=True)
    sha=lambda file:hashlib.sha256(file.read_bytes()).hexdigest()
    before=sha(map_file)
    original_assets={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'Content/GHSOrderReplay').rglob('*.uasset') if p!=target}
    backup=out/'M_ReplayTrail.before.uasset'
    if target.exists() and not backup.exists():shutil.copy2(target,backup)
    stats=build_trail_material()
    assert sha(map_file)==before, 'Map changed during material-only repair'
    assert all(sha(ROOT/p)==value for p,value in original_assets.items()), 'Unrelated replay asset changed'
    material=LIB.load_asset(PATH)
    nodes=[o for o in unreal.ObjectIterator(unreal.MaterialExpression) if o.get_outer()==material]
    indices=[o.get_editor_property('data_index') for o in nodes if isinstance(o,unreal.MaterialExpressionPerInstanceCustomData)]
    assert sorted(indices)==[0,1]
    assert sum(isinstance(o,unreal.MaterialExpressionVertexInterpolator) for o in nodes)==2
    report=dict(success=True,path=PATH,instanced_static_meshes=True,custom_data_indices=indices,
                vertex_interpolators=2,wavelength_m=5.,flow_speed_mps=1.2,clock='ReplayTime',
                statistics=stats,map_sha256=before,map_unchanged=True,
                other_replay_assets_unchanged=len(original_assets),material_sha256=sha(target))
    (ROOT/'Saved/OrderReplay/trail_material_repair.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    unreal.log('ORDER_REPLAY_TRAIL_MATERIAL_REPAIRED '+json.dumps(report))


if __name__=='__main__':repair()
