"""Build an additive MPR perimeter in isolated Blender, never rewrite V4.

The original scene and shared material/mesh resources are inputs only. Three
terminal mesh references are the only allowed replacement slots, following the
user's explicit connection-band exception. All other geometry is additive.
"""
import copy
import hashlib
import json
import math
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'Tools/MPRWarehouse'), str(ROOT/'Saved/ParkRefinement/python_deps'), str(ROOT/'Scripts/ghs')]
import bpy
import shapely
from shapely.geometry import GeometryCollection, LineString, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union
from mpr_blender_common import Geometry
from mpr_extension_context import build_context, source_footprint, TREE_RADIAL_EXTENT_M
from mpr_plan_layout import plan_to_world, world_to_plan
from mpr_plan_site import terminal_fade, terminal_shape
from mpr_railway_detail import build_railways
import mpr_railway_detail as rail_detail
import build_mpr_reference_site as core
import build_mpr_reference_context_v4 as context_style

OUT = ROOT/'SourceAssets/MPR/extension_b50b57'
V4 = ROOT/'SourceAssets/MPR/reference_v4'
CACHE = ROOT/'Saved/MPR/extension_20261104'
SOURCE_BLEND = Path('D:/CodexTemp/2026-11-04/topoexport-B50B57/topoexport-B50B57.blend')
G = -1.2
TILE = 150.0
GEO = Geometry()
TRIANGULATION_AUDIT = []


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Polygon':
        return [geometry]
    return [p for g in getattr(geometry, 'geoms', []) for p in polygons(g)]


