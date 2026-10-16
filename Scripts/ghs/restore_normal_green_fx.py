"""Restore GHS green and increase visibility only in the light-style FX assets."""
import hashlib,json,shutil,sys
from datetime import datetime,timezone
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from normal_fx_style import update_master,connected_nodes
SOURCE=ROOT/'SourceAssets/GHS_Normal/lighting_style.json'
REPORT=ROOT/'Saved/GHS_NormalGreenFX.json'
FX='/Game/GHSNormalWarehouse/FX/'
lib=unreal.EditorAssetLibrary;ml=unreal.MaterialEditingLibrary


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data):path.write_text(json.dumps(data,indent=2),encoding='utf-8')
def color(c):return [float(c.r),float(c.g),float(c.b)]
def state(mi):
    return dict(parent=mi.get_editor_property('parent').get_path_name(),
                tint=color(ml.get_material_instance_vector_parameter_value(mi,'Tint')),
                speed=ml.get_material_instance_scalar_parameter_value(mi,'Speed'),
                phase=ml.get_material_instance_scalar_parameter_value(mi,'Phase'))


def run():
    assert not REPORT.exists(),'Already applied; use the saved verification and review before another change'
    style=json.loads(SOURCE.read_text());target=dict(style,fx_tint=[.04,.8,.30],fx_opacity_scale=1.8,fx_emissive_scale=.12)
    backup=ROOT/'Saved/Backups'/('GHS_NormalGreenFX_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True)
    hashes={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Content').rglob('*') if p.is_file()}
    write(backup/'content_hashes.json',hashes);shutil.copy2(SOURCE,backup/SOURCE.name)
    build=json.loads((ROOT/'Saved/GHS_NormalBuild.json').read_text())
    records=build['fx'];assert len(records)==40
    masters={kind:lib.load_asset(FX+'M_GHN_FX_'+kind) for kind in ['Diffusion','Radar']}
    instances={r['actor']:lib.load_asset(r['material']) for r in records}
    all_assets=list(masters.values())+list(instances.values());assert all(all_assets)
    changed_paths=[]
    for asset in all_assets:
        assert asset.get_path_name().startswith(FX)
        relative='Content/'+asset.get_path_name().split('.')[0][6:]+'.uasset'
        path=ROOT/relative;dest=backup/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest);changed_paths.append(relative)
    originals={k:state(mi) for k,mi in instances.items()}
    shader_before={k:[n.get_editor_property('code') for n in connected_nodes(m) if isinstance(n,unreal.MaterialExpressionCustom)] for k,m in masters.items()}
    assert all(len(v)==1 for v in shader_before.values())
    for master in masters.values():
        update_master(master,target);assert lib.save_loaded_asset(master,only_if_is_dirty=False)
    for label,mi in instances.items():
        ml.set_material_instance_vector_parameter_value(mi,'Tint',unreal.LinearColor(*target['fx_tint'],1))
        ml.update_material_instance(mi)
        actual=state(mi)
        assert actual['parent']==originals[label]['parent'] and actual['phase']==originals[label]['phase'] and actual['speed']==originals[label]['speed']
        assert max(abs(a-b) for a,b in zip(actual['tint'],target['fx_tint']))<1e-5
        assert lib.save_loaded_asset(mi,only_if_is_dirty=False)
    for kind,master in masters.items():
        assert shader_before[kind]==[n.get_editor_property('code') for n in connected_nodes(master) if isinstance(n,unreal.MaterialExpressionCustom)]
    write(SOURCE,target)
    actual_changes=[r for r,h in hashes.items() if sha(ROOT/r)!=h]
    assert set(actual_changes)==set(changed_paths),actual_changes
    report=dict(success=True,map='/Game/Maps/GHS_CAD_NormalWarehouse',backup_root=str(backup),
                old_style=style,new_style=target,changed_content=actual_changes,original_instances=originals,
                original_custom_shaders=shader_before,unchanged_content_count=len(hashes)-len(actual_changes),
                map_files_unchanged=True,shared_green_effects_unchanged=True,animation_code_speed_phase_preserved=True,
                changed_hashes={r:dict(before=hashes[r],after=sha(ROOT/r)) for r in actual_changes},
                completed_utc=datetime.now(timezone.utc).isoformat())
    write(REPORT,report)
    unreal.log('GHS_NORMAL_GREEN_FX_SAVED: 40 animated effects; original green restored')


if __name__=='__main__':run()
