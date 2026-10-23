"""Build exact non-car park derivatives in an isolated background Blender.

No spatial deletion: every removed polygon must match an original build_car
polygon by all float32 vertex coordinates, winding, role, and topology.
The source .blend, original assets and map are never saved or modified.
"""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import math
import struct
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/GHS/OrderReplayParking'
PARK = ROOT / 'SourceAssets/GHS/Park'
SOURCE = PARK / 'GHS_Park_Source.blend'
ORIGIN = (239.33385, 60.24019)
ROLES = ('Buildings', 'Blue', 'Detail', 'Solar', 'Rubber', 'VehicleLights', 'Markings')
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
sys.path.insert(0, str(ROOT / 'Saved/ParkRefinement/python_deps'))
from park_vehicles import build_car
from shapely.geometry import LineString


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def vertex_key(v):
    return struct.pack('<fff', *v)


def face_key(points):
    keys = [vertex_key(p) for p in points]
    return min(tuple(keys[i:] + keys[:i]) for i in range(len(keys)))


def face_digest(mesh, polygon_ids):
    h = hashlib.sha256()
    for index in polygon_ids:
        p = mesh.polygons[index]
        h.update(struct.pack('<IIB', len(p.vertices), p.material_index, p.use_smooth))
        for v in p.vertices:
            h.update(vertex_key(mesh.vertices[v].co))
    return h.hexdigest()


def candidates(report):
    result = []
    for index, stall in enumerate(report['parking']['stalls']):
        if stall['occupied']:
            result.append(dict(kind='parking', source_index=index,
                center=stall['center'], angle=stall['heading'], required=True))
    for index, house in enumerate(report['residential']['houses']):
        if index % 3 or not house.get('driveway_path_uv_m'):
            continue
        line = LineString(house['driveway_path_uv_m'])
        if line.length <= 7.2:
            continue
        p = line.interpolate(min(3.7, line.length * .45))
        a, b = list(line.coords)[0], list(line.coords)[-1]
        result.append(dict(kind='residential', source_index=index,
            source_id=house['cad_id'], center=[p.x, p.y],
            angle=math.atan2(b[1]-a[1], b[0]-a[0]), required=False))
    return result


