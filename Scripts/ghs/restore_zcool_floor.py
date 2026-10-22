"""Restore the Zcool scene's full floor storage without saving or editing assets.

Call restore_floor(by_label) from the parent editor mutation script. The original
successful Zcool build contains all world transforms; the original binding groups
retain their CAD IDs and ordering. Rack occupancy and private materials are kept.
"""
import json
import math
from pathlib import Path

import unreal

ROOT = Path('D:/UEPro/Test')
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
EXPECTED = {
    'GHS_CAD_PalletCargo': ('SM_GHS_Presentation_CargoMid', 3726),
    'GHS_CAD_PalletCargoHigh': ('SM_GHS_Presentation_CargoHigh', 1900),
    'GHS_CAD_PalletCargoLow': ('SM_GHS_Presentation_CargoLow', 1904),
}


def _read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


def _path(obj):
    return obj.get_path_name() if obj else None


def _transform(row):
    result = unreal.Transform(
        location=unreal.Vector(*row['position']),
        scale=unreal.Vector(*row['scale']))
    result.rotation = unreal.Quat(*row['rotation'])
    return result


def _assert_transform(actual, expected, context):
    assert (actual.translation - unreal.Vector(*expected['position'])).length() < .02, context
    assert (actual.scale3d - unreal.Vector(*expected['scale'])).length() < .00002, context
    # Quaternions q and -q represent the same rotation.
    q = actual.rotation
    values = (q.x, q.y, q.z, q.w)
    delta = min(sum((a - b) ** 2 for a, b in zip(values, expected['rotation'])),
                sum((a + b) ** 2 for a, b in zip(values, expected['rotation'])))
    assert delta < 1.e-9, context


def restore_floor(by):
    """Restore 7,530 floor loads, returning a checked report without saving a map."""
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    world = editor.get_editor_world()
    assert world.get_path_name().split('.')[0] == MAP, 'Only the Zcool map may be edited'
    assert not levels.is_in_play_in_editor(), 'Stop Play before restoring editor instances'
    source = _read('Saved/GHS_ZcoolBuild.json')
    assert source['success'] and source['saved_and_reloaded'] and source['map'] == MAP
    original = source['after']
    registry = _read('Content/GHSTwinUI/data/scene-bindings.json')
    groups = {g['mesh']: g for g in registry['groups']}
    plans = []

    # Validate all actors, transforms, mesh assets and CAD ordering before mutation.
    for label, (mesh_name, count) in EXPECTED.items():
        actor = by[label]
        assert actor.get_path_name().startswith(world.get_path_name() + ':PersistentLevel.'), label
        component = actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        assert component and component.static_mesh
        current_name = component.static_mesh.get_name()
        assert current_name in (mesh_name, mesh_name + '_Occ70'), (label, current_name)
        saved = original[label]['components'][component.get_name()]
        assert saved['mesh'].rsplit('/', 1)[-1].split('.')[0] == mesh_name
        rows = saved['instances']
        cad = groups[mesh_name]
        assert len(rows) == cad['count'] == len(cad['instances']) == count
        assert len({r['id'] for r in cad['instances']}) == count
        for index, (row, binding) in enumerate(zip(rows, cad['instances'])):
            assert all(math.isfinite(v) for key in ('position', 'scale', 'rotation') for v in row[key])
            x, y, z = binding['position_m']
            assert sum((a - b) ** 2 for a, b in zip(row['position'], (x * 100, -y * 100, z * 100))) < .0004, (label, index, 'CAD order')
        current = groups[current_name]['instances']
        assert component.get_instance_count() == len(current), (label, 'Unexpected current instance count')
        for index, binding in enumerate(current):
            x, y, z = binding['position_m']
            location = component.get_instance_transform(index, world_space=True).translation
            assert (location - unreal.Vector(x * 100, -y * 100, z * 100)).length() < .02, (label, index, 'Current CAD order')
        # A private visual revision can retain the basename/CAD identity. Keep
        # that current mesh when restoring instances rather than reverting it.
        mesh = component.static_mesh if current_name == mesh_name else unreal.EditorAssetLibrary.load_asset(saved['mesh'])
        assert mesh and mesh.get_name() == mesh_name
        materials = [component.get_material(i) for i in range(component.get_num_materials())]
        assert len(mesh.static_materials) == len(materials)
        plans.append(dict(label=label, actor=actor, component=component, mesh=mesh,
                          rows=rows, materials=materials, before=component.get_instance_count()))

    report = dict(map=MAP, source='Saved/GHS_ZcoolBuild.json:after', groups=[], saved=False)
    for plan in plans:
        component, rows = plan['component'], plan['rows']
        component.clear_instances()
        component.set_static_mesh(plan['mesh'])
        indices = component.add_instances([_transform(row) for row in rows],
            should_return_indices=True, world_space=True, update_navigation=False)
        assert list(indices) == list(range(len(rows)))
        for index, material in enumerate(plan['materials']):
            component.set_material(index, material)
        actor = plan['actor']
        actor.tags = [tag for tag in actor.tags if not str(tag).startswith(
            ('InstanceCount=', 'OccupancyCapacity=', 'OccupancyOccupied='))] + [
                unreal.Name('InstanceCount=' + str(len(rows))),
                unreal.Name('OccupancyCapacity=' + str(len(rows))),
                unreal.Name('OccupancyOccupied=' + str(len(rows)))]
        assert component.get_instance_count() == len(rows)
        for index, row in enumerate(rows):
            _assert_transform(component.get_instance_transform(index, world_space=True), row,
                              (plan['label'], index))
        material_paths = [_path(m) for m in plan['materials']]
        assert [_path(component.get_material(i)) for i in range(component.get_num_materials())] == material_paths
        report['groups'].append(dict(actor=plan['label'], mesh=plan['mesh'].get_name(),
            before=plan['before'], count=len(rows), capacity=len(rows), occupied=len(rows),
            materials=material_paths, cad_order_verified=True, transforms_verified=True))
    report['total'] = sum(row['count'] for row in report['groups'])
    assert report['total'] == 7530
    report.update(success=True, metadata_changes_required=False, ratio=1.0)
    return report
