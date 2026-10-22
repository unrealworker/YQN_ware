"""Refresh only the six woodland/ground meshes, preserving every scene actor."""
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import traceback
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/ParkForestFill'
BEFORE=OUT/'Before'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
ROLES={'Ground','Landscape','Trees','TreesDark','TreesLight','Trunk'}
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

report=dict(success=False,map=MAP,operation='refresh woodland meshes in place',new_actors=[],meshes=[])
try:
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assert not levels.is_in_play_in_editor()
    assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
    dirty_assets={p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
    target_assets={'/Game/GHSZcoolSmartFactory/Park/Meshes/SM_GHSPark_'+role for role in ROLES}
    assert not dirty_assets.intersection(target_assets), 'A target woodland mesh has unsaved edits'
    assert all(p.get_path_name()==MAP for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    new=read(ROOT/'SourceAssets/GHS/Park/park_manifest.json')
    old=read(BEFORE/'park_manifest.json')
    assert new['materials']==old['materials']
    assert [r['name'] for r in new['meshes']]==[r['name'] for r in old['meshes']]
    for a,b in zip(old['meshes'],new['meshes']):
        if a['role'] in ROLES: continue
        for key in ('vertices','triangles','bounds_ue_cm','role','material_roles','instances','component_material_overrides'):
            assert a.get(key)==b.get(key),(a['name'],key,'Unrelated geometry changed')
    site=read(ROOT/'SourceAssets/GHS/Park/site_geometry_report.json')
    previous=read(BEFORE/'site_geometry_report.json')
    for key in previous:
        if key!='forests': assert site[key]==previous[key], ('Non-forest layout changed',key)
    assert site['forests']['groups'][:2]==previous['forests']['groups'], 'Existing woodland changed'
    assert len(site['forests']['groups'])==7
    validator=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))
    def snapshot():
        return sorted([validator['snapshot'](a,unreal) for a in actors.get_all_level_actors()],key=lambda r:r['label'])
    rows=snapshot()
    if not (BEFORE/'editor_snapshot.json').exists():
        write(BEFORE/'editor_snapshot.json',rows)
        assert levels.save_current_level()
        shutil.copy2(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap',BEFORE/'current_user_saved.umap')
    source=read(ROOT/'Saved/ParkExpansion/source_map_baseline.json')
    assert sha(Path(source['path']))==source['sha256']
    importer=runpy.run_path(str(ROOT/'Scripts/ghs/apply_park_expansion.py'))
    mats={role:unreal.load_asset('/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_'+role) for role in ROLES}
    assert all(mats.values())
    changed=[]
    for row in new['meshes']:
        if row['role'] in ROLES:
            importer['import_mesh'](row,mats)
            changed.append(row['name'])
        report['meshes'].append(dict(name=row['name'],triangles=row['triangles'],instances=len(row.get('instances',[None]))))
    assert snapshot()==rows, 'Import changed an actor transform, material, identity or instance'
    assert {p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}==dirty_assets, 'Unrelated unsaved assets were changed'
    assert len(changed)==6
    assert levels.save_current_level()
    assert sha(Path(source['path']))==source['sha256']
    report.update(success=True,saved=True,source_map_preserved=True,updated_meshes=changed,
                  actor_snapshot_preserved=True,actor_count=len(rows),
                  unsaved_unrelated_assets_preserved=sorted(dirty_assets),
                  original_woodland_preserved=True,added_woodland_groups=5,
                  added_trees=site['forests']['total_trees']-previous['forests']['total_trees'],
                  triangle_total=new['triangles_total'],reference_accuracy=new['measurement_status'])
except Exception:
    report['error']=traceback.format_exc()
    unreal.log_error(report['error'])
write(OUT/'apply_report.json',report)
if report['success']: write(ROOT/'Saved/ParkExpansion/apply_report.json',report)
assert report['success'],report.get('error')
unreal.log('GHS_FOREST_FILL_APPLIED')
