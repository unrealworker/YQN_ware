"""Import three private double-pallet meshes and preserve all scene identities."""
import copy
import hashlib
import json
from pathlib import Path
import runpy
import traceback
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/DoublePallet'
DEST='/Game/GHSZcoolSmartFactory/DoublePallet/Meshes'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
LIB=unreal.EditorAssetLibrary
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
report=dict(success=False,meshes=[])

def path(obj):return obj.get_path_name() if obj else None

try:
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
    assert not levels.is_in_play_in_editor()
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(),'Save current map edits before applying'
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages(),'Save current asset edits before applying'
    baseline=json.loads((OUT/'baseline.json').read_text(encoding='utf-8'))
    snapshot=runpy.run_path(str(ROOT/'Scripts/ghs/inspect_double_pallet_scene.py'))['snapshot']
    by={a.get_actor_label():a for a in actors.get_all_level_actors()}
    assert {name:snapshot(actor) for name,actor in by.items()}==baseline['actors'],'Scene changed after inspection'
    manifest=json.loads((ROOT/'SourceAssets/GHS/DoublePallet/double_pallet_storage.json').read_text(encoding='utf-8'))
    targets={row['path'].rsplit('/',1)[-1].split('.')[0]:row for row in baseline['targets']}
    original_paths={row['path'].split('.')[0] for row in targets.values()}
    source_hashes={p:hashlib.sha256((ROOT/('Content/'+p.removeprefix('/Game/')+'.uasset')).read_bytes()).hexdigest() for p in original_paths}
    unreal.load_module('StaticMeshEditor')
    subsystem=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    plans=[]
    for row in manifest['meshes']:
        original=targets[row['name']]
        actor=by[original['actor']]
        component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        materials=[component.get_material(i) for i in range(component.get_num_materials())]
        task=unreal.AssetImportTask()
        task.filename=row['fbx'];task.destination_path=DEST;task.destination_name=row['name']
        task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=False
        options=unreal.FbxImportUI()
        options.import_mesh=True;options.import_as_skeletal=False
        options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
        options.automated_import_should_detect_type=False
        options.import_materials=False;options.import_textures=False;options.import_animations=False
        options.static_mesh_import_data.combine_meshes=True
        options.static_mesh_import_data.generate_lightmap_u_vs=False
        options.static_mesh_import_data.auto_generate_collision=False
        options.static_mesh_import_data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        task.options=options;TOOLS.import_asset_tasks([task])
        mesh=LIB.load_asset(DEST+'/'+row['name']);assert isinstance(mesh,unreal.StaticMesh)
        slots=mesh.static_materials
        assert [str(s.get_editor_property('imported_material_slot_name')) for s in slots]==original['slots']
        for i,slot in enumerate(slots):slot.material_interface=materials[i];slots[i]=slot
        mesh.set_editor_property('static_materials',slots)
        reduction=unreal.StaticMeshReductionOptions()
        reduction.set_editor_property('auto_compute_lod_screen_size',False)
        reduction.set_editor_property('reduction_settings',[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s)
            for p,s in zip([1.,.5,.22,.16],[1.,.35,.12,.03])])
        assert subsystem.set_lods(mesh,reduction)==4
        bound=mesh.get_bounds()
        for key,vector in [('min',bound.origin-bound.box_extent),('max',bound.origin+bound.box_extent)]:
            assert max(abs(a-b) for a,b in zip(vector.to_tuple(),original['bounds_cm'][key]))<.01,(row['name'],key)
        lods=[]
        for lod in range(4):
            assert mesh.get_num_sections(lod)==3
            vertices,indices,*_=unreal.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,lod,0)
            used=[vertices[i] for i in set(indices)]
            half=row['pallet_base_z_m'][1]*100
            bands=[[v for v in used if base-.1<=v.z<=base+17.1] for base in (0.,half)]
            assert sum(len(band) for band in bands)==len(used),'Blue pallet geometry escaped the two base bands'
            for band in bands:
                assert len(band)>=8,(row['name'],lod,'Missing pallet base')
                assert max(v.x for v in band)-min(v.x for v in band)>110
                assert max(v.y for v in band)-min(v.y for v in band)>90
                assert max(v.z for v in band)-min(v.z for v in band)>10
            lods.append(dict(lod=lod,triangles=mesh.get_num_triangles(lod),blue_band_vertices=[len(b) for b in bands]))
        assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
        plans.append((component,mesh,materials))
        report['meshes'].append(dict(actor=original['actor'],path=path(mesh),bounds_cm=dict(min=list((bound.origin-bound.box_extent).to_tuple()),
            max=list((bound.origin+bound.box_extent).to_tuple())),pallet_base_z_cm=[0.,half],lods=lods,count=component.get_instance_count()))
    for component,mesh,materials in plans:
        component.set_static_mesh(mesh)
        for i,material in enumerate(materials):component.set_material(i,material)
    expected=copy.deepcopy(baseline['actors'])
    for row in report['meshes']:
        comps=expected[row['actor']]['components'];assert len(comps)==1
        comps[0]['mesh']=row['path']
    assert {name:snapshot(actor) for name,actor in by.items()}==expected,'Only the three mesh references may change'
    assert sum(r['count'] for r in report['meshes'])==7530
    assert levels.save_current_level()
    assert all(hashlib.sha256((ROOT/('Content/'+p.removeprefix('/Game/')+'.uasset')).read_bytes()).hexdigest()==old for p,old in source_hashes.items())
    report.update(success=True,saved=True,instances=7530,original_meshes_unchanged=True,
                  all_actor_transforms_materials_and_instance_order_preserved=True,
                  map_sha256=hashlib.sha256((ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap').read_bytes()).hexdigest())
except Exception:
    report['error']=traceback.format_exc()
finally:
    (OUT/'apply.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert report['success'],report.get('error')
print('DOUBLE_PALLET_APPLIED')