def lines(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'LineString':
        return [geometry]
    return [p for g in getattr(geometry, 'geoms', []) for p in lines(g)]


def tiled(geometry):
    if geometry.is_empty:
        return
    x0, y0, x1, y1 = geometry.bounds
    for x in range(math.floor(x0/TILE), math.floor(x1/TILE)+1):
        for y in range(math.floor(y0/TILE), math.floor(y1/TILE)+1):
            cut = geometry.intersection(box(x*TILE, y*TILE, (x+1)*TILE, (y+1)*TILE))
            if not cut.is_empty:
                yield x, y, cut


def safe_triangles(polygon, label, segment=None):
    """Resolve submillimetre overlay slivers without dropping real surfaces."""
    original = shapely.make_valid(polygon)
    source_area = original.area
    failures = []
    for grid in (.0001, .001):
        try:
            clean = shapely.set_precision(original, grid, mode='valid_output')
            clean = clean.simplify(grid*.5, preserve_topology=True)
            if segment:
                clean = shapely.set_precision(shapely.segmentize(clean, segment), grid,
                                              mode='valid_output')
            clean = shapely.make_valid(clean)
            triangles = [tri for p in polygons(clean)
                         for tri in shapely.constrained_delaunay_triangles(p).geoms
                         if tri.area > 1e-10]
            actual = sum(tri.area for tri in triangles)
            allowed = max(.0001, original.length*grid*2)
            assert abs(actual-source_area) <= allowed, (label, 'Surface area loss', source_area, actual, allowed)
            assert abs(actual-clean.area) <= max(1e-7, clean.area*1e-9), (label, 'Incomplete tessellation')
            TRIANGULATION_AUDIT.append(dict(label=label, precision_m=grid, source_area_m2=source_area,
                    emitted_area_m2=actual, absolute_area_change_m2=abs(actual-source_area),
                    permitted_area_change_m2=allowed, repaired_after_errors=failures))
            return triangles
        except shapely.errors.GEOSException as exc:
            failures.append(str(exc))
    raise RuntimeError(('Cannot triangulate surface safely', label, source_area, failures))


def surface(name, role, geometry, z, *, tile=True):
    pieces = tiled(geometry) if tile else [(None, None, geometry)]
    for x, y, part in pieces:
        target = name+'_%d_%d' % (x, y) if tile else name
        for polygon in polygons(shapely.make_valid(part)):
            for tri in safe_triangles(polygon, target):
                if tri.area < 1e-8:
                    continue
                pts = list(tri.exterior.coords)[:3]
                cross = (pts[1][0]-pts[0][0])*(pts[2][1]-pts[0][1])-(pts[1][1]-pts[0][1])*(pts[2][0]-pts[0][0])
                GEO.mesh(target, role, [(a, b, z) for a, b in pts], [(0, 1, 2) if cross > 0 else (0, 2, 1)])


def faded_surface(name, role, geometry, z, frame, *, tile=True):
    """Two-metre rings preserve the outer fade on long triangulated roads."""
    inner = frame.buffer(-30)
    surface(name, role, geometry.intersection(inner), z, tile=tile)
    for lo in range(0, 30, 2):
        ring = frame.buffer(-lo).difference(frame.buffer(-(lo+2)))
        surface(name, role, geometry.intersection(ring), z, tile=tile)
    # Retained old terminal pieces outside the new survey frame are allowed;
    # their old terminal fade is evaluated independently at export.
    surface(name, role, geometry.difference(frame), z, tile=tile)


def curve_surface(value, width):
    if value is None or value.is_empty:
        return GeometryCollection()
    if value.geom_type in ('LineString', 'MultiLineString'):
        return value.buffer(width/2, cap_style=2, join_style=2)
    return value


def replacement_surface(name, role, geometry, z, fade_rows, old_frame):
    """Keep the original 2m longitudinal gradient sampling on retained tails."""
    remaining = geometry
    for row in fade_rows:
        origin, direction = row['origin_m'], row['direction']
        normal = [-direction[1], direction[0]]
        support = terminal_shape(row).buffer(.55, quad_segs=8).difference(old_frame)
        piece = remaining.intersection(support)
        if piece.is_empty:
            continue
        coordinates = shapely.get_coordinates(piece)
        projected = [(p[0]-origin[0])*direction[0]+(p[1]-origin[1])*direction[1] for p in coordinates]
        first, last = min(0., min(projected)), max(row['length_m'], max(projected))
        stations = sorted({first, last, 0., row['fade_start_m'], row['length_m'],
                           *(first+2*i for i in range(math.ceil((last-first)/2)+1))})
        width = row['width_m']+3
        for a, b in zip(stations, stations[1:]):
            clip = Polygon([[origin[i]+direction[i]*distance+normal[i]*sign*width for i in range(2)]
                            for distance, sign in [(a, -1), (b, -1), (b, 1), (a, 1)]])
            surface(name, role, piece.intersection(clip), z, tile=False)
        remaining = remaining.difference(support)
    for x, y, part in tiled(remaining):
        surface(name, role, part, z, tile=False)


def archive_inputs():
    directory = OUT/'inputs'
    directory.mkdir(parents=True, exist_ok=True)
    entries = {}
    sources = {
        'source_geometry.json': CACHE/'source_geometry.json',
        'registration_proposal.json': CACHE/'registration_proposal.json',
        'LICENSE-topoexport.txt': SOURCE_BLEND.parent/'source/LICENSE.txt',
        'topoexport-B50B57.blend': SOURCE_BLEND,
    }
    for name, original in sources.items():
        destination = directory/name
        # A rerun can be made from the archived exact input after the external
        # scratch directory disappears. Different inputs are never overwritten.
        if destination.exists():
            if original.exists():
                assert sha(destination) == sha(original), ('Archived input mismatch', name)
        else:
            assert original.is_file(), str(original)
            shutil.copy2(original, destination)
        entries[name] = dict(sha256=sha(destination), bytes=destination.stat().st_size)
    return read(directory/'source_geometry.json'), read(directory/'registration_proposal.json'), entries


def transformation(spec):
    scale, matrix, offset = spec['scale'], spec['rotation_row_matrix'], spec['offset_xy_m']
    def apply(point):
        x, y = point[:2]
        return [scale*(x*matrix[0][0]+y*matrix[1][0])+offset[0],
                scale*(x*matrix[0][1]+y*matrix[1][1])+offset[1]]
    return apply


def baseline_geometry():
    context = read(V4/'context/manifest.json')
    buildings = unary_union([Polygon(p) for p in context['footprints_m']])
    composition = read(V4/'validation_blender/composition_instances.json')
    trees = []
    for group in composition.values():
        for row in group.get('SM_MPR4_Tree_Oak', []):
            x, y = row['position_m'][:2]
            trees.append(Point(x, y).buffer(TREE_RADIAL_EXTENT_M*max(row['scale'][:2])+.3, quad_segs=12))
    old_tracks = []
    for row in read(V4/'site/plan_railway_v5.json')['tracks']:
        points = [tuple(plan_to_world(p)[:2]) for p in row['path_px']]
        result = list(points)
        for index, neighbour in [(0, 1), (-1, -2)]:
            p, q = points[index], points[neighbour]
            pixel = world_to_plan(p)
            if not (pixel[1] < 1 or pixel[1] > 908):
                continue
            length = math.dist(p, q)
            end = tuple(p[i]+(p[i]-q[i])/length*160 for i in range(2))
            if index == 0:
                result.insert(0, end)
            else:
                result.append(end)
        old_tracks.append(dict(id=row['id'], points_m=result))
    rail = unary_union([LineString(r['points_m']).buffer(2.25, cap_style=2, quad_segs=8) for r in old_tracks])
    return dict(buildings=buildings, trees=unary_union(trees), rail=rail, tracks=old_tracks)


def railway_extension(baseline, frame, frame_old, forbidden):
    """Extend actual rendered endpoints, preserving gauge and parallel tracks.

    The new GIS rail axes differ from the approved stylized old layout. No old
    rail is moved or relaid. Only old outward tangents already inside the new
    frame are continued to its edge; interior turnout ends are never extended.
    """
    tracks, audit = [], []
    for row in baseline['tracks']:
        pts = row['points_m']
        for index, neighbour in [(0, 1), (-1, -2)]:
            p, q = pts[index], pts[neighbour]
            if not frame.buffer(-3).covers(Point(p)) or frame_old.buffer(1).covers(Point(p)):
                continue
            length = math.dist(p, q)
            direction = [(p[i]-q[i])/length for i in range(2)]
            ray = LineString([p, [p[i]+direction[i]*2500 for i in range(2)]]).intersection(frame.buffer(-2.5))
            candidates = [part for part in lines(ray) if part.distance(Point(p)) < .01]
            if not candidates:
                continue
            curve = max(candidates, key=lambda item: item.length)
            coords = list(curve.coords)
            if math.dist(coords[-1], p) < math.dist(coords[0], p):
                coords.reverse()
            # Stop at a real obstacle instead of moving it or building rails
            # across a road/house. No branches or closed rail loops are added.
            path = LineString(coords)
            conflicts = path.buffer(2.25, cap_style=2).intersection(forbidden)
            if not conflicts.is_empty:
                distances = [path.project(Point(x, y)) for x, y in shapely.get_coordinates(conflicts)]
                available = min(distances)-.75 if distances else path.length
                if available < 8:
                    audit.append(dict(track=row['id'], endpoint=index, skipped='outside obstacle at rail end'))
                    continue
                end = path.interpolate(available)
                path = LineString([p, end.coords[0]])
            if path.length < 5:
                continue
            tracks.append(dict(id=row['id']+'_'+str(index), layer='railways', vertices=[[*a, 0] for a in path.coords]))
            audit.append(dict(track=row['id'], endpoint=index, points_m=list(path.coords), length_m=path.length,
                              method='existing_rendered_endpoint_tangent_continuation'))
    if not tracks:
        return dict(exclusion=GeometryCollection(), stats=dict(added_tracks=0), endpoint_audit=audit)
    rail_detail.HEAD_WIDTH_M = .09
    rail_detail.RAIL_OFFSET_M = (rail_detail.GAUGE_M+.09)/2
    def sink(name, role, vertices, faces):
        # Existing detail builder already batches by midpoint zone. Rename only;
        # retain exact gauge and sleeper/rail heights from the current scene.
        if 'Sleepers' in name:
            occupancy = Polygon([v[:2] for v in vertices[:4]])
            if occupancy.intersection(baseline['rail']).area > 1e-7:
                return
        target = name.replace('SM_MPR_Env_', 'SM_MPRE_Rail_')
        GEO.mesh(target, 'MPR3_'+role, vertices, faces)
    def zone(x, y):
        return '%d_%d' % (math.floor(x/TILE), math.floor(y/TILE))
    corridor = unary_union([LineString(r['vertices']).buffer(2.25, cap_style=2) for r in tracks])
    regions = {str(x)+'_'+str(y): part for x, y, part in tiled(corridor)}
    result = build_railways(dict(mesh=sink, zone=zone, regions=regions, include_freight=False), tracks, G)
    result['endpoint_audit'] = audit
    result['stats']['policy'] = 'Only unchanged old rendered endpoint tangents; no source-axis snap, no invented turnout or loop'
    return result


def grade_crossings(rail, road_geometry, protection):
    """Display-only level crossings; continuous steel stays above the deck."""
    paths = [LineString(row['vertices']) for row in rail.get('centerlines', [])]
    if not paths:
        return dict(audit=[], surface_mask=GeometryCollection())
    rail_deck = unary_union([p.buffer(1.7, cap_style=2) for p in paths])
    decks = rail_deck.intersection(road_geometry).difference(protection.buffer(.03))
    decks = unary_union([p for p in polygons(decks) if p.area > .5])
    surface('SM_MPRE_CrossingDeck', 'MPR3_Concrete', decks, G+.375)
    ramp = decks.buffer(2.2, quad_segs=8).difference(decks).intersection(road_geometry).difference(protection.buffer(.03))
    for ix, iy, part in tiled(ramp):
        name = 'SM_MPRE_CrossingRamp_%d_%d' % (ix, iy)
        for polygon in polygons(part):
            for tri in safe_triangles(polygon, name, segment=.75):
                if tri.area < 1e-8:
                    continue
                pts = list(tri.exterior.coords)[:3]
                vertices = []
                for x, y in pts:
                    t = min(1., Point(x, y).distance(decks)/2.2)
                    z = G+.083+(.375-.083)*(1-t)
                    vertices.append((x, y, z))
                cross = (pts[1][0]-pts[0][0])*(pts[2][1]-pts[0][1])-(pts[1][1]-pts[0][1])*(pts[2][0]-pts[0][0])
                GEO.mesh(name, 'MPR3_Asphalt', vertices, [(0, 1, 2) if cross > 0 else (0, 2, 1)])
    audit = [dict(footprint_m=list(p.exterior.coords), area_m2=p.area,
                 rail_head_z_m=G+.445, deck_z_m=G+.375, ramp_m=2.2,
                 policy='New-area display level crossing, not a surveyed bridge or engineering crossing')
            for p in polygons(decks)]
    return dict(audit=audit, surface_mask=decks.union(ramp))


def main():
    from mpr_extension_roads import build_extension_roads
    OUT.mkdir(parents=True, exist_ok=True)
    source, registration, archived = archive_inputs()
    assert source['sha256'] == archived['topoexport-B50B57.blend']['sha256'], 'Extraction is not from the archived Blender source'
    assert registration['source_sha256'] == source['sha256'], 'Registration source mismatch'
    tx = transformation(registration['transform'])
    baseline = baseline_geometry()
    source_buildings = [dict(name=row['name'], geometry=source_footprint(row, tx))
                       for row in source['objects'] if row.get('layer') == 'TPX_BUILDINGS']
    roads = build_extension_roads(source, registration['transform'],
                    existing_buildings=baseline['buildings'], existing_tree_clearance=baseline['trees'],
                    new_buildings=source_buildings)
    assert not roads['audit']['unresolved'], ('Unresolved road interface', roads['audit']['unresolved'])
    assert not roads['audit']['transition_crossings'], ('Road transitions cross', roads['audit']['transition_crossings'])
    assert roads['audit']['all_surfaces_valid']
    frame, old_frame = roads['frame_new'], roads['frame_old']
    # Road planning uses a conservative railway clearance. The frozen render
    # mask uses the actual flat-ended ballast occupancy, allowing new rails to
    # meet the existing physical cut plane without a fictitious 3.5m gap.
    protection = unary_union([old_frame, baseline['buildings'].buffer(.25), baseline['trees'], baseline['rail']])
    road_geometry = unary_union([roads['extension_roads'], roads['replacement_terminal_roads']])
    rail = railway_extension(baseline, frame, old_frame, unary_union([baseline['buildings'], baseline['trees']]))
    crossing_info = grade_crossings(rail, road_geometry, protection)
    crossings, crossing_mask = crossing_info['audit'], crossing_info['surface_mask']
    rail_geometry = unary_union([baseline['rail'], rail['exclusion']])
    water_parts = [source_footprint(row, tx) for row in source['objects']
                   if row.get('layer') == 'TPX_WATERWAYS_HATCH']
    water = unary_union(water_parts).intersection(frame).difference(protection.buffer(.3)).difference(road_geometry.buffer(.6)).difference(rail_geometry)
    water = unary_union([p for p in polygons(water) if p.area > 12])
    surface('SM_MPRE_Water', 'MPR3_PondWater', water, G+.015)
    bank = water.buffer(.65).difference(water).difference(protection).difference(road_geometry).difference(rail_geometry)
    surface('SM_MPRE_WaterBank', 'MPR3_Grass', bank, G+.025)

    faded_surface('SM_MPRE_Roads', 'MPR4_TerminalAsphalt', roads['extension_roads'].difference(crossing_mask), G+.08, frame)
    new_curb = roads['curbs'].intersection(frame)
    faded_surface('SM_MPRE_Curblines', 'MPR4_TerminalCurb', new_curb, G+.21, frame)
    faded_surface('SM_MPRE_WhiteEdges', 'MPR4_TerminalWhiteLine', curve_surface(roads.get('white_edges'), .12), G+.106, frame)
    faded_surface('SM_MPRE_RoadDashes', 'MPR4_TerminalWhiteLine', curve_surface(roads.get('dash_lines'), .13), G+.106, frame)
    replacements = []
    for key, suffix, role, z in [
        ('replacement_terminal_roads', 'Roads', 'MPR4_TerminalAsphalt', G+.08),
        ('replacement_terminal_curbs', 'Curbs', 'MPR4_TerminalCurb', G+.21),
        ('replacement_terminal_white_edges', 'Edges', 'MPR4_TerminalWhiteLine', G+.106)]:
        name = 'SM_MPRE_ReplacementTerminal'+suffix
        geometry = curve_surface(roads[key], .12)
        if suffix == 'Roads':
            geometry = geometry.difference(crossing_mask)
        replacement_surface(name, role, geometry, z, roads.get('fade_terminals', []), old_frame)
        old_name = 'SM_MPR4_Site_RoadTerminal'+suffix
        replacements.append(dict(old_mesh='/Game/MPRWarehouse/ReferenceV4/Site/Meshes/'+old_name+'.'+old_name,
                    new_mesh=name,
                    new_mesh_name=name, authorized_scope='Existing outside road terminal connection band and explicitly audited mouth stitches up to 0.12m inside the old raster edge; no old asset changes'))

    context = build_context(GEO, source, tx, protection, road_geometry, rail_geometry, water, frame,
                            ground_z=G, tile_size=TILE)
    for key in ('extension_roads', 'replacement_terminal_roads', 'curbs', 'white_edges', 'dash_lines'):
        intrusion = roads[key].intersection(old_frame.buffer(-.001)).difference(roads['mouth_stitches'])
        assert intrusion.area < 1e-5, ('Completed-frame intrusion beyond authorized mouth stitches', key, intrusion.area)
    assert water.intersection(protection).area < 1e-6
    assert all(r['protected_clearance_m'] >= .349 for r in context['audit']['buildings'])
    assert all(r['protected_clearance_m'] >= .349 for r in context['audit']['trees'])
    materials = copy.deepcopy(read(V4/'site/manifest.json')['materials'])
    materials.update(copy.deepcopy(context_style.MATERIALS))
    used_roles = {role for model in GEO.data.values() for role in model}
    materials = {role: materials[role] for role in sorted(used_roles)}
    textures = {}
    for spec in read(V4/'site/manifest.json')['materials'].values():
        if spec.get('texture') and spec.get('textures'):
            textures[spec['texture']] = spec['textures']
    readonly_paths = [V4/'site/manifest.json', V4/'context/manifest.json', V4/'site/plan_railway_v5.json',
                      V4/'site/plan_registration_v5.json', V4/'validation_blender/composition_instances.json']
    readonly_paths += [ROOT/path for item in textures.values() for path in item.values()]
    readonly_hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in set(readonly_paths)}
    fade_terminals = roads.get('fade_terminals', [])
    def fade(name, point):
        p = Point(point[:2])
        if 'ReplacementTerminal' in name:
            eligible = [r for r in fade_terminals if r.get('length_m', 0) > 0]
            if not eligible:
                return 0.0
            # Only retained disconnected survey-exterior tails keep their
            # original fade; new connection bands have no matching fade row.
            for row in eligible:
                origin, direction = row['origin_m'], row['direction']
                distance = (point[0]-origin[0])*direction[0]+(point[1]-origin[1])*direction[1]
                lateral = abs((point[0]-origin[0])*(-direction[1])+(point[1]-origin[1])*direction[0])
                if -.5 <= distance <= row['length_m']+.5 and lateral <= row['width_m']/2+.8:
                    return terminal_fade(row, point)
            return 0.0
        distance = frame.boundary.distance(p)
        t = max(0., min(1., 1-distance/30.))
        return t*t*(3-2*t)
    audit = dict(source_archive=archived, registration=registration,
                 source_frame=mapping(frame), completed_frame=mapping(old_frame),
                 protected_geometry=mapping(protection), mouth_stitches=mapping(roads['mouth_stitches']),
                 mouth_stitch_policy='Only per-mouth audited patches up to 0.12m; no whole-frame relaxation',
                 existing_buildings=mapping(baseline['buildings']),
                 existing_tree_clearance=mapping(baseline['trees']), existing_rails=mapping(baseline['rail']),
                 road_audit=roads['audit'], connections=roads.get('connections', []),
                 new_roads=mapping(roads['extension_roads']), replacement_roads=mapping(roads['replacement_terminal_roads']),
                 railway_audit=rail['stats'], railway_endpoints=rail['endpoint_audit'], grade_crossings=crossings,
                 grade_crossing_surface_mask=mapping(crossing_mask), grade_crossing_underlying_asphalt_removed=True, water=mapping(water),
                 context=context['audit'], readonly_input_hashes=readonly_hashes,
                 triangulation_repairs=dict(calls=len(TRIANGULATION_AUDIT),
                    source_area_m2=sum(r['source_area_m2'] for r in TRIANGULATION_AUDIT),
                    emitted_area_m2=sum(r['emitted_area_m2'] for r in TRIANGULATION_AUDIT),
                    absolute_area_change_m2=sum(r['absolute_area_change_m2'] for r in TRIANGULATION_AUDIT),
                    max_precision_m=max((r['precision_m'] for r in TRIANGULATION_AUDIT), default=0),
                    fallback_calls=[r for r in TRIANGULATION_AUDIT if r['repaired_after_errors']]),
                 metrics=dict(old_frame_m2=old_frame.area, source_frame_m2=frame.area,
                              added_frame_m2=frame.difference(protection).area, new_water_m2=water.area,
                              new_roads_m2=roads['extension_roads'].area),
                 limitations=['Current approved reference layout and new GIS positions have different peripheral geometry.',
                              'Old rail endpoints are extended along their unchanged tangents only; no original rail relocation.',
                              'Source terrain elevation is normalized to the current flat ground style.'])
    write(OUT/'geometry_audit.json', audit)
    write(OUT/'inputs/existing_geometry.json', {k: audit[k] for k in ('completed_frame', 'existing_buildings', 'existing_tree_clearance', 'existing_rails')})
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1
    core.OUT, core.GEO, core.MATERIALS, core.INSTANCES = OUT, GEO, materials, defaultdict(list, context['instances'])
    core.G, core.COUNTS = G, Counter({key: value for key, value in context['audit']['summary'].items() if isinstance(value, (int, float))})
    metadata = dict(extension_namespace='/Game/MPRWarehouse/ExtensionB50B57',
                    reused_meshes=context['reused_meshes'], allowed_replacements=replacements,
                    immutable_old_scene=True, readonly_materials=True,
                    source_input='inputs/topoexport-B50B57.blend', audit='geometry_audit.json',
                    source_blend_sha256=archived['topoexport-B50B57.blend']['sha256'])
    core.export(textures, metadata, vertex_fade=fade)
    generated = OUT/'MPR_ReferenceSite.blend'
    renamed = OUT/'MPR_ExtensionB50B57.blend'
    for image in bpy.data.images:
        if image.source == 'FILE' and image.filepath:
            image.filepath = bpy.path.relpath(bpy.path.abspath(image.filepath), start=str(OUT))
    bpy.ops.wm.save_as_mainfile(filepath=str(renamed))
    assert generated.resolve().parent == OUT.resolve()
    generated.unlink()
    manifest = read(OUT/'manifest.json')
    for row in manifest['meshes']:
        row['category'] = 'Context' if '_Context_' in row['name'] else 'Site'
        row['replacement_only'] = row['name'].startswith('SM_MPRE_ReplacementTerminal')
        row['full_precision_uvs'] = True
    manifest['blend'] = renamed.relative_to(ROOT).as_posix()
    manifest['source_generated_triangles'] = sum(r['triangles'] for r in manifest['meshes'])
    manifest['read_only_inputs_unchanged'] = all(sha(ROOT/p) == digest for p, digest in readonly_hashes.items())
    assert manifest['read_only_inputs_unchanged']
    assert sha(SOURCE_BLEND) == archived['topoexport-B50B57.blend']['sha256'] if SOURCE_BLEND.exists() else True
    write(OUT/'manifest.json', manifest)
    print('MPR_EXTENSION_BUILT', len(manifest['meshes']), manifest['source_generated_triangles'], context['audit']['summary'])


if __name__ == '__main__':
    main()
