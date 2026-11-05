"""Apply round-one style in place; preserve original shared assets and geometry."""
import hashlib
import json
import sys
from pathlib import Path
import unreal as u

ROOT = Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
sys.path.insert(0, str(ROOT/'Tools/MPRWarehouse'))
from mpr_site_completion_style import MAP, DEST, FOV, VIEWS, COLORS, linear

OUT = ROOT/'Saved/MPR/site_completion_20261105'
OUT.mkdir(parents=True, exist_ok=True)
L = u.get_editor_subsystem(u.LevelEditorSubsystem)
A = u.get_editor_subsystem(u.EditorActorSubsystem)
LIB = u.EditorAssetLibrary
MAT = u.MaterialEditingLibrary
TOOLS = u.AssetToolsHelpers.get_asset_tools()
world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
assert world.get_path_name().split('.')[0] == MAP, 'Open the existing MPR map first; never reload a live editor.'
assert not L.is_in_play_in_editor(), 'Stop PIE before editing the current map.'
assert not u.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Save/review existing manual map edits before applying the visual round.'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

existing = {str(p.relative_to(ROOT)): digest(p) for p in (ROOT/'Content/MPRWarehouse').rglob('*.uasset')
            if 'SiteComplete' not in p.parts}
all_actors = A.get_all_level_actors()
fixtures = {a.get_name(): (a.get_actor_transform(), [c.static_mesh for c in a.get_components_by_class(u.StaticMeshComponent)])
            for a in all_actors if not isinstance(a, (u.CameraActor, u.DirectionalLight))}
created = {}
changes = []
for actor in all_actors:
    for component in actor.get_components_by_class(u.StaticMeshComponent):
        for index, material in enumerate(component.get_materials()):
            if material is None:
                continue
            role = material.get_name().removeprefix('MI_SC_').removeprefix('MI_')
            if role not in COLORS:
                continue
            source = material.get_path_name().split('.')[0]
            assert source.startswith(('/Game/MPRWarehouse/RebuildB50B57/Materials/', DEST+'/Materials/')), source
            if role not in created:
                name = 'MI_SC_'+role
                destination = DEST+'/Materials/'+name
                clone = LIB.load_asset(destination) if LIB.does_asset_exist(destination) else TOOLS.duplicate_asset(name, DEST+'/Materials', material)
                assert isinstance(clone, u.MaterialInstanceConstant), destination
                tint = linear(COLORS[role])
                MAT.set_material_instance_vector_parameter_value(clone, 'Tint', u.LinearColor(*tint, 1))
                actual = MAT.get_material_instance_vector_parameter_value(clone, 'Tint')
                assert max(abs(a-b) for a,b in zip((actual.r,actual.g,actual.b),tint)) < 1e-5, role
                if role in ('MPR3_Grass','MPRR_CampusGreen') or 'Leaf' in role:
                    MAT.set_material_instance_scalar_parameter_value(clone, 'Roughness', .9)
                    MAT.set_material_instance_scalar_parameter_value(clone, 'NormalStrength', .01)
                if role in ('MPR4_TerminalAsphalt', 'MPR4_TerminalCurb', 'MPR3_Asphalt'):
                    MAT.set_material_instance_vector_parameter_value(clone, 'GroundTint', u.LinearColor(*linear(COLORS['MPR3_Grass']), 1))
                assert LIB.save_loaded_asset(clone, only_if_is_dirty=False)
                created[role] = clone
            component.set_material(index, created[role])
            changes.append(dict(actor=actor.get_actor_label(), component=component.get_name(), slot=index,
                                source=source, destination=created[role].get_path_name().split('.')[0]))

by_label = {a.get_actor_label(): a for a in all_actors}
sun = by_label['MPR4_KeyLight']
sun.set_actor_rotation(u.Rotator(pitch=-43, yaw=130), False)
light = sun.get_component_by_class(u.DirectionalLightComponent)
for key, value in dict(intensity=5.0, light_source_angle=4.0, use_temperature=False,
                       indirect_lighting_intensity=1.0, cast_shadows=True).items():
    light.set_editor_property(key, value)
sky = by_label['MPR4_Ambient'].get_component_by_class(u.SkyLightComponent)
sky.set_editor_property('intensity', .65)
post = by_label['MPR4_ReferenceStyle']
settings = post.get_editor_property('settings')
for key, value in dict(override_auto_exposure_min_brightness=True, override_auto_exposure_max_brightness=True,
                       auto_exposure_min_brightness=-.1, auto_exposure_max_brightness=-.1,
                       override_auto_exposure_bias=True, auto_exposure_bias=0.0,
                       override_bloom_intensity=True, bloom_intensity=0.0).items():
    settings.set_editor_property(key, value)
post.set_editor_property('settings', settings)
camera = by_label['MPR_ReviewCamera']
_, target, distance, pitch, yaw, _ = VIEWS[0]
rotation = u.Rotator(pitch=pitch, yaw=yaw)
point = u.Vector(target[0]*100, -target[1]*100, target[2]*100)
camera.set_actor_location_and_rotation(point-u.MathLibrary.get_forward_vector(rotation)*distance, rotation, False, True)
cc = camera.get_component_by_class(u.CameraComponent)
cc.set_editor_property('field_of_view', FOV)
cc.set_editor_property('constrain_aspect_ratio', False)
cc.set_editor_property('override_aspect_ratio_axis_constraint', True)
cc.set_editor_property('aspect_ratio_axis_constraint', u.AspectRatioAxisConstraint.ASPECT_RATIO_MAINTAIN_XFOV)

for actor in all_actors:
    if actor.get_name() not in fixtures:
        continue
    transform, meshes = fixtures[actor.get_name()]
    assert actor.get_actor_transform() == transform, actor.get_actor_label()
    assert [c.static_mesh for c in actor.get_components_by_class(u.StaticMeshComponent)] == meshes
assert L.save_current_level()
changed = [name for name, value in existing.items() if digest(ROOT/name) != value]
assert not changed, changed
report = dict(success=True, map=MAP, map_sha256=digest(ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'),
              original_assets_unchanged=len(existing), geometry_actor_count=len(all_actors),
              material_slot_changes=changes, colors_srgb=COLORS, fov=FOV, views=VIEWS,
              lighting=dict(directional_lux=5., sun_pitch=-43, sun_yaw=130, source_angle=4.0,
                            sky_intensity=.65, fixed_ev100=-.1, bloom=0.))
(OUT/'round1_apply.json').write_text(json.dumps(report, indent=2), encoding='utf8')
u.log('MPR_SITE_ROUND1_APPLIED '+str(OUT/'round1_apply.json'))
