"""Replace only the warehouse partitions with Blender-authored thick wall meshes."""
import json
import shutil
import traceback
from datetime import datetime
from pathlib import Path
import unreal

root=Path(r'D:\UEPro\Test')
base=(root/'Scripts/build_video_warehouse.py').read_text(encoding='utf-8')
exec(compile(base.split('\ntry:main()')[0],'build_video_warehouse.py','exec'),globals())
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert world.get_path_name().split('.')[0]==MAP,'Open VideoDigitalTwinWarehouse before the wall upgrade'
wall_report_path=ROOT/'Saved/VideoWarehouse_WallsReport.json'
wall_report=dict(success=False,scope='Replace partition geometry and materials only')

def transform(a):
    p=a.get_actor_location();r=a.get_actor_rotation();s=a.get_actor_scale3d()
    return dict(position_m=[p.x/100,p.y/100,p.z/100],yaw=r.yaw,rotation=[r.pitch,r.yaw,r.roll],scale=[s.x,s.y,s.z])

try:
    assert levels.save_current_level(),'Could not preserve current editor changes'
    backup_dir=ROOT/'Saved/Backups';backup_dir.mkdir(parents=True,exist_ok=True)
    backup=backup_dir/('VideoWarehouse_BeforeWallThickness_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.umap')
    shutil.copy2(ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap',backup)
    wall_report['backup']=str(backup)
    spec=json.loads((SOURCE/'walls.json').read_text(encoding='utf-8'))
    by={a.get_actor_label():a for a in actors.get_all_level_actors()}
    before={name:transform(a) for name,a in by.items()}
    for item in spec['materials']:make_material(item)
    changed=[];hidden=[]
    for item in spec['meshes']:
        label=item['metadata']['wall_label'];a=by[label]
        task=unreal.AssetImportTask();task.filename=item['fbx'];task.destination_path=DEST+'/Meshes';task.destination_name=item['name']
        task.automated=True;task.replace_existing=True;task.save=True
        opt=unreal.FbxImportUI();opt.import_mesh=True;opt.import_as_skeletal=False;opt.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
        opt.automated_import_should_detect_type=False;opt.import_materials=False;opt.import_textures=False;opt.import_animations=False
        opt.static_mesh_import_data.combine_meshes=True;opt.static_mesh_import_data.generate_lightmap_u_vs=False;opt.static_mesh_import_data.auto_generate_collision=False
        opt.static_mesh_import_data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        opt.static_mesh_import_data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
        task.options=opt;assets.import_asset_tasks([task])
        mesh=lib.load_asset(DEST+'/Meshes/'+item['name']);assert mesh,item['name']
        slots=mesh.get_editor_property('static_materials')
        for index,slot in enumerate(slots):
            name=str(slot.get_editor_property('imported_material_slot_name'))
            if name not in MATS:name=str(slot.get_editor_property('material_slot_name'))
            assert name in MATS,name
            slot.set_editor_property('material_interface',MATS[name]);slots[index]=slot
        mesh.set_editor_property('static_materials',slots);save(mesh)
        c=a.get_component_by_class(unreal.StaticMeshComponent)
        c.set_editor_property('override_materials',[]);c.set_static_mesh(mesh)
        a.set_actor_scale3d(unreal.Vector(1,1,1))
        c.set_visibility(True,True);c.set_hidden_in_game(False,True)
        for old_name,old_actor in by.items():
            if old_name.startswith(label+'_Rim') or old_name.startswith(label+'_Post'):
                old_c=old_actor.get_component_by_class(unreal.StaticMeshComponent)
                old_c.set_visibility(False,True);old_c.set_hidden_in_game(True,True)
                hidden.append(old_name)
        bounds=mesh.get_bounds();extent=bounds.box_extent
        assert abs(extent.y*2-20)<.02 and abs(extent.z*2-280)<.02,item['name']
        changed.append(dict(id=label,mesh=item['name'],thickness_cm=extent.y*2,height_cm=extent.z*2))
    changed_ids={r['id'] for r in changed}
    assert len(changed)==27
    for name,a in by.items():
        now=transform(a)
        if name in changed_ids:
            assert now['position_m']==before[name]['position_m'] and now['rotation']==before[name]['rotation'],name
        else:assert now==before[name],name+' was moved unexpectedly'
    records=json.loads((SOURCE/'scene_registry.json').read_text(encoding='utf-8'))
    new_names={r['id']:r['mesh'] for r in changed}
    # Preserve and record the current editor placement, including manual edits.
    for record in records:
        a=by[record['id']];current=transform(a)
        record['position_m']=current['position_m'];record['yaw']=current['yaw']
        if record['id'] in new_names:record['mesh']=new_names[record['id']]
    (SOURCE/'scene_registry.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    assert levels.save_current_level()
    wall_report.update(success=True,walls=changed,hidden_previous_outline_count=len(hidden),
                       non_wall_transforms_preserved=True,actor_count=len(by),
                       thickness_m=.20,height_m=2.8,opaque_coping_and_end_sections=True,
                       wall_opacity_bottom=.40,wall_opacity_top=.15)
    wall_report_path.write_text(json.dumps(wall_report,indent=2),encoding='utf-8')
    unreal.log('VIDEO_WAREHOUSE_THICK_WALLS_COMPLETE: 27 Blender walls, 20 cm thick, opaque top and end sections')
    exec(compile((ROOT/'Scripts/capture_video_warehouse.py').read_text(encoding='utf-8'),'capture_video_warehouse.py','exec'),globals())
except Exception:
    wall_report['error']=traceback.format_exc();wall_report_path.write_text(json.dumps(wall_report,indent=2),encoding='utf-8')
    raise
