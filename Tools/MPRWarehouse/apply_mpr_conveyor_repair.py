"""Apply the reviewed CAD conveyor delta to the existing MPR level only.

The manifest matches source handles to exact old HISM instances. Existing
shared packages are never reimported: corrected meshes are MPR-private.
Apply the complete delta with -MPRConveyorApply in an owned commandlet.
-MPRConveyorAdditions extends the verified first repair with recovered feeds.
Without either flag the script independently reloads and verifies the result.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import rebuild_preservation as guard
import mpr_scene_patch_guard as patch

MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE = ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
SRC = ROOT/'SourceAssets/MPR/conveyor_repair_20261106'
OUT = ROOT/'Saved/MPR/conveyor_repair_20261106'
DEST = '/Game/MPRWarehouse/ConveyorRepair20261106/Meshes'
BP = '/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup'
COMPONENT = 'HierarchicalInstancedStaticMesh'
RENDER_FIELDS = ('receives_decals', 'instance_start_cull_distance', 'instance_end_cull_distance',
                 'min_lod', 'forced_lod_model', 'override_min_lod', 'cast_shadow')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pose(row):
    x, y, z = row['position_m']
    half = math.radians(-row['rotation_deg'])/2
    return dict(translation_cm=[x*100, -y*100, z*100],
                rotation_xyzw=[0., 0., math.sin(half), math.cos(half)],
                scale=row['scale'])


def transform(u, row):
    q = row['rotation_xyzw']
    assert abs(q[0])+abs(q[1]) < 1e-8, 'Only reviewed plan rotations are supported'
    return u.Transform(location=u.Vector(*row['translation_cm']),
                       rotation=u.Rotator(yaw=math.degrees(2*math.atan2(q[2],q[3]))), scale=u.Vector(*row['scale']))


def mesh_object(name):
    return DEST+'/'+name+'.'+name


def updated_tags(tags, count):
    assert sum(str(t).startswith('InstanceCount=') for t in tags) == 1
    return ['InstanceCount='+str(count) if str(t).startswith('InstanceCount=') else t for t in tags]


def derive_plan(before, manifest):
    """No actor selection by proximity or broad name matching is allowed."""
    actors = {a['guid']: a for a in before['actors']}
    selected = defaultdict(dict)
    additions = defaultdict(list)
    for old in manifest['removals']:
        assert old['instance_index'] >= 0
        assert old['instance_index'] not in selected[old['actor_guid']]
        selected[old['actor_guid']][old['instance_index']] = old
    for change in manifest['replacements']:
        assert change['old_instances'] and change['new_instances']
        owner = change['old_instances'][0]['actor_guid']
        for old in change['old_instances']:
            assert old['instance_index'] >= 0
            assert old['instance_index'] not in selected[old['actor_guid']]
            selected[old['actor_guid']][old['instance_index']] = old
        for new in change['new_instances']:
            additions[owner].append(dict(mesh=mesh_object(new['mesh']), transform=pose(new)))
    result = []
    for guid, indices in selected.items():
        actor = actors[guid]
        assert actor['class'] == BP+'.BP_GHS_InstanceGroup_C'
        assert actor['folder'] == 'MPR/Operations'
        assert actor['hidden'] is False and actor['tick_enabled'] is False
        components = [c for c in actor['components'] if 'instance_transforms' in c]
        assert len(components) == 1
        component = components[0]
        assert component['name'] == COMPONENT and component['num_custom_data_floats'] == 0
        identity = dict(translation_cm=[0.,0.,0.], rotation_xyzw=[0.,0.,0.,1.], scale=[1.,1.,1.])
        assert actor['transform'] == component['transform'] == identity
        partitions = defaultdict(list)
        for index, tr in enumerate(component['instance_transforms']):
            if index in indices:
                old = indices[index]
                assert old['actor_label'] == actor['label']
                assert old['component_name'] == component['name']
                assert not patch.differences(tr, old['original_transform']), (guid, index)
                assert component['mesh'].split('.')[-1] == old['old_pose']['mesh']
            else:
                partitions[component['mesh']].append(tr)
        assert len(indices) == sum(i < component['instance_count'] for i in indices)
        for new in additions[guid]:
            partitions[new['mesh']].append(new['transform'])
        primary = component['mesh'] if partitions.get(component['mesh']) else next(iter(partitions), None)
        result.append(dict(guid=guid, old=actor, component=component, primary=primary,
                           partitions=dict(partitions), selected_indices=sorted(indices)))
    return result


def validate_source_scope(manifest):
    evidence = patch.read(SRC/'semantics_audit_evidence.json')
    symbol_handles = {h for row in evidence['confirmed_annotation_misclassifications'] for h in row['handles']}
    drive_handles = {'2C93C9','2C9831','2C983F','2C984D','2C985B','2C9869','2C9877','2C9885','2C994A'}
    assert len(symbol_handles) == 173
    removed = [h for row in manifest['removals'] for h in row['source_handles']]
    assert len(removed) == len(set(removed)) == 182
    assert set(removed) == symbol_handles | drive_handles
    layout = patch.read(ROOT/'SourceAssets/MPR/mpr_cad_layout.json')
    cells = {h for row in layout['equipment'] if row['block'] == '321321' for h in row['source_handles']}
    changed = [h for row in manifest['replacements'] for h in row['source_handles']]
    terminals = {'2CA6A4','2CA7A5','2CA8A6','2CA9A7','2CAAA8','2CABA9','2CACAA',
                 '2CBA4E','2CBB4F','2CBC50','2CBD51','2CBE52','2CBF53','2CC054'} if manifest.get('additions') else set()
    assert len(cells) == 146 and len(changed) == len(set(changed)) == 149+len(terminals)
    assert set(changed) == cells | {'2CC6A3','2CC7DB','2E886D'} | terminals
    counts = manifest['counts']
    assert all(counts[k] == v for k,v in dict(old=1029,removed=182,replaced_old=149+len(terminals),replaced_new=149+len(terminals),unchanged=698-len(terminals)).items())
    added = sum(len(group['new_instances']) for group in manifest.get('additions',[]))
    assert counts['new'] == 847+added and counts.get('added',0) == added


def import_meshes(u, manifest):
    imported = {}
    for row in manifest['new_meshes']:
        assert row['name'] in {'SM_MPR_CollectionCellsCAD', 'SM_MPR_YMergeCAD', 'SM_MPR_Turn__U33_Reflected'} or row['name'].startswith('SM_MPR_CADFeed')
        source = ROOT/row['fbx']
        assert source.resolve() == (ROOT/'SourceAssets/MPR/operations'/(row['name']+'.fbx')).resolve()
        assert source.is_file() and row['triangles'] < 1800
        path = DEST+'/'+row['name']
        task = u.AssetImportTask()
        task.filename = str(source)
        task.destination_path = DEST
        task.destination_name = row['name']
        task.automated = True
        task.replace_existing = True
        task.replace_existing_settings = True
        task.save = False
        opts = u.FbxImportUI()
        opts.import_mesh = True
        opts.import_as_skeletal = False
        opts.import_materials = False
        opts.import_textures = False
        opts.import_animations = False
        opts.mesh_type_to_import = u.FBXImportType.FBXIT_STATIC_MESH
        opts.automated_import_should_detect_type = False
        data = opts.static_mesh_import_data
        data.combine_meshes = True
        data.auto_generate_collision = False
        data.generate_lightmap_u_vs = False
        data.convert_scene = True
        data.convert_scene_unit = True
        data.force_front_x_axis = False
        data.normal_import_method = u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        data.normal_generation_method = u.FBXNormalGenerationMethod.BUILT_IN
        task.options = opts
        task.factory = u.FbxFactory()
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        mesh = u.EditorAssetLibrary.load_asset(path)
        assert mesh and isinstance(mesh, u.StaticMesh)
        slots = mesh.static_materials
        assert len(slots) == len(row['material_roles'])
        for i, slot in enumerate(slots):
            role = str(slot.get_editor_property('imported_material_slot_name'))
            assert role in row['material_roles']
            mat = u.EditorAssetLibrary.load_asset('/Game/GHSZcoolSmartFactory/Materials/M_Zcool_'+role)
            assert mat
            assert u.MaterialEditingLibrary.has_material_usage(mat, u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
            slot.material_interface = mat
            slots[i] = slot
        mesh.set_editor_property('static_materials', slots)
        b = mesh.get_bounds()
        actual = [[b.origin.x-b.box_extent.x, b.origin.x+b.box_extent.x],
                  [b.origin.y-b.box_extent.y, b.origin.y+b.box_extent.y],
                  [b.origin.z-b.box_extent.z, b.origin.z+b.box_extent.z]]
        src = row['bounds_m']
        expected = [[src[0][0]*100, src[0][1]*100], [-src[1][1]*100, -src[1][0]*100], [src[2][0]*100, src[2][1]*100]]
        assert max(abs(a-b) for aa, bb in zip(actual, expected) for a,b in zip(aa,bb)) < .1
        imported[mesh.get_path_name()] = dict(mesh=mesh, bounds_cm=actual, roles=row['material_roles'], source_sha256=sha(source))
    return imported


def render_properties(u, actor):
    c = actor.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
    return {k:c.get_editor_property(k) for k in RENDER_FIELDS}


def fill(u, actor, mesh_path, transforms, tags, properties):
    # Changing Blueprint actor tags can reconstruct and clear SCS components.
    # Resolve components AFTER actor properties, then restore the complete list.
    actor.modify()
    actor.tags = tags
    for key, value in properties.items():
        actor.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent).set_editor_property(key, value)
    component = actor.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
    component.modify()
    mesh = u.EditorAssetLibrary.load_asset(mesh_path)
    assert mesh
    component.set_static_mesh(mesh)
    component.set_editor_property('override_materials', [])
    component = actor.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
    component.set_static_mesh(mesh)
    for i, slot in enumerate(mesh.static_materials):
        component.set_material(i, slot.material_interface)
    component.clear_instances()
    component.add_instances([transform(u, t) for t in transforms], should_return_indices=True,
                            world_space=True, update_navigation=False)
    assert component.get_instance_count() == len(transforms)
    assert render_properties(u, actor) == properties


def expected_primary(row, materials):
    actor = deepcopy(row['old'])
    c = next(c for c in actor['components'] if c['name'] == COMPONENT)
    trs = row['partitions'][row['primary']]
    actor['tags'] = updated_tags(actor['tags'], len(trs))
    c.update(mesh=row['primary'], materials=materials, instance_count=len(trs), instance_transforms=trs)
    return actor


def pose_differences(actual, expected):
    actual = deepcopy(actual)
    # UE canonicalizes +/-180 degrees. q and -q are the same rotation;
    # translations/scales and all other quaternion changes remain checked.
    if len(actual) == len(expected):
        for a, b in zip(actual, expected):
            if sum(x*y for x,y in zip(a['rotation_xyzw'],b['rotation_xyzw'])) < 0:
                a['rotation_xyzw'] = [-v for v in a['rotation_xyzw']]
    return patch.differences(actual, expected)


def validate(before, after, plan, created, material_paths, *, reload=False):
    old = {a['guid']: patch.normalize(a, commandlet_compat=reload) for a in before['actors']}
    actual = {a['guid']: patch.normalize(a, commandlet_compat=reload) for a in after['actors']}
    expected = dict(old)
    for row in plan:
        if row['primary']:
            expected[row['guid']] = patch.normalize(expected_primary(row, material_paths[row['primary']]), commandlet_compat=reload)
        else:
            del expected[row['guid']]
    assert set(actual) == set(expected) | set(created), 'Unexpected actor creation/deletion'
    for guid, row in expected.items():
        diff = patch.differences(row, actual[guid])
        assert not diff, (row['label'], diff[:5])
    for guid, spec in created.items():
        row = actual[guid]
        assert row['label'] == spec['label'] and row['class'] == BP+'.BP_GHS_InstanceGroup_C'
        assert row['folder'] == 'MPR/Operations' and row['tick_enabled'] is False and row['collision_enabled'] is False
        assert row['tags'] == ['MPRWarehouse', 'mpr-cad-scene-v1', 'InstanceCount='+str(len(spec['transforms']))]
        assert row['transform'] == dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],scale=[1.,1.,1.])
        assert len(row['components']) == 3 and {c['name'] for c in row['components']} == {'DefaultSceneRoot', COMPONENT, next(c['name'] for c in row['components'] if c['class'] == '/Script/Engine.BillboardComponent')}
        c = next(c for c in row['components'] if c['name'] == COMPONENT)
        assert c['mesh'] == spec['mesh'] and c['materials'] == material_paths[spec['mesh']]
        assert c['collision_profile'] == 'NoCollision' and c['num_custom_data_floats'] == 0
        assert c['visible'] and not c['hidden_in_game'] and c['cast_shadow']
        assert c['instance_count'] == len(spec['transforms'])
        diff = pose_differences(c['instance_transforms'], spec['transforms'])
        assert not diff, (row['label'],diff[:8])
    assert before['world_settings'] == after['world_settings']
    assert patch.normalized_coverage(before['world_actor_coverage'], commandlet_compat=reload) == patch.normalized_coverage(after['world_actor_coverage'], commandlet_compat=reload)


def add_feed_groups(u, manifest, created, material_paths, render_after):
    groups = manifest.get('additions', [])
    if not groups:
        return
    evidence = patch.read(ROOT/'SourceAssets/MPR/operations/cad_loose_feed_geometry.json')
    expected = {h for r in evidence['feeds'] if r.get('action','add')=='add' for h in r['source_handles']}
    actual = {h for r in groups for h in r['source_handles']}
    assert actual == expected and expected
    subsystem = u.get_editor_subsystem(u.EditorActorSubsystem)
    bp = u.EditorAssetLibrary.load_asset(BP)
    template = next(a for a in subsystem.get_all_level_actors()
                    if a.get_actor_label() == 'MPR_SM_MPR_Conveyor2m_-3_0')
    properties = render_properties(u, template)
    for group in groups:
        rows = group['new_instances']
        assert rows and len({r['mesh'] for r in rows}) == 1
        assert rows[0]['mesh'].startswith('SM_MPR_CADFeed')
        mesh_path = mesh_object(rows[0]['mesh'])
        mesh = u.EditorAssetLibrary.load_asset(mesh_path)
        material_paths[mesh_path] = [s.material_interface.get_path_name() for s in mesh.static_materials]
        trs = [pose(r) for r in rows]
        key = hashlib.sha256('|'.join(group['source_handles']).encode()).hexdigest()[:8]
        label = 'MPR_CADLooseFeed_'+group['source_handles'][0]+'_'+key
        assert not any(a.get_actor_label()==label for a in subsystem.get_all_level_actors())
        actor = subsystem.spawn_actor_from_class(bp.generated_class(), u.Vector())
        actor.set_actor_label(label)
        actor.set_folder_path('MPR/Operations')
        actor.set_actor_tick_enabled(False)
        actor.set_actor_enable_collision(False)
        fill(u, actor, mesh_path, trs, ['MPRWarehouse','mpr-cad-scene-v1','InstanceCount='+str(len(trs))], properties)
        actor.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent).set_collision_profile_name('NoCollision')
        guid = u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid'))
        created[guid] = dict(label=label, mesh=mesh_path, transforms=trs)
        render_after[guid] = properties


def apply(u):
    commandlet = '-run=pythonscript' in u.SystemLibrary.get_command_line().lower()
    if commandlet:
        assert '-mprconveyorapply' in u.SystemLibrary.get_command_line().lower()
        assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    assert not u.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    assert not u.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    manifest = patch.read(SRC/'repair_manifest.json')
    validate_source_scope(manifest)
    before = guard.capture(u, ROOT, MAP)
    guard.assert_clean(before)
    baseline = patch.read(OUT/'live_before.json.gz')
    assert before['map_file_sha256'] == baseline['map_file_sha256']
    assert not patch.differences([patch.normalize(a,commandlet_compat=commandlet) for a in baseline['actors']], [patch.normalize(a,commandlet_compat=commandlet) for a in before['actors']]), 'Scene edited during audit'
    plan = derive_plan(before, manifest)
    subsystem = u.get_editor_subsystem(u.EditorActorSubsystem)
    actors = {u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')): a for a in subsystem.get_all_level_actors()}
    render_before = {r['guid']:render_properties(u,actors[r['guid']]) for r in plan}
    files = list((ROOT/'Content/MPRWarehouse').rglob('*.uasset')) + list((ROOT/'Content/GHSZcoolSmartFactory').rglob('*.uasset'))
    existing = {p.as_posix(): sha(p) for p in files if '/ConveyorRepair20261106/' not in p.as_posix()}
    patch.write(OUT/'before.json.gz', before)
    shutil.copy2(MAP_FILE, OUT/'before_MPR.umap')
    imported = import_meshes(u, manifest)
    material_paths = {}
    for row in plan:
        for mesh_path in row['partitions']:
            mesh = u.EditorAssetLibrary.load_asset(mesh_path)
            material_paths[mesh_path] = [s.material_interface.get_path_name() for s in mesh.static_materials]
            if mesh_path == row['component']['mesh']:
                assert material_paths[mesh_path] == row['component']['materials'], 'Existing component material override requires review'
    created = {}
    render_after = {}
    with u.ScopedEditorTransaction('按原CAD修复MPR输送线与作业图例'):
        for row in plan:
            actor = actors[row['guid']]
            if not row['primary']:
                assert subsystem.destroy_actor(actor)
                continue
            primary = row['primary']
            props = render_before[row['guid']]
            fill(u, actor, primary, row['partitions'][primary], updated_tags(row['old']['tags'], len(row['partitions'][primary])), props)
            render_after[row['guid']] = props
            for mesh_path, trs in row['partitions'].items():
                if mesh_path == primary:
                    continue
                bp = u.EditorAssetLibrary.load_asset(BP)
                new = subsystem.spawn_actor_from_class(bp.generated_class(), u.Vector())
                label = 'MPR_CADRepair_'+mesh_path.split('.')[-1]+'_'+row['guid'][:8]
                new.set_actor_label(label)
                new.set_folder_path('MPR/Operations')
                new.set_actor_tick_enabled(False)
                new.set_actor_enable_collision(False)
                fill(u, new, mesh_path, trs, ['MPRWarehouse','mpr-cad-scene-v1','InstanceCount='+str(len(trs))], props)
                new.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent).set_collision_profile_name('NoCollision')
                guid = u.GuidLibrary.conv_guid_to_string(new.get_editor_property('actor_guid'))
                created[guid] = dict(label=label, mesh=mesh_path, transforms=trs)
                render_after[guid] = props
        add_feed_groups(u, manifest, created, material_paths, render_after)
    after = guard.capture(u, ROOT, MAP)
    patch.write(OUT/'candidate.json.gz', after)
    patch.write(OUT/'candidate_created.json', created)
    validate(before, after, plan, created, material_paths, reload=commandlet)
    assert sha(MAP_FILE) == before['map_file_sha256']
    assert all(sha(path) == digest for path, digest in existing.items()), 'Existing package changed'
    for record in imported.values():
        assert u.EditorAssetLibrary.save_loaded_asset(record['mesh'], only_if_is_dirty=False)
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    saved = guard.capture(u, ROOT, MAP)
    guard.assert_clean(saved)
    validate(before, saved, plan, created, material_paths, reload=commandlet)
    assert all(sha(path) == digest for path, digest in existing.items())
    patch.write(OUT/'after.json.gz', saved)
    patch.write(OUT/'scope_plan.json', dict(plan=plan, created=created, material_paths=material_paths, render_before=render_before, render_after=render_after))
    patch.write(OUT/'apply_validation.json', dict(success=True, map_before=before['map_file_sha256'], map_after=sha(MAP_FILE),
        actors_before=len(before['actors']), actors_after=len(saved['actors']), edited_groups=len(plan), new_groups=len(created),
        deleted_groups=sum(r['primary'] is None for r in plan), preserved_existing_assets=len(existing),
        counts=manifest['counts'], imported=[dict(path=k, **{f:v for f,v in r.items() if f!='mesh'}) for k,r in imported.items()]))


def complete_feed_additions(u):
    """Append independently confirmed loose CAD feeds to this task's checkpoint."""
    assert '-run=pythonscript' in u.SystemLibrary.get_command_line().lower()
    assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    current = guard.capture(u, ROOT, MAP)
    guard.assert_clean(current)
    prior = patch.read(OUT/'after.json.gz')
    assert current['map_file_sha256'] == prior['map_file_sha256']
    assert [patch.normalize(a,commandlet_compat=True) for a in current['actors']] == [patch.normalize(a,commandlet_compat=True) for a in prior['actors']]
    manifest = patch.read(SRC/'repair_manifest.json')
    validate_source_scope(manifest)
    scope = patch.read(OUT/'scope_plan.json')
    assert not any(v['label'].startswith('MPR_CADLooseFeed_') for v in scope['created'].values())
    hashes = {p.as_posix():sha(p) for p in list((ROOT/'Content/MPRWarehouse').rglob('*.uasset'))+list((ROOT/'Content/GHSZcoolSmartFactory').rglob('*.uasset'))}
    new_specs = [r for r in manifest['new_meshes'] if r['name'].startswith('SM_MPR_CADFeed')]
    assert new_specs and all(not u.EditorAssetLibrary.does_asset_exist(DEST+'/'+r['name']) for r in new_specs)
    imported = import_meshes(u,dict(new_meshes=new_specs))
    original = patch.read(OUT/'before.json.gz')
    final_plan = derive_plan(original,manifest)
    previous = {r['guid']:r for r in scope['plan']}
    for row in final_plan:
        if row['guid'] in previous:
            assert row == previous[row['guid']], 'Earlier repaired groups must remain unchanged'
    extra = [r for r in final_plan if r['guid'] not in previous]
    assert {r['guid'] for r in extra} == {'2FD2EF3E40A3BC8FDA09E7BF3C683FF1','8EB0DB114D3184ADCCF358A15EC7BA67'}
    actors = {u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    with u.ScopedEditorTransaction('补齐原CAD散线供包段'):
        for row in extra:
            assert row['primary'] and len(row['partitions'])==1
            actor = actors[row['guid']]
            props = render_properties(u,actor)
            scope['render_before'][row['guid']] = props
            scope['render_after'][row['guid']] = props
            mesh_path = row['primary']
            mesh = u.EditorAssetLibrary.load_asset(mesh_path)
            scope['material_paths'][mesh_path] = [s.material_interface.get_path_name() for s in mesh.static_materials]
            trs = row['partitions'][mesh_path]
            fill(u,actor,mesh_path,trs,updated_tags(row['old']['tags'],len(trs)),props)
        add_feed_groups(u,manifest,scope['created'],scope['material_paths'],scope['render_after'])
    scope['plan'] = final_plan
    candidate = guard.capture(u,ROOT,MAP)
    validate(original,candidate,scope['plan'],scope['created'],scope['material_paths'],reload=True)
    assert all(sha(p)==h for p,h in hashes.items())
    assert sha(MAP_FILE)==current['map_file_sha256']
    for record in imported.values():
        assert u.EditorAssetLibrary.save_loaded_asset(record['mesh'],only_if_is_dirty=False)
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    saved = guard.capture(u,ROOT,MAP)
    guard.assert_clean(saved)
    validate(original,saved,scope['plan'],scope['created'],scope['material_paths'],reload=True)
    assert all(sha(p)==h for p,h in hashes.items()), 'Existing package changed during save'
    patch.write(OUT/'feed_preserved_assets.json',hashes)
    patch.write(OUT/'scope_plan.json',scope)
    patch.write(OUT/'after.json.gz',saved)
    report = patch.read(OUT/'apply_validation.json')
    report.update(map_after=sha(MAP_FILE),actors_after=len(saved['actors']),edited_groups=len(final_plan),new_groups=len(scope['created']),counts=manifest['counts'],loose_feeds_added=True)
    report['imported'].extend(dict(path=k, **{f:v for f,v in r.items() if f!='mesh'}) for k,r in imported.items())
    patch.write(OUT/'apply_validation.json',report)


def verify_reload(u):
    assert '-run=pythonscript' in u.SystemLibrary.get_command_line().lower()
    assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    actual = guard.capture(u, ROOT, MAP)
    guard.assert_clean(actual)
    expected = patch.read(OUT/'after.json.gz')
    assert [patch.normalize(a, commandlet_compat=True) for a in actual['actors']] == [patch.normalize(a, commandlet_compat=True) for a in expected['actors']]
    scope = patch.read(OUT/'scope_plan.json')
    validate(patch.read(OUT/'before.json.gz'), actual, scope['plan'], scope['created'], scope['material_paths'], reload=True)
    actors = {u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')): a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    assert all(render_properties(u,actors[guid]) == properties for guid,properties in scope['render_after'].items())
    report = patch.read(OUT/'apply_validation.json')
    assert sha(MAP_FILE) == report['map_after']
    if report.get('loose_feeds_added'):
        hashes = patch.read(OUT/'feed_preserved_assets.json')
        assert all(sha(p)==h for p,h in hashes.items()), 'Existing package changed since feed repair'
    patch.write(OUT/'reload_validation.json', dict(success=True, actors=len(actual['actors']), map_sha256=sha(MAP_FILE),
        unrelated_scene_preserved=True, corrected_hism_instances_reloaded=True))


if __name__ == '__main__':
    import unreal as u
    cli = u.SystemLibrary.get_command_line().lower()
    if '-mprconveyoradditions' in cli:
        complete_feed_additions(u)
    elif '-run=pythonscript' in cli and '-mprconveyorapply' not in cli:
        verify_reload(u)
    else:
        apply(u)
