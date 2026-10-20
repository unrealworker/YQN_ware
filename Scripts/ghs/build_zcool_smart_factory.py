"""Clone the saved CAD warehouse into a private porcelain/blue presentation scene.

Run in an owned full UE editor process with -ExecutePythonScript=<this file>
-ZcoolQuit. Only the new map and /Game/GHSZcoolSmartFactory assets are saved.
The source map is always inventoried first; meshes and source Blueprints are shared
unchanged. A rerun requires this script's ownership report and original hashes.
"""
import hashlib
import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

ROOT = Path(r'D:\UEPro\Test')
SOURCE_MAP = '/Game/Maps/GHS_CAD_NormalWarehouse'
MAP = SOURCE_MAP + '_ZcoolSmartFactory'
DEST = '/Game/GHSZcoolSmartFactory'
REPORT = ROOT / 'Saved/GHS_ZcoolBuild.json'
BASELINE = ROOT / 'Saved/GHS_ZcoolSceneSourceHashes.json'
OWNER = 'ghs-zcool-smart-factory-scene-v1'
LIB = unreal.EditorAssetLibrary
ML = unreal.MaterialEditingLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
A = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
L = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
E = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

# Colors are linear values. All modeled surfaces remain lit and deliberately matte.
STYLE = {
    'Porcelain': ([.83, .85, .88], .77, .0),
    'WallTop': ([.92, .935, .95], .79, .0),
    'PaleGray': ([.63, .68, .73], .76, .0),
    'Cargo': ([.76, .80, .85], .86, .0),
    'CargoSeam': ([.51, .57, .64], .88, .0),
    'Cobalt': ([.018, .075, .51], .61, .04),
    'SoftBlue': ([.24, .39, .68], .72, .0),
    'Charcoal': ([.055, .075, .11], .73, .02),
    'Rubber': ([.025, .035, .055], .93, .0),
    'Metal': ([.43, .49, .57], .56, .20),
    'Glass': ([.055, .14, .22], .25, .12),
    'Cyan': ([.025, .53, .84], .56, .0),
    'SafetyRed': ([.62, .045, .045], .7, .0),
    'SafetyAmber': ([.88, .43, .025], .74, .0),
    'Skin': ([.54, .36, .26], .9, .0),
    'FloorGrid': ([.48, .53, .59], .89, .0),
    'SurroundGrid': ([.65, .69, .74], .91, .0),
    'Sky': ([.70, .75, .82], 1.0, .0),
    'Invisible': ([.7, .75, .8], 1.0, .0),
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def owned_file(relative):
    return (relative.startswith('Content/GHSZcoolSmartFactory/')
            or relative == 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap')


def content_hashes():
    return {p.relative_to(ROOT).as_posix(): sha(p)
            for p in (ROOT / 'Content').rglob('*')
            if p.is_file() and not owned_file(p.relative_to(ROOT).as_posix())}


def path_of(obj):
    return obj.get_path_name() if obj else None


def xyz(value):
    return [round(float(v), 5) for v in (value.x, value.y, value.z)]


def transform(value):
    q = value.rotation
    return dict(position=xyz(value.translation), scale=xyz(value.scale3d),
                rotation=[round(float(v), 6) for v in (q.x, q.y, q.z, q.w)])


def labels():
    rows = list(A.get_all_level_actors())
    result = {a.get_actor_label(): a for a in rows}
    assert len(result) == len(rows), 'Duplicate actor labels prevent reliable parity checks'
    return result


def inventory():
    result = {}
    for label, actor in sorted(labels().items()):
        parent = actor.get_attach_parent_actor()
        row = dict(actor_class=actor.get_class().get_path_name(),
                   transform=transform(actor.get_actor_transform()),
                   tags=[str(t) for t in actor.tags], folder=str(actor.get_folder_path()),
                   attached_to=parent.get_actor_label() if parent else None,
                   hidden=bool(actor.get_editor_property('hidden')), components={})
        for c in sorted(actor.get_components_by_class(unreal.ActorComponent), key=lambda x: x.get_name()):
            item = dict(component_class=c.get_class().get_path_name(),
                        tags=[str(t) for t in c.component_tags])
            if isinstance(c, unreal.SceneComponent):
                item.update(transform=transform(c.get_world_transform()),
                            relative_transform=transform(c.get_relative_transform()),
                            attached_to=c.get_attach_parent().get_name() if c.get_attach_parent() else None,
                            visible=bool(c.get_editor_property('visible')),
                            hidden_in_game=bool(c.get_editor_property('hidden_in_game')),
                            mobility=str(c.get_editor_property('mobility')))
            if isinstance(c, unreal.StaticMeshComponent):
                item.update(mesh=path_of(c.static_mesh),
                            materials=[path_of(c.get_material(i)) for i in range(c.get_num_materials())],
                            cast_shadow=bool(c.get_editor_property('cast_shadow')),
                            receives_decals=bool(c.get_editor_property('receives_decals')),
                            collision_profile=str(c.get_collision_profile_name()))
                if isinstance(c, unreal.InstancedStaticMeshComponent):
                    item['instances'] = [transform(c.get_instance_transform(i, world_space=True))
                                         for i in range(c.get_instance_count())]
            if isinstance(c, unreal.DecalComponent):
                item.update(decal_material=path_of(c.get_decal_material()),
                            decal_size=xyz(c.get_editor_property('decal_size')),
                            fade_screen_size=float(c.get_editor_property('fade_screen_size')),
                            sort_order=int(c.get_editor_property('sort_order')))
            if isinstance(c, unreal.TextRenderComponent):
                item['text'] = str(c.get_editor_property('text'))
                item['world_size'] = float(c.get_editor_property('world_size'))
            # These serialized components are retained if present. Runtime discovery
            # also supports actors which have tags but no serialized data component.
            if 'GHSStackerDataComponent' in item['component_class']:
                item['stacker_id'] = str(c.get_editor_property('stacker_id'))
            row['components'][c.get_name()] = item
        result[label] = row
    return result


def counts(state):
    flat = [c for a in state.values() for c in a['components'].values()]
    return dict(actors=len(state),
                dock_trucks=sum('IndependentDockTruck' in a['tags'] for a in state.values()),
                stackers=sum('NormalWarehouseFloorStacker' in a['tags'] for a in state.values()),
                manual_forklifts=sum('NormalWarehouseMannedForklift' in a['tags'] for a in state.values()),
                agvs=sum(bool(re.fullmatch(r'GHS_AGV_[0-9]+', name)) for name in state),
                chargers=sum(bool(re.fullmatch(r'GHS_CH_[0-9]+', name)) for name in state),
                decals=sum('decal_material' in c for c in flat),
                hism_groups=sum('HierarchicalInstancedStaticMeshComponent' in c['component_class'] for c in flat),
                instances=sum(len(c.get('instances', [])) for c in flat))


def check_equal(before, after, location=''):
    if isinstance(before, (float, int)) and not isinstance(before, bool):
        assert abs(before - after) <= .0001, (location, before, after)
    elif isinstance(before, dict):
        assert set(before) == set(after), (location, 'keys changed')
        for key in before:
            check_equal(before[key], after[key], location + '/' + key)
    elif isinstance(before, list):
        assert len(before) == len(after), (location, 'length changed')
        for i, (a, b) in enumerate(zip(before, after)):
            check_equal(a, b, location + '/' + str(i))
    else:
        assert before == after, (location, before, after)


def assert_parity(before, after, identity_changes):
    expected = json.loads(json.dumps(before))
    actual = json.loads(json.dumps(after))
    assert set(expected) == set(actual), 'Actor membership changed'
    changed_ids = {r['actor']: r for r in identity_changes}
    for label in expected:
        if label in changed_ids:
            expected[label]['tags'] = changed_ids[label]['after_tags']
        for name, old in expected[label]['components'].items():
            new = actual[label]['components'][name]
            for presentation_key in ('materials', 'decal_material'):
                old.pop(presentation_key, None)
                new.pop(presentation_key, None)
            if label in changed_ids and 'stacker_id' in old:
                old['stacker_id'] = changed_ids[label]['after_id']
        # Only the placed camera may move for the new overview. Equipment,
        # all mesh instances, lights, and saved reference cameras keep transforms.
        if label == 'GHS_WarehouseCamera':
            expected[label]['transform'] = actual[label]['transform']
            for name in expected[label]['components']:
                for key in ('transform', 'relative_transform'):
                    if key in expected[label]['components'][name]:
                        expected[label]['components'][name][key] = actual[label]['components'][name][key]
    check_equal(expected, actual)


def save(asset):
    assert path_of(asset).startswith(DEST + '/'), path_of(asset)
    assert LIB.save_loaded_asset(asset, only_if_is_dirty=False), path_of(asset)


def node(mat, cls, **props):
    value = ML.create_material_expression(mat, cls)
    for key, item in props.items():
        value.set_editor_property(key, item)
    return value


def scalar(mat, name, value):
    return node(mat, unreal.MaterialExpressionScalarParameter,
                parameter_name=name, default_value=float(value))


def vector(mat, name, values):
    return node(mat, unreal.MaterialExpressionVectorParameter,
                parameter_name=name, default_value=unreal.LinearColor(*values, 1))


def connect(source, target, pin):
    assert ML.connect_material_expressions(source, '', target, pin), pin


def plug(source, prop):
    assert ML.connect_material_property(source, '', prop), str(prop)


def make_material(name):
    package = DEST + '/Materials/M_Zcool_' + name
    mat = LIB.load_asset(package) if LIB.does_asset_exist(package) else TOOLS.create_asset(
        'M_Zcool_' + name, DEST + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    assert isinstance(mat, unreal.Material), package
    # UE5.4 removes expressions while iterating its expression array. On an
    # existing asset one call can leave nodes behind, so check actual progress.
    while ML.get_num_material_expressions(mat):
        count = ML.get_num_material_expressions(mat)
        ML.delete_all_material_expressions(mat)
        assert ML.get_num_material_expressions(mat) < count, package
    mat.set_editor_property('used_with_instanced_static_meshes', True)
    mat.set_editor_property('two_sided', name in ('Sky', 'Invisible'))
    mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT
                            if name == 'Sky' else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED
                            if name == 'Invisible' else unreal.BlendMode.BLEND_OPAQUE)
    color, roughness, metallic = STYLE[name]
    base = vector(mat, 'SurfaceTint', color)
    surface = base
    if name.endswith('Grid'):
        # Derivative-filtered world-space grid keeps fine lines stable in overview
        # and aligned across independent floor/surround meshes and HISM instances.
        code = '''float2 uv = P.xy / Period;
float2 fw = max(fwidth(uv), float2(0.00001, 0.00001));
float2 d = abs(frac(uv + 0.5) - 0.5);
float2 lines = 1.0 - smoothstep(Width/Period, Width/Period + fw, d);
float visibility = 1.0-smoothstep(0.12,0.5,max(fw.x,fw.y));
float minor = max(lines.x, lines.y)*visibility;
float2 majorUV = uv/5.0;
float2 majorFW = max(fwidth(majorUV),float2(0.00001,0.00001));
float2 majorD = abs(frac(majorUV+0.5)-0.5);
float2 majorL = 1.0-smoothstep(Width/Period/5.0,Width/Period/5.0+majorFW,majorD);
float mask = max(minor*0.65,max(majorL.x,majorL.y)*0.9);
return lerp(Base,Line,mask*Strength);'''
        surface = node(mat, unreal.MaterialExpressionCustom, code=code,
                       output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        inputs = []
        for key in ('P', 'Base', 'Line', 'Period', 'Width', 'Strength'):
            entry = unreal.CustomInput()
            entry.set_editor_property('input_name', key)
            inputs.append(entry)
        surface.set_editor_property('inputs', inputs)
        connect(node(mat, unreal.MaterialExpressionWorldPosition), surface, 'P')
        connect(base, surface, 'Base')
        connect(vector(mat, 'GridTint', [.31, .36, .43]), surface, 'Line')
        for key, value in [('Period', 250.0), ('Width', 1.4),
                           ('Strength', .25 if name == 'FloorGrid' else .40)]:
            connect(scalar(mat, 'Grid' + key, value), surface, key)
    plug(surface, unreal.MaterialProperty.MP_EMISSIVE_COLOR if name == 'Sky'
         else unreal.MaterialProperty.MP_BASE_COLOR)
    plug(scalar(mat, 'Roughness', roughness), unreal.MaterialProperty.MP_ROUGHNESS)
    plug(scalar(mat, 'Metallic', metallic), unreal.MaterialProperty.MP_METALLIC)
    plug(scalar(mat, 'Specular', .25), unreal.MaterialProperty.MP_SPECULAR)
    if name == 'Invisible':
        plug(scalar(mat, 'Opacity', 0), unreal.MaterialProperty.MP_OPACITY_MASK)
    ML.layout_material_expressions(mat)
    ML.recompile_material(mat)
    save(mat)
    return mat


def semantic_material(label, original, index):
    name = (original or '').rsplit('.', 1)[-1].lower()
    if label in ('GHN_StudioGround', 'GHS_DarkSurround'):
        return 'SurroundGrid'
    if label == 'GHS_CAD_ExactFootprint':
        return 'FloorGrid'
    if label == 'GHN_StudioSky':
        return 'Sky'
    if 'ghostdisabled' in name:
        return 'Invisible'
    if label in ('GHS_CAD_WallSections', 'GHS_ChargingSupportCaps', 'GHS_ChargingSupportEnds'):
        return 'WallTop'
    if label in ('GHS_CAD_WallEdges', 'GHS_ColumnEdgeOutlines'):
        return 'PaleGray'
    if label.startswith('GHS_V2_Rack_') and index in (1,):
        return 'Cobalt'
    if 'cardboardseam' in name or 'bininterior' in name:
        return 'CargoSeam'
    if 'cardboard' in name or 'binrim' in name:
        return 'Cargo'
    if 'rubber' in name or 'seat' in name:
        return 'Rubber'
    if 'glass' in name or 'screen' in name:
        return 'Glass'
    if 'emergencyred' in name or 'taillight' in name or name.endswith('_red'):
        return 'SafetyRed' if 'charger' not in name else 'Cobalt'
    if 'safety' in name or 'warning' in name or 'amber' in name:
        return 'SafetyAmber'
    if 'skin' in name:
        return 'Skin'
    if 'led' in name or 'headlight' in name:
        return 'Cyan'
    if any(word in name for word in ('charcoal', 'chassis', 'fastener', '_dark', '_navy', '_frame')):
        return 'Charcoal' if 'rack' not in name else 'Porcelain'
    if any(word in name for word in ('blue', 'accent', 'orange', 'reflective')):
        return 'Cobalt'
    if any(word in name for word in ('metal', 'steel')):
        return 'Metal'
    if any(word in name for word in ('trim', 'seam', 'doorline', 'sidegray')):
        return 'PaleGray'
    return 'Porcelain'


def connected_nodes(material):
    pending = [ML.get_material_property_input_node(material, prop) for prop in
               (unreal.MaterialProperty.MP_BASE_COLOR, unreal.MaterialProperty.MP_EMISSIVE_COLOR,
                unreal.MaterialProperty.MP_OPACITY)]
    seen, result = set(), []
    while pending:
        n = pending.pop()
        if n is None or path_of(n) in seen:
            continue
        seen.add(path_of(n))
        result.append(n)
        pending.extend(x for x in ML.get_inputs_for_material_expression(material, n) if x)
    return result


def graph_signature(material):
    nodes = connected_nodes(material)
    return dict(time_nodes=sum(isinstance(n, unreal.MaterialExpressionTime) for n in nodes),
                custom_code=sorted(n.get_editor_property('code') for n in nodes
                                   if isinstance(n, unreal.MaterialExpressionCustom)))


def make_fx(original_path, cache, report):
    if original_path in cache:
        return cache[original_path]
    original = LIB.load_asset(original_path)
    assert isinstance(original, (unreal.Material, unreal.MaterialInstanceConstant)), original_path
    suffix = hashlib.sha256(original_path.encode()).hexdigest()[:8]
    name = 'Zcool_' + original.get_name() + '_' + suffix
    dest = DEST + '/FX/' + name
    asset = LIB.load_asset(dest) if LIB.does_asset_exist(dest) else LIB.duplicate_asset(original_path, dest)
    assert asset
    cache[original_path] = asset
    if isinstance(original, unreal.MaterialInstanceConstant):
        parent = make_fx(path_of(original.get_editor_property('parent')), cache, report)
        ML.set_material_instance_parent(asset, parent)
        tint = [.015, .20, .90] if 'Radar' in original.get_name() else [.015, .58, .92]
        ML.set_material_instance_vector_parameter_value(asset, 'Tint', unreal.LinearColor(*tint, 1))
        ML.set_material_instance_scalar_parameter_value(asset, 'OpacityScale', 1.65)
        ML.set_material_instance_scalar_parameter_value(asset, 'EmissionScale', .12)
        ML.update_material_instance(asset)
        for param in ('Speed', 'Phase'):
            before = float(ML.get_material_instance_scalar_parameter_value(original, param))
            after = float(ML.get_material_instance_scalar_parameter_value(asset, param))
            assert abs(before - after) < 1e-6, (original_path, param)
        report['fx_assets'][original_path] = dict(path=path_of(asset), tint=tint,
            speed=ML.get_material_instance_scalar_parameter_value(asset, 'Speed'),
            phase=ML.get_material_instance_scalar_parameter_value(asset, 'Phase'))
    else:
        assert original.get_editor_property('material_domain') == unreal.MaterialDomain.MD_DEFERRED_DECAL
        signature = graph_signature(original)
        assert signature['time_nodes'] > 0 and signature['custom_code'], original_path
        for n in connected_nodes(asset):
            if (isinstance(n, unreal.MaterialExpressionVectorParameter)
                    and str(n.get_editor_property('parameter_name')) == 'Tint'):
                n.set_editor_property('default_value', unreal.LinearColor(.015, .4, .95, 1))
        ML.recompile_material(asset)
        assert graph_signature(asset) == signature, 'FX animation graph changed'
        report['fx_assets'][original_path] = dict(path=path_of(asset), time_nodes=signature['time_nodes'],
            shader_sha256=hashlib.sha256('\n'.join(signature['custom_code']).encode()).hexdigest())
    save(asset)
    return asset


def unique_stackers(by):
    groups = {}
    for label, actor in by.items():
        if 'NormalWarehouseFloorStacker' not in [str(t) for t in actor.tags]:
            continue
        tags = [str(t) for t in actor.tags]
        identity = [t for t in tags if t.startswith('TwinId=')]
        assert len(identity) == 1, (label, identity)
        match = re.fullmatch(r'TwinId=GHN_FloorStacker_([0-9]+)', identity[0])
        assert match and int(match[1]) > 0, (label, identity)
        groups.setdefault(int(match[1]), []).append(actor)
    used = set(groups)
    changes = []
    for number, group in sorted(groups.items()):
        # Keep the actor whose label matches its tag, then the lexical first copy.
        group.sort(key=lambda a: (a.get_actor_label() != 'GHN_FloorStacker_%02d' % number,
                                  a.get_actor_label()))
        for actor in group[1:]:
            candidate = 1
            while candidate in used:
                candidate += 1
            used.add(candidate)
            before = [str(t) for t in actor.tags]
            after = ['TwinId=GHN_FloorStacker_%02d' % candidate if t.startswith('TwinId=') else t for t in before]
            actor.tags = [unreal.Name(t) for t in after]
            data = actor.get_component_by_class(unreal.GHSStackerDataComponent)
            if data:
                assert data.initialize_from_actor_tags(), actor.get_actor_label()
            changes.append(dict(actor=actor.get_actor_label(), before_tags=before, after_tags=after,
                                before_id='STACKER-%02d' % number, after_id='STACKER-%02d' % candidate))
    return changes


def apply_presentation(by, report):
    lighting = dict(directional_intensity=3.1, skylight_intensity=.72,
                    directional_source_angle=5.0, ambient_occlusion_intensity=.85,
                    ambient_occlusion_radius=95.0, exposure_ev100=0.0)
    for actor in by.values():
        light = actor.get_component_by_class(unreal.DirectionalLightComponent)
        if light:
            light.set_intensity(lighting['directional_intensity'])
            light.set_light_color(unreal.LinearColor(1.0, .985, .965, 1))
            light.set_editor_property('light_source_angle', lighting['directional_source_angle'])
            light.set_editor_property('cast_shadows', True)
            light.set_editor_property('contact_shadow_length', .04)
        sky = actor.get_component_by_class(unreal.SkyLightComponent)
        if sky:
            sky.set_intensity(lighting['skylight_intensity'])
            sky.set_light_color(unreal.LinearColor(.94, .97, 1.0, 1))
        text = actor.get_component_by_class(unreal.TextRenderComponent)
        if text:
            text.set_text_render_color(unreal.Color(r=47, g=68, b=103, a=255))
        if isinstance(actor, unreal.PostProcessVolume):
            settings = actor.get_editor_property('settings')
            values = dict(vignette_intensity=0., bloom_intensity=.035,
                          ambient_occlusion_intensity=lighting['ambient_occlusion_intensity'],
                          ambient_occlusion_radius=lighting['ambient_occlusion_radius'],
                          ambient_occlusion_quality=80., auto_exposure_min_brightness=0.,
                          auto_exposure_max_brightness=0., auto_exposure_bias=0.)
            for name, value in values.items():
                settings.set_editor_property('override_' + name, True)
                settings.set_editor_property(name, value)
            actor.set_editor_property('settings', settings)
    camera = by.get('GHS_WarehouseCamera')
    if camera:
        camera.set_editor_property('overview_pitch', -43.0)
        camera.set_editor_property('overview_yaw', -110.0)
        camera.set_editor_property('overview_distance', 55000.0)
        camera.reset_overview(True)
        view = camera.get_component_by_class(unreal.CameraComponent)
        if view:
            E.set_level_viewport_camera_info(view.get_world_location(), view.get_world_rotation())
        report['camera_overview'] = dict(pitch=-43., yaw=-110., distance=55000.)
    report['lighting'] = lighting


def main():
    report = dict(owner=OWNER, success=False, source_map=SOURCE_MAP, map=MAP,
                  created_utc=datetime.now(timezone.utc).isoformat(), material_assets={},
                  component_overrides=[], fx_assets={}, identity_changes=[], added_actors=[])
    source_hashes = None
    try:
        if LIB.does_asset_exist(MAP):
            assert REPORT.is_file(), 'Existing destination map has no ownership report'
            previous = json.loads(REPORT.read_text(encoding='utf-8'))
            assert previous.get('owner') == OWNER and previous.get('map') == MAP, 'Destination is not owned by this script'
            assert BASELINE.is_file(), 'Owned map has no source hash baseline'
        source_hashes = content_hashes()
        if BASELINE.exists():
            assert json.loads(BASELINE.read_text(encoding='utf-8')) == source_hashes, 'Original Content differs from saved baseline'
        else:
            write(BASELINE, source_hashes)
        write(REPORT, report)
        assert L.load_level(SOURCE_MAP), SOURCE_MAP
        before = inventory()
        report['before'] = before
        report['source_counts'] = counts(before)
        assert report['source_counts']['actors'] == 248, report['source_counts']
        write(REPORT, report)
        if LIB.does_asset_exist(MAP):
            assert L.load_level(MAP), MAP
        else:
            assert L.new_level_from_template(MAP, SOURCE_MAP), MAP
        assert E.get_editor_world().get_path_name().split('.')[0] == MAP
        by = labels()
        assert set(by) == set(before), 'Cloned map membership differs'
        LIB.make_directory(DEST + '/Materials')
        LIB.make_directory(DEST + '/FX')
        mats = {name: make_material(name) for name in STYLE}
        report['material_assets'] = {name: path_of(mat) for name, mat in mats.items()}
        fx_cache = {}
        for label, actor in by.items():
            for c in actor.get_components_by_class(unreal.StaticMeshComponent):
                if not c.static_mesh or path_of(c.static_mesh).startswith('/Engine/EditorMeshes/'):
                    continue
                original = before[label]['components'][c.get_name()]
                assert path_of(c.static_mesh) == original['mesh'], label
                chosen = []
                assert c.get_num_materials() == len(original['materials']), label
                for index, old in enumerate(original['materials']):
                    name = semantic_material(label, old, index)
                    c.set_material(index, mats[name])
                    chosen.append(name)
                report['component_overrides'].append(dict(actor=label, component=c.get_name(), materials=chosen))
            for c in actor.get_components_by_class(unreal.DecalComponent):
                original = before[label]['components'][c.get_name()]['decal_material']
                c.set_decal_material(make_fx(original, fx_cache, report))
        # On a rerun the target already contains the same repair; derive the
        # permitted differences from the immutable source inventory afterward.
        unique_stackers(by)
        for label, actor in by.items():
            after_tags = [str(t) for t in actor.tags]
            if after_tags != before[label]['tags']:
                assert 'NormalWarehouseFloorStacker' in before[label]['tags'], label
                assert [t for t in after_tags if not t.startswith('TwinId=')] == [
                    t for t in before[label]['tags'] if not t.startswith('TwinId=')], (
                        label, 'Only the duplicate stacker TwinId may change')
                ids = [t for t in after_tags if t.startswith('TwinId=GHN_FloorStacker_')]
                assert len(ids) == 1, label
                report['identity_changes'].append(dict(actor=label, before_tags=before[label]['tags'],
                    after_tags=after_tags, after_id='STACKER-%02d' % int(ids[0].rsplit('_', 1)[-1])))
        apply_presentation(by, report)
        report['after_before_save'] = inventory()
        assert_parity(before, report['after_before_save'], report['identity_changes'])
        A.set_selected_level_actors([])
        assert L.save_current_level(), MAP
        # Reload from disk, not only in-memory state, before asserting completion.
        assert L.load_level(SOURCE_MAP)
        assert L.load_level(MAP)
        after = inventory()
        assert_parity(before, after, report['identity_changes'])
        # The shared camera Blueprint recalculates editor-only frustum/spring
        # arm transforms on construction. Its serialized overview settings are
        # checked explicitly; other actors and every material override must reload.
        reload_expected = report['after_before_save']
        if 'GHS_WarehouseCamera' in after:
            camera_before = reload_expected['GHS_WarehouseCamera']
            camera_after = after['GHS_WarehouseCamera']
            camera_before['transform'] = camera_after['transform']
            for name, component in camera_before['components'].items():
                for key in ('transform', 'relative_transform'):
                    if key in component:
                        component[key] = camera_after['components'][name][key]
            camera = labels()['GHS_WarehouseCamera']
            for key, expected in [('overview_pitch', -43.), ('overview_yaw', -110.),
                                  ('overview_distance', 55000.)]:
                assert abs(float(camera.get_editor_property(key)) - expected) < .001, key
        check_equal(reload_expected, after, 'saved_reload')
        report['after'] = after
        report.pop('after_before_save')
        report['target_counts'] = counts(after)
        assert report['target_counts'] == report['source_counts'], 'Object or instance count differs'
        final_hashes = content_hashes()
        changed = sorted(k for k in set(source_hashes) | set(final_hashes)
                         if source_hashes.get(k) != final_hashes.get(k))
        report['source_hash_verification'] = dict(files=len(source_hashes), changed=changed,
            before_manifest=str(BASELINE), source_map_sha256=sha(ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap'))
        assert not changed, 'Original Content was modified: ' + repr(changed)
        report.update(success=True, geometry_transform_attachment_parity=True,
                      source_content_unchanged=True, saved_and_reloaded=True,
                      map_sha256=sha(ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'))
        unreal.log('GHS_ZCOOL_SCENE_SAVED_AND_RELOADED ' + json.dumps(report['target_counts']))
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
        raise
    finally:
        if source_hashes is not None:
            current = content_hashes()
            report['source_content_changed_on_exit'] = sorted(k for k in set(source_hashes) | set(current)
                if source_hashes.get(k) != current.get(k))
        write(REPORT, report)
        if '-zcoolquit' in unreal.SystemLibrary.get_command_line().lower():
            unreal.SystemLibrary.quit_editor()


if __name__ == '__main__':
    main()
