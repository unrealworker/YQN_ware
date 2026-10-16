"""Read-only fresh-UE validation of joined walls and the corrected warehouse."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import traceback

import unreal

ROOT = Path(r'D:\UEPro\Test')
sys.path.insert(0, str(ROOT/'Scripts/ghs'))
import verify_clearance_scene as clearance
import verify_ue_scene as common

REPORT_PATH = ROOT/'Saved/GHS_JoinedWallsVerification.json'
WALLS = {
    'GHS_CAD_WallFaces': ('SM_GHS_JoinedWallFaces', 'M_GHS_WallVolume'),
    'GHS_CAD_WallSections': ('SM_GHS_JoinedWallSections', 'M_GHS_WallSection'),
    'GHS_CAD_WallEdges': ('SM_GHS_JoinedWallEdges', 'M_GHS_WallTrim'),
}
TOLERANCE_M = .0001  # 0.1 mm, larger than float32 FBX error at 240 m.
AREA_TOLERANCE_M2 = .02  # Imported float32 vertices along ~2 km of perimeter.


def signed_area(poly):
    return sum(p[0]*q[1]-q[0]*p[1]
               for p, q in zip(poly, poly[1:]+poly[:1]))*.5 if poly else 0.0


def ccw(poly):
    return poly if signed_area(poly) >= 0 else list(reversed(poly))


def clip_half(poly, a, b, inside=True):
    """Clip to the left/right of a directed line; polygons remain convex."""
    if not poly:
        return []
    sign = 1 if inside else -1
    distance = lambda p: sign*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))
    out = []
    for p, q in zip(poly, poly[1:]+poly[:1]):
        dp, dq = distance(p), distance(q)
        if dp >= 0:
            out.append(p)
        if (dp >= 0) != (dq >= 0):
            t = dp/(dp-dq)
            out.append((p[0]+t*(q[0]-p[0]), p[1]+t*(q[1]-p[1])))
    return out


def subtract_convex(poly, clip):
    """Disjoint convex pieces of poly outside a convex CCW clipping polygon."""
    remaining, result = poly, []
    for a, b in zip(clip, clip[1:]+clip[:1]):
        if not remaining:
            break
        outside = clip_half(remaining, a, b, False)
        if abs(signed_area(outside)) > 1e-12:
            result.append(outside)
        remaining = clip_half(remaining, a, b, True)
    return result


class PolygonGrid:
    def __init__(self, polygons, cell_size=4.0):
        self.polygons = polygons
        self.cell_size = cell_size
        self.grid = defaultdict(set)
        for index, poly in enumerate(polygons):
            for cell in self.cells(poly):
                self.grid[cell].add(index)

    def cells(self, poly):
        lo = [min(p[i] for p in poly) for i in range(2)]
        hi = [max(p[i] for p in poly) for i in range(2)]
        return itertools.product(range(math.floor(lo[0]/self.cell_size), math.floor(hi[0]/self.cell_size)+1),
                                 range(math.floor(lo[1]/self.cell_size), math.floor(hi[1]/self.cell_size)+1))

    def candidates(self, poly):
        result = set()
        for cell in self.cells(poly):
            result.update(self.grid.get(cell, ()))
        return result

    def outside_area(self, poly, indices=None):
        pieces = [ccw(poly)]
        for index in sorted(self.candidates(poly) if indices is None else indices):
            pieces = [part for p in pieces for part in subtract_convex(p, self.polygons[index])]
            if not pieces:
                break
        return sum(abs(signed_area(p)) for p in pieces)


def wall_rectangles(cad, padding=0.0):
    rectangles = []
    for wall in cad['walls']:
        a, b = wall['points_m']
        length = math.dist(a, b)
        ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
        hx, hy = length/2+padding, wall['thickness_m']/2+padding
        x, y = (a[0]+b[0])/2, (a[1]+b[1])/2
        rectangles.append([(x+ux*px-uy*py, y+uy*px+ux*py)
                           for px, py in [(-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy)]])
    return rectangles


def triangle_area_3d(triangle):
    a, b, c = triangle
    u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
    cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
    return math.sqrt(sum(value*value for value in cross))/2


def saved_mesh_triangles(mesh, transform, editor):
    """Source LOD0 is stored in the asset; build settings are checked explicitly."""
    assert editor.get_lod_count(mesh) == 1, mesh.get_name()+' unexpected LOD'
    settings = editor.get_lod_build_settings(mesh, 0)
    common.compare(common.xyz(settings.get_editor_property('build_scale3d')), [1,1,1], 1e-6, 'Wall mesh build scale')
    reduction = editor.get_lod_reduction_settings(mesh, 0)
    assert abs(reduction.get_editor_property('percent_triangles')-1) < 1e-6
    # Historical walls use identity instances. The height correction keeps the
    # saved mesh unchanged and permits only the exact per-mesh profile transform.
    identity = dict(position_m=[0,0,0],scale=[1,1,1],rotation_deg=0)
    try:
        common.check_transform(transform, identity, mesh.get_name())
        transform_profile = 'historical_identity'
    except AssertionError:
        from wall_height_profile import row_for
        labels = [label for label, (name, _) in WALLS.items() if name == mesh.get_name()]
        assert len(labels) == 1, 'Height profile is restricted to the three joined wall meshes'
        common.check_transform(transform, row_for(labels[0]), mesh.get_name()+' height profile')
        transform_profile = 'synchronized_wall_height'
    scale = common.xyz(transform.scale3d)
    translation = common.xyz(transform.translation)
    description = mesh.get_static_mesh_description(0)
    assert description, mesh.get_name()+' missing saved MeshDescription'
    target_count = description.get_triangle_count()
    result, skipped_ids = [], 0
    for index in range(max(target_count*4, target_count+1024)):
        triangle_id = unreal.TriangleID(id_value=index)
        if not description.is_triangle_valid(triangle_id):
            skipped_ids += 1
            continue
        points = []
        # UE5.4 GetTriangleVertices sets an uninitialized three-item array and
        # then Algo::Copy appends three more entries. Read the three corners
        # through the scalar APIs to avoid those invalid leading VertexIDs.
        for corner in range(3):
            instance_id = description.get_triangle_vertex_instance(triangle_id, corner)
            vertex_id = description.get_vertex_instance_vertex(instance_id)
            p = description.get_vertex_position(vertex_id)
            # Both approved transforms have zero rotation. Apply the actual
            # instance scale and translation before mapping UE cm to CAD metres.
            world = [float(value)*scale[axis]+translation[axis]
                     for axis, value in enumerate((p.x, p.y, p.z))]
            points.append([world[0]/100, -world[1]/100, world[2]/100])
        assert len(points) == 3
        result.append(points)
        if len(result) == target_count:
            break
    assert len(result) == target_count, 'Incomplete sparse triangle ID traversal'
    return result, dict(source_triangle_count=target_count, render_triangle_count=mesh.get_num_triangles(0),
                        source_vertex_count=description.get_vertex_count(), skipped_triangle_ids=skipped_ids,
                        source_description_matches_unreduced_unit_scale_lod0=True,
                        verified_instance_transform_profile=transform_profile)


def compare_geometry(actual, source):
    vertices = source['vertices']
    expected = [[vertices[index] for index in face] for face in source['faces']]
    assert all(len(triangle)==3 for triangle in expected), 'Source mesh must already be triangulated'
    centroid = lambda triangle: tuple(sum(p[i] for p in triangle)/3 for i in range(3))
    cell = lambda point: tuple(math.floor(v/TOLERANCE_M) for v in point)
    grid = defaultdict(list)
    for index, triangle in enumerate(expected):
        grid[cell(centroid(triangle))].append(index)
    matched, extra, maximum = set(), [], 0.0
    permutations = list(itertools.permutations(range(3)))
    for triangle in actual:
        key = cell(centroid(triangle))
        candidates = {index for delta in itertools.product([-1,0,1], repeat=3)
                      for index in grid.get(tuple(key[i]+delta[i] for i in range(3)), ())}
        best = None
        for index in candidates-matched:
            reference = expected[index]
            error = min(max(math.dist(triangle[i],reference[order[i]]) for i in range(3))
                        for order in permutations)
            if error <= TOLERANCE_M and (best is None or error < best[0]):
                best = error,index
        if best is None:
            extra.append(triangle)
        else:
            maximum=max(maximum,best[0])
            matched.add(best[1])
    missing = [triangle for index,triangle in enumerate(expected) if index not in matched]
    missing_area=sum(triangle_area_3d(triangle) for triangle in missing)
    extra_area=sum(triangle_area_3d(triangle) for triangle in extra)
    missing_widths=[2*triangle_area_3d(t)/max(math.dist(t[0],t[1]),math.dist(t[1],t[2]),math.dist(t[2],t[0]),1e-15)
                    for t in missing]
    missing_max_width=max(missing_widths,default=0.0)
    # FBX import removes a few long slivers whose shortest altitude is only
    # micrometres. Require every omitted triangle to be thinner than the SAME
    # 0.1-mm coordinate tolerance; this never excuses meaningful missing faces.
    topology_ok=missing_max_width<=TOLERANCE_M and missing_area<.001 and extra_area<1e-10
    if not topology_ok:
        (ROOT/'Saved/GHS_JoinedWallsTopologyDiagnostic.json').write_text(json.dumps(dict(
            missing_area=missing_area,extra_area=extra_area,missing=missing,extra=extra,
            source_count=len(expected),actual_count=len(actual)),indent=2),encoding='utf-8')
    assert topology_ok, ('Saved topology differs',missing_area,extra_area,missing_max_width)
    return dict(all_saved_triangles_match_source=True,maximum_vertex_error_m=maximum,
                missing_triangle_area_m2=missing_area,extra_triangle_area_m2=extra_area,
                source_triangle_count=len(expected),imported_triangle_count=len(actual),
                imported_degenerate_triangles_removed=len(missing),missing_triangle_max_width_m=missing_max_width,
                all_missing_triangles_below_coordinate_tolerance=True,tolerance_m=TOLERANCE_M)


def validate_surfaces(name, triangles, rectangles, expanded_rectangles, union_area, source_proof):
    flat = [t for t in triangles if max(p[2] for p in t)-min(p[2] for p in t) < TOLERANCE_M]
    result = {}
    if name.endswith('Faces'):
        assert not flat, 'Joined wall face mesh contains horizontal caps'
        return result
    selected = flat if name.endswith('Edges') else [t for t in flat if sum(p[2] for p in t)/3 > 2]
    assert selected, name+' has no horizontal surface'
    polygons = [ccw([(p[0],p[1]) for p in t]) for t in selected]
    area = sum(abs(signed_area(poly)) for poly in polygons)
    outside = sum(expanded_rectangles.outside_area(poly) for poly in polygons)
    assert outside < 1e-6, (name+' protrudes beyond CAD wall union',outside)
    expected_area = source_proof['edge_band_area_m2'] if name.endswith('Edges') else union_area
    assert abs(area-expected_area) < AREA_TOLERANCE_M2, (name+' area mismatch',area,expected_area)
    # Nonoverlapping top triangles plus equal union area proves that no measured
    # door gap/hole was filled and no wall footprint was omitted.
    top_grid = PolygonGrid(polygons)
    duplicate_area = 0.0
    for index, poly in enumerate(polygons):
        for other in top_grid.candidates(poly):
            if other >= index:
                continue
            intersection = poly
            for a,b in zip(polygons[other],polygons[other][1:]+polygons[other][:1]):
                intersection=clip_half(intersection,a,b)
            duplicate_area += abs(signed_area(intersection))
    assert duplicate_area < 1e-5, (name+' duplicate horizontal coverage',duplicate_area)
    result.update(projected_area_m2=area, expected_area_m2=expected_area,
                  outside_cad_union_area_m2=outside, duplicate_triangle_area_m2=duplicate_area,
                  containment_tolerance_m=TOLERANCE_M)
    if name.endswith('Edges'):
        common.compare([min(p[2] for t in triangles for p in t),max(p[2] for t in triangles for p in t)],
                       [source_proof['edge_z_m']]*2,TOLERANCE_M,'Joined wall edge height')
    return result


def main(report):
    build = common.read_json(ROOT/'Saved/GHS_BuildReport.json')
    assert build.get('wall_joined_corrected'), 'Joined walls have not been applied'
    applied = common.read_json(ROOT/'Saved/GHS_JoinedWallsApplied.json')
    assert applied['success']
    geometry = common.read_json(ROOT/'SourceAssets/GHS/joined_walls_geometry.json')
    manifest = common.read_json(ROOT/'SourceAssets/GHS/joined_walls.json')
    cad = common.read_json(ROOT/'SourceAssets/GHS/cad_layout.json')
    registry = common.read_json(ROOT/'SourceAssets/GHS/ue_scene_registry.json')
    historical_path = ROOT/'Saved/GHS_ClearanceVerification.json'
    historical_sha = clearance.sha(historical_path)
    backup_registry = Path(applied['backup'])/'ue_scene_registry.json'
    before = common.read_json(backup_registry)
    old_groups = {group['actor']:group for group in before['groups']}
    groups = {group['actor']:group for group in registry['groups']}
    added_groups = {'GHS_ColumnEdgeOutlines'} if build.get('column_outlines_added') else set()
    assert set(groups) == set(old_groups) | added_groups
    assert registry['individuals'] == before['individuals'], 'Non-wall individual data changed'
    for label in set(old_groups)-set(WALLS):
        assert groups[label] == old_groups[label], 'Non-wall group changed: '+label
    source_ids = {wall['id'] for wall in cad['walls']}
    mapping = geometry['source_mapping']
    assert len(mapping) == 330 and {row['id'] for row in mapping} == source_ids
    cad_sources = {row['id']:row['source_handles'] for row in cad['walls']}
    assert all(row['source_handles']==cad_sources[row['id']] for row in mapping)
    for source in geometry['meshes'].values():
        assert set(source['source_wall_ids']) == source_ids
    proof=geometry['verification']
    assert proof['all_loops_closed'] and proof['union_valid'] and proof['no_snapping_or_positive_buffer']
    assert all(loop['closed'] and math.dist(loop['points'][0],loop['points'][-1]) < 1e-9
               for loop in geometry['boundary_loops'])
    rect_list=wall_rectangles(cad)
    rectangles=PolygonGrid(rect_list)
    expanded=PolygonGrid(wall_rectangles(cad,TOLERANCE_M))
    union_area=sum(rectangles.outside_area(poly,{i for i in rectangles.candidates(poly) if i<index})
                   for index,poly in enumerate(rect_list))
    assert abs(union_area-proof['footprint_union_area_m2'])<1e-6
    report['wall_source_mapping']=dict(source_wall_count=330,all_ids_and_source_handles_preserved=True,
                                       closed_loop_count=len(geometry['boundary_loops']),
                                       hole_count=sum(loop['hole'] for loop in geometry['boundary_loops']),
                                       independently_recomputed_union_area_m2=union_area)
    # This also reloads the saved map and verifies all non-wall regression checks.
    clearance.main(report)
    report['success']=False
    added=bool(build.get('column_outlines_added'))
    assert report['actor_count']==(225 if build.get('lighting_optimized') else (248 if added else 247))
    assert report['hism_group_count']==(16 if added else 15)
    assert report['instanced_count']==(14116 if added else 12076)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    by_label={actor.get_actor_label():actor for actor in actors}
    editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    specs={item['name']:item for item in manifest['meshes']}
    report['joined_walls']=[]
    extracted={}
    for label,(name,_) in WALLS.items():
        component=by_label[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        triangles,metrics=saved_mesh_triangles(component.get_editor_property('static_mesh'),
                                               component.get_instance_transform(0,world_space=True),editor)
        extracted[name]=dict(triangles=triangles,metrics=metrics)
    (ROOT/'Saved/GHS_JoinedWallsSavedGeometry.json').write_text(json.dumps(extracted),encoding='utf-8')
    for label,(name,material_name) in WALLS.items():
        component=by_label[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        assert component.get_instance_count()==groups[label]['count']==1
        mesh=component.get_editor_property('static_mesh')
        assert mesh.get_name()==groups[label]['mesh']==name
        assert component.get_num_materials()==1 and component.get_material(0).get_name()==material_name
        material_path=common.DEST+'/Materials/Instanced/'+material_name+'.'+material_name
        assert component.get_material(0).get_path_name()==material_path
        transform=component.get_instance_transform(0,world_space=True)
        triangles,metrics=extracted[name]['triangles'],extracted[name]['metrics']
        metrics.update(compare_geometry(triangles,geometry['meshes'][name]))
        metrics.update(validate_surfaces(name,triangles,rectangles,expanded,union_area,proof))
        bounds=mesh.get_bounds()
        expected_bounds=specs[name]['bounds_m']
        center=[(a+b)*50 for a,b in expected_bounds]
        center[1]*=-1
        extent=[(b-a)*50 for a,b in expected_bounds]
        common.compare(common.xyz(bounds.origin),center,.05,name+' bounds origin')
        common.compare(common.xyz(bounds.box_extent),extent,.05,name+' bounds extent')
        metrics.update(actor=label,mesh=mesh.get_path_name(),material=material_path,instance_count=1)
        report['joined_walls'].append(metrics)
    assert clearance.sha(historical_path)==historical_sha
    assert clearance.sha(ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap')==clearance.SOURCE_SHA
    report.update(success=True,wall_joined_corrected=True,source_wall_segment_count=330,
                  wall_mesh_instance_count=3,non_wall_groups_unchanged=12,
                  all_individual_records_unchanged=True,clearance_history_preserved=True,
                  clearance_history_sha256=historical_sha,door_gaps_and_holes_preserved=True,
                  geometry_source='Saved StaticMesh LOD0 MeshDescription; unreduced/unit build scale',
                  source_geometry_sha256=clearance.sha(ROOT/'SourceAssets/GHS/joined_walls_geometry.json'))


def run():
    if common.read_json(ROOT/'Saved/GHS_BuildReport.json').get('column_outlines_added'):
        import verify_column_outlines
        return verify_column_outlines.run()
    report=dict(success=False,map=common.MAP,created_utc=datetime.now(timezone.utc).isoformat(),
                verification_mode='Fresh UE saved geometry and world transforms; no asset/level save',
                groups=[],individuals=[],effects=[],meshes=[])
    try:
        main(report)
    except Exception:
        report['success']=False
        report['error']=traceback.format_exc()
        raise
    finally:
        REPORT_PATH.write_text(json.dumps(report,indent=2),encoding='utf-8')
    unreal.log('GHS_JOINED_WALLS_VERIFIED '+json.dumps({key:report[key] for key in
               ['success','actor_count','instanced_count','wall_mesh_instance_count','clearance_actual_obb_overlap_count']}))


if __name__=='__main__':
    run()
