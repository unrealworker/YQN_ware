"""Apply reviewed tree instances and two ground meshes to the OPEN MPR map.

All scene expectations are derived from committed source plans, independently
of the apply result. Shared assets and every other Actor field are protected.
"""
from copy import deepcopy
import importlib
import math
from pathlib import Path
import shutil
import traceback

import mpr_scene_patch_guard as g
from apply_mpr_site_round2 import legacy_fbx, package

ROOT = g.ROOT
SOURCE = ROOT/'SourceAssets/MPR/landscape_layout_20261106'
OUT = ROOT/'Saved/MPR/landscape_layout_20261106'
DEST = '/Game/MPRWarehouse/LandscapeLayout20261106'
TREE = '/Game/MPRWarehouse/SiteComplete/Meshes/SM_MPRSC_Tree_Canopy'
LEAVES = ['/Game/MPRWarehouse/Hierarchy/Materials/MI_MPRH_'+r
          for r in ('LeafMid', 'LeafLight', 'LeafShade')]
OLD_GROUND = {'/Game/MPRWarehouse/SiteComplete/Meshes/SM_MPRSC_'+r
              for r in ('MPRR_CampusGreen', 'MPR4_TerminalCurb')}


def canonical(row, commandlet=False):
    row = g.normalize(row, commandlet_compat=commandlet)
    # Matrix-backed instances can return the equivalent quaternion -q.
    for c in row['components']:
        for t in c.get('instance_transforms', []):
            q = t['rotation_xyzw']
            pivot = next((v for v in reversed(q) if abs(v) > 1e-10), 1.)
            if pivot < 0:
                t['rotation_xyzw'] = [-v for v in q]
    return row


def source_contract():
    vegetation = g.read(SOURCE/'vegetation_plan.json')
    ground = g.read(SOURCE/'ground/manifest.json')
    baseline_path = OUT/'before.json.gz'
    baseline = g.read(baseline_path)
    g.require(vegetation['map'] == ground['map'] == g.MAP, 'Wrong landscape map')
    g.require(ground['namespace'] == DEST, 'Unexpected landscape asset namespace')
    g.require(vegetation['baseline_sha256'] == g.guard.sha(baseline_path), 'Stale vegetation baseline')
    ground_plan = g.read(SOURCE/'ground/plan.json')
    audit = g.read(SOURCE/'ground/geometry_validation.json')
    g.require(ground_plan['baseline_sha256'] == vegetation['baseline_sha256'], 'Different ground baseline')
    g.require(audit['success'] and audit['manifest_sha256'] == g.guard.sha(SOURCE/'ground/manifest.json') and
              audit['plan_sha256'] == ground['plan_sha256'] == g.guard.sha(SOURCE/'ground/plan.json'),
              'Ground geometry validation is missing or stale')
    g.require(vegetation['tree_mesh'].split('.')[0] == TREE, 'Unreviewed tree mesh')
    g.require(vegetation['validation']['success'] and
              vegetation['validation']['protected_overlap_m2'] < 1e-7 and
              vegetation['validation']['min_canopy_gap_m'] >= .64,
              'Vegetation geometry validation failed')
    for plan in (vegetation, ground):
        for name, digest in plan.get('source_hashes', {}).items():
            p = (ROOT/name).resolve()
            g.require(p.is_relative_to(ROOT) and g.guard.sha(p) == digest, 'Source changed: '+name)
    identities = {(r['guid'], c['name']) for r in baseline['actors'] for c in r['components']
                  if c.get('mesh') == g.obj(TREE)}
    groups = vegetation['groups']
    actual = [(r['actor_guid'], r['component_name']) for r in groups]
    g.require(len(actual) == len(set(actual)) == 64 and set(actual) == identities,
              'Tree component scope changed')
    count = sum(len(r['instance_transforms']) for r in groups)
    g.require(0 < count <= 1302, 'Unexpected final tree count')
    for row in groups:
        transforms = row['instance_transforms']
        g.require(len(row['custom_data']) == len(transforms) and
                  all(v in (0, 1) for v in row['custom_data']), 'Invalid tree colour mask')
        for t in transforms:
            values = t['translation_cm']+t['rotation_xyzw']+t['scale']
            g.require(all(math.isfinite(v) for v in values), 'Non-finite tree transform')
            g.require(len(t['translation_cm']) == 3 and len(t['rotation_xyzw']) == 4 and
                      len(t['scale']) == 3 and all(.15 < v < 1. for v in t['scale']), 'Invalid tree scale')
            q = t['rotation_xyzw']
            g.require(max(abs(v) for v in q[:2]) < 1e-6 and abs(sum(v*v for v in q)-1.) < 1e-5,
                      'Only normalized yaw rotations are reviewed')
    mappings = ground['mesh_mappings']
    g.require(len(mappings) == 2 and {s['old_mesh'] for s in mappings} == OLD_GROUND,
              'Ground scope must be exactly the green and curb meshes')
    g.require({s['new_mesh'] for s in mappings} == {DEST+'/Meshes/'+r['name'] for r in ground['meshes']},
              'Ground manifest mappings differ')
    g.require(len(ground['meshes']) == 2, 'Unexpected ground mesh count')
    for row in ground['meshes']:
        p = (ROOT/row['fbx']).resolve()
        g.require(p.is_relative_to(SOURCE/'ground') and p.suffix.lower() == '.fbx' and
                  g.guard.sha(p) == row['sha256'], 'FBX source changed')
    return vegetation, ground, baseline


