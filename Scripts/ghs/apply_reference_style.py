"""Apply the reference palette and new planting geometry in place."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import runpy
import shutil
import sys
import traceback
import unreal
ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/ParkReferenceStyle'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
ROLES={'Landscape','Trees','TreesLight','TreesDark','Trunk'}
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import reference_style_materials
importlib.reload(reference_style_materials)
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
report=dict(success=False,updated_meshes=[])
try:
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assert not levels.is_in_play_in_editor()
    assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
    baseline=read(OUT/'Before/scene_state.json')
    manifest=read(ROOT/'SourceAssets/GHS/Park/park_manifest.json')
    old=read(OUT/'Before/park_manifest.json')
    assert len(manifest['meshes'])==len(old['meshes'])==22
    for a,b in zip(old['meshes'],manifest['meshes']):
        assert a['name']==b['name']
        if a['role'] in ROLES:continue
        for key in ['vertices','triangles','bounds_ue_cm','instances']:
            assert a.get(key)==b.get(key),(a['name'],key)
    style=read(ROOT/'SourceAssets/GHS/Park/reference_style.json')
    source=read(ROOT/'Saved/ParkExpansion/source_map_baseline.json')
    assert sha(Path(source['path']))==source['sha256']
    material_report=reference_style_materials.apply(style,save_assets=True)
    mats={role:unreal.load_asset('/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_'+role) for role in ROLES}
    mesh_editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for role in ['Trees','TreesLight','TreesDark']:
        mats[role].set_editor_property('used_with_nanite',True)
        unreal.MaterialEditingLibrary.recompile_material(mats[role])
        assert unreal.EditorAssetLibrary.save_loaded_asset(mats[role],only_if_is_dirty=False)
    importer=runpy.run_path(str(ROOT/'Scripts/ghs/apply_park_expansion.py'))
    for row in manifest['meshes']:
        if row['role'] not in ROLES:continue
        original=ROOT/('Content/GHSZcoolSmartFactory/Park/Meshes/'+row['name']+'.uasset')
        backup=OUT/'Before/Assets'/original.name
        if not backup.exists():shutil.copy2(original,backup)
        mesh=importer['import_mesh'](row,mats)
        if row['role'] in ['Trees','TreesLight','TreesDark']:
            settings=mesh_editor.get_nanite_settings(mesh)
            settings.enabled=True
            settings.fallback_relative_error=0.
            mesh_editor.set_nanite_settings(mesh,settings,True)
            assert mesh_editor.get_nanite_settings(mesh).enabled
            assert unreal.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
        report['updated_meshes'].append(row['name'])
    by={a.get_actor_label():a for a in actors.get_all_level_actors()}
    by['GHSPark_Landscape'].get_component_by_class(unreal.StaticMeshComponent).set_editor_property('cast_shadow',True)
    assert len(by)==len(baseline['actors'])==360
    snap=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
    for old_row in baseline['actors']:
        expected=copy.deepcopy(old_row);actual=snap(by[old_row['label']],unreal)
        label=old_row['label']
        if label=='GHSPark_Ground':expected['components'][0]['materials']=[style['ground_material']]
        if label=='GHN_StudioGround':expected['components'][0]['materials']=[style['studio_ground_material']]
        if label=='GHS_CoolOverheadKey':
            expected['transform']['rotation']=actual['transform']['rotation']
        assert expected==actual,(label,'Unexpected actor transform/material/identity/instance change')
    assert levels.save_current_level()
    assert sha(Path(source['path']))==source['sha256']
    assert set(p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())==set(material_report['unrelated_dirty_assets_preserved'])
    report.update(success=True,saved=True,actor_count=len(by),static_layout_preserved=True,
        material_report=material_report,counts=manifest['counts'],triangles=manifest['triangles_total'],
        style=style,nanite_crown_meshes=['Trees','TreesLight','TreesDark'],
        map_sha256=sha(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'),
        park_manifest_sha256=sha(ROOT/'SourceAssets/GHS/Park/park_manifest.json'),
        original_source_map_preserved=True)
except Exception:
    report['error']=traceback.format_exc();unreal.log_error(report['error'])
(OUT/'apply_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert report['success'],report.get('error')
