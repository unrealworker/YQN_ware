"""Scoped in-place scene edits and independent, read-only reload verification.

run(unreal, 'transport'|'hierarchy') applies to the already open map and saves
only that map. verify_reload is for an owned commandlet, never the live editor.
Source geometry/material preparation is delegated to the scoped apply modules.
"""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import importlib
import json
import math
from pathlib import Path
import shutil
import traceback

import rebuild_preservation as guard

ROOT = Path(__file__).resolve().parents[2]
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE = ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
FOLDERS = {'transport': 'transport_cleanup_20261105', 'hierarchy': 'hierarchy_20261105',
           'crossing': 'crossing_surface_20261105'}


def read(path):
    p = Path(path)
    return json.loads((gzip.decompress(p.read_bytes()) if p.suffix == '.gz' else p.read_bytes()).decode('utf-8-sig'))


def write(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2).encode('utf8')
    p.write_bytes(gzip.compress(data, mtime=0) if p.suffix == '.gz' else data)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def obj(package):
    return package+'.'+package.rsplit('/', 1)[-1]


def _identity_transform(scale=1.):
    return dict(translation_cm=[0., 0., 0.], rotation_xyzw=[0., 0., 0., 1.], scale=[scale]*3)


def _editor_visualization(row, name, cls, parent, *, scale=1., **extra):
    return dict(name=name, **{'class': '/Script/Engine.'+cls}, tags=[],
                transform=_identity_transform(scale), attach_parent=row['path']+'.'+parent,
                mobility='<ComponentMobility.MOVABLE: 2>', visible=True, hidden_in_game=True, **extra)


def normalize(row, *, commandlet_compat=False):
    row = guard.canonical_actor(row)
    if not commandlet_compat:
        return row
    # CameraComponent.cpp:164-190 creates both visualization components only
    # outside commandlets. Match complete known transient records, not classes
    # or name prefixes; authored camera components/settings remain compared.
    cameras = {
        'D2ECE8B94CE837BB50E7F098CA7C353C':
            ('CameraActor_0', '/Script/Engine.CameraActor', 'MPR_ReviewCamera', 'CameraComponent'),
        '672B1EC34EBAE7420C58BB8462E8257C':
            ('BP_GHS_WarehouseCamera_C_0', '/Game/GHSNormalWarehouse/Camera/BP_GHS_WarehouseCamera.BP_GHS_WarehouseCamera_C',
             'MPR_WarehouseCamera', 'WarehouseCamera'),
    }
    camera = cameras.get(row['guid'])
    if camera and (row['name'], row['class'], row['label']) == camera[:3]:
        parent = camera[3]
        require(any(c['name'] == parent and c['class'] == '/Script/Engine.CameraComponent'
                    for c in row['components']), 'Reviewed camera component is missing')
        proxy = _editor_visualization(row, 'CameraProxyMeshComponent_0', 'CameraProxyMeshComponent', parent,
            mesh='/Engine/EditorMeshes/MatineeCam_SM.MatineeCam_SM',
            materials=['/Engine/EditorMaterials/MatineeCam_mat.MatineeCam_mat'],
            collision_profile='NoCollision', cast_shadow=False)
        frustum = _editor_visualization(row, 'DrawFrustumComponent_0', 'DrawFrustumComponent', parent)
        row['components'] = [c for c in row['components'] if c not in (proxy, frustum)]
    # SceneComponent.cpp:894-930 creates transient visualization billboards.
    # SkyLightComponent.cpp:298-305 and DirectionalLightComponent.cpp:1018-1026
    # initialize sprite scales only outside commandlets. LightComponent.cpp:235-
    # 242 then overwrites billboard scale with that value (zero in commandlets).
    # Keep the billboard and every other field; normalize only the known scale.
    lights = {
        '9C971A07486E959639DDF4861749C387':
            ('SkyLight_0', '/Script/Engine.SkyLight', 'MPR4_Ambient', 'SkyLightComponent0', 1.),
        'FAD00F004D6AFDEE6CC10488819683E4':
            ('DirectionalLight_0', '/Script/Engine.DirectionalLight', 'MPR4_KeyLight', 'LightComponent0', .5),
    }
    light = lights.get(row['guid'])
    if light and (row['name'], row['class'], row['label']) == light[:3]:
        cmd_sprite = _editor_visualization(row, 'BillboardComponent_0', 'BillboardComponent', light[3], scale=0.)
        for component in row['components']:
            if component == cmd_sprite:
                component['transform']['scale'] = [light[4]]*3
    return row


