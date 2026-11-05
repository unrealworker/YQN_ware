"""Build a continuous, full oak canopy for the existing MPR tree instances.

Run in an owned background Blender process. No UE package or source tree asset
is changed. Geometry uses metres, ground origin and the existing FBX convention.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector, noise

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/MPR/site_completion_20261105/tree'
NAME = 'SM_MPRSC_Tree_Canopy'
ROLES = ['Bark', 'LeafMid', 'LeafLight', 'LeafShade']
SOURCE = ROOT / 'SourceAssets/MPR/reference_v4/props/manifest.json'
SEED = 51052026


def bounds(obj):
    points = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return [[min(v[i] for v in points), max(v[i] for v in points)] for i in range(3)]


def linear(swatch):
    values = [int(swatch[i:i+2], 16) / 255 for i in (0, 2, 4)]
    return [v / 12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in values]


def material(role, swatch):
    mat = bpy.data.materials.new(role)
    mat.diffuse_color = (*linear(swatch), 1)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = mat.diffuse_color
    bsdf.inputs['Roughness'].default_value = .93 if role != 'Bark' else .86
    bsdf.inputs['Specular IOR Level'].default_value = .2
    return mat


def trunk_mesh():
    verts, faces = [], []

    def tube(points, radii, segments=10):
        offset = len(verts)
        for j, (point, radius) in enumerate(zip(points, radii)):
            center = Vector(point)
            tangent = (Vector(points[min(j+1, len(points)-1)]) - Vector(points[max(0, j-1)])).normalized()
            axis = tangent.cross(Vector((0, 1, 0))).normalized()
            cross = tangent.cross(axis).normalized()
            for i in range(segments):
                angle = i*math.tau/segments
                # Slight fluting makes the short exposed trunk read as wood.
                radial = radius*(1+.045*math.sin(i*2.4+j*.8))
                point_on_ring = center+(axis*math.cos(angle)+cross*math.sin(angle))*radial
                if j == 0 and center.z == 0:
                    point_on_ring.z = 0
                verts.append(tuple(point_on_ring))
        faces.append(tuple(offset+i for i in reversed(range(segments))))
        for j in range(len(points)-1):
            for i in range(segments):
                a = offset+j*segments+i
                b = offset+j*segments+(i+1)%segments
                faces.append((a, b, b+segments, a+segments))
        faces.append(tuple(offset+(len(points)-1)*segments+i for i in range(segments)))

    tube([(0, 0, 0), (.06, -.03, .7), (-.06, .05, 2.5), (.11, -.02, 4.7),
          (-.08, .12, 7.5), (.25, .05, 10.0)], [.44, .32, .26, .21, .13, .035], 12)
    for index in range(8):
        angle = index*2.39996323+.27
        z = 3.35+(index%3)*.74
        length = 2.8+(index%2)*.65
        end = (length*math.cos(angle), length*math.sin(angle), z+3.8)
        tube([(.04, 0, z), (end[0]*.46, end[1]*.46, z+1.2), end], [.17, .105, .025], 8)
    mesh = bpy.data.meshes.new('OakScaffold')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('OakScaffold', mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(bpy.data.materials['Bark'])
    return obj


def canopy_mesh(target_bounds, target_radius):
    noise.seed_set(SEED)
    lobes = []

    def lobe(center, radii):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1, location=center)
        ob = bpy.context.object
        ob.scale = radii
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        lobes.append(ob)

    # The ellipsoidal core joins several tiers of substantial branch masses.
    # Their union keeps rounded valleys without detached spherical silhouettes.
    lobe((0, 0, 9.5), (3.3, 3.2, 4.4))
    for count, radius, z, size, phase in ((8, 2.7, 7.3, 2.65, .3),
                                        (9, 3.45, 10.25, 2.55, 1.0),
                                        (7, 2.25, 12.9, 2.25, 1.7)):
        for i in range(count):
            angle = i*math.tau/count+phase
            reach = radius*(1+.12*math.sin(i*2.7+phase))
            height = z+.48*math.sin(i*2.1+phase)
            lobe((math.cos(angle)*reach, math.sin(angle)*reach*.94, height),
                 (size*(1+.06*math.sin(i)), size*.94, size*(1.06+.08*math.cos(i))))
    lobe((-.35, .25, 14.0), (1.75, 1.8, 1.7))
    bpy.ops.object.select_all(action='DESELECT')
    for ob in lobes:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = lobes[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = 'ContinuousCanopy'
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    remesh = obj.modifiers.new('JoinedBranchMasses', 'REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = .16
    remesh.use_smooth_shade = True
    bpy.ops.object.modifier_apply(modifier=remesh.name)
    smooth = obj.modifiers.new('OrganicTransitions', 'SMOOTH')
    smooth.factor = .58
    smooth.iterations = 3
    bpy.ops.object.modifier_apply(modifier=smooth.name)
    # Medium surface undulations give the canopy a leafy volume at close range,
    # without the high-frequency holes and pinpoints of individual leaf cards.
    for vertex in obj.data.vertices:
        p = vertex.co.copy()
        n = vertex.normal.copy()
        macro = noise.noise_vector(p*1.28+Vector((.4, 2.8, -1.6)))[0]
        detail = noise.noise_vector(p*4.3+Vector((8.9, -4.2, 6.4)))[1]
        vertex.co += n*(.23*macro+.045*detail)
    obj.data.update()
    obj.data.calc_loop_triangles()
    modifier = obj.modifiers.new('ControlledDensity', 'DECIMATE')
    modifier.ratio = min(1.0, 10800/len(obj.data.loop_triangles))
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    current = bounds(obj)
    desired = [target_bounds[0], target_bounds[1], [3.45, target_bounds[2][1]]]
    for vertex in obj.data.vertices:
        for axis in range(3):
            vertex.co[axis] = desired[axis][0]+(vertex.co[axis]-current[axis][0])/(current[axis][1]-current[axis][0])*(desired[axis][1]-desired[axis][0])
        # Preserve the old radial clearance envelope as well as its bounding
        # box. Keep the dominant coordinate so all six extrema stay pinned.
        x, y = vertex.co.x, vertex.co.y
        if math.hypot(x, y) > target_radius:
            if abs(x) >= abs(y):
                vertex.co.y = math.copysign(math.sqrt(max(0, target_radius**2-x*x)), y)
            else:
                vertex.co.x = math.copysign(math.sqrt(max(0, target_radius**2-y*y)), x)
    for role in ROLES[1:]:
        obj.data.materials.append(bpy.data.materials[role])
    obj.data.update()
    for face in obj.data.polygons:
        # Most of the crown is one pale sage material; only the most horizontal
        # top and deeply down-facing surfaces use the adjacent tone slots.
        face.material_index = 1 if face.normal.z > .91 and face.center.z > 12.5 else (2 if face.normal.z < -.83 and face.center.z < 6 else 0)
        face.use_smooth = True
    return obj


def audit(obj):
    obj.data.calc_loop_triangles()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    open_edges = sum(not e.is_manifold for e in bm.edges)
    bm.free()
    return dict(bounds_m=bounds(obj), origin_m=list(obj.location), scale=list(obj.scale),
                vertices=len(obj.data.vertices), triangles=len(obj.data.loop_triangles),
                radial_extent_m=max(math.hypot(v.co.x, v.co.y) for v in obj.data.vertices),
                nonmanifold_edges=open_edges,
                material_roles=[m.name for m in obj.data.materials],
                material_triangle_counts=dict(Counter(obj.data.materials[t.material_index].name for t in obj.data.loop_triangles)))


def preview(tree):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 20
    scene.cycles.use_denoising = True
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 4
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'AgX'
    scene.world = bpy.data.worlds.new('TreeReviewWorld')
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = (.76, .81, .85, 1)
    bg.inputs['Strength'].default_value = .7
    mat = material('ReviewGround', 'D5DBD0')
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.025))
    bpy.context.object.data.materials.append(mat)
    sun = bpy.data.lights.new('ReviewSun', 'SUN')
    sun.energy = 2.6
    sun.angle = .12
    obj = bpy.data.objects.new('ReviewSun', sun)
    scene.collection.objects.link(obj)
    obj.rotation_euler = (math.radians(28), math.radians(-23), math.radians(-35))
    cam = bpy.data.cameras.new('ReviewCamera')
    co = bpy.data.objects.new('ReviewCamera', cam)
    scene.collection.objects.link(co)
    scene.camera = co
    cam.type = 'ORTHO'
    cam.ortho_scale = 21
    target = Vector((0, 0, 8))
    co.location = (22, -35, 24)
    co.rotation_euler = (target-co.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(OUT/'canopy_review.png')
    bpy.ops.render.render(write_still=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SOURCE.read_bytes()
    reference = next(row for row in json.loads(source_raw)['meshes'] if row['name'] == 'SM_MPR4_Tree_Oak')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1
    for role, swatch in zip(ROLES, ['777E6B', 'A3B397', 'A8B79C', '9CAD90']):
        material(role, swatch)
    scaffold = trunk_mesh()
    canopy = canopy_mesh(reference['bounds_m'], reference['metadata']['radial_extent_m'])
    bpy.ops.object.select_all(action='DESELECT')
    scaffold.select_set(True)
    canopy.select_set(True)
    bpy.context.view_layer.objects.active = scaffold
    bpy.ops.object.join()
    tree = bpy.context.object
    tree.name = NAME
    tree.data.name = NAME
    modifier = tree.modifiers.new('ExportTriangles', 'TRIANGULATE')
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    for face in tree.data.polygons:
        face.use_smooth = True
    info = audit(tree)
    assert info['material_roles'] == ROLES, info['material_roles']
    assert 3000 <= info['triangles'] <= 15000, info['triangles']
    assert info['nonmanifold_edges'] == 0, info['nonmanifold_edges']
    assert info['radial_extent_m'] <= reference['metadata']['radial_extent_m']+.000001
    assert all(abs(info['bounds_m'][a][b]-reference['bounds_m'][a][b]) < .001 for a in range(3) for b in range(2)), (info['bounds_m'], reference['bounds_m'])
    assert info['origin_m'] == [0, 0, 0] and info['scale'] == [1, 1, 1]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_Site_Tree_Canopy.blend'))
    fbx = OUT/(NAME+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'MESH'},
                            axis_forward='-Y', axis_up='Z', apply_unit_scale=True,
                            bake_anim=False, mesh_smooth_type='FACE', add_leaf_bones=False)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(fbx))
    imported = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    assert len(imported) == 1
    reread = audit(imported[0])
    error = max(abs(reread['bounds_m'][a][b]-info['bounds_m'][a][b]) for a in range(3) for b in range(2))
    assert error < .001 and reread['triangles'] == info['triangles']
    assert reread['nonmanifold_edges'] == 0
    for index, role in enumerate(ROLES):
        assert imported[0].data.materials[index].name.split('.')[0] == role
    for obj in list(bpy.data.objects):
        if obj not in before:
            bpy.data.objects.remove(obj, do_unlink=True)
    assert SOURCE.read_bytes() == source_raw
    info.update(success=True, name=NAME, coordinate_frame='Local metres, ground origin; FBX -Y forward, +Z up',
                units='metres', source_reference_bounds_m=reference['bounds_m'],
                original_triangles=reference['triangles'], triangle_reduction_percent=(1-info['triangles']/reference['triangles'])*100,
                source_manifest_sha256=hashlib.sha256(source_raw).hexdigest(),
                fbx_sha256=hashlib.sha256(fbx.read_bytes()).hexdigest(),
                fbx_roundtrip_bounds_error_m=error, fbx_roundtrip_triangles=reread['triangles'],
                shader='Opaque default-lit, no cards, no wind tick, roughness .93',
                geometry='One closed, smoothly connected perturbed canopy envelope with broad organic lobes and a closed branch scaffold',
                original_assets_modified=False, seed=SEED)
    (OUT/'geometry_audit.json').write_text(json.dumps(info, indent=2), encoding='utf8')
    print('MPR_SITE_TREE_READY '+json.dumps(info), flush=True)
    preview(tree)


if __name__ == '__main__':
    main()
