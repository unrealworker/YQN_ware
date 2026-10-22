"""Read seven static-display-truck materials without loading a level."""
from datetime import datetime,timezone
import json
from pathlib import Path
import traceback

import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/ParkReferenceStyle'
ROLES=('TruckBody','TruckBlue','TruckTrim','TruckGlass','TruckRubber','TruckHeadlight','TruckTailLight')
PACKAGES=tuple('/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_'+role for role in ROLES)
USAGE='used_with_instanced_static_meshes'


def snapshot_materials():
    """No map load, material compilation, save or mutation is performed."""
    records=[]
    ml=unreal.MaterialEditingLibrary
    for role,path in zip(ROLES,PACKAGES):
        material=unreal.load_asset(path)
        assert isinstance(material,unreal.Material),path
        tint=ml.get_material_default_vector_parameter_value(material,'SurfaceTint')
        records.append(dict(role=role,path=material.get_path_name(),
            SurfaceTint=[float(tint.r),float(tint.g),float(tint.b),float(tint.a)],
            Roughness=float(ml.get_material_default_scalar_parameter_value(material,'Roughness')),
            Specular=float(ml.get_material_default_scalar_parameter_value(material,'Specular')),
            Metallic=float(ml.get_material_default_scalar_parameter_value(material,'Metallic')),
            expression_count=ml.get_num_material_expressions(material),
            blend=str(material.get_editor_property('blend_mode')),
            shading=str(material.get_editor_property('shading_model')),
            two_sided=bool(material.get_editor_property('two_sided')),
            used_with_instanced_static_meshes=bool(material.get_editor_property(USAGE))))
    return records


def main():
    disk='-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
    report=dict(success=False,mode='disk' if disk else 'live',materials=[],loaded_map_by_script=False)
    try:
        report['materials']=snapshot_materials()
        assert len(report['materials'])==7
        report['success']=True
    except Exception:
        report['error']=traceback.format_exc()
        unreal.log_error(report['error'])
    report['finished_utc']=datetime.now(timezone.utc).isoformat()
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/('truck_materials_disk.json' if disk else 'truck_materials_live.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert report['success'],report.get('error')
    unreal.log('GHS_TRUCK_MATERIAL_INSPECTION_'+report['mode'].upper())


if __name__=='__main__':main()
