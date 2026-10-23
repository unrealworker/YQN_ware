"""Restore only missing road extensions and match their fade to live surfaces.

Never regenerates the park or changes the user's ground transform/material.
Run with PIE stopped through the local editor dispatcher.
"""
import hashlib
import json
import runpy
import shutil
from datetime import datetime
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/RoadTerminalFade'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
DEST='/Game/GHSZcoolSmartFactory/RoadTerminalFade'
PREFIX='GHSContextTransition_'
ROLES=('ContextRoads','Curbs','Markings')
LIB=unreal.EditorAssetLibrary
ML=unreal.MaterialEditingLibrary

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def node(mat,kind,**props):
    n=ML.create_material_expression(mat,kind)
    for k,v in props.items(): n.set_editor_property(k,v)
    return n

def main():
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    assert not levels.is_in_play_in_editor()
    assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
    # Refuse to discard or save unrelated pending edits.
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    by={a.get_actor_label():a for a in actors.get_all_level_actors()}
    assert all(PREFIX+role not in by for role in ROLES),'Expected exactly the three missing extension actors'
    snapshot=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
    before={label:snapshot(a,unreal) for label,a in by.items()}
    selected=list(actors.get_selected_level_actors())
    ground=by['GHSPark_Ground'].get_component_by_class(unreal.StaticMeshComponent).get_material(0)
    assert isinstance(ground,unreal.Material)
    manifest=json.loads((ROOT/'SourceAssets/GHS/ContextTransition/context_transition.json').read_text(encoding='utf-8'))
    rows={r['role']:r for r in manifest['meshes']}
    meshes={role:LIB.load_asset('/Game/GHSZcoolSmartFactory/ContextTransition/Meshes/'+rows[role]['name']) for role in ROLES}
    assert all(isinstance(m,unreal.StaticMesh) for m in meshes.values())
    original_assets={ground.get_path_name().split('.')[0]}
    for role in ROLES:
        m=by['GHSPark_'+role].get_component_by_class(unreal.StaticMeshComponent).get_material(0)
        original_assets.add(m.get_path_name().split('.')[0])
        original_assets.add(meshes[role].get_path_name().split('.')[0])
    def asset_file(path): return ROOT/'Content'/(path.removeprefix('/Game/')+'.uasset')
    hashes={p:sha(asset_file(p)) for p in original_assets}
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    OUT.mkdir(parents=True,exist_ok=True)
    map_file=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
    backup=OUT/('before-'+stamp+'.umap')
    shutil.copy2(map_file,backup)
    (OUT/'before_scene.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'success':False,'backup':str(backup),'before_map_sha256':sha(map_file),'materials':[]}
    LIB.make_directory(DEST)
    spawned=[]
    try:
        for role in ROLES:
            path=DEST+'/M_RoadTerminal_'+role
            assert not LIB.does_asset_exist(path),'Refuse to overwrite an existing material'
            mat=LIB.duplicate_asset(ground.get_path_name().split('.')[0],path)
            assert mat
            # Inherit the exact current spatial ground-color graph. This avoids
            # a fixed old ground tint leaving a rectangle at the distant end.
            field=ML.get_material_property_input_node(mat,unreal.MaterialProperty.MP_BASE_COLOR)
            output=ML.get_material_property_input_node_output_name(mat,unreal.MaterialProperty.MP_BASE_COLOR)
            source=by['GHSPark_'+role].get_component_by_class(unreal.StaticMeshComponent).get_material(0)
            tint=ML.get_material_default_vector_parameter_value(source,'SurfaceTint')
            assert max(tint.r,tint.g,tint.b)>0
            start=node(mat,unreal.MaterialExpressionVectorParameter,parameter_name='RoadSurfaceTint',default_value=tint)
            fade=node(mat,unreal.MaterialExpressionVertexColor)
            blend=node(mat,unreal.MaterialExpressionLinearInterpolate)
            assert ML.connect_material_expressions(start,'',blend,'A')
            assert ML.connect_material_expressions(field,output,blend,'B')
            assert ML.connect_material_expressions(fade,'R',blend,'Alpha')
            assert ML.connect_material_property(blend,'',unreal.MaterialProperty.MP_BASE_COLOR)
            ML.layout_material_expressions(mat)
            ML.recompile_material(mat)
            LIB.set_metadata_tag(mat,'GHS.RoadTerminal.Owner','road-terminal-fade-v1')
            assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
            mesh=meshes[role]
            bounds=mesh.get_bounds()
            for key,actual in [('min',bounds.origin-bounds.box_extent),('max',bounds.origin+bounds.box_extent)]:
                assert max(abs(x-y) for x,y in zip((actual.x,actual.y,actual.z),rows[role]['bounds_ue_cm'][key]))<2
            a=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector())
            spawned.append(a)
            a.set_actor_label(PREFIX+role)
            a.set_folder_path('GHS/Park/ContextTransition')
            a.tags=['GHS_ContextTransition','GHS_ArchitecturalContext']
            a.set_actor_enable_collision(False)
            a.set_actor_tick_enabled(False)
            c=a.get_component_by_class(unreal.StaticMeshComponent)
            c.set_static_mesh(mesh)
            c.set_material(0,mat)
            c.set_mobility(unreal.ComponentMobility.STATIC)
            c.set_collision_profile_name('NoCollision')
            c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            c.set_editor_property('cast_shadow',False)
            report['materials'].append({'actor':a.get_actor_label(),'material':path,'source_surface':source.get_path_name(),
                                        'surface_tint':[tint.r,tint.g,tint.b], 'ground_source':ground.get_path_name()})
        actors.set_selected_level_actors(selected)
        after={a.get_actor_label():snapshot(a,unreal) for a in actors.get_all_level_actors()}
        assert set(after)-set(before)=={PREFIX+r for r in ROLES}
        assert all(after[k]==v for k,v in before.items()),'Existing actor changed'
        assert hashes=={p:sha(asset_file(p)) for p in hashes},'Existing material or mesh modified'
        assert levels.save_current_level()
        report.update(success=True,existing_actors_preserved=len(before),restored_actors=[PREFIX+r for r in ROLES],
                      original_assets_unchanged=True,after_map_sha256=sha(map_file))
        (OUT/'after_scene.json').write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        # Revert scene additions on failure; source assets and preexisting actors
        # are never modified. Saved private materials may remain for diagnosis.
        for a in spawned: actors.destroy_actor(a)
        actors.set_selected_level_actors(selected)
        raise
    finally:
        (OUT/'restoration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    unreal.log('GHS_ROAD_TERMINAL_RESTORED')

if __name__=='__main__': main()
