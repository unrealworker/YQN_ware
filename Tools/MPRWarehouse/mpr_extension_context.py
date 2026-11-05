"""Additive Topoexport context: exact footprint shells and read-only oak reuse.

This module never opens/saves a Blender file or writes a UE package. The caller
owns extraction, registration, protection geometry, export and import. All
world coordinates are CAD metres; UE applies the Y reflection at import only.
"""
from collections import Counter, defaultdict
import hashlib
import math

from shapely.geometry import GeometryCollection, MultiPoint, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import triangulate, unary_union


TREE_NAME = "SM_MPR4_Tree_Oak"
TREE_PATH = "/Game/MPRWarehouse/ReferenceV4/Props/Meshes/" + TREE_NAME
TREE_RADIAL_EXTENT_M = 6.418041146908877
ROLES = dict(wall="MPR4_ContextWall", roof="MPR4_ContextRoof",
             trim="MPR4_ContextTrim", glass="MPR4_ContextGlass",
             paving="MPR4_ContextPaving")


def _polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if hasattr(geometry, "geoms"):
        return [p for child in geometry.geoms for p in _polygons(child)]
    return []


def source_footprint(row, transform_xy):
    """Union projected source triangles, retaining concavities and courtyards.

    Roof/base triangulation supplies the horizontal coverage. Vertical faces
    collapse to lines and are discarded, never replaced with a convex hull.
    """
    points = [tuple(map(float, transform_xy(v[:2]))) for v in row["vertices"]]
    pieces = []
    for face in row["faces"]:
        if len(face) < 3:
            continue
        polygon = Polygon([points[i] for i in face])
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.area > 1e-7:
            pieces.extend(_polygons(polygon))
    if not pieces:
        return GeometryCollection()
    # Only sub-millimetre coordinate noise may be removed, never shape detail.
    return unary_union(pieces).buffer(0).simplify(.0002, preserve_topology=True)


def _stable_unit(name, salt=""):
    return int.from_bytes(hashlib.sha256((name + salt).encode()).digest()[:4],
                          "little") / 4294967295.0


def _tile(x, y, tile_size):
    return math.floor(x / tile_size), math.floor(y / tile_size)


def _merge(target, model, name, origin=(0, 0, 0), yaw=0):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    ox, oy, oz = origin
    for roles in model.data.values():
        for role, (vertices, faces) in roles.items():
            target.mesh(name, role, [(ox + c*x - s*y, oy + s*x + c*y, oz+z)
                                     for x, y, z in vertices], faces)


def _envelope(model, origin=(0, 0, 0), yaw=0):
    """Conservative occupancy of ALL roof, porch, door and trim geometry."""
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    x, y, _ = origin
    return MultiPoint([(x+c*vx-s*vy, y+s*vx+c*vy)
                       for roles in model.data.values()
                       for vertices, _ in roles.values()
                       for vx, vy, _ in vertices]).convex_hull


def _rectangle(polygon):
    points = list(polygon.minimum_rotated_rectangle.exterior.coords)[:-1]
    a, b, d = points[0], points[1], points[3]
    w, depth = math.dist(a, b), math.dist(a, d)
    yaw = math.degrees(math.atan2(b[1]-a[1], b[0]-a[0]))
    if depth > w:
        w, depth = depth, w
        yaw += 90
    center = list(polygon.minimum_rotated_rectangle.centroid.coords)[0]
    return center, w, depth, yaw


def _extrude(geo, name, polygon, height, *, windows=True):
    """Closed shell including inner courtyard walls; no bridged concavities."""
    polygon = orient(polygon, sign=1.0)
    for tri in triangulate(polygon):
        if not polygon.covers(tri):
            continue
        pts = list(orient(tri, sign=1.0).exterior.coords)[:-1]
        geo.mesh(name, ROLES["roof"], [(x, y, height) for x, y in pts], [(0, 1, 2)])
        geo.mesh(name, ROLES["wall"], [(x, y, 0) for x, y in pts], [(2, 1, 0)])
    for ring in [polygon.exterior, *polygon.interiors]:
        pts = list(ring.coords)
        for a, b in zip(pts, pts[1:]):
            geo.mesh(name, ROLES["wall"],
                     [(a[0], a[1], 0), (b[0], b[1], 0),
                      (b[0], b[1], height), (a[0], a[1], height)], [(0, 1, 2, 3)])
            geo.segment(name, ROLES["trim"], a, b, .13, height+.04, .13)
            length = math.dist(a, b)
            if length < 4 or not windows:
                continue
            # Quiet repeated facade recesses follow the measured facade, not
            # a global grid. No windows are generated on very short edges.
            tx, ty = (b[0]-a[0])/length, (b[1]-a[1])/length
            nx, ny = ty, -tx
            yaw = math.degrees(math.atan2(ty, tx))
            count = max(1, min(20, int(length/5)))
            for index in range(count):
                distance = length*(index+.5)/count
                x, y = a[0]+tx*distance+nx*.025, a[1]+ty*distance+ny*.025
                z = min(2.4, height*.55)
                width, high = min(1.7, length/count*.48), min(1.25, height*.3)
                geo.box(name, ROLES["trim"], (x, y, z), (width+.12, .065, high+.12), yaw)
                geo.box(name, ROLES["glass"], (x+nx*.04, y+ny*.04, z), (width, .026, high), yaw)