def normalized_coverage(rows, *, commandlet_compat=False):
    result = guard.canonical_coverage(rows)
    if not commandlet_compat:
        return result
    # Chaos/ChaosDebugDrawComponent.cpp:371-415 skips this precise transient,
    # editor-hidden debug actor in commandlets. No other auxiliary is optional.
    name = '__Engine_chaos_debug_draw__'
    expected = dict(path=MAP+'.'+MAP.rsplit('/', 1)[-1]+':PersistentLevel.'+name,
                    engine_role='chaos_debug_draw', name=name, **{'class': '/Script/Engine.Actor'},
                    transform=_identity_transform(), hidden=False, tick_enabled=False,
                    collision_enabled=True, tags=[], label='Actor', folder='None', attachment_parent=None,
                    components=[dict(name='ChaosDebugDrawComponent',
                                     **{'class': '/Script/ChaosSolverEngine.ChaosDebugDrawComponent'}, tags=[])])
    debug = [row for row in result if row.get('engine_role') == 'chaos_debug_draw']
    require(len(debug) <= 1 and all(row == expected for row in debug),
            'Chaos editor auxiliary differs from its exact automatic shape')
    return [row for row in result if row != expected]


def differences(left, right, path=''):
    if isinstance(left, dict) and isinstance(right, dict):
        result = [path+'/'+k+': missing/added' for k in sorted(set(left)^set(right))]
        for k in sorted(set(left)&set(right)):
            result += differences(left[k], right[k], path+'/'+k)
        return result
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return [path+': length differs']
        result = []
        for i, (a, b) in enumerate(zip(left, right)):
            result += differences(a, b, path+'/'+str(i))
        return result
    if isinstance(left, float) and isinstance(right, (float, int)) and abs(left-right) < 1e-6:
        return []
    return [] if left == right else [path+': '+str(left)[:180]+' -> '+str(right)[:180]]