def expected_actors(before, vegetation, ground, commandlet=False):
    expected = {a['guid']: canonical(a, commandlet) for a in before['actors']}
    for row in vegetation['groups']:
        a = expected[row['actor_guid']]
        matches = [c for c in a['components'] if c['name'] == row['component_name']]
        g.require(len(matches) == 1 and matches[0]['mesh'] == g.obj(TREE), 'Tree component differs')
        c = matches[0]
        c.update(instance_count=len(row['instance_transforms']),
                 instance_transforms=deepcopy(row['instance_transforms']),
                 num_custom_data_floats=1, custom_data=list(row['custom_data']),
                 materials=c['materials'][:1]+[g.obj(p) for p in LEAVES])
    for row in ground['mesh_mappings']:
        matches = [c for a in expected.values() for c in a['components']
                   if c.get('mesh') == g.obj(row['old_mesh'])]
        g.require(len(matches) == 1, 'Ground source is not unique')
        matches[0]['mesh'] = g.obj(row['new_mesh'])
    return {guid: canonical(a, commandlet) for guid, a in expected.items()}


def validate(before, after, vegetation, ground, commandlet=False):
    expected = expected_actors(before, vegetation, ground, commandlet)
    current = {a['guid']: canonical(a, commandlet) for a in after['actors']}
    errors = g.differences(expected, current)
    errors += g.differences(before['world_settings'], after['world_settings'])
    errors += g.differences(g.normalized_coverage(before['world_actor_coverage'], commandlet_compat=commandlet),
                            g.normalized_coverage(after['world_actor_coverage'], commandlet_compat=commandlet))
    g.require(not errors, 'Unreviewed scene change: '+str(errors[:12]))
    targets = {r['actor_guid'] for r in vegetation['groups']}
    targets |= {a['guid'] for a in before['actors'] for c in a['components']
                if c.get('mesh', '').split('.')[0] in OLD_GROUND}
    return dict(success=True, actor_count=len(current), tree_groups=len(vegetation['groups']),
                trees=sum(len(r['instance_transforms']) for r in vegetation['groups']),
                changed_actors=len(targets), unchanged_actors=len(current)-len(targets))


def content_check(before, ground):
    now = g.guard.content_hashes(ROOT)
    map_rel = g.MAP_FILE.relative_to(ROOT).as_posix()
    g.require(not [p for p, h in before.items() if p != map_rel and now.get(p) != h],
              'Existing Content package modified')
    additions = {p: h for p, h in now.items() if p not in before}
    expected = {'Content/'+DEST.removeprefix('/Game/')+'/Meshes/'+r['name']+'.uasset'
                for r in ground['meshes']}
    g.require(set(additions) == expected, 'Unexpected new Content assets')
    return dict(success=True, protected_packages=len(before)-1, new_packages=additions)


def component(u, actor, name):
    matches = [c for c in actor.get_components_by_class(u.ActorComponent) if c.get_name() == name]
    g.require(len(matches) == 1, 'Missing component '+name)
    return matches[0]


