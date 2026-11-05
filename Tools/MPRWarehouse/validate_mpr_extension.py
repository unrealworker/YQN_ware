"""Read-only saved-map reload, ownership and full generated-state validation."""
import hashlib,json,re,sys,traceback
from pathlib import Path
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
import extension_preservation as guard
from mpr_scene_ownership import verify_owned_scene
OUT=ROOT/'Saved/MPR/extension_20261104'
SRC=ROOT/'SourceAssets/MPR/extension_b50b57'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def require(condition,message):
    if not condition:raise guard.PreservationError(message)

def assert_snapshot_content_equal(expected,actual,*,new_actor_guids=()):
    expected_rows={r['guid']:r for r in expected['actors']}
    actual_rows={r['guid']:r for r in actual['actors']}
    renames=[]
    for guid in sorted(set(new_actor_guids)&set(expected_rows)&set(actual_rows)):
        old=expected_rows[guid];current=actual_rows[guid]
        # UE5.8 SceneComponent.cpp CreateSpriteComponent uses NAME_None and
        # RF_Transient|RF_TextExportTransient for this editor-only root icon.
        # Blueprint reconstruction can consume suffixes before the first save;
        # a new editor process recreates the same visualization with another
        # suffix. Normalize only that name, never instance/transform fields.
        if not (old.get('class')==current.get('class')==
                '/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup.BP_GHS_InstanceGroup_C'
                and old.get('folder')==current.get('folder')==guard.EXTENSION_FOLDER+'/Vegetation'
                and guard.EXTENSION_TAG in old.get('tags',[]) and guard.EXTENSION_TAG in current.get('tags',[])):
            continue
        def sprites(row):
            return [c for c in row['components'] if c.get('class')=='/Script/Engine.BillboardComponent']
        left,right=sprites(old),sprites(current)
        if len(left)!=1 or len(right)!=1:continue
        left,right=left[0],right[0]
        if not all(re.fullmatch(r'BillboardComponent_\d+',c.get('name','')) for c in (left,right)):continue
        if left['name']==right['name']:continue
        if not (left.get('hidden_in_game') is True
                and left.get('attach_parent')==old['path']+'.DefaultSceneRoot'
                and left.get('transform',{}).get('scale')==[.5,.5,.5]
                and any(c.get('name')=='DefaultSceneRoot' and c.get('class')=='/Script/Engine.SceneComponent'
                        for c in old['components'])):
            continue
        if {k:v for k,v in left.items() if k!='name'}!={k:v for k,v in right.items() if k!='name'}:continue
        normalized=dict(current)
        normalized['components']=[dict(c,name=left['name']) if c is right else c for c in current['components']]
        normalized['components'].sort(key=lambda c:c['name'])
        actual_rows[guid]=normalized
        renames.append(dict(actor_guid=guid,actor_label=old['label'],
                            saved_name=left['name'],reloaded_name=right['name'],
                            reason='UE transient DefaultSceneRoot editor visualization auto-name'))
    changed=sorted(g for g in set(expected_rows)|set(actual_rows)
                   if expected_rows.get(g)!=actual_rows.get(g))
    require(not changed,'Reload changed actor/component/instance state: '+', '.join(changed[:12]))
    require(expected['asset_hashes']==actual['asset_hashes'],'Reload dependency package set/bytes changed')
    return dict(actors=[actual_rows[r['guid']] for r in actual['actors']],
                transient_editor_billboard_names=renames)

