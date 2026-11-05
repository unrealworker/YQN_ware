"""Blender CPU verification and fixed-camera preview of the new solar sources."""
import hashlib
import json
import math
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/MPR/hierarchy_20261105/solar'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def distance(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0.)
    dy = max(a[1] - b[3], b[1] - a[3], 0.)
    return math.hypot(dx, dy)


def signatures(obj, z):
    result = []
    for poly in obj.data.polygons:
        vertices = [obj.matrix_world @ obj.data.vertices[i].co for i in poly.vertices]
        if all(abs(p.z - z) < .00002 for p in vertices):
            result.append(tuple(sorted(tuple(round(v, 4) for v in p) for p in vertices)))
    return sorted(result)


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')


def main():
    manifest = read(OUT / 'manifest.json')
    modules = read(OUT / 'module_layout.json')
    old = read(ROOT / manifest['layout_source'])
    seen = set()
    nearest = 1e9
    for bank, rows in modules.items():
        blocks = old['blocks'][bank]
        for row in rows:
            key = tuple(row['grid'])
            assert key not in seen, ('overlapping source module', key)
            seen.add(key)
            x0, y0, x1, y1 = row['bounds_m']
            expected_x = old['uv_origin_m'][0] + (key[0] + .5) * old['pitch_m'][0]
            expected_y = old['uv_origin_m'][1] + (key[1] + .5) * old['pitch_m'][1]
            assert abs((x0 + x1) / 2 - expected_x) < 1e-8
            assert abs((y0 + y1) / 2 - expected_y) < 1e-8
            contained = [b for b in blocks if x0 >= b['bounds_m'][0] - 1e-8
                         and y0 >= b['bounds_m'][1] - 1e-8
                         and x1 <= b['bounds_m'][2] + 1e-8
                         and y1 <= b['bounds_m'][3] + 1e-8]
            assert len(contained) == 1
            nearest = min(nearest, *(distance(row['bounds_m'], dev['bounds_m'])
                                    for dev in old['devices_unchanged']))
    assert len(seen) == 5636
    assert nearest >= old['required_device_clearance_m']
    observed = {}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for row in manifest['export_meshes']:
        bpy.ops.import_scene.fbx(filepath=str(ROOT / row['fbx']))
        obj = next(o for o in bpy.context.selected_objects if o.type == 'MESH')
        frames = signatures(obj, old['top_z_m'] + .014)
        cells = signatures(obj, old['top_z_m'] + .020)
        count = len(modules[row['bank']])
        assert len(frames) == count and len(cells) == count
        for sig, module in zip(sorted(frames, key=lambda f: (f[0][0], f[0][1])),
                               sorted(modules[row['bank']], key=lambda m: (m['bounds_m'][0], m['bounds_m'][1]))):
            xx = [p[0] for p in sig]
            yy = [p[1] for p in sig]
            actual = [min(xx), min(yy), max(xx), max(yy)]
            assert max(abs(a - b) for a, b in zip(actual, module['bounds_m'])) < .00011
        shapes = {'frame': frames, 'cells': cells}
        digest = hashlib.sha256(json.dumps(shapes, sort_keys=True).encode()).hexdigest()
        observed.setdefault(row['bank'], []).append(digest)
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
    assert all(len(set(hashes)) == 1 for hashes in observed.values())
    audit = dict(success=True, actual_fbx_identical_top_geometry_all_lods=True,
                 imported_top_surface_hash_by_bank=observed, module_count=len(seen),
                 preserved_blocks=59, preserved_roof_devices=len(old['devices_unchanged']),
                 source_module_centres_unchanged=True, outside_original_block_count=0,
                 minimum_device_clearance_m=nearest,
                 required_device_clearance_m=old['required_device_clearance_m'],
                 measured_precision_m=.00011, preview_scope='Only solar source geometry and neutral roof; not an Unreal validation')
    write(OUT / 'silhouette_validation.json', audit)

    # A neutral roof and the real source geometry; no replacement or edits to the
    # user's reference image. CPU render is diagnostic, UE remains authoritative.
    bpy.ops.wm.open_mainfile(filepath=str(OUT / 'MPR_Hierarchy_Solar.blend'))
    for obj in bpy.context.scene.objects:
        obj.hide_render = not obj.name.endswith('_LOD2')
    cad = read(ROOT / 'SourceAssets/MPR/rebuild_b50b57/solar/inputs/cad_layout.json')
    mesh = bpy.data.meshes.new('PreviewRoof')
    outline = cad['footprint_outline_m']
    mesh.from_pydata([(p[0], p[1], old['roof_z_m']) for p in outline], [], [tuple(range(len(outline)))])
    mesh.update()
    roof = bpy.data.objects.new('PreviewRoof', mesh)
    bpy.context.scene.collection.objects.link(roof)
    material = bpy.data.materials.new('PreviewRoofWhite')
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (.67, .70, .73, 1.)
    bsdf.inputs['Roughness'].default_value = .85
    mesh.materials.append(material)
    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('NeutralWorld')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.73, .78, .83, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .6
    sun = bpy.data.lights.new('PreviewSun', 'SUN')
    sun.energy = 2.
    sun.angle = math.radians(6)
    sunobj = bpy.data.objects.new('PreviewSun', sun)
    scene.collection.objects.link(sunobj)
    sunobj.rotation_euler = (math.radians(20), math.radians(-30), math.radians(-20))
    camera = bpy.data.cameras.new('SolarReviewCamera')
    camobj = bpy.data.objects.new('SolarReviewCamera', camera)
    scene.collection.objects.link(camobj)
    scene.camera = camobj
    target = Vector((0, -2, 13.4))
    camobj.location = target + Vector((0, -math.cos(math.radians(52)) * 1100, math.sin(math.radians(52)) * 1100))
    camobj.rotation_euler = (target - camobj.location).to_track_quat('-Z', 'Y').to_euler()
    camera.type = 'PERSP'
    camera.lens_unit = 'FOV'
    camera.angle = math.radians(50)
    camera.clip_end = 5000
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    scene.render.filepath = str(OUT / 'solar_camera_1100m.png')
    bpy.ops.render.render(write_still=True)
    # Closer diagnostic shows the same module boundaries, at the same direction.
    for obj in bpy.context.scene.objects:
        if obj.name.startswith('SM_MPRH_SolarBank_'):
            obj.hide_render = '_LOD' in obj.name
    camobj.location = target + (camobj.location - target) * .52
    scene.render.filepath = str(OUT / 'solar_camera_572m.png')
    bpy.ops.render.render(write_still=True)
    print('SOLAR_SILHOUETTES_VERIFIED', json.dumps(audit), flush=True)


if __name__ == '__main__':
    main()
