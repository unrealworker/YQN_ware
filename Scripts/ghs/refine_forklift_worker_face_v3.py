"""Replace only the forklift worker's head/face with an adult neutral face.

No Blender startup, scene clearing, exports or automatic execution. Call
refine_face(scene, collection, materials) from the existing Blender session.
Coordinates are the original metre-space operator, looking toward +X.
"""

import bisect
import math

import bpy
from mathutils import Vector


def refine_face(scene, collection, materials):
    """Replace the specified face parts, preserving helmet, neck and body.

    The nose, cheeks, chin, lips and eye sockets are sculpted into one closed
    surface. Small eyes use muted ivory, skin-coloured eyelids and dark brown
    irises. Repeated calls replace this module's own parts without duplicating
    them. Returns a geometry/change report. No mesh modifiers are needed.
    """
    if collection is None or "Skin" not in materials:
        raise ValueError("A driver collection and Skin material are required")
    existing = list(collection.all_objects)
    head = next((o for o in existing if o.type == "MESH"
                 and o.name.split(".")[0] == "DRV_Head"), None)
    if head is None:
        raise ValueError("DRV_Head was not found in the provided collection")
    world_matrix = head.matrix_world.copy()
    original_parent = head.parent
    replace_names = {"DRV_Head", "DRV_Nose", "DRV_MouthLine", "DRV_LowerLip"}
    for side in ("Right", "Left"):
        for part in ("Ear", "EarFold", "EyeSocket", "Eye", "Pupil",
                     "UpperLid", "LowerLid", "Eyebrow", "Nostril"):
            replace_names.add("DRV_" + side + part)
    to_remove = [o for o in existing
                 if o.name.split(".")[0] in replace_names
                 or o.name.startswith("DRV_FaceV3_")]
    untouched = [o.name for o in existing if o not in to_remove]
    made = []
    skin = materials["Skin"]

    def skin_colour():
        if skin.use_nodes and skin.node_tree:
            shader = next((n for n in skin.node_tree.nodes
                           if n.type == "BSDF_PRINCIPLED"), None)
            if shader:
                return tuple(shader.inputs["Base Color"].default_value[:3])
        return tuple(skin.diffuse_color[:3])

    base = skin_colour()

    def derived(name, colour, roughness=.66):
        name = "DRV_FaceV3_" + name
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        shader.inputs["Base Color"].default_value = (*colour, 1)
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Metallic"].default_value = 0
        if "Specular IOR Level" in shader.inputs:
            shader.inputs["Specular IOR Level"].default_value = .25
        mat.diffuse_color = (*colour, 1)
        return mat

    skin_shade = derived("SkinShade", tuple(c*.80 for c in base))
    lip_colour = tuple(c*.75 + r*.25 for c, r in zip(base, (.25, .095, .075)))
    lip_mat = derived("Lips", lip_colour)
    crease_mat = derived("SoftCrease", tuple(c*.52 for c in base))
    brow_mat = derived("Brows", (.027, .020, .016), .88)
    sclera_mat = derived("MutedIvory", (.31, .285, .25), .43)
    iris_mat = derived("BrownIris", (.055, .036, .020), .46)
    pupil_mat = derived("Pupil", (.010, .008, .006), .40)

    def mesh(name, verts, faces, material, smooth=True):
        data = bpy.data.meshes.new("DRV_FaceV3_" + name + "_Mesh")
        data.from_pydata(verts, [], faces)
        data.update()
        obj = bpy.data.objects.new("DRV_FaceV3_" + name, data)
        collection.objects.link(obj)
        data.materials.append(material)
        for polygon in data.polygons:
            polygon.use_smooth = smooth
        obj.parent = original_parent
        obj.matrix_world = world_matrix.copy()
        obj["Assembly"] = "Seated operator"
        obj["WorkerFaceVersion"] = 3
        obj["Units"] = "metres"
        made.append(obj)
        return obj

    def gaussian(y, z, cy, cz, sy, sz):
        return math.exp(-.5*((y-cy)/sy)**2 - .5*((z-cz)/sz)**2)

    # z, frontal X, occipital X, half-width Y. Jaw corners remain broad;
    # the forehead and cheek planes are flatter than an egg-shaped sphere.
    profile = [
        (1.681, -.341, -.443, .028),
        (1.695, -.313, -.459, .044),
        (1.711, -.301, -.478, .058),
        (1.730, -.303, -.493, .069),
        (1.754, -.305, -.505, .074),
        (1.784, -.305, -.516, .080),
        (1.815, -.308, -.521, .079),
        (1.846, -.306, -.520, .079),
        (1.872, -.305, -.516, .078),
        (1.897, -.312, -.507, .074),
        (1.919, -.337, -.490, .061),
        (1.936, -.393, -.444, .025),
    ]
    heights = [p[0] for p in profile]

    def shape_at(z):
        z = max(heights[0], min(heights[-1], z))
        i = max(0, min(len(profile)-2, bisect.bisect_right(heights, z)-1))
        a, b = profile[i], profile[i+1]
        span = b[0]-a[0]
        t = (z-a[0])/span
        values = []
        for axis in (1, 2, 3):
            lower = profile[max(0, i-1)]
            upper = profile[min(len(profile)-1, i+2)]
            m0 = (b[axis]-lower[axis])/(b[0]-lower[0])
            m1 = (upper[axis]-a[axis])/(upper[0]-a[0])
            value = ((2*t**3-3*t*t+1)*a[axis]
                     + (t**3-2*t*t+t)*span*m0
                     + (-2*t**3+3*t*t)*b[axis]
                     + (t**3-t*t)*span*m1)
            values.append(value)
        return values

    def face_displacement(y, z):
        # Integrated rounded nose: a bridge, fleshy tip and two broad alae.
        out = .019*gaussian(y, z, 0, 1.816, .0095, .030)
        out += .030*gaussian(y, z, 0, 1.785, .0115, .0100)
        for side in (-1, 1):
            out += .014*gaussian(y, z, side*.0145, 1.780, .0070, .0070)
            out -= .0055*gaussian(y, z, side*.034, 1.830, .017, .010)
            out += .0042*gaussian(y, z, side*.033, 1.849, .020, .0075)
            out += .0070*gaussian(y, z, side*.049, 1.793, .018, .016)
            out -= .0014*gaussian(y, z, side*.027, 1.764, .0065, .014)
        out += .0035*gaussian(y, z, 0, 1.747, .030, .013)
        out += .0020*gaussian(y, z, 0, 1.751, .020, .0034)
        out += .0023*gaussian(y, z, 0, 1.741, .020, .0037)
        out -= .0015*gaussian(y, z, 0, 1.747, .022, .0015)
        out += .0050*gaussian(y, z, 0, 1.711, .032, .013)
        return out

    def front_x(y, z):
        front, back, width = shape_at(z)
        c = math.sqrt(max(0, 1-(y/max(width, .001))**2))
        # Flatten the facial plane with a polynomial whose derivative matches
        # the back half at the temples; a fractional power makes a hard seam.
        flattened = c + .65*c*c*(1-c)
        x = (front+back)*.5 + (front-back)*.5*flattened
        fade = min(1, (c/.35)**2)
        return x + face_displacement(y, z)*fade

    def surface_point(y, z, offset=0):
        return (front_x(y, z)+offset, y, z)

    def line(name, points, radii, material, sides=6):
        verts = []
        pp = [Vector(p) for p in points]
        for i, point in enumerate(pp):
            tangent = (pp[min(i+1, len(pp)-1)]-pp[max(i-1, 0)]).normalized()
            u = Vector((1, 0, 0))
            u = (u-tangent*u.dot(tangent)).normalized()
            v = tangent.cross(u).normalized()
            r = radii[i] if isinstance(radii, (list, tuple)) else radii
            for k in range(sides):
                angle = 2*math.pi*k/sides
                verts.append(tuple(point+u*(r*math.cos(angle))+v*(r*math.sin(angle))))
        faces = [tuple(reversed(range(sides)))]
        for i in range(len(pp)-1):
            for k in range(sides):
                n = (k+1) % sides
                faces.append((i*sides+k, i*sides+n, (i+1)*sides+n, (i+1)*sides+k))
        faces.append(tuple((len(pp)-1)*sides+k for k in range(sides)))
        return mesh(name, verts, faces, material)

    def surface_oval(name, cy, cz, ry, rz, offset, material, steps=20, bulge=.0004):
        verts = [surface_point(cy, cz, offset+bulge)]
        for i in range(steps):
            angle = 2*math.pi*i/steps
            verts.append(surface_point(cy+ry*math.cos(angle),
                                       cz+rz*math.sin(angle), offset))
        # Surface faces point along +X.
        return mesh(name, verts, [(0, i+1, (i+1) % steps+1) for i in range(steps)], material)

    try:
        # More samples on the face than on the back of the head. This keeps
        # integrated nose and sockets smooth without a dense full character.
        angles = [-math.pi/2 + math.pi*i/72 for i in range(72)]
        angles += [math.pi/2 + math.pi*i/24 for i in range(24)]
        ring_count, radial_count = 84, len(angles)
        vertices = []
        for j in range(ring_count):
            z = heights[0] + (heights[-1]-heights[0])*j/(ring_count-1)
            front, back, width = shape_at(z)
            for theta in angles:
                c = math.cos(theta)
                y = width*math.sin(theta)
                x = front_x(y, z) if c >= -1e-8 else (front+back)*.5+(front-back)*.5*c
                vertices.append((x, y, z))
        faces = []
        for j in range(ring_count-1):
            for i in range(radial_count):
                n = (i+1) % radial_count
                faces.append((j*radial_count+i, j*radial_count+n,
                              (j+1)*radial_count+n, (j+1)*radial_count+i))
        for ring, reverse in ((0, True), (ring_count-1, False)):
            pts = vertices[ring*radial_count:(ring+1)*radial_count]
            centre = tuple(sum(v[k] for v in pts)/len(pts) for k in range(3))
            index = len(vertices)
            vertices.append(centre)
            for i in range(radial_count):
                a, b = ring*radial_count+i, ring*radial_count+(i+1) % radial_count
                faces.append((index, b, a) if reverse else (index, a, b))
        new_head = mesh("Head", vertices, faces, skin)

        for side, label in ((-1, "Right"), (1, "Left")):
            cy, cz = side*.034, 1.830
            # Almond-shaped opening, substantially smaller and less white
            # than the former reflective eye overlays.
            steps = 24
            verts = [surface_point(cy, cz, .0016)]
            contour = []
            for i in range(steps):
                a = 2*math.pi*i/steps
                y = cy + .0135*math.cos(a)
                z = cz + (.0035 if math.sin(a) >= 0 else .0027)*math.sin(a)
                p = surface_point(y, z, .0009)
                contour.append(p)
                verts.append(p)
            mesh(label+"Eye", verts,
                 [(0, i+1, (i+1) % steps+1) for i in range(steps)], sclera_mat)
            surface_oval(label+"Iris", cy, cz, .0037, .0030, .0019, iris_mat)
            surface_oval(label+"Pupil", cy, cz, .0016, .0020, .00245, pupil_mat, 16, .0002)
            # Thin eyelids cover the eye border with actual skin geometry.
            upper = []
            lower = []
            for i in range(13):
                t = i/12
                y = cy-.0135+.027*t
                upper.append(surface_point(y, cz+.0035*math.sin(math.pi*t), .0010))
                lower.append(surface_point(y, cz-.0027*math.sin(math.pi*t), .0010))
            line(label+"UpperLid", upper, [.00035+.00065*math.sin(math.pi*i/12)
                                           for i in range(13)], skin, 6)
            line(label+"LowerLid", lower, .00065, skin, 6)
            # Eyebrows are soft tapered patches, with no oversized black bars.
            bv, bf = [], []
            for i in range(13):
                t = i/12
                y = side*(.019+.036*t)
                z = 1.848+.0040*math.sin(math.pi*t)-.0013*t
                half = .00035+.0011*math.sin(math.pi*t)**.6
                bv += [surface_point(y, z-half, .0009),
                       surface_point(y, z+half, .0010)]
                if i:
                    face = (2*i-2, 2*i, 2*i+1, 2*i-1)
                    bf.append(face if side > 0 else tuple(reversed(face)))
            mesh(label+"Eyebrow", bv, bf, brow_mat)
            surface_oval(label+"Nostril", side*.0128, 1.7755,
                         .0032, .0015, .0007, crease_mat, 16, .0001)

            # Ears are a closed smooth pinna, not bare spheres at the temples.
            # The outer ridge is part of the surface, with a recessed concha.
            ear_verts = [(-.418, side*.089, 1.803)]
            ear_faces = []
            segments, bands = 24, 12
            for j in range(1, bands):
                theta = math.pi*j/bands
                for k in range(segments):
                    a = 2*math.pi*k/segments
                    r = math.sin(theta)
                    x = -.418+.019*r*math.cos(a)
                    z = 1.803+.032*r*math.sin(a)
                    outward = .012*math.cos(theta)
                    if theta < math.pi/2:
                        outward += .003*math.exp(-((r-.78)/.16)**2)
                        outward -= .003*math.exp(-(r/.40)**2)
                    y = side*(.080+outward)
                    ear_verts.append((x, y, z))
            ear_verts.append((-.418, side*.068, 1.803))
            for k in range(segments):
                n = (k+1) % segments
                f = (0, 1+n, 1+k)
                ear_faces.append(f if side > 0 else tuple(reversed(f)))
            for j in range(bands-2):
                for k in range(segments):
                    n = (k+1) % segments
                    f = (1+j*segments+k, 1+j*segments+n,
                         1+(j+1)*segments+n, 1+(j+1)*segments+k)
                    ear_faces.append(f if side > 0 else tuple(reversed(f)))
            base = 1+(bands-2)*segments
            for k in range(segments):
                n = (k+1) % segments
                f = (base+k, base+n, len(ear_verts)-1)
                ear_faces.append(f if side > 0 else tuple(reversed(f)))
            mesh(label+"Ear", ear_verts, ear_faces, skin)

        # Neutral closed lips: a subdued crease and softly coloured lower lip.
        mouth, radii = [], []
        for i in range(25):
            y = -.024+.048*i/24
            z = 1.747+.0012*(1-(y/.024)**2)-.0009*math.exp(-(y/.007)**2)
            mouth.append(surface_point(y, z, .0007))
            radii.append(.00025+.00040*math.sin(math.pi*i/24))
        line("MouthCrease", mouth, radii, crease_mat, 6)
        lipv, lipf = [], []
        for i in range(25):
            y = -.023+.046*i/24
            fade = math.sin(math.pi*i/24)
            z = 1.7425-.0004*(1-fade)
            lipv += [surface_point(y, z-.0013*fade, .00035),
                     surface_point(y, z+.0011*fade, .0004)]
            if i:
                lipf.append((2*i-2, 2*i, 2*i+1, 2*i-1))
        mesh("LowerLip", lipv, lipf, lip_mat)

        # Validate the replacement before removing any existing geometry.
        triangle_count = sum(sum(len(p.vertices)-2 for p in o.data.polygons)
                             for o in made)
        if triangle_count > 21000:
            raise RuntimeError("Face triangle budget unexpectedly exceeded")
        if any(not math.isfinite(c) for o in made for v in o.data.vertices for c in v.co):
            raise RuntimeError("Non-finite face coordinates")
        removed = [o.name for o in to_remove]
        for obj in to_remove:
            bpy.data.objects.remove(obj, do_unlink=True)
        new_head.name = "DRV_Head"
        bounds = [[min(v.co[k] for o in made for v in o.data.vertices),
                   max(v.co[k] for o in made for v in o.data.vertices)] for k in range(3)]
        return {"version": 3, "removed": removed, "created": [o.name for o in made],
                "triangles": triangle_count, "local_bounds_metres": bounds,
                "preserved_objects": len(untouched),
                "helmet_neck_body_unchanged": True,
                "integrated_face_surface": True}
    except Exception:
        # A generation error leaves the previous head in the scene.
        for obj in made:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        raise

