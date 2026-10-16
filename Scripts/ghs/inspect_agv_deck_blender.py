"""Read actual evaluated corner/deck geometry without modifying the Blender source."""
import json
from pathlib import Path
import bpy
from mathutils import Vector

root = Path(r'D:\UEPro\Test')
bpy.ops.wm.open_mainfile(filepath=str(root/'SourceAssets/GHS/kuka_agv.blend'))
deps = bpy.context.evaluated_depsgraph_get()
rows = []
for obj in bpy.data.objects:
    if not obj.name.startswith(('Deck_panel_outline', 'Deck_screw', 'Rubber_load_surface', 'Central_')):
        continue
    ev = obj.evaluated_get(deps)
    mesh = ev.to_mesh()
    points = [obj.matrix_world @ v.co for v in mesh.vertices]
    bounds = [[min(v[i] for v in points), max(v[i] for v in points)] for i in range(3)]
    rows.append(dict(name=obj.name, bounds_m=bounds, vertices=len(mesh.vertices), faces=len(mesh.polygons)))
    ev.to_mesh_clear()
report = dict(source=bpy.data.filepath, objects=rows)
(root/'Saved/GHS_AGVDeckBefore.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('ACTUAL_AGV_DECK_BOUNDS', json.dumps(rows))