def validate_delta(before, after, mode, *, commandlet_compat=False):
    """Derive the whitelist from reviewed source plans, independently of apply()."""
    a = {r['guid']: normalize(r, commandlet_compat=commandlet_compat) for r in before['actors']}
    b = {r['guid']: normalize(r, commandlet_compat=commandlet_compat) for r in after['actors']}
    expected = deepcopy(a)
    changed = []
    deleted = []
    new = []
    if mode == 'transport':
        import mpr_transport_cleanup as patch
        plan = read(ROOT/'SourceAssets/MPR/transport_cleanup_20261105/manifest.json')
        replacements = {r['name'] for r in plan['meshes']}
        removals = set(plan['remove_mesh_names'])
        seen = set()
        for guid, row in list(expected.items()):
            for c in row['components']:
                mesh = c.get('mesh', '')
                name = mesh.split('.')[-1]
                if name not in replacements | removals:
                    continue
                require(mesh.startswith('/Game/MPRWarehouse/RebuildB50B57/Site/Meshes/'), 'Unexpected old transport package')
                require(row['class'] == '/Script/Engine.StaticMeshActor' and len(row['components']) == 1,
                        'Transport target contains unrelated components')
                require(name not in seen, 'Duplicate transport target')
                seen.add(name)
                if name in removals:
                    del expected[guid]
                    deleted.append(dict(guid=guid, mesh=mesh))
                else:
                    c['mesh'] = obj(patch.DEST+'/Meshes/'+name)
                    changed.append(dict(guid=guid, component=c['name'], fields=['mesh']))
        require(seen == replacements | removals and len(replacements) == 23 and len(removals) == 7,
                'Transport target set must match all 23 replacements and 7 removals')
        require(set(b) == set(expected), 'Unexpected actor creation/deletion')
    elif mode == 'crossing':
        plan = read(ROOT/'SourceAssets/MPR/crossing_surface_20261105/manifest.json')
        require(len(plan['mesh_mappings']) == 8 and not plan['remove_mesh_names'], 'Unexpected crossing scope')
        require(set(a) == set(b), 'Crossing must preserve every Actor')
        for spec in plan['mesh_mappings']:
            matches = [(r, c) for r in expected.values() for c in r['components']
                       if c.get('mesh') == obj(spec['old_mesh'])]
            require(len(matches) == 1, 'Crossing source identity changed')
            row, c = matches[0]
            materials = dict(zip(spec['old_material_roles'], c['materials']))
            fields = ['mesh']
            if spec['material_reference_mesh']:
                references = [c for r in a.values() for c in r['components']
                              if c.get('mesh') == obj(spec['material_reference_mesh'])]
                require(len(references) == 1 and len(references[0]['materials']) == 1, 'Ambiguous road material reference')
                materials['MPR4_TerminalAsphalt'] = references[0]['materials'][0]
                fields.append('materials')
            c['mesh'] = obj(spec['new_mesh'])
            c['materials'] = [materials[role] for role in spec['new_material_roles']]
            changed.append(dict(guid=row['guid'], component=c['name'], fields=fields))
    elif mode == 'hierarchy':
        solar = read(ROOT/'SourceAssets/MPR/hierarchy_20261105/solar/manifest.json')
        for spec in solar['meshes']:
            matches = [r for r in expected.values() if r['label'] == spec['retained_actor_label']]
            require(len(matches) == 1, 'Missing/duplicate original solar actor')
            row = matches[0]
            matches = [c for c in row['components'] if c.get('mesh') == obj(spec['source_mesh'])]
            require(len(matches) == 1, 'Original solar component changed')
            c = matches[0]
            c['mesh'] = obj(solar['namespace']+'/Meshes/'+spec['name'])
            # Module creates four plain materials with these exact role names.
            c['materials'] = [obj(solar['namespace']+'/Materials/M_'+r) for r in spec['material_roles']]
            changed.append(dict(guid=row['guid'], component=c['name'], fields=['mesh', 'materials']))
        plan = read(ROOT/'SourceAssets/MPR/hierarchy_20261105/landscape/selection.json')
        dest = '/Game/MPRWarehouse/Hierarchy/Materials'
        selected = 0
        for spec in plan['groups']:
            if not spec['selected_indices']:
                continue
            row = expected[spec['actor_guid']]
            c = next(c for c in row['components'] if c['name'] == spec['component_name'])
            require(c['instance_transforms'] == spec['instance_transforms'], 'Tree baseline does not match reviewed plan')
            c['materials'] = c['materials'][:1]+[obj(dest+'/MI_MPRH_'+r) for r in ('LeafMid', 'LeafLight', 'LeafShade')]
            c['num_custom_data_floats'] = 1
            c['custom_data'] = [float(i in spec['selected_indices']) for i in range(spec['instance_count'])]
            selected += sum(c['custom_data'])
            changed.append(dict(guid=row['guid'], component=c['name'], fields=['materials', 'num_custom_data_floats', 'custom_data']))
        require(selected == 111, 'Expected exactly 111 recoloured existing trees')
        spec = plan['campus_green']
        c = next(c for c in expected[spec['actor_guid']]['components'] if c['name'] == spec['component_name'])
        c['materials'] = [obj(dest+'/MI_MPRH_CampusGreen')]
        changed.append(dict(guid=spec['actor_guid'], component=c['name'], fields=['materials']))
        require(set(expected) <= set(b) and len(set(b)-set(expected)) == 1, 'Expected only one new campus infill actor')
        added = b[next(iter(set(b)-set(expected)))]
        require(added['label'] == 'MPRH_CampusPerimeterInfill' and 'mpr-campus-hierarchy-20261105' in added['tags'], 'Unexpected infill identity')
        trees = [c for c in added['components'] if c.get('instance_count')]
        require(len(trees) == 1 and trees[0]['instance_count'] == len(plan['infill']) == 20, 'Expected twenty infill trees')
        require(trees[0]['custom_data'] == [1.]*20 and not added['collision_enabled'] and not added['tick_enabled'], 'Unexpected infill data/behavior')
        for tr, spec in zip(trees[0]['instance_transforms'], plan['infill']):
            target = [spec['position_m'][0]*100, -spec['position_m'][1]*100, spec['position_m'][2]*100]
            require(not differences(tr['translation_cm'], target) and not differences(tr['scale'], spec['scale']), 'Infill location/size differs from approved clearances')
            angle = math.radians(-spec['rotation_deg'])/2
            rotation = [0., 0., math.sin(angle), math.cos(angle)]
            error = min(max(abs(x-y) for x, y in zip(tr['rotation_xyzw'], rotation)),
                        max(abs(x+y) for x, y in zip(tr['rotation_xyzw'], rotation)))
            require(error < 1e-6, 'Infill rotation differs from reviewed plan')
        new = [added['guid']]
        expected[added['guid']] = added
    else:
        raise ValueError(mode)
    errors = []
    for guid in sorted(set(expected)&set(b)):
        errors += differences(expected[guid], b[guid], expected[guid]['name'])
    errors += differences(before['world_settings'], after['world_settings'], 'world_settings')
    errors += differences(normalized_coverage(before['world_actor_coverage'], commandlet_compat=commandlet_compat),
                          normalized_coverage(after['world_actor_coverage'], commandlet_compat=commandlet_compat), 'world_auxiliaries')
    require(not errors, 'Out-of-scope scene changes: '+json.dumps(errors[:30], ensure_ascii=False))
    return dict(success=True, before_actors=len(a), after_actors=len(b),
                changed_components=changed, deleted_actors=deleted, new_actor_ids=new,
                unchanged_actors=len(a)-len({r['guid'] for r in changed})-len(deleted))