try:
    before=json.loads((OUT/'baseline.json').read_text(encoding='utf-8'))
    imported=json.loads((OUT/'import_report.json').read_text(encoding='utf-8'))
    require(imported.get('success') is True,'No successful incremental import to validate')
    require(sha(OUT/'after_import.json')==imported['after_import_sha256'],'Post-import snapshot file changed')
    saved=json.loads((OUT/'after_import.json').read_text(encoding='utf-8'))
    require(sha(SRC/'scene_ownership.json')==imported['extension_ownership_sha256'],'Extension ownership changed')
    ownership=json.loads((SRC/'scene_ownership.json').read_text(encoding='utf-8'))
    require(ownership['owner']==guard.EXTENSION_TAG and ownership['namespace']==guard.EXTENSION_NAMESPACE
            and ownership['map']==guard.MAP,'Extension ownership identity mismatch')
    require(ownership['allowed_mesh_replacements']==imported['allowed_mesh_replacements'],
            'Terminal replacement audit changed')
    require(ownership['new_actor_guids']==imported['preservation_after_save']['new_actor_guids'],
            'Extension actor ownership changed')
    require(sha(SRC/'manifest.json')==imported['source_manifest_sha256']==ownership['source_manifest_sha256'],
            'Build manifest no longer matches the imported geometry')
    for filename,digest in ownership['source_files'].items():
        path=(ROOT/filename).resolve()
        require(path.is_relative_to(SRC.resolve()),'Source ownership escapes extension directory')
        require(sha(path)==digest,'Imported FBX source changed: '+filename)
    # This also validates dormant original assets not referenced by this map.
    original_token=verify_owned_scene(ROOT)
    require(original_token['manifest_sha256']==ownership['original_ownership_sha256']
            ==imported['original_ownership_sha256'],'Original ownership was changed after import')
    original=json.loads((ROOT/'SourceAssets/MPR/scene_ownership.json').read_text(encoding='utf-8'))
    original_assets=[r for r in original['packages'] if r['package']!=guard.MAP]
    require(guard.canonical_digest(original_assets)==ownership['original_owned_packages_digest'],
            'Original package records changed beyond the permitted map hash')
    require(len(original_assets)==ownership['original_owned_package_count'],'Original package count changed')
    new_hashes={r['package']:r['files'] for r in ownership['packages']}
    require(len(new_hashes)==len(ownership['packages']) and sorted(new_hashes)==sorted(imported['planned_packages']),
            'Extension package ownership does not match the original import plan')
    require(all(p.startswith(guard.EXTENSION_NAMESPACE+'/') for p in new_hashes),
            'Extension owns a package outside its namespace')
    require(guard.package_hashes(ROOT,new_hashes)==new_hashes,'New extension package bytes changed')
    current=guard.capture_editor_snapshot(u,project_root=ROOT,
        additional_packages=before['asset_hashes'],frozen_paths=before['frozen_files'])
    (OUT/'after_reload_observed.json').write_text(json.dumps(current,ensure_ascii=False),encoding='utf-8')
    guard.assert_clean_baseline(current)
    result=guard.assert_preserved(before,current,
        allowed_mesh_replacements=imported['allowed_mesh_replacements'],
        expected_new_guids=imported['preservation_after_save']['new_actor_guids'])
    # GUID presence alone misses HISM instances cleared/reordered on reload.
    comparison=assert_snapshot_content_equal(saved,current,new_actor_guids=ownership['new_actor_guids'])
    require(guard.canonical_digest(comparison['actors'])==ownership['actor_snapshot_digest'],
            'Reloaded scene differs from the durable extension actor digest')
    require(current['map_file_sha256']==imported['map_sha256']==ownership['post_save_map_sha256'],
            'Saved map bytes changed after import')
    guard.verify_protected_files(before,project_root=ROOT)
    (OUT/'after_reload.json').write_text(json.dumps(current,ensure_ascii=False),encoding='utf-8')
    normalized_snapshot=dict(current,actors=comparison['actors'])
    normalized_snapshot['protected_digest']=guard.canonical_digest(comparison['actors'])
    (OUT/'after_reload_digest_normalized.json').write_text(json.dumps(normalized_snapshot,ensure_ascii=False),encoding='utf-8')
    result.update(success=True,map_sha256=current['map_file_sha256'],
        original_owned_package_count=len(original_assets),new_package_count=len(new_hashes),
        all_generated_durable_actor_records_equal=True,
        raw_actor_records_equal=not comparison['transient_editor_billboard_names'],
        transient_editor_billboard_names=comparison['transient_editor_billboard_names'],
        transient_editor_billboard_name_count=len(comparison['transient_editor_billboard_names']),
        digest_snapshot='after_reload_digest_normalized.json',raw_snapshot='after_reload_observed.json')
except Exception:
    result=dict(success=False,error=traceback.format_exc())
    u.log_error(result['error'])
(OUT/'reload_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('MPRE_RELOAD',result.get('success'))