def build_context(geo, source, transform_xy, protected_geometry, road_geometry,
                  rail_geometry, water_geometry, source_frame_geometry, *,
                  ground_z=-1.2, tile_size=150.0):
    """Write new buildings into ``geo`` and return oak instances plus audit.

    Whole objects touching completed geometry are rejected, never cut into
    partial houses. Transport/water inputs must include both old and new
    coverage. The protection geometry must include existing terminal fades.
    Caller may additionally protect an entirely read-only transition band.
    """
    from mpr_blender_common import Geometry
    import build_mpr_reference_context_v4 as style

    objects = source["objects"] if isinstance(source, dict) else source
    protection = protected_geometry.buffer(.35)
    roads = road_geometry.buffer(.65)
    rail = rail_geometry.buffer(.8)
    water = water_geometry.buffer(.5)
    frame = source_frame_geometry
    blockers = unary_union([roads, rail, water])
    audit = dict(schema_version=1, policy="Completed area and all existing assets are immutable; whole-object rejection; source footprints retained",
                 ground_z_m=ground_z, tile_size_m=tile_size,
                 materials_read_only=list(ROLES.values()),
                 buildings=[], trees=[], rejected_buildings=[], rejected_trees=[])
    raw_buildings = []
    for row in objects:
        if row.get("layer") != "TPX_BUILDINGS":
            continue
        footprint = source_footprint(row, transform_xy)
        raw_buildings.append((row, footprint))
    occupied = []
    before_triangles = sum(sum(len(f)-2 for f in faces) for roles in geo.data.values()
                           for _, faces in roles.values())
    for row, footprint in raw_buildings:
        source_id = row["name"]
        reason = None
        if footprint.is_empty or footprint.area < 3:
            reason = "empty_or_tiny_source"
        elif footprint.intersects(protection):
            reason = "completed_area"
        elif not frame.covers(footprint.buffer(.3)):
            reason = "source_frame_edge"
        elif footprint.intersects(blockers):
            reason = "transport_or_water_conflict"
        if reason:
            audit["rejected_buildings"].append(dict(source_id=source_id, reason=reason))
            continue
        model = Geometry()
        polys = _polygons(footprint)
        zs = [v[2] for v in row["vertices"]]
        # Source heights are preserved; only ground elevation is normalized to
        # the existing flat diorama. No completed terrain is touched.
        height = max(zs)-min(zs)
        if height < .2:
            audit["rejected_buildings"].append(dict(source_id=source_id, reason="missing_source_height"))
            continue
        origin, yaw, kind = (0, 0, ground_z), 0, "source_footprint_shell"
        if len(polys) == 1 and not polys[0].interiors:
            polygon = polys[0]
            center, width, depth, proposed_yaw = _rectangle(polygon)
            rectangularity = polygon.area / polygon.minimum_rotated_rectangle.area
            if (rectangularity > .982 and 5 <= depth <= 16 and width <= 30
                    and footprint.area < 420 and 3.5 <= height <= 13):
                previous = style.G
                try:
                    style.G = model
                    # Same low-poly house implementation as the completed
                    # context. Compact porch avoids altering road footprints.
                    ridge = height
                    eave = max(2.65, ridge-min(2.3, depth*.23))
                    style.house(source_id, width, depth, eave, ridge,
                                variant=int(_stable_unit(source_id)*2), compact=True)
                finally:
                    style.G = previous
                origin, yaw, kind = (center[0], center[1], ground_z), proposed_yaw, "existing_house_style"
        if not model.data:
            for polygon in polys:
                circular = (4*math.pi*polygon.area/polygon.length**2 > .94
                            and polygon.area > 120
                            and len(polygon.exterior.coords) > 12)
                _extrude(model, source_id, polygon, height, windows=not circular)
                if circular:
                    kind = "source_tank_shell"
                    for a, b in zip(polygon.exterior.coords, list(polygon.exterior.coords)[1:]):
                        model.segment(source_id, ROLES["trim"], a, b, .15, .10, .18)
        envelope = _envelope(model, origin, yaw)
        collision = (envelope.intersects(protection) or envelope.intersects(blockers)
                     or not frame.covers(envelope))
        if collision and kind == "existing_house_style":
            # Source building may be safe while a style porch/eave is not.
            # Fall back to its exact shell instead of moving the building.
            model = Geometry()
            for polygon in polys:
                _extrude(model, source_id, polygon, height)
            origin, yaw, kind = (0, 0, ground_z), 0, "source_footprint_shell"
            envelope = _envelope(model, origin, yaw)
            collision = (envelope.intersects(protection) or envelope.intersects(blockers)
                         or not frame.covers(envelope))
        if collision:
            audit["rejected_buildings"].append(dict(source_id=source_id, reason="full_geometry_clearance"))
            continue
        cx, cy = footprint.centroid.coords[0]
        tile = _tile(cx, cy, tile_size)
        mesh_name = "SM_MPRE_Context_%d_%d" % tile
        _merge(geo, model, mesh_name, origin, yaw)
        occupied.append(envelope)
        audit["buildings"].append(dict(source_id=source_id, mesh=mesh_name, tile=list(tile),
                    kind=kind, height_m=height, source_footprint_area_m2=footprint.area,
                    source_footprints_m=[list(poly.exterior.coords) for poly in polys],
                    full_geometry_envelope_m=list(envelope.exterior.coords),
                    protected_clearance_m=envelope.distance(protected_geometry),
                    transport_clearance_m=envelope.distance(unary_union([road_geometry, rail_geometry])),
                    rigid_rotation_deg=yaw))

    # Include all source building footprints, even rejected ones: never place
    # a new tree into an unsupported/partly protected building footprint.
    tree_blockers = unary_union([protection, roads, rail, water,
                                unary_union([fp for _, fp in raw_buildings]),
                                unary_union(occupied)])
    tree_instances = []
    accepted_centres = []
    for row in objects:
        if row.get("layer") != "TPX_VEGETATION_TREES_INDIVIDUAL":
            continue
        source_id = row["name"]
        position = row.get("position", [r[3] for r in row["matrix"][:3]])
        x, y = map(float, transform_xy(position[:2]))
        # 10.9–17.0 m tall with the same full oak silhouette; stable per ID.
        scale = .69 + .38*_stable_unit(source_id, "scale")
        radius = TREE_RADIAL_EXTENT_M*scale
        crown = Point(x, y).buffer(radius+.25, quad_segs=16)
        reason = None
        if crown.intersects(protection):
            reason = "completed_area"
        elif not frame.covers(crown):
            reason = "source_frame_edge"
        elif crown.intersects(tree_blockers):
            reason = "crown_transport_water_building_clearance"
        elif any(math.hypot(x-ax, y-ay) < (radius+ar)*.57 for ax, ay, ar in accepted_centres):
            reason = "duplicate_or_crowded_canopy"
        if reason:
            audit["rejected_trees"].append(dict(source_id=source_id, reason=reason))
            continue
        tile = _tile(x, y, tile_size)
        tree_instances.append(dict(position_m=[x, y, ground_z+.01],
                    rotation_deg=360*_stable_unit(source_id, "yaw"), scale=[scale]*3,
                    source_id=source_id, tile=list(tile), crown_radius_m=radius))
        accepted_centres.append((x, y, radius))
        audit["trees"].append(dict(source_id=source_id, position_m=[x, y, ground_z+.01],
                    crown_radius_m=radius, protected_clearance_m=crown.distance(protected_geometry)))
    after_triangles = sum(sum(len(f)-2 for f in faces) for roles in geo.data.values()
                          for _, faces in roles.values())
    audit["summary"] = dict(source_buildings=len(raw_buildings),
                    buildings_added=len(audit["buildings"]),
                    buildings_rejected=dict(Counter(r["reason"] for r in audit["rejected_buildings"])),
                    source_trees=sum(o.get("layer") == "TPX_VEGETATION_TREES_INDIVIDUAL" for o in objects),
                    trees_added=len(tree_instances),
                    trees_rejected=dict(Counter(r["reason"] for r in audit["rejected_trees"])),
                    context_mesh_tiles=len({b["mesh"] for b in audit["buildings"]}),
                    tree_hism_tiles=len({tuple(r["tile"]) for r in tree_instances}),
                    building_triangles=after_triangles-before_triangles,
                    newly_created_tree_meshes=0,
                    old_resources_modified=0)
    return dict(instances={TREE_NAME: tree_instances}, reused_meshes={TREE_NAME: TREE_PATH}, audit=audit)
