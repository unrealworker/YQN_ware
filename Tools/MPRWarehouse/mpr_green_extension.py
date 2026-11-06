"""Extend the existing campus green mesh in the two user-marked regions.

Only the existing component's mesh reference changes. Material, vegetation,
roads, buildings, cameras and all other actor fields must remain identical.
"""
import importlib
import shutil
import traceback

import mpr_scene_patch_guard as g
from mpr_landscape_layout import canonical, component
from apply_mpr_site_round2 import legacy_fbx

ROOT = g.ROOT
SOURCE = ROOT/'SourceAssets/MPR/green_extension_20261106'
OUT = ROOT/'Saved/MPR/green_extension_20261106'
DEST = '/Game/MPRWarehouse/GreenExtension20261106'
GUID = '8AACBD08462839D9FDF1A79A307C9952'
COMPONENT = 'StaticMeshComponent0'
OLD = '/Game/MPRWarehouse/LandscapeLayout20261106/Meshes/SM_MPRLG_CampusGreen'
MATERIAL = '/Game/MPRWarehouse/Hierarchy/Materials/MI_MPRH_CampusGreen'


def inputs():
    manifest = g.read(SOURCE/'manifest.json')
    audit = g.read(SOURCE/'geometry_validation.json')
    g.require(manifest['map'] == g.MAP and manifest['namespace'] == DEST, 'Wrong map or namespace')
    g.require(len(manifest['meshes']) == 1, 'Expected only the campus green mesh')
    row = manifest['meshes'][0]
    g.require(row['material_roles'] == ['MPRR_CampusGreen'], 'Green material role changed')
    g.require(audit['success'], 'Geometry validation failed')
    g.require(manifest['plan_sha256'] == g.guard.sha(SOURCE/'plan.json'), 'Stale source plan')
    g.require(audit['manifest_sha256'] == g.guard.sha(SOURCE/'manifest.json'), 'Stale geometry audit')
    for path, digest in manifest['source_hashes'].items():
        source = (ROOT/path).resolve()
        g.require(source.is_relative_to(ROOT) and g.guard.sha(source) == digest, 'Source changed: '+path)
    fbx = (ROOT/row['fbx']).resolve()
    g.require(fbx.is_relative_to(SOURCE) and fbx.suffix == '.fbx' and
              g.guard.sha(fbx) == row['sha256'], 'FBX differs from reviewed geometry')
    return manifest, row


def validate(before, after, row, commandlet=False):
    expected = {a['guid']: canonical(a, commandlet) for a in before['actors']}
    target = expected[GUID]
    c = next(c for c in target['components'] if c['name'] == COMPONENT)
    g.require(c['mesh'] == g.obj(OLD), 'Original campus green mesh differs')
    g.require(c['materials'] == [g.obj(MATERIAL)], 'Existing green material differs')
    c['mesh'] = g.obj(DEST+'/Meshes/'+row['name'])
    actual = {a['guid']: canonical(a, commandlet) for a in after['actors']}
    errors = g.differences(expected, actual)
    errors += g.differences(before['world_settings'], after['world_settings'])
    errors += g.differences(g.normalized_coverage(before['world_actor_coverage'], commandlet_compat=commandlet),
                            g.normalized_coverage(after['world_actor_coverage'], commandlet_compat=commandlet))
    g.require(not errors, 'Unexpected scene change: '+str(errors[:8]))
    return dict(success=True, actor_count=len(actual), changed_mesh_references=1,
                unchanged_actors=len(actual)-1, material_unchanged=MATERIAL)


def check_content(row):
    before = g.read(OUT/'content_before.json.gz')
    after = g.guard.content_hashes(ROOT)
    map_rel = g.MAP_FILE.relative_to(ROOT).as_posix()
    g.require(not [p for p,h in before.items() if p != map_rel and after.get(p) != h],
              'An existing unrelated Content package changed')
    additions = {p:h for p,h in after.items() if p not in before}
    expected = 'Content/'+DEST.removeprefix('/Game/')+'/Meshes/'+row['name']+'.uasset'
    g.require(set(additions) == {expected}, 'Unexpected asset additions')
    return dict(success=True, unchanged_packages=len(before)-1, new_mesh=additions)