def replace_instances(u, c, rows, values):
    c.modify()
    c.clear_instances()
    c.set_num_custom_data_floats(1)
    transforms = []
    for row in rows:
        q = row['rotation_xyzw']
        transforms.append(u.Transform(location=u.Vector(*row['translation_cm']),
                          rotation=u.Rotator(yaw=math.degrees(2*math.atan2(q[2], q[3]))),
                          scale=u.Vector(*row['scale'])))
    if transforms:
        indices = c.add_instances(transforms, should_return_indices=True, world_space=False, update_navigation=False)
        g.require(list(indices) == list(range(len(transforms))), 'HISM instance allocation failed')
    g.require(c.get_instance_count() == len(rows), 'HISM count differs')
    for i, value in enumerate(values):
        g.require(c.set_custom_data_value(i, 0, float(value), i == len(values)-1), 'Tree mask write failed')
    g.require(list(c.get_editor_property('per_instance_sm_custom_data')) == list(values), 'Tree mask readback differs')


def apply(u, before, vegetation, ground):
    actors = {u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')): a
              for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    leaves = [u.EditorAssetLibrary.load_asset(p) for p in LEAVES]
    g.require(all(leaves), 'Existing hierarchy leaf materials missing')
    import mpr_transport_cleanup as importer
    importer = importlib.reload(importer)
    importer.DEST = DEST
    importer.OWNER = 'mpr-landscape-layout-20261106'
    imports, prepared = [], []
    with legacy_fbx(u):
        for mapping in ground['mesh_mappings']:
            targets = [(a, c) for a in before['actors'] for c in a['components']
                       if c.get('mesh') == g.obj(mapping['old_mesh'])]
            g.require(len(targets) == 1, 'Ambiguous ground source')
            a, c = targets[0]
            live = component(u, actors[a['guid']], c['name'])
            row = next(r for r in ground['meshes'] if r['name'] == mapping['name'])
            roles = [str(s.get_editor_property('imported_material_slot_name')) for s in live.static_mesh.static_materials]
            g.require(roles == row['material_roles'], 'Ground roles differ from current material slots')
            materials = [live.get_material(i) for i in range(live.get_num_materials())]
            mesh, report = importer.import_mesh(u, row, materials)
            imports.append(report)
            prepared.append((live, mesh))
    # No Actor property/tag writes: they can rerun Blueprint construction and
    # erase the HISM. Origin InstanceCount tags remain historical provenance.
    with u.ScopedEditorTransaction('MPR 植被与绿地布局整理'):
        for row in vegetation['groups']:
            c = component(u, actors[row['actor_guid']], row['component_name'])
            replace_instances(u, c, row['instance_transforms'], row['custom_data'])
            for i, material in enumerate(leaves, 1):
                c.set_material(i, material)
        for c, mesh in prepared:
            c.modify()
            g.require(c.set_static_mesh(mesh), 'Ground mesh replacement failed')
    return imports


def run(u):
    vegetation, ground, baseline = source_contract()
    g.require(not u.get_editor_subsystem(u.LevelEditorSubsystem).is_in_play_in_editor(), 'Exit PIE first')
    g.require(not (OUT/'after.json.gz').exists(), 'Apply already completed; inspect before reapplying')
    before = g.guard.capture(u, ROOT, g.MAP)
    g.guard.assert_clean(before)
    g.require(not g.differences({r['guid']: canonical(r) for r in baseline['actors']},
                                {r['guid']: canonical(r) for r in before['actors']}), 'Live scene changed after planning')
    g.require(not g.differences(baseline['world_settings'], before['world_settings']), 'World settings changed')
    hashes = g.read(OUT/'content_before.json.gz')
    g.require(hashes == g.guard.content_hashes(ROOT), 'Content changed after planning')
    shutil.copy2(g.MAP_FILE, OUT/'map_before.umap')
    report = dict(success=False, vegetation_sha256=g.guard.sha(SOURCE/'vegetation_plan.json'),
                  ground_sha256=g.guard.sha(SOURCE/'ground/manifest.json'))
    try:
        report['imports'] = apply(u, before, vegetation, ground)
        current = g.guard.capture(u, ROOT, g.MAP)
        report['preservation'] = validate(before, current, vegetation, ground)
        report['content'] = content_check(hashes, ground)
        g.require(u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level(), 'Cannot save current MPR map')
        current = g.guard.capture(u, ROOT, g.MAP)
        report['preservation'] = validate(before, current, vegetation, ground)
        g.guard.assert_clean(current)
        g.write(OUT/'after.json.gz', current)
        report['success'] = True
        report['map_sha256'] = g.guard.sha(g.MAP_FILE)
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        g.write(OUT/'apply_report.json', report)
    print('MPR_LANDSCAPE_APPLY_OK', report['preservation'])


def export_render_geometry(u, destination):
    """Read actual built buffers, not the importer source MeshDescription."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    ground = g.read(SOURCE/'ground/manifest.json')
    rows = []
    for row in ground['meshes']:
        mesh = u.EditorAssetLibrary.load_asset(DEST+'/Meshes/'+row['name'])
        options = u.FbxExportOption()
        for key, value in dict(ascii=False, export_source_mesh=False, level_of_detail=False,
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
        g.require(u.Exporter.run_asset_export_task(task), 'Native render-data export failed')
        rows.append(dict(name=row['name'], native_triangles=mesh.get_num_triangles(0),
                         fbx=task.filename, sha256=g.guard.sha(task.filename),
                         asset_sha256=g.guard.sha(ROOT/('Content/'+DEST.removeprefix('/Game/')+'/Meshes/'+row['name']+'.uasset'))))
    g.write(destination/'manifest.json', dict(export_source_mesh=False, meshes=rows))
    print('MPR_LANDSCAPE_NATIVE_EXPORTED', [(r['name'], r['native_triangles']) for r in rows])


def verify_reload(u):
    g.require('-run=pythonscript' in u.SystemLibrary.get_command_line().lower(), 'Owned commandlet only')
    vegetation, ground, before = source_contract()
    g.require(u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(g.MAP), 'Cannot reload saved MPR map')
    current = g.guard.capture(u, ROOT, g.MAP)
    report = dict(success=False, preservation=validate(before, current, vegetation, ground, commandlet=True))
    final = g.read(OUT/'after.json.gz')
    g.require(not g.differences({a['guid']: canonical(a, True) for a in final['actors']},
                                {a['guid']: canonical(a, True) for a in current['actors']}), 'Reload differs from saved scene')
    # FBX import removes zero-area / below-normal-threshold faces. Bind the
    # expected built count to independently audited render-buffer geometry and
    # the exact saved asset, rather than silently accepting a count tolerance.
    native = g.read(SOURCE/'native_validation.json')
    g.require(native['success'] and native['ground_manifest_sha256'] == g.guard.sha(SOURCE/'ground/manifest.json'),
              'Native geometry audit is stale')
    audited = {r['name']: r for r in native['meshes']}
    g.require(set(audited) == {r['name'] for r in ground['meshes']}, 'Native geometry audit scope differs')
    for row in ground['meshes']:
        mesh = u.EditorAssetLibrary.load_asset(DEST+'/Meshes/'+row['name'])
        audit = audited[row['name']]
        asset_file = ROOT/('Content/'+DEST.removeprefix('/Game/')+'/Meshes/'+row['name']+'.uasset')
        g.require(audit['asset_sha256'] == g.guard.sha(asset_file) and audit['source_fbx_sha256'] == row['sha256'],
                  'Audited native/source geometry changed')
        g.require(mesh.get_num_triangles(0) == audit['native_triangles'], 'Reloaded ground triangles differ')
        g.require([str(s.get_editor_property('imported_material_slot_name')) for s in mesh.static_materials]
                  == row['material_roles'], 'Reloaded ground roles differ')
    report['content'] = content_check(g.read(OUT/'content_before.json.gz'), ground)
    report['native_validation_sha256'] = g.guard.sha(SOURCE/'native_validation.json')
    g.require(current['map_file_sha256'] == final['map_file_sha256'], 'Saved map hash differs')
    report['success'] = True
    g.write(OUT/'reload_report.json', report)
    print('MPR_LANDSCAPE_RELOAD_OK', report['preservation'])
