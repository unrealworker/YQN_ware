"""Measure FBX axis conversion using four geodetic control meshes.

Run with full UnrealEditor -ExecutePythonScript, before importing the globe.
The meshes retain their authored positions in their vertices, so local bounds
expose the actual importer conversion without actors or guessed axis signs.
"""
import json
import math
from pathlib import Path

import unreal as u


root = Path(u.Paths.project_dir())
source = root / 'SourceAssets/GlobeNavigation/GeographicCalibration.fbx'
if not source.is_file():
    raise FileNotFoundError(source)
editor = u.get_editor_subsystem(u.UnrealEditorSubsystem)
if editor is None or editor.get_editor_world() is None:
    raise RuntimeError('Use full UnrealEditor -ExecutePythonScript, not the PythonScript commandlet')

options = u.FbxImportUI()
options.import_mesh = True
options.import_materials = False
options.import_textures = False
options.import_animations = False
options.automated_import_should_detect_type = False
options.mesh_type_to_import = u.FBXImportType.FBXIT_STATIC_MESH
mesh_options = options.static_mesh_import_data
mesh_options.combine_meshes = False
mesh_options.auto_generate_collision = False
mesh_options.generate_lightmap_u_vs = False
mesh_options.convert_scene = True
mesh_options.convert_scene_unit = True
mesh_options.force_front_x_axis = False
mesh_options.transform_vertex_to_absolute = True
mesh_options.bake_pivot_in_vertex = False
mesh_options.import_translation = u.Vector(0, 0, 0)
mesh_options.import_rotation = u.Rotator(0, 0, 0)
mesh_options.import_uniform_scale = 1.0

task = u.AssetImportTask()
task.filename = str(source)
task.destination_path = '/Game/Developers/GlobeValidation'
task.automated = True
task.replace_existing = True
task.replace_existing_settings = True
task.save = True
task.options = options
# UE 5.8 AssetTools bypasses Interchange when a specific Factory is supplied.
# FbxImportUI alone does not select the legacy importer or guarantee its axes.
task.factory = u.FbxFactory()
u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

report = {}
expected = {'CAL_GHS', 'CAL_North', 'CAL_Greenwich', 'CAL_East90'}
found = set()
for asset in task.get_objects():
    if not isinstance(asset, u.StaticMesh):
        continue
    name = asset.get_name()
    matches = [marker for marker in expected if name == marker or name.endswith('_' + marker)]
    if len(matches) != 1 or matches[0] in found:
        raise RuntimeError('Unexpected or duplicate calibration mesh: ' + name)
    import_data = asset.get_editor_property('asset_import_data')
    if not isinstance(import_data, u.FbxStaticMeshImportData):
        raise RuntimeError('Calibration did not use the FBX importer: ' + name)
    bounds = asset.get_bounds()
    center = [bounds.origin.x, bounds.origin.y, bounds.origin.z]
    extent = [bounds.box_extent.x, bounds.box_extent.y, bounds.box_extent.z]
    if not all(math.isfinite(value) for value in center + extent):
        raise RuntimeError('Non-finite calibration bounds: ' + name)
    # The source markers are ~100 cm from the origin with a 0.2 cm radius.
    # This rejects centered geometry, incorrect units, or unbuilt mesh bounds.
    radius = math.sqrt(sum(value * value for value in center))
    if not 95.0 < radius < 110.0 or not all(0.01 < value < 1.0 for value in extent):
        raise RuntimeError('Invalid calibration scale/position for {}: {}, {}'.format(name, center, extent))
    found.add(matches[0])
    report[name] = {'center': center, 'extent': extent}

if found != expected:
    raise RuntimeError('Missing calibration meshes: ' + ', '.join(sorted(expected - found)))

# Preserve the flat asset-name format consumed by the import verification step.
report_path = root / 'SourceAssets/GlobeNavigation/ue-axis-report.json'
report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
print('GHS_AXIS_REPORT ' + json.dumps(report))
