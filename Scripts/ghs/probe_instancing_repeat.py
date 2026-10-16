"""Regression probe for repeated reuse of one HISM Blueprint; Tests assets only."""
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
import unreal

ROOT = Path(r'D:\UEPro\Test')
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
import ue_instancing

REPORT = ROOT / 'Saved/GHS_InstancingRepeatProbe.json'
VERIFY = '-GHSRepeatVerify' in unreal.SystemLibrary.get_command_line()
report = json.loads(REPORT.read_text(encoding='utf-8')) if VERIFY else dict(success=False)
assets = unreal.EditorAssetLibrary
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def check_actor(actor):
    components = actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    assert len(components) == 1
    component = components[0]
    assert component.get_instance_count() == 3
    actual = []
    for index in range(3):
        transform = component.get_instance_transform(index, world_space=True)
        position = [float(transform.translation.x), float(transform.translation.y), float(transform.translation.z)]
        expected = [100 * index, -200 * index, 50]
        assert all(abs(a - b) < .01 for a, b in zip(position, expected)), (position, expected)
        actual.append(position)
    return dict(actor=actor.get_actor_label(), instance_count=3, world_positions_cm=actual)


try:
    if VERIFY:
        assert levels.load_level(report['map'])
        bp = ue_instancing.ensure_hism_blueprint(report['blueprint'])
        assert bp
        found = [actor for actor in actors.get_all_level_actors() if actor.get_actor_label().startswith('RepeatProbe_')]
        assert len(found) == 2
        report['fresh_process_verify'] = [check_actor(actor) for actor in found]
        report['success'] = True
    else:
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        report.update(map='/Game/GHSDigitalTwin/Tests/InstancingRepeat_' + stamp,
                      blueprint='/Game/GHSDigitalTwin/Tests/BP_InstancingRepeat_' + stamp)
        ue_instancing.BLUEPRINT_PATH = report['blueprint']
        assert levels.new_level(report['map'])
        transforms = [unreal.Transform(location=unreal.Vector(100 * i, -200 * i, 50)) for i in range(3)]
        mesh = assets.load_asset('/Engine/BasicShapes/Cube')
        first = ue_instancing.spawn_group('RepeatProbe_A', 'GHS/Tests', mesh, transforms)
        report['first'] = check_actor(first)
        bp = assets.load_asset(report['blueprint'])
        subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        library = unreal.SubobjectDataBlueprintFunctionLibrary
        report['raw_subobjects'] = []
        for handle in subsystem.k2_gather_subobject_data_for_blueprint(bp):
            data = library.get_data(handle)
            obj = library.get_object_for_blueprint(data, bp)
            raw = library.get_object(data)
            report['raw_subobjects'].append(dict(editable=obj.get_path_name() if obj else None,
                                                  raw=raw.get_path_name() if raw else None))
        for _ in range(3):
            assert ue_instancing.ensure_hism_blueprint(report['blueprint']) == bp
        report['repeated_ensure_count'] = 3
        second = ue_instancing.spawn_group('RepeatProbe_B', 'GHS/Tests', mesh, transforms)
        report['second'] = check_actor(second)
        assert levels.save_current_level()
        report['saved'] = True
    report.pop('error', None)
except Exception:
    report['success'] = False
    report['error'] = traceback.format_exc()
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    raise
else:
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    unreal.log('GHS_HISM_REPEAT_PROBE ' + json.dumps(dict(success=report['success'], verify=VERIFY)))
