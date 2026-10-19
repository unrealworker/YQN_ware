"""Limited exterior refinement of the existing seated forklift operator.

Call refine_driver(scene, collection, materials) after building/loading the
DRV_ meshes. This module does not execute itself, alter the pose, add interior
detail, run exports, or touch UE. Object transforms and material assignments
are preserved. The operation is idempotent and uses no context operators.
"""

import math

import bpy
from mathutils import Vector


def refine_driver(scene, collection, materials):
    """Round the worker's major silhouettes and return a small QA report.

    Reconstructs the original ring-based surfaces with a smooth interpolating
    spline. Unlike unconstrained subdivision, this retains every original
    cross-section sample, so the face landmarks, wrist endpoints, trouser
    cuffs, seat contact, and helmet clearance remain in place.
    """
    if collection is None:
        raise ValueError("A driver-containing collection is required")
    report = {"version": 2, "changed": [], "already_refined": [], "skipped": []}
    candidates = [o for o in collection.all_objects
                  if o.type == "MESH" and o.name.startswith("DRV_")]

    def catmull(a, b, c, d, t):
        # Uniform cubic interpolation with exact interpolation at t=0 and 1.
        t2, t3 = t*t, t*t*t
        return (b*2 + (c-a)*t + (a*2-b*5+c*4-d)*t2
                + (-a+b*3-c*3+d)*t3) * .5

    def resample(obj, sides, rings, vertical_steps=3, radial_steps=2):
        if obj.get("DriverExteriorRefinement", 0) >= 2:
            report["already_refined"].append(obj.name)
            return
        expected = sides*rings
        if len(obj.data.vertices) != expected:
            report["skipped"].append({"object": obj.name,
                                      "reason": "Original ring topology was edited",
                                      "expected_vertices": expected,
                                      "actual_vertices": len(obj.data.vertices)})
            return

        previous = obj.data
        source = [[previous.vertices[r*sides+i].co.copy() for i in range(sides)]
                  for r in range(rings)]
        z_min = min(v.z for ring in source for v in ring)
        z_max = max(v.z for ring in source for v in ring)
        new_sides = sides*radial_steps
        new_rings = (rings-1)*vertical_steps+1

        def radial_sample(r, u):
            r = max(0, min(rings-1, r))
            i = int(math.floor(u))
            fraction = u-i
            row = source[r]
            return catmull(row[(i-1) % sides], row[i % sides],
                           row[(i+1) % sides], row[(i+2) % sides], fraction)

        verts = []
        for j in range(new_rings):
            v = j/vertical_steps
            r = min(int(math.floor(v)), rings-2)
            fraction = v-r
            for i in range(new_sides):
                u = i/radial_steps
                point = catmull(radial_sample(r-1, u), radial_sample(r, u),
                                radial_sample(r+1, u), radial_sample(r+2, u),
                                fraction)
                # Cubic interpolation can exceed an end ring by millimetres;
                # keep original head/helmet heights and all garment endpoints.
                point.z = min(z_max, max(z_min, point.z))
                verts.append(tuple(point))
        faces = []
        for j in range(new_rings-1):
            for i in range(new_sides):
                n = (i+1) % new_sides
                faces.append((j*new_sides+i, j*new_sides+n,
                              (j+1)*new_sides+n, (j+1)*new_sides+i))
        side_faces = len(faces)
        # Close the mesh with planar fans; no large ngon shading artefacts.
        for end, reverse in ((0, True), (new_rings-1, False)):
            centre = sum((Vector(verts[end*new_sides+i])
                          for i in range(new_sides)), Vector()) / new_sides
            centre_index = len(verts)
            verts.append(tuple(centre))
            for i in range(new_sides):
                a = end*new_sides+i
                b = end*new_sides+(i+1) % new_sides
                faces.append((centre_index, b, a) if reverse
                             else (centre_index, a, b))

        data = bpy.data.meshes.new(obj.name + "_ExteriorV2")
        data.from_pydata(verts, [], faces)
        data.update()
        for mat in previous.materials:
            data.materials.append(mat)
        for i, polygon in enumerate(data.polygons):
            polygon.use_smooth = i < side_faces
        obj.data = data
        obj["DriverExteriorRefinement"] = 2
        obj["ExteriorRefinementDescription"] = "Smooth silhouette; original pose retained"
        report["changed"].append({"object": obj.name,
                                  "vertices_before": len(previous.vertices),
                                  "vertices_after": len(data.vertices)})

    # Only large, externally visible forms. Hands, fingers, feet, facial
    # features, pockets and interior-related parts are deliberately untouched.
    specifications = {
        "DRV_Head": (24, 8, 3, 2),
        "DRV_WorkJacket": (24, 7, 3, 2),
        "DRV_HiVisVest": (24, 4, 3, 2),
        "DRV_TrouserSeat": (20, 4, 3, 2),
        "DRV_RightSleeve": (16, 8, 3, 2),
        "DRV_LeftSleeve": (16, 8, 3, 2),
        "DRV_RightTrouserLeg": (16, 8, 3, 2),
        "DRV_LeftTrouserLeg": (16, 8, 3, 2),
        "DRV_SafetyHelmetShell": (32, 6, 4, 2),
        "DRV_SafetyHelmetBrim": (32, 3, 2, 2),
    }
    for obj in candidates:
        canonical_name = obj.name.split(".")[0]
        spec = specifications.get(canonical_name)
        if spec:
            resample(obj, *spec)
        elif canonical_name.startswith("DRV_HelmetRidge"):
            # A single smoothing pass rounds the existing three ribs; it adds
            # no new part and is a convex interpolation, so cannot raise them.
            modifier = obj.modifiers.get("Exterior rib smoothing")
            if modifier is None:
                modifier = obj.modifiers.new("Exterior rib smoothing", "SUBSURF")
                modifier.subdivision_type = "CATMULL_CLARK"
                modifier.levels = 1
                modifier.render_levels = 1
                report["changed"].append({"object": obj.name,
                                          "adjustment": "Round existing helmet ridge"})
        elif canonical_name == "DRV_Nose":
            # Keep the existing nose location and basic mesh. Softer edge
            # normals prevent its tiny facets reading as a block at distance.
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
            for modifier in obj.modifiers:
                if modifier.type == "BEVEL":
                    modifier.segments = max(3, modifier.segments)

    report["base_triangles"] = sum(sum(len(p.vertices)-2 for p in o.data.polygons)
                                    for o in candidates)
    report["pose_unchanged"] = True
    report["new_objects"] = 0
    return report

