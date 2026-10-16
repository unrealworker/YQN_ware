"""Isolated HISM persistence probe; pass -GHSProbeMode=verify for read-only reload."""
import json
import math
import sys
import traceback
from pathlib import Path

import unreal

ROOT = Path(r'D:\UEPro\Test')
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
REPORT = ROOT / 'Saved/GHS_InstancingProbe.json'
TEST_BP = '/Game/GHSDigitalTwin/Tests/BP_GHS_InstanceGroup_Probe_20261015'
TEST_MAP = '/Game/GHSDigitalTwin/Tests/InstancingProbe'
LABEL = 'GHS_HISM_PersistenceProbe'
MODE = 'verify' if '-GHSProbeMode=verify' in unreal.SystemLibrary.get_command_line() else 'create'
SPECS = [
    dict(location=[0, 0, 50], yaw=0, scale=[1, 1, 1]),
    dict(location=[350, -225, 75], yaw=90, scale=[1.5, .75, 2]),
    dict(location=[-1250, 650, 125], yaw=-37, scale=[.5, 2.25, 1.1]),
]
report = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.is_file() else {}
report.update(success=False, current_mode=MODE, map=TEST_MAP, blueprint=TEST_BP)


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def compare(values, expected, tolerance=.01):
    assert all(math.isfinite(a) and abs(a - b) < tolerance for a, b in zip(values, expected)), (values, expected)


def verify_actor(actor):
    components = actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    assert len(components) == 1, 'Expected one HISM component'
    component = components[0]
    assert component.get_instance_count() == 3, 'Saved HISM instance count differs from 3'
    assert component.get_editor_property('static_mesh').get_path_name() == '/Engine/BasicShapes/Cube.Cube'
    details = []
    for index, expected in enumerate(SPECS):
        transform = component.get_instance_transform(index, world_space=True)
        assert transform is not None, 'Unable to read HISM transform'
        location = vec(transform.translation)
        scale = vec(transform.scale3d)
        yaw = float(transform.rotation.rotator().yaw)
        compare(location, expected['location'])
        compare(scale, expected['scale'])
        assert abs((yaw - expected['yaw'] + 180) % 360 - 180) < .01, (yaw, expected['yaw'])
        details.append(dict(index=index, location_cm=location, yaw=yaw, scale=scale))
    return dict(actor=actor.get_path_name(), component=component.get_path_name(),
                component_class=component.get_class().get_name(), instance_count=3, transforms=details)


try:
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_system = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assets = unreal.EditorAssetLibrary
    if MODE == 'create':
        assert not assets.does_asset_exist(TEST_MAP), 'Probe must never replace an existing test level'
        assert not assets.does_asset_exist(TEST_BP), 'Probe must use a new unique test blueprint'
        import ue_instancing
        ue_instancing.BLUEPRINT_PATH = TEST_BP
        assert levels.new_level(TEST_MAP), 'Failed to create isolated test level'
        transforms = [unreal.Transform(location=unreal.Vector(*spec['location']),
                                       rotation=unreal.Rotator(pitch=0, yaw=spec['yaw'], roll=0),
                                       scale=unreal.Vector(*spec['scale'])) for spec in SPECS]
        actor = ue_instancing.spawn_group(LABEL, 'GHS/Tests', assets.load_asset('/Engine/BasicShapes/Cube'), transforms)
        report['create'] = verify_actor(actor)
        assert levels.save_current_level(), 'Failed to save probe level'
        report['create']['saved'] = True
    else:
        assert assets.does_asset_exist(TEST_MAP), 'Missing saved HISM probe map'
        assert assets.does_asset_exist(TEST_BP), 'Missing saved HISM probe blueprint'
        assert levels.load_level(TEST_MAP), 'Failed to load saved probe level'
        found = [actor for actor in actor_system.get_all_level_actors() if actor.get_actor_label() == LABEL]
        assert len(found) == 1, 'Saved probe actor missing or duplicated'
        report['fresh_process_verify'] = verify_actor(found[0])
        report['success'] = True
    report.pop('error', None)
except Exception:
    report['error'] = traceback.format_exc()
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    raise
else:
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    unreal.log('GHS_HISM_PROBE ' + json.dumps(dict(mode=MODE, success=report['success'], instances=3)))