def check_content(before, mode):
    current = guard.content_hashes(ROOT)
    map_rel = MAP_FILE.relative_to(ROOT).as_posix()
    errors = [p for p, h in before.items() if p != map_rel and current.get(p) != h]
    require(not errors, 'Pre-existing shared assets changed: '+str(errors[:10]))
    prefixes = {'transport': ('Content/MPRWarehouse/TransportCleanup20261105/',),
                'crossing': ('Content/MPRWarehouse/CrossingSurface20261105/',),
                'hierarchy': ('Content/MPRWarehouse/Hierarchy/', 'Content/MPRWarehouse/Hierarchy20261105/')}[mode]
    new = {p: h for p, h in current.items() if p not in before}
    require(all(p.startswith(prefixes) for p in new), 'New packages escaped patch namespaces')
    return dict(protected_existing_packages=len(before)-1, new_packages=new, map_sha256=current[map_rel])


def run(u, mode):
    out = ROOT/'Saved/MPR'/FOLDERS[mode]/'apply'
    out.mkdir(parents=True, exist_ok=True)
    require(not u.get_editor_subsystem(u.LevelEditorSubsystem).is_in_play_in_editor(), 'Exit PIE before changing the current map')
    before = guard.capture(u, ROOT, MAP)
    if (out/'before.json.gz').exists():
        baseline = read(out/'before.json.gz')
        require(before['map_file_sha256'] == baseline['map_file_sha256'], 'Saved map has changed since patch preflight')
        before = baseline
        hashes = read(out/'content_before.json.gz')
    else:
        guard.assert_clean(before)
        hashes = guard.content_hashes(ROOT)
        write(out/'before.json.gz', before)
        write(out/'content_before.json.gz', hashes)
        shutil.copy2(MAP_FILE, out/'map_before.umap')
    report = dict(success=False, mode=mode, map=MAP, started_utc=datetime.now(timezone.utc).isoformat())
    try:
        if mode == 'transport':
            module = importlib.import_module('mpr_transport_cleanup')
            report['transport'] = importlib.reload(module).apply(u)
        elif mode == 'crossing':
            module = importlib.import_module('mpr_crossing_surface')
            report['crossing'] = importlib.reload(module).apply(u)
        else:
            for name in ('mpr_solar_hierarchy', 'mpr_campus_hierarchy'):
                report[name] = importlib.reload(importlib.import_module(name)).apply(u)
        after = guard.capture(u, ROOT, MAP)
        write(out/'after_unsaved.json.gz', after)
        report['preservation'] = validate_delta(before, after, mode)
        report['content'] = check_content(hashes, mode)
        require(u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level(), 'Saving current MPR map failed')
        after = guard.capture(u, ROOT, MAP)
        report['preservation_after_save'] = validate_delta(before, after, mode)
        report['content'] = check_content(hashes, mode)
        write(out/'after.json.gz', after)
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        write(out/'report.json', report)
    print(json.dumps({k: report[k] for k in ('success', 'mode', 'preservation', 'content')}, ensure_ascii=False))
    return report


