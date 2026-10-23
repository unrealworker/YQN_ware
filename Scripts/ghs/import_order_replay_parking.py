"""Asset-only import of exact non-car park derivatives; run via root UE bridge.

Does not change actors, component meshes, visibility, transforms, or maps.
Original static-material slots are copied onto the new assets.
"""
import hashlib
import json
from pathlib import Path
import traceback

import unreal

ROOT = Path('D:/UEPro/Test')
SOURCE = ROOT/'SourceAssets/GHS/OrderReplayParking'
OUT = ROOT/'Saved/OrderReplay'
DEST = '/Game/GHSOrderReplay/Parking'
LIB = unreal.EditorAssetLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
MESH_EDITOR = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def asset_file(asset):
    return ROOT/'Content'/(asset.removeprefix('/Game/')+'.uasset')


def slots(mesh):
    return [dict(name=str(s.material_slot_name), imported_name=str(s.get_editor_property('imported_material_slot_name')),
                 material=s.material_interface.get_path_name() if s.material_interface else None)
            for s in mesh.static_materials]


def scene_snapshot():
    result = []
    for actor in ACTORS.get_all_level_actors():
        for c in actor.get_components_by_class(unreal.StaticMeshComponent):
            transform=c.get_world_transform()
            xf=dict(position=[float(transform.translation.x),float(transform.translation.y),float(transform.translation.z)],
                rotation=[float(transform.rotation.x),float(transform.rotation.y),float(transform.rotation.z),float(transform.rotation.w)],
                scale=[float(transform.scale3d.x),float(transform.scale3d.y),float(transform.scale3d.z)])
            result.append(dict(actor=actor.get_path_name(),component=c.get_name(),
                mesh=c.static_mesh.get_path_name() if c.static_mesh else None,
                transform=xf,
                visible=c.is_visible(),hidden=bool(c.get_editor_property('hidden_in_game')),
                materials=[c.get_material(i).get_path_name() if c.get_material(i) else None
                           for i in range(c.get_num_materials())]))
    return sorted(result,key=lambda x:(x['actor'],x['component']))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['success'] and manifest['cars_removed']==157
    assert sha(Path(manifest['source_blend']))==manifest['source_blend_sha256']
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assert not levels.is_in_play_in_editor(), 'Run asset import outside PIE'
    before=scene_snapshot()
    dirty_maps_before=sorted(p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    protected=[asset_file(r['source']) for r in manifest['roles']]
    protected += [ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap']
    before_hash={str(p):sha(p) for p in protected}
    report=dict(success=False,asset_only=True,cars_removed=157,rows=[])
    mapping=[]
    try:
        existing_dirty={p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
        assert not any(p.startswith(DEST+'/') for p in existing_dirty), 'Replacement assets have unsaved edits'
        LIB.make_directory(DEST)
        for row in manifest['roles']:
            source=LIB.load_asset(row['source'])
            assert isinstance(source,unreal.StaticMesh),row['source']
            source_slots=slots(source)
            source_triangles=source.get_num_triangles(0)
            expected_source_triangles=row['source_triangles']-row['source_zero_area_triangles']
            assert source_triangles==expected_source_triangles, (row['role'],'Original UE triangle count drift',source_triangles,expected_source_triangles)
            assert len(source_slots)==len(row['material_slot_names'])
            item=dict(role=row['role'],source=row['source'],source_triangles=source_triangles,
                      source_material_slots=source_slots,source_asset_unchanged=True)
            if row['hide']:
                assert row['retained_faces']==0
                mapping.append(dict(source=row['source'],hide=True))
                item.update(hide=True,retained_faces=0)
                report['rows'].append(item)
                continue
            fbx=Path(row['fbx'])
            assert fbx.is_relative_to(SOURCE) and sha(fbx)==row['fbx_sha256']
            task=unreal.AssetImportTask()
            task.filename=str(fbx);task.destination_path=DEST;task.destination_name=row['name']
            task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=False
            options=unreal.FbxImportUI()
            options.import_mesh=True;options.import_as_skeletal=False
            options.import_materials=False;options.import_textures=False;options.import_animations=False
            options.automated_import_should_detect_type=False
            options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
            data=options.static_mesh_import_data
            data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
            data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
            task.options=options
            TOOLS.import_asset_tasks([task])
            target=LIB.load_asset(row['replacement'])
            assert isinstance(target,unreal.StaticMesh), row['replacement']
            assert len(target.static_materials)==len(source.static_materials)
            target.set_editor_property('static_materials',source.get_editor_property('static_materials'))
            assert slots(target)==source_slots, row['role']
            expected_triangles=row['triangles']-row['zero_area_triangles']
            assert target.get_num_triangles(0)==expected_triangles,(row['role'],target.get_num_triangles(0),expected_triangles)
            bounds=target.get_bounds()
            actual={key:[float(v.x),float(v.y),float(v.z)] for key,v in [
                ('min',bounds.origin-bounds.box_extent),('max',bounds.origin+bounds.box_extent)]}
            error=max(abs(actual[k][i]-row['bounds_ue_cm'][k][i]) for k in ('min','max') for i in range(3))
            assert error<.1,(row['role'],'Origin or scale drift',error)
            assert LIB.save_loaded_asset(target,only_if_is_dirty=False),row['replacement']
            mapping.append(dict(source=row['source'],replacement=row['replacement']))
            item.update(hide=False,replacement=row['replacement'],triangles=target.get_num_triangles(0),
                material_slots=slots(target),bounds_cm=actual,max_bounds_error_cm=error,
                asset_file=str(asset_file(row['replacement'])),asset_sha256=sha(asset_file(row['replacement'])))
            report['rows'].append(item)
        after=scene_snapshot()
        if after!=before:
            report['scene_differences']=[{'before':a,'after':b} for a,b in zip(before,after) if a!=b]
        assert after==before,'Scene components were changed during asset-only import'
        after_hash={str(p):sha(p) for p in protected}
        assert after_hash==before_hash,'Original asset or map changed'
        dirty_maps_after=sorted(p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
        assert dirty_maps_after==dirty_maps_before,'Dirty map state changed'
        target_json=ROOT/'Content/GHSTwinUI/data/order-replay-parking.json'
        target_json.parent.mkdir(parents=True,exist_ok=True)
        temporary=target_json.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(mapping,indent=2),encoding='utf-8')
        temporary.replace(target_json)
        report.update(success=True,scene_unchanged=True,dirty_maps_unchanged=True,
            protected_files=after_hash,mapping_file=str(target_json),mapping=mapping)
    except Exception:
        report['error']=traceback.format_exc()
        raise
    finally:
        (OUT/'parking_import.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('ORDER_REPLAY_PARKING_IMPORTED '+json.dumps(dict(success=True,replacements=5,hide_only=2,cars_removed=157)))


if __name__=='__main__':
    main()