def expected_faces(car, blue):
    faces = defaultdict(list)
    def emit(role, vertices, polygons):
        local = [(u-ORIGIN[0], -(v-ORIGIN[1]), z) for u, v, z in vertices]
        for face in polygons:
            faces[role].append(face_key([local[i] for i in reversed(face)]))
    u, v = car['center']
    build_car({'mesh': emit}, u, v, car['angle'], blue,
              int(abs(u*13.7 + v*7.3)) % 2)
    return faces


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    original_hash = digest(SOURCE)
    source_manifest = json.loads((PARK/'park_manifest.json').read_text(encoding='utf-8'))
    site = json.loads((PARK/'site_geometry_report.json').read_text(encoding='utf-8'))
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    objects = {role: bpy.data.objects['SM_GHSPark_'+role] for role in ROLES}
    lookup = {}
    for role, obj in objects.items():
        assert len(obj.data.uv_layers) == 0, (role, 'unexpected UV layer')
        assert not obj.modifiers, (role, 'unexpected modifier')
        assert all(abs(obj.matrix_world[r][c] - (1 if r == c else 0)) < 1e-9
                   for r in range(4) for c in range(4)), (role, 'non-identity transform')
        role_lookup = defaultdict(list)
        for polygon in obj.data.polygons:
            key = face_key([obj.data.vertices[i].co for i in polygon.vertices])
            role_lookup[key].append(polygon.index)
        lookup[role] = role_lookup
    removal = {role: set() for role in ROLES}
    matches, omitted = [], []
    for car in candidates(site):
        valid = []
        for blue in (False, True):
            expected = expected_faces(car, blue)
            if all(len(lookup[role].get(key, [])) == 1
                   for role, keys in expected.items() for key in keys):
                valid.append((blue, expected))
        if not valid:
            omitted.append(car)
            assert not car['required'], ('Required parked car did not exactly match', car)
            continue
        assert len(valid) == 1, ('Ambiguous car color match', car)
        blue, expected = valid[0]
        per_role = {}
        for role, keys in expected.items():
            ids = {lookup[role][key][0] for key in keys}
            assert len(ids) == len(keys), ('Duplicate expected face', car, role)
            assert not ids.intersection(removal[role]), ('Duplicate vehicle match', car, role)
            removal[role].update(ids)
            per_role[role] = len(ids)
        matches.append(dict(**car, blue=blue, removed_faces_by_role=per_role))
    expected_count = source_manifest['counts']['parked_cars']
    preliminary = dict(expected_cars=expected_count, matched_cars=len(matches),
        exact_float32_polygon_match=True, counts=dict(Counter(c['kind'] for c in matches)),
        omitted_candidates=omitted, role_removals={r:len(ids) for r,ids in removal.items()})
    (OUT/'exact-match-probe.json').write_text(json.dumps(preliminary,indent=2),encoding='utf-8')
    assert len(matches) == expected_count, ('Not every source car matched', preliminary)
    assert preliminary['counts'] == {'parking':68, 'residential':89}, preliminary
    assets = []
    for role, obj in objects.items():
        src = obj.data
        keep = [p.index for p in src.polygons if p.index not in removal[role]]
        src.calc_loop_triangles()
        removed_triangles = sum(1 for t in src.loop_triangles if t.polygon_index in removal[role])
        zero_area = [t.polygon_index for t in src.loop_triangles if t.area == 0.0]
        assert not set(zero_area).intersection(removal[role]), (role, 'Unexpected degenerate vehicle triangle')
        retained_hash = face_digest(src, keep)
        slot_names = [m.name if m else None for m in src.materials]
        row = dict(role=role, source='/Game/GHSZcoolSmartFactory/Park/Meshes/SM_GHSPark_'+role,
            source_object=obj.name, source_vertices=len(src.vertices),
            source_faces=len(src.polygons), source_triangles=len(src.loop_triangles),
            source_zero_area_triangles=len(zero_area),zero_area_source_polygon_ids=zero_area,
            removed_faces=len(removal[role]), removed_triangles=removed_triangles,
            retained_faces=len(keep), retained_face_sha256=retained_hash,
            material_slot_names=slot_names, exact_nonvehicle_face_preservation=True)
        if not keep:
            row.update(hide=True, replacement=None)
            assets.append(row)
            continue
        used = sorted({v for pi in keep for v in src.polygons[pi].vertices})
        remap = {old:new for new,old in enumerate(used)}
        name = 'SM_ReplayNoCars_'+role
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(src.vertices[i].co) for i in used], [],
            [tuple(remap[v] for v in src.polygons[i].vertices) for i in keep])
        mesh.update()
        for mat in src.materials:
            mesh.materials.append(mat)
        for index, old in enumerate(keep):
            mesh.polygons[index].material_index = src.polygons[old].material_index
            mesh.polygons[index].use_smooth = src.polygons[old].use_smooth
        assert face_digest(mesh, range(len(mesh.polygons))) == retained_hash, role
        vehicle_keys = {face_key([src.vertices[i].co for i in src.polygons[j].vertices])
                        for j in removal[role]}
        for p in mesh.polygons:
            assert face_key([mesh.vertices[i].co for i in p.vertices]) not in vehicle_keys
        target = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(target)
        bpy.ops.object.select_all(action='DESELECT')
        target.select_set(True)
        bpy.context.view_layer.objects.active = target
        fbx = OUT/(name+'.fbx')
        bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},
            axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,
            mesh_smooth_type='FACE',use_mesh_modifiers=True,add_leaf_bones=False)
        mesh.calc_loop_triangles()
        bounds = [[min(v.co[i] for v in mesh.vertices),max(v.co[i] for v in mesh.vertices)] for i in range(3)]
        row.update(hide=False,replacement='/Game/GHSOrderReplay/Parking/'+name,
            name=name,fbx=str(fbx),fbx_sha256=digest(fbx),vertices=len(mesh.vertices),
            triangles=len(mesh.loop_triangles),bounds_blender_m=bounds,
            zero_area_triangles=sum(t.area==0.0 for t in mesh.loop_triangles),
            bounds_ue_cm={'min':[bounds[0][0]*100,-bounds[1][1]*100,bounds[2][0]*100],
                'max':[bounds[0][1]*100,-bounds[1][0]*100,bounds[2][1]*100]})
        assert row['triangles'] == row['source_triangles']-removed_triangles, role
        assert row['zero_area_triangles'] == row['source_zero_area_triangles'], role
        assets.append(row)
    for obj in list(bpy.data.objects):
        if not obj.name.startswith('SM_ReplayNoCars_'):
            bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'GHS_OrderReplay_NoParkingCars.blend'))
    assert digest(SOURCE) == original_hash, 'Source .blend changed'
    manifest=dict(version=1,success=True,method='Exact original build_car polygon signatures; no bounding-box deletion',
        source_blend=str(SOURCE),source_blend_sha256=original_hash,
        source_site_sha256=digest(PARK/'site_geometry_report.json'),
        source_vehicle_builder_sha256=digest(ROOT/'Scripts/ghs/park_vehicles.py'),
        source_manifest_sha256=digest(PARK/'park_manifest.json'),
        cars_removed=len(matches),cars_by_kind=preliminary['counts'],cars=matches,
        roles=assets,original_source_unchanged=True,map_modified=False,
        material_contract='Slot count/order retained; UE import copies original static_materials; runtime preserves component overrides',
        coordinate_contract=source_manifest['coordinate_contract'])
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('ORDER_REPLAY_PARKING_READY '+json.dumps({
        'cars':len(matches),'roles':len(assets),'replacement_meshes':sum(not x['hide'] for x in assets),
        'hide_only':[x['role'] for x in assets if x['hide']],
        'removed_triangles':sum(x['removed_triangles'] for x in assets)}))


if __name__ == '__main__':
    main()