def verify_reload(u, mode):
    require('-run=pythonscript' in u.SystemLibrary.get_command_line().lower(), 'Reload is only allowed in an owned commandlet')
    out = ROOT/'Saved/MPR'/FOLDERS[mode]/'apply'
    report = dict(success=False, mode=mode, read_only=True)
    sha_before = guard.sha(MAP_FILE)
    try:
        require(read(out/'report.json')['success'], 'Apply was not successful')
        require(u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(MAP), 'Cannot load saved map')
        current = guard.capture(u, ROOT, MAP)
        write(out/'reload_observed.json.gz', current)
        report['preservation'] = validate_delta(read(out/'before.json.gz'), current, mode, commandlet_compat=True)
        expected = read(out/'after.json.gz')
        aa = {a['guid']: normalize(a, commandlet_compat=True) for a in expected['actors']}
        bb = {a['guid']: normalize(a, commandlet_compat=True) for a in current['actors']}
        errors = differences(aa, bb)
        require(not errors, 'Reload differs from saved state: '+json.dumps(errors[:30]))
        report['content'] = check_content(read(out/'content_before.json.gz'), mode)
        if mode == 'hierarchy':
            import mpr_solar_hierarchy as solar
            manifest, source = solar.source_contract()
            report['solar_native_readback'] = dict(source=source,
                materials=[solar.material_audit(u, u.EditorAssetLibrary.load_asset(solar.material_path(role)), spec)
                           for role, spec in manifest['materials'].items()],
                meshes=[])
            # StaticMeshEditorSubsystem requires the editor UI module. Read the
            # serialized StaticMesh directly in the NullRHI commandlet.
            for row in manifest['meshes']:
                mesh = u.EditorAssetLibrary.load_asset(solar.mesh_path(row))
                triangles = [mesh.get_num_triangles(i) for i in range(3)]
                require(triangles == row['lod_triangles'], 'Reloaded solar LOD geometry differs')
                roles = [str(s.get_editor_property('imported_material_slot_name')) for s in mesh.static_materials]
                require(roles == row['material_roles'], 'Reloaded solar material slots differ')
                report['solar_native_readback']['meshes'].append(dict(package=solar.mesh_path(row),
                    triangles=triangles, material_roles=roles))
        if mode == 'crossing':
            import mpr_crossing_surface as crossing
            manifest = crossing.source_inputs()
            refined = {r['package']: r for r in read(out/'normal_refinement.json')['assets']} if (out/'normal_refinement.json').exists() else {}
            report['crossing_native_readback'] = []
            for row in manifest['meshes']:
                path = crossing.DEST+'/Meshes/'+row['name']
                mesh = u.EditorAssetLibrary.load_asset(path)
                require(u.EditorAssetLibrary.get_metadata_tag(mesh, crossing.TAG_SHA) == row['sha256'], 'Reloaded crossing source hash differs')
                roles = [str(s.get_editor_property('imported_material_slot_name')) for s in mesh.static_materials]
                require(roles == row['material_roles'], 'Reloaded crossing slots differ')
                triangles = mesh.get_num_triangles(0)
                if path in refined:
                    require(triangles == refined[path]['triangles'], 'Reloaded refined ramp render count differs')
                report['crossing_native_readback'].append(dict(package=path, triangles=triangles,
                    material_roles=roles, source_sha256=row['sha256'], **crossing.check_bounds(mesh, row)))
        require(guard.sha(MAP_FILE) == sha_before, 'Verification changed the map file')
        write(out/'reload_snapshot.json.gz', current)
        report.update(success=True, map_unchanged=True)
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        write(out/'reload_report.json', report)
    print('MPR_PATCH_RELOAD_SUCCESS '+mode)
