"""Seated industrial forklift operator, metres, facing local +X.

Import this module, then call ``build_driver(scene, collection, materials)``.
No scene clearing, context-dependent operators, new materials, or exports.
Every resulting mesh is independent, prefixed DRV_, and linked only to the
provided collection. The caller owns saving, applying modifiers, and export.
"""

import math

import bpy
from mathutils import Vector


def build_driver(scene, collection, materials):
    """Build a seated worker with PPE and return the new mesh objects.

    Required material keys: Cloth, Navy, Safety, Reflective, Skin, Rubber,
    Helmet, Dark, Metal. Geometry is designed for a cushion at Z=1.00 m,
    wheel centre (0.10, 0, 1.25), and canopy underside at Z=2.13 m.
    """
    required = ("Cloth", "Navy", "Safety", "Reflective", "Skin", "Rubber",
                "Helmet", "Dark", "Metal")
    for key in required:
        if key not in materials:
            raise KeyError("Driver material missing: " + key)
    made = []

    def mesh(name, vertices, faces, mat, smooth=True, bevel=0):
        data = bpy.data.meshes.new("DRV_" + name + "_Mesh")
        data.from_pydata(vertices, [], faces)
        data.update()
        obj = bpy.data.objects.new("DRV_" + name, data)
        collection.objects.link(obj)
        data.materials.append(materials[mat])
        for polygon in data.polygons:
            polygon.use_smooth = smooth
        if bevel:
            modifier = obj.modifiers.new("Soft manufactured edges", "BEVEL")
            modifier.width = bevel
            modifier.segments = 2
        obj["Assembly"] = "Seated operator"
        made.append(obj)
        return obj

    def loft(name, rings, mat, sides=16, exponent=1.0, bevel=0):
        # Horizontal rings: centre xyz, half-depth X, half-width Y.
        verts = []
        for centre, rx, ry in rings:
            cx, cy, cz = centre
            for i in range(sides):
                t = 2 * math.pi * i / sides
                c, s = math.cos(t), math.sin(t)
                px = math.copysign(abs(c) ** exponent, c)
                py = math.copysign(abs(s) ** exponent, s)
                verts.append((cx + rx * px, cy + ry * py, cz))
        faces = [tuple(reversed(range(sides)))]
        for j in range(len(rings) - 1):
            for i in range(sides):
                n = (i + 1) % sides
                faces.append((j*sides+i, j*sides+n,
                              (j+1)*sides+n, (j+1)*sides+i))
        faces.append(tuple((len(rings)-1)*sides+i for i in range(sides)))
        return mesh(name, verts, faces, mat, True, bevel)

    def limb(name, stations, mat, sides=12):
        # Each station is (xyz, radius in the XZ plane, width along Y).
        # Smooth lofts across elbows/knees avoid exposed spherical joints.
        verts = []
        pts = [Vector(s[0]) for s in stations]
        for j, (position, radius, width) in enumerate(stations):
            tangent = pts[min(j+1, len(pts)-1)] - pts[max(j-1, 0)]
            tangent.normalize()
            side = Vector((0, 1, 0))
            side -= tangent * side.dot(tangent)
            if side.length < 0.01:
                side = Vector((1, 0, 0))
                side -= tangent * side.dot(tangent)
            side.normalize()
            radial = side.cross(tangent).normalized()
            for i in range(sides):
                theta = i * 2 * math.pi / sides
                v = Vector(position) + radial * (radius * math.cos(theta))
                v += side * (width * math.sin(theta))
                verts.append(tuple(v))
        faces = [tuple(reversed(range(sides)))]
        for j in range(len(stations)-1):
            for i in range(sides):
                n = (i+1) % sides
                faces.append((j*sides+i, j*sides+n,
                              (j+1)*sides+n, (j+1)*sides+i))
        faces.append(tuple((len(stations)-1)*sides+i for i in range(sides)))
        return mesh(name, verts, faces, mat)

    def tube(name, points, radius, mat, sides=8):
        return limb(name, [(p, radius, radius) for p in points], mat, sides)

    def ellipsoid(name, centre, radii, mat, segments=16, rings=10):
        # Truncated polar rings eliminate duplicate, degenerate pole vertices.
        cx, cy, cz = centre
        rx, ry, rz = radii
        verts = [(cx, cy, cz-rz)]
        for j in range(1, rings):
            theta = math.pi*j/rings
            for i in range(segments):
                phi = 2*math.pi*i/segments
                verts.append((cx+rx*math.sin(theta)*math.cos(phi),
                              cy+ry*math.sin(theta)*math.sin(phi),
                              cz-rz*math.cos(theta)))
        verts.append((cx, cy, cz+rz))
        faces = []
        for i in range(segments):
            n = (i+1) % segments
            faces.append((0, 1+n, 1+i))
        for j in range(rings-2):
            a, b = 1+j*segments, 1+(j+1)*segments
            for i in range(segments):
                n = (i+1) % segments
                faces.append((a+i, a+n, b+n, b+i))
        top, base = len(verts)-1, 1+(rings-2)*segments
        for i in range(segments):
            faces.append((base+i, base+(i+1) % segments, top))
        return mesh(name, verts, faces, mat)

    def patch(name, vertices, mat, thickness=0.002):
        # Front/back panels are closed shallow solids, suitable for FBX.
        vertices = [Vector(v) for v in vertices]
        normal = (vertices[1]-vertices[0]).cross(vertices[2]-vertices[0]).normalized()
        half = normal * thickness * 0.5
        n = len(vertices)
        verts = [tuple(v-half) for v in vertices] + [tuple(v+half) for v in vertices]
        faces = [tuple(reversed(range(n))), tuple(n+i for i in range(n))]
        for i in range(n):
            j = (i+1) % n
            faces.append((i, j, n+j, n+i))
        return mesh(name, verts, faces, mat, False, min(thickness*0.3, .001))

    def ribbon(name, points, width, mat, across=(0, 1, 0)):
        # Continuous flat ribbon follows a supplied garment surface.
        axis = Vector(across).normalized() * width * 0.5
        verts = []
        for p in points:
            verts += [tuple(Vector(p)-axis), tuple(Vector(p)+axis)]
        faces = [(i*2, i*2+1, i*2+3, i*2+2) for i in range(len(points)-1)]
        return mesh(name, verts, faces, mat, False)

    # Hips compressed into the cushion, with relaxed blue work trousers.
    loft("TrouserSeat", [((-.48, 0, 1.025), .11, .135),
                         ((-.46, 0, 1.075), .16, .174),
                         ((-.46, 0, 1.15), .145, .167),
                         ((-.47, 0, 1.18), .13, .145)], "Navy", 20, .76)
    for s, side in ((-1, "Right"), (1, "Left")):
        y = s * .145
        limb(side+"TrouserLeg", [((-.45, y, 1.105), .122, .104),
                                ((-.32, y, 1.04), .124, .102),
                                ((-.16, y, .94), .107, .093),
                                ((-.035, y, .862), .092, .088),
                                ((.005, y, .819), .081, .082),
                                ((.071, y, .713), .071, .074),
                                ((.12, y, .60), .067, .066),
                                ((.135, y, .545), .065, .061)], "Navy", 16)
        # Side cargo pockets are cut to the bent upper thigh plane.
        patch(side+"CargoPocket", [(-.31, y+s*.106, 1.075),
                                  (-.16, y+s*.101, .987),
                                  (-.195, y+s*.100, .922),
                                  (-.345, y+s*.107, 1.005)], "Cloth", .008)
        tube(side+"PocketFlap", [(-.314, y+s*.112, 1.073),
                                (-.165, y+s*.107, .985)], .004, "Cloth")
        # Knee creases and lower leg reflective tabs follow the cloth.
        for k in range(2):
            tube(side+"KneeCrease"+str(k),
                 [(.035-k*.012, y-.059, .883-k*.028),
                  (.057-k*.012, y, .877-k*.028),
                  (.035-k*.012, y+.059, .883-k*.028)], .0028, "Cloth")
        ribbon(side+"TrouserReflective", [(.151, y, .697), (.166, y, .67)],
               .103, "Reflective")
        # Boots have an ankle cuff, separate rubber sole, toe cap, tongue/laces.
        loft(side+"Boot", [((.196, y, .469), .151, .078),
                           ((.197, y, .50), .149, .079),
                           ((.183, y, .55), .135, .077),
                           ((.146, y, .585), .083, .067),
                           ((.131, y, .621), .069, .062)], "Rubber", 16, .65)
        loft(side+"BootSole", [((.199, y, .457), .153, .082),
                               ((.199, y, .475), .155, .083),
                               ((.199, y, .489), .153, .081)], "Dark", 16, .65)
        patch(side+"BootToeCap", [(.29, y-.057, .532), (.336, y-.045, .511),
                                 (.336, y+.045, .511), (.29, y+.057, .532)],
              "Dark", .003)
        for k in range(3):
            x = .205-k*.018
            z = .577+k*.006
            tube(side+"Lace"+str(k), [(x, y-.042, z),
                                     (x-.007, y, z+.006),
                                     (x, y+.042, z)], .0025, "Dark", 6)

    # Continuous jacket torso, narrowed waist and broad tailored shoulders.
    torso = [((-.47, 0, 1.135), .138, .157),
             ((-.47, 0, 1.20), .143, .161),
             ((-.48, 0, 1.35), .143, .178),
             ((-.485, 0, 1.49), .141, .197),
             ((-.48, 0, 1.565), .126, .202),
             ((-.46, 0, 1.61), .105, .14),
             ((-.435, 0, 1.635), .075, .082)]
    loft("WorkJacket", torso, "Cloth", 24, .78)
    loft("JacketWaistBand", [((-.47, 0, 1.145), .144, .164),
                             ((-.47, 0, 1.177), .147, .164)], "Navy", 24, .78)
    # Vest shell hugs the jacket; seam and stripe geometry sits above it.
    vest = [((-.47, 0, 1.19), .149, .166),
            ((-.48, 0, 1.35), .149, .184),
            ((-.485, 0, 1.49), .147, .203),
            ((-.478, 0, 1.555), .129, .195)]
    loft("HiVisVest", vest, "Safety", 24, .78)
    for s, side in ((-1, "Right"), (1, "Left")):
        # Vertical front strips and over-shoulder continuation.
        ribbon(side+"VestFrontReflective", [(-.316, s*.105, 1.205),
                                            (-.326, s*.11, 1.35),
                                            (-.331, s*.118, 1.48),
                                            (-.347, s*.12, 1.555)],
               .027, "Reflective")
        ribbon(side+"VestShoulderReflective", [(-.347, s*.12, 1.555),
                                               (-.395, s*.12, 1.61),
                                               (-.48, s*.12, 1.623),
                                               (-.55, s*.12, 1.59),
                                               (-.607, s*.12, 1.54)],
               .027, "Reflective")
        ribbon(side+"VestBackReflective", [(-.607, s*.12, 1.54),
                                           (-.635, s*.11, 1.36),
                                           (-.624, s*.10, 1.21)],
               .027, "Reflective")
        patch(side+"VestPocket", [(-.319, s*.025, 1.23), (-.319, s*.082, 1.23),
                                  (-.324, s*.085, 1.315), (-.324, s*.025, 1.315)],
              "Safety", .006)
        tube(side+"VestPocketSeam", [(-.317, s*.024, 1.312),
                                    (-.317, s*.084, 1.312)], .002, "Navy", 6)
    # A continuous waist band reads clearly from rear three-quarter views.
    loft("VestWaistReflective", [((-.473, 0, 1.255), .153, .178),
                                 ((-.475, 0, 1.285), .154, .181)],
         "Reflective", 24, .78)
    tube("VestZipper", [(-.312, 0, 1.19), (-.328, 0, 1.37),
                        (-.332, 0, 1.49), (-.348, 0, 1.554)], .0032, "Dark", 6)
    ellipsoid("ZipperPull", (-.343, 0, 1.518), (.005, .008, .014), "Metal", 8, 5)
    # Standing blue collar around the neck, with separate fold tips.
    loft("Neck", [((-.427, 0, 1.613), .055, .057),
                  ((-.414, 0, 1.70), .056, .058)], "Skin", 16)
    loft("JacketCollar", [((-.43, 0, 1.611), .083, .079),
                          ((-.425, 0, 1.66), .069, .069)], "Navy", 20)
    for s, side in ((-1, "Right"), (1, "Left")):
        patch(side+"CollarFold", [(-.351, s*.008, 1.639),
                                 (-.355, s*.078, 1.619),
                                 (-.331, s*.052, 1.581)], "Cloth", .006)

    # Bent sleeves reach naturally toward the steering wheel, no ball joints.
    for s, side in ((-1, "Right"), (1, "Left")):
        limb(side+"Sleeve", [((-.476, s*.181, 1.565), .094, .087),
                             ((-.395, s*.215, 1.51), .087, .081),
                             ((-.285, s*.24, 1.423), .078, .074),
                             ((-.19, s*.247, 1.342), .068, .065),
                             ((-.147, s*.238, 1.32), .068, .064),
                             ((-.063, s*.209, 1.311), .061, .056),
                             ((.017, s*.172, 1.304), .049, .044),
                             ((.044, s*.159, 1.298), .044, .04)], "Cloth", 16)
        limb(side+"SleeveCuff", [((.018, s*.172, 1.304), .049, .045),
                                 ((.054, s*.157, 1.296), .047, .042)], "Navy", 16)
        # Elbow stitched reinforcement conforms to outside of the fabric.
        ellipsoid(side+"ElbowPatch", (-.196, s*.292, 1.35),
                  (.065, .012, .055), "Navy", 12, 8)
        tube(side+"SleeveSeam", [(-.419, s*.285, 1.514),
                                (-.294, s*.308, 1.422),
                                (-.19, s*.31, 1.35),
                                (-.06, s*.261, 1.32)], .002, "Navy", 6)
        # The glove palm wraps the wheel; fingers are individual, bent meshes.
        limb(side+"GlovePalm", [((.041, s*.157, 1.296), .038, .036),
                                ((.073, s*.157, 1.299), .041, .041),
                                ((.102, s*.157, 1.304), .032, .036)], "Dark", 12)
        ellipsoid(side+"GloveBack", (.066, s*.157, 1.332),
                  (.035, .036, .009), "Cloth", 12, 7)
        for finger in range(4):
            fy = s*(.133+finger*.016)
            length = .021 if finger == 3 else .027
            tube(side+"GloveFinger"+str(finger+1),
                 [(.085, fy, 1.327), (.107, fy, 1.326),
                  (.119, fy, 1.312), (.116, fy, 1.295),
                  (.108-length*.35, fy, 1.288)], .009, "Dark", 8)
        tube(side+"GloveThumb", [(.057, s*.119, 1.31),
                                 (.074, s*.108, 1.30),
                                 (.093, s*.112, 1.287),
                                 (.099, s*.126, 1.284)], .012, "Dark", 8)

    # Shaped face: jaw, cheeks, temples, flattened forehead, and cranium.
    head = [((-.405, 0, 1.681), .049, .041),
            ((-.393, 0, 1.704), .073, .055),
            ((-.396, 0, 1.744), .093, .072),
            ((-.401, 0, 1.787), .104, .081),
            ((-.403, 0, 1.835), .106, .079),
            ((-.405, 0, 1.882), .099, .075),
            ((-.413, 0, 1.916), .079, .065),
            ((-.419, 0, 1.936), .043, .039)]
    loft("Head", head, "Skin", 24, .92)
    # Nose bridge, nostril wings, and modest mouth preserve adult proportions.
    mesh("Nose", [(-.298, -.016, 1.842), (-.298, .016, 1.842),
                  (-.274, -.017, 1.789), (-.274, .017, 1.789),
                  (-.253, -.013, 1.779), (-.253, .013, 1.779),
                  (-.276, -.024, 1.77), (-.276, .024, 1.77),
                  (-.302, -.023, 1.773), (-.302, .023, 1.773)],
         [(0, 1, 3, 2), (2, 3, 5, 4), (4, 5, 7, 6),
          (6, 7, 9, 8), (0, 2, 4, 6, 8), (1, 9, 7, 5, 3),
          (0, 8, 9, 1)], "Skin", True, .002)
    for s, side in ((-1, "Right"), (1, "Left")):
        ellipsoid(side+"Ear", (-.413, s*.081, 1.802),
                  (.021, .015, .037), "Skin", 12, 8)
        tube(side+"EarFold", [(-.405, s*.094, 1.824),
                             (-.398, s*.098, 1.812),
                             (-.401, s*.096, 1.789)], .003, "Skin", 6)
        # Small inset eye sockets, lids and pupil; no oversized cartoon eyes.
        ellipsoid(side+"EyeSocket", (-.301, s*.042, 1.827),
                  (.006, .021, .009), "Dark", 12, 7)
        ellipsoid(side+"Eye", (-.295, s*.042, 1.828),
                  (.006, .013, .0052), "Reflective", 12, 7)
        ellipsoid(side+"Pupil", (-.289, s*.039, 1.828),
                  (.0025, .004, .004), "Dark", 8, 6)
        tube(side+"UpperLid", [(-.298, s*.023, 1.83),
                              (-.29, s*.04, 1.835),
                              (-.305, s*.058, 1.832)], .0023, "Skin", 6)
        tube(side+"Eyebrow", [(-.302, s*.022, 1.85),
                             (-.298, s*.04, 1.855),
                             (-.31, s*.059, 1.85)], .003, "Dark", 6)
        ellipsoid(side+"Nostril", (-.275, s*.016, 1.77),
                  (.005, .005, .002), "Dark", 8, 5)
    tube("MouthLine", [(-.304, -.026, 1.742), (-.297, -.011, 1.74),
                       (-.296, 0, 1.741), (-.297, .011, 1.74),
                       (-.304, .026, 1.742)], .0019, "Dark", 6)
    tube("LowerLip", [(-.301, -.019, 1.736), (-.296, 0, 1.734),
                      (-.301, .019, 1.736)], .0026, "Skin", 6)

    # Proper safety helmet: suspended shell, solid rim, visor, ribs and strap.
    loft("HelmetSuspension", [((-.416, 0, 1.903), .105, .087),
                               ((-.416, 0, 1.924), .107, .09)], "Dark", 24)
    shell = [((-.416, 0, 1.917), .12, .101),
             ((-.42, 0, 1.947), .117, .099),
             ((-.424, 0, 1.977), .103, .089),
             ((-.427, 0, 2.001), .079, .068),
             ((-.429, 0, 2.016), .042, .038),
             ((-.43, 0, 2.021), .012, .013)]
    loft("SafetyHelmetShell", shell, "Helmet", 32)
    # Slightly longer forward brim shades the face without hiding it.
    loft("SafetyHelmetBrim", [((-.399, 0, 1.911), .153, .116),
                              ((-.399, 0, 1.921), .153, .116),
                              ((-.404, 0, 1.927), .142, .109)], "Helmet", 32, .9)
    for n, yy in enumerate((-.045, 0, .045)):
        height = 0 if yy == 0 else -.011
        tube("HelmetRidge"+str(n+1), [(-.321, yy, 1.947+height),
                                      (-.351, yy, 1.981+height),
                                      (-.398, yy, 2.017+height),
                                      (-.44, yy, 2.027+height),
                                      (-.49, yy, 2.005+height),
                                      (-.526, yy, 1.97+height)],
             .0055 if yy == 0 else .004, "Helmet", 8)
    # Small nonspecific safety mark: no external brand or text texture needed.
    patch("HelmetFrontSafetyMark", [(-.298, -.027, 1.942),
                                     (-.299, .027, 1.942),
                                     (-.318, .023, 1.975),
                                     (-.317, -.023, 1.975)], "Reflective", .0018)
    for s, side in ((-1, "Right"), (1, "Left")):
        ribbon(side+"HelmetChinStrap", [(-.417, s*.086, 1.913),
                                       (-.435, s*.088, 1.80),
                                       (-.391, s*.057, 1.699),
                                       (-.354, s*.025, 1.687)],
               .008, "Dark", (1, 0, 0))
    ellipsoid("HelmetStrapBuckle", (-.354, -.028, 1.688),
              (.009, .009, .006), "Dark", 8, 6)

    # Metadata aids assembly QA without relying on hidden scene state.
    for obj in made:
        obj["DriverPose"] = "Seated; hands on wheel; boots on floor"
        obj["Units"] = "metres"
    return made

