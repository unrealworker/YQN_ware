"""Persist only the proven instanced-static-mesh usage flag on seven materials.

The live and fresh commandlet snapshots must match in every reported material
field except this usage flag. The live snapshot is checked again immediately
before mutation. No material graph is rebuilt and no map is saved.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import traceback

import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/ParkReferenceStyle'
MAP_FILE=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dirty():return {p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}


def main():
    report=dict(success=False,operation='persist instanced mesh material usage only',saved_paths=[],backups=[])
    try:
        assert '-run=pythonscript' not in unreal.SystemLibrary.get_command_line().lower(),'Run only in the live editor'
        levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        assert levels and not levels.is_in_play_in_editor(),'Stop PIE before persisting usage flags'
        helper=runpy.run_path(str(ROOT/'Scripts/ghs/inspect_truck_material_usage.py'))
        packages=helper['PACKAGES'];usage=helper['USAGE'];snapshot=helper['snapshot_materials']
        live=read(OUT/'truck_materials_live.json')
        disk=read(OUT/'truck_materials_disk.json')
        assert live['success'] and disk['success'] and live['mode']=='live' and disk['mode']=='disk'
        assert len(live['materials'])==len(disk['materials'])==len(packages)==7
        def without_usage(row):return {k:v for k,v in row.items() if k!=usage}
        def indexed(rows):
            data={row['path'].split('.',1)[0]:row for row in rows}
            assert len(data)==len(rows)==7 and set(data)==set(packages)
            return data
        live_by=indexed(live['materials']);disk_by=indexed(disk['materials'])
        for package in packages:
            assert without_usage(live_by[package])==without_usage(disk_by[package]),(package,'Live material properties differ from disk; do not save user edits')
        before=snapshot()
        assert indexed(before)==live_by,'Live material values changed since inspection'
        dirty_before=dirty();map_before=sha(MAP_FILE)
        # Back up every old package before touching any material.
        for package in packages:
            source=ROOT/'Content'/(package.removeprefix('/Game/')+'.uasset')
            assert source.resolve().is_relative_to((ROOT/'Content').resolve()) and source.is_file()
            target=OUT/'Before/Assets/Content'/source.relative_to(ROOT/'Content')
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copy2(source,target)
            report['backups'].append(dict(package=package,path=str(target),sha256=sha(target)))
        report.update(comparison_passed=True,live_before=before,disk_before=disk['materials'],
                      unrelated_dirty_assets_before=sorted(dirty_before-set(packages)))
        for package in packages:
            material=unreal.load_asset(package)
            assert isinstance(material,unreal.Material)
            # This is the only property mutation in the repair.
            material.set_editor_property(usage,True)
            unreal.MaterialEditingLibrary.recompile_material(material)
            assert material.get_editor_property(usage)
            current=indexed(snapshot())[package]
            assert without_usage(current)==without_usage(live_by[package]),(package,'Material graph/defaults changed during recompilation')
            assert unreal.EditorAssetLibrary.save_loaded_asset(material,only_if_is_dirty=False),package
            report['saved_paths'].append(package)
        after=snapshot();after_by=indexed(after)
        for package in packages:
            assert after_by[package][usage] is True
            assert without_usage(after_by[package])==without_usage(live_by[package]),package
        dirty_after=dirty()
        assert dirty_after-set(packages)==dirty_before-set(packages),'Unrelated dirty assets changed'
        assert not dirty_after.intersection(packages),'A target material was not saved cleanly'
        assert sha(MAP_FILE)==map_before,'The repair must not save or alter the map'
        assert set(report['saved_paths'])==set(packages)
        report.update(success=True,materials_after=after,only_usage_flags_changed=True,
                      all_seven_saved=True,map_saved=False,map_sha256=map_before,
                      unrelated_dirty_assets_preserved=sorted(dirty_after-set(packages)))
    except Exception:
        report['error']=traceback.format_exc()
        unreal.log_error(report['error'])
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'truck_material_usage_fix.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert report['success'],report.get('error')
    unreal.log('GHS_TRUCK_INSTANCED_MATERIAL_USAGE_SAVED')


if __name__=='__main__':main()
