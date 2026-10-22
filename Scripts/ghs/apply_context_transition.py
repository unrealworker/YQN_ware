"""Scoped editor import for edge scenery and exterior-building contrast.

Run through the live dispatcher after stopping PIE. Existing meshes, ground
bindings, transforms and source materials are never modified. On repeat only
the explicitly owned context assets/components are reused.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import runpy
import traceback
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/RoofTraffic'
SOURCE=ROOT/'SourceAssets/GHS/ContextTransition'
DEST='/Game/GHSZcoolSmartFactory/ContextTransition'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
PREFIX='GHSContextTransition_'
TARGET_ROLES=('Buildings','Roofs','Glass','Blue','Solar')
LIB=unreal.EditorAssetLibrary
ML=unreal.MaterialEditingLibrary
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def node(mat,kind,**values):
    result=ML.create_material_expression(mat,kind)
    for key,value in values.items():result.set_editor_property(key,value)
    return result


def custom_inputs(names):
    result=[]
    for name in names:
        entry=unreal.CustomInput()
        entry.set_editor_property('input_name',name)
        result.append(entry)
    return result


def ground_color(by):
    # Read the current component assignment, never reset it to an old palette.
    mat=by['GHSPark_Ground'].get_component_by_class(unreal.StaticMeshComponent).get_material(0)
    if isinstance(mat,unreal.MaterialInstanceConstant):
        value=ML.get_material_instance_vector_parameter_value(mat,'SurfaceTint')
    else:value=ML.get_material_default_vector_parameter_value(mat,'SurfaceTint')
    assert max(value.r,value.g,value.b)>0,'Ground material must expose SurfaceTint; preserve and inspect other material types before applying'
    return [value.r,value.g,value.b]


def original_color_node(mat):
    source=ML.get_material_property_input_node(mat,unreal.MaterialProperty.MP_BASE_COLOR)
    output=ML.get_material_property_input_node_output_name(mat,unreal.MaterialProperty.MP_BASE_COLOR)
    assert source,'Original material base color must be connected'
    return source,output


def outside_hlsl(hull):
    # Clockwise convex support planes, measured in UV metres. Max positive
    # distance is outside; the 5m guard protects the complete original campus.
    signed=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(hull,hull[1:]))
    if signed>0:hull=list(reversed(hull))
    lines=['float2 p=Position.xy/100.0+float2(239.33385,60.24019);','float d=-100000.0;']
    for a,b in zip(hull,hull[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length<.01:continue
        nx,ny=-dy/length,dx/length
        lines.append('d=max(d,dot(p-float2(%.9f,%.9f),float2(%.9f,%.9f)));'%(a[0],a[1],nx,ny))
    lines.append('return smoothstep(5.0,9.0,d)*Strength;')
    return '\n'.join(lines)


def contrast_material(role,source,ground,hull):
    path=DEST+'/Materials/M_GHSContext_Exterior_'+role
    if LIB.does_asset_exist(path):
        mat=LIB.load_asset(path)
        assert abs(ML.get_material_default_scalar_parameter_value(mat,'ContextExteriorBlend')-.18)<1e-5
        return mat
    assert isinstance(source,unreal.Material),source.get_path_name()
    mat=LIB.duplicate_asset(source.get_path_name().split('.')[0],path)
    assert mat
    base,output=original_color_node(mat)
    position=node(mat,unreal.MaterialExpressionWorldPosition)
    strength=node(mat,unreal.MaterialExpressionScalarParameter,parameter_name='ContextExteriorBlend',default_value=.18)
    mask=node(mat,unreal.MaterialExpressionCustom,code=outside_hlsl(hull),
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,
        inputs=custom_inputs(('Position','Strength')))
    assert ML.connect_material_expressions(position,'',mask,'Position')
    assert ML.connect_material_expressions(strength,'',mask,'Strength')
    tint=node(mat,unreal.MaterialExpressionVectorParameter,parameter_name='ContextGroundTint',
        default_value=unreal.LinearColor(*ground,1))
    blend=node(mat,unreal.MaterialExpressionLinearInterpolate)
    assert ML.connect_material_expressions(base,output,blend,'A')
    assert ML.connect_material_expressions(tint,'',blend,'B')
    assert ML.connect_material_expressions(mask,'',blend,'Alpha')
    assert ML.connect_material_property(blend,'',unreal.MaterialProperty.MP_BASE_COLOR)
    ML.layout_material_expressions(mat);ML.recompile_material(mat)
    assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
    return mat


def edge_material(role,ground):
    path=DEST+'/Materials/M_GHSContextTransition_'+role
    if LIB.does_asset_exist(path):return LIB.load_asset(path)
    source='/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_'+role
    mat=LIB.duplicate_asset(source,path);assert mat,source
    base,output=original_color_node(mat)
    color=node(mat,unreal.MaterialExpressionVertexColor)
    tint=node(mat,unreal.MaterialExpressionVectorParameter,parameter_name='ContextGroundTint',
        default_value=unreal.LinearColor(*ground,1))
    blend=node(mat,unreal.MaterialExpressionLinearInterpolate)
    assert ML.connect_material_expressions(base,output,blend,'A')
    assert ML.connect_material_expressions(tint,'',blend,'B')
    assert ML.connect_material_expressions(color,'R',blend,'Alpha')
    assert ML.connect_material_property(blend,'',unreal.MaterialProperty.MP_BASE_COLOR)
    ML.layout_material_expressions(mat);ML.recompile_material(mat)
    assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
    return mat


def import_mesh(row,material):
    path=(ROOT/row['fbx']).resolve()
    assert path.is_relative_to(SOURCE.resolve()) and sha(path)==row['sha256']
    task=unreal.AssetImportTask()
    task.filename=str(path);task.destination_path=DEST+'/Meshes';task.destination_name=row['name']
    task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=False
    options=unreal.FbxImportUI();options.import_mesh=True;options.import_as_skeletal=False
    options.import_materials=False;options.import_textures=False;options.import_animations=False
    options.automated_import_should_detect_type=False;options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
    data=options.static_mesh_import_data
    data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
    data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    data.vertex_color_import_option=unreal.VertexColorImportOption.REPLACE
    task.options=options;TOOLS.import_asset_tasks([task])
    result=LIB.load_asset(DEST+'/Meshes/'+row['name']);assert isinstance(result,unreal.StaticMesh)
    slots=result.static_materials;assert len(slots)==1
    slot=slots[0];slot.material_interface=material;slots[0]=slot;result.set_editor_property('static_materials',slots)
    bounds=result.get_bounds()
    for key,actual in [('min',bounds.origin-bounds.box_extent),('max',bounds.origin+bounds.box_extent)]:
        assert max(abs(a-b) for a,b in zip((actual.x,actual.y,actual.z),row['bounds_ue_cm'][key]))<2.,row['name']
    assert LIB.save_loaded_asset(result,only_if_is_dirty=False)
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(success=False)
    try:
        levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        assert not levels.is_in_play_in_editor(),'Stop PIE before applying context assets'
        assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
        current=actors.get_all_level_actors();by={a.get_actor_label():a for a in current}
        assert len(current)==len(by)
        snap=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
        before={a.get_actor_label():snap(a,unreal) for a in current if not a.get_actor_label().startswith(PREFIX)}
        dirty={p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
        assert not any(p.startswith(DEST+'/') for p in dirty),'Owned context asset has unsaved edits'
        manifest=read(SOURCE/'context_transition.json');ground=ground_color(by)
        LIB.make_directory(DEST+'/Materials');LIB.make_directory(DEST+'/Meshes')
        changes=[]
        for role in TARGET_ROLES:
            label='GHSPark_'+role;component=by[label].get_component_by_class(unreal.StaticMeshComponent)
            assert component.get_num_materials()==1,label
            source=component.get_material(0)
            replacement=contrast_material(role,source,ground,manifest['protected_campus_hull_uv_m'])
            component.set_material(0,replacement)
            changes.append(dict(actor=label,source=source.get_path_name(),replacement=replacement.get_path_name()))
        labels=[]
        for row in manifest['meshes']:
            material=edge_material(row['role'],ground);mesh=import_mesh(row,material)
            label=PREFIX+row['role'];labels.append(label)
            actor=by.get(label)
            if actor:assert actor.actor_has_tag('GHS_ContextTransition')
            else:actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector())
            actor.set_actor_label(label);actor.set_folder_path('GHS/Park/ContextTransition')
            actor.tags=['GHS_ContextTransition','GHS_ArchitecturalContext']
            actor.set_actor_enable_collision(False);actor.set_actor_tick_enabled(False)
            component=actor.get_component_by_class(unreal.StaticMeshComponent)
            component.set_static_mesh(mesh);component.set_mobility(unreal.ComponentMobility.STATIC)
            component.set_collision_profile_name('NoCollision');component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            component.set_editor_property('cast_shadow',row['role'] in ('Trees','TreesDark','TreesLight','Trunk'))
        after={a.get_actor_label():snap(a,unreal) for a in actors.get_all_level_actors()}
        allowed={c['actor']:c['replacement'] for c in changes}
        for label,old in before.items():
            expected=copy.deepcopy(old)
            if label in allowed:expected['components'][0]['materials']=[allowed[label]]
            assert expected==after[label],(label,'Unexpected geometry, transform or material change')
        assert set(after)-set(before)==set(labels)
        assert levels.save_current_level()
        assert {p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}==dirty
        report.update(success=True,saved=True,changes=changes,new_actors=labels,
            ground_color_linear=ground,triangles=manifest['triangles'],tree_count=manifest['trees'],
            original_actors_preserved=len(before),
            ground_snapshot=before['GHSPark_Ground'],studio_ground_snapshot=before['GHN_StudioGround'],
            map_sha256=sha(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'))
    except Exception:
        report['error']=traceback.format_exc();unreal.log_error(report['error'])
    (OUT/'context-apply.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert report['success'],report.get('error')
    unreal.log('GHS_CONTEXT_TRANSITION_APPLIED')


if __name__=='__main__':main()