def run(u):
    manifest, row = inputs()
    g.require(not u.get_editor_subsystem(u.LevelEditorSubsystem).is_in_play_in_editor(), 'PIE is running')
    g.require(not (OUT/'after.json.gz').exists(), 'Already applied; inspect before repeating')
    before = g.read(OUT/'before.json.gz')
    live = g.guard.capture(u, ROOT, g.MAP)
    g.guard.assert_clean(live)
    g.require(not g.differences({a['guid']:canonical(a) for a in before['actors']},
                                {a['guid']:canonical(a) for a in live['actors']}), 'Scene changed during planning')
    g.require(before['world_settings'] == live['world_settings'], 'World settings changed')
    g.require(g.read(OUT/'content_before.json.gz') == g.guard.content_hashes(ROOT), 'Content changed during planning')
    actors = {u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a
              for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    c = component(u, actors[GUID], COMPONENT)
    g.require(c.static_mesh.get_path_name() == g.obj(OLD), 'Target mesh changed')
    g.require(c.get_material(0).get_path_name() == g.obj(MATERIAL), 'Target material changed')
    shutil.copy2(g.MAP_FILE, OUT/'map_before.umap')
    report = dict(success=False, manifest_sha256=g.guard.sha(SOURCE/'manifest.json'))
    try:
        import mpr_transport_cleanup as importer
        importer = importlib.reload(importer)
        importer.DEST = DEST
        importer.OWNER = 'mpr-green-extension-20261106'
        with legacy_fbx(u):
            mesh, report['import'] = importer.import_mesh(u, row, [c.get_material(0)])
        with u.ScopedEditorTransaction('扩展主仓园区绿色地坪'):
            c.modify()
            g.require(c.set_static_mesh(mesh), 'Failed to replace campus green mesh')
        after = g.guard.capture(u, ROOT, g.MAP)
        report['preservation'] = validate(before, after, row)
        report['content'] = check_content(row)
        g.require(u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level(), 'Failed to save MPR map')
        after = g.guard.capture(u, ROOT, g.MAP)
        report['preservation'] = validate(before, after, row)
        g.guard.assert_clean(after)
        g.write(OUT/'after.json.gz', after)
        report.update(success=True, map_sha256=g.guard.sha(g.MAP_FILE))
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        g.write(OUT/'apply_report.json', report)
    print('MPR_GREEN_EXTENSION_APPLIED', report['preservation'])


def verify_reload(u):
    g.require('-run=pythonscript' in u.SystemLibrary.get_command_line().lower(), 'Owned commandlet only')
    _, row = inputs()
    g.require(u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(g.MAP), 'Cannot load saved MPR map')
    before = g.read(OUT/'before.json.gz')
    saved = g.read(OUT/'after.json.gz')
    current = g.guard.capture(u, ROOT, g.MAP)
    preservation = validate(before, current, row, True)
    g.require(not g.differences({a['guid']:canonical(a, True) for a in saved['actors']},
                                {a['guid']:canonical(a, True) for a in current['actors']}), 'Reload differs from saved scene')
    mesh = u.EditorAssetLibrary.load_asset(DEST+'/Meshes/'+row['name'])
    native = g.read(SOURCE/'native_validation.json')
    asset = ROOT/('Content/'+DEST.removeprefix('/Game/')+'/Meshes/'+row['name']+'.uasset')
    g.require(native['success'] and native['manifest_sha256'] == g.guard.sha(SOURCE/'manifest.json') and
              native['source_fbx_sha256'] == row['sha256'] and native['asset_sha256'] == g.guard.sha(asset),
              'Native geometry audit is stale')
    g.require(native['all_retained_source_faces_accounted'] and native['all_native_faces_mapped'] and
              native['rejected_surface_area_m2'] == 0, 'Native geometry differs from valid source faces')
    g.require(mesh.get_num_triangles(0) == native['native_triangles'], 'Reloaded mesh triangle count differs')
    g.require(current['map_file_sha256'] == saved['map_file_sha256'], 'Saved map hash differs')
    report = dict(success=True, preservation=preservation, content=check_content(row),
                  native_triangles=mesh.get_num_triangles(0), map_sha256=current['map_file_sha256'],
                  native_audit_sha256=g.guard.sha(SOURCE/'native_validation.json'))
    g.write(OUT/'reload_report.json', report)
    print('MPR_GREEN_EXTENSION_RELOAD_OK', report)


def export_native(u):
    """Export built render triangles for validate_mpr_green_extension_native.py."""
    _, row = inputs()
    destination = OUT/'native'
    destination.mkdir(exist_ok=True)
    mesh = u.EditorAssetLibrary.load_asset(DEST+'/Meshes/'+row['name'])
    options = u.FbxExportOption()
    for key,value in dict(ascii=False, export_source_mesh=False, level_of_detail=False,
                           collision=False, force_front_x_axis=False, vertex_color=True).items():
        options.set_editor_property(key, value)
    task = u.AssetExportTask()
    task.object = mesh
    task.filename = str(destination/(row['name']+'.fbx'))
    task.automated = True
    task.prompt = False
    task.replace_identical = True
    task.exporter = u.StaticMeshExporterFBX()
    task.options = options
    g.require(u.Exporter.run_asset_export_task(task), 'Cannot export native render geometry')
    asset = ROOT/('Content/'+DEST.removeprefix('/Game/')+'/Meshes/'+row['name']+'.uasset')
    g.write(destination/'manifest.json', dict(export_source_mesh=False, triangles=mesh.get_num_triangles(0),
            fbx=task.filename, sha256=g.guard.sha(task.filename), asset_sha256=g.guard.sha(asset)))
