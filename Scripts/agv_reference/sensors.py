"""Reference AGV's roof sensor and compact red warning beacon.

Units are metres, Z up, with the vehicle front facing negative X.
This module adds geometry only; scene management and export belong to the
assembly script.
"""

import math

from agv_common import *


def _rounded_profile(width, height, radius, steps=6):
    """A counterclockwise rounded rectangle in the local Y/Z plane."""
    result = []
    corners = (
        (width / 2 - radius, height / 2 - radius, 0),
        (-width / 2 + radius, height / 2 - radius, 90),
        (-width / 2 + radius, -height / 2 + radius, 180),
        (width / 2 - radius, -height / 2 + radius, 270),
    )
    for cy, cz, start in corners:
        for step in range(steps + 1):
            angle = math.radians(start + step * 90 / steps)
            result.append((cy + radius * math.cos(angle),
                           cz + radius * math.sin(angle)))
    return result


def _rounded_prism_x(name, x0, x1, center_y, center_z,
                     width, height, radius, mat):
    profile = _rounded_profile(width, height, radius)
    count = len(profile)
    verts = [(x, center_y + y, center_z + z)
             for x in (x0, x1) for y, z in profile]
    faces = [tuple(reversed(range(count))),
             tuple(range(count, 2 * count))]
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, j, count + j, count + i))
    return mesh(name, verts, faces, mat)


def _rounded_frame_x(name, x0, x1, center_z,
                     outer_width, outer_height, outer_radius,
                     inner_width, inner_height, inner_radius, mat):
    outer = _rounded_profile(outer_width, outer_height, outer_radius)
    inner = _rounded_profile(inner_width, inner_height, inner_radius)
    count = len(outer)
    verts = [(x, y, center_z + z)
             for x in (x0, x1) for profile in (outer, inner)
             for y, z in profile]
    faces = []
    for i in range(count):
        j = (i + 1) % count
        # Front/back annuli, followed by the outside and recessed inside wall.
        faces.extend(((i, count + i, count + j, j),
                      (2 * count + i, 2 * count + j,
                       3 * count + j, 3 * count + i),
                      (i, j, 2 * count + j, 2 * count + i),
                      (count + i, 3 * count + i,
                       3 * count + j, count + j)))
    return mesh(name, verts, faces, mat)


def _lathe_z(name, center_x, center_y, profile, mat, segments=64):
    """Closed lathed part, with profile supplied as (height, radius)."""
    verts = []
    for z, radius in profile:
        for i in range(segments):
            theta = 2 * math.pi * i / segments
            verts.append((center_x + radius * math.cos(theta),
                          center_y + radius * math.sin(theta), z))
    faces = [tuple(reversed(range(segments)))]
    for row in range(len(profile) - 1):
        first = row * segments
        second = (row + 1) * segments
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((first + i, first + j, second + j, second + i))
    last = (len(profile) - 1) * segments
    faces.append(tuple(range(last, last + segments)))
    obj = mesh(name, verts, faces, mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = len(polygon.vertices) == 4
    return obj


def build_sensors():
    """Add the cabinet-top sensor pod and red beacon to the AGV assembly."""
    collection("AGV_Sensors")

    dark = material("DarkMetal", (.028, .035, .045), roughness=.34,
                    metallic=.55)
    rubber = material("Rubber", (.012, .014, .017), roughness=.48)
    chrome = material("Chrome", (.5, .55, .6), roughness=.23, metallic=.92)
    glass = material("OpticalGlass", (.006, .015, .022), roughness=.12,
                     metallic=.4)
    ir_glass = material("SensorIRGlass", (.027, .012, .021), roughness=.18,
                        metallic=.38)
    red = material("LensRed", (.6, .005, .008), roughness=.17,
                   metallic=.1, emission=.15)
    dark_red = material("LensRedRim", (.24, .002, .004), roughness=.24,
                        metallic=.1)
    label = material("SensorWarningLabel", (.63, .66, .63), roughness=.55)
    yellow = material("SensorWarningYellow", (.95, .61, .008), roughness=.44)
    print_ink = material("SensorLabelInk", (.009, .009, .008), roughness=.66)

    # Low, chamfered rectangular head.  The inset has genuine depth so the
    # individual optical elements remain readable from a three-quarter view.
    _rounded_prism_x("Sensor_Housing", .403, .680, 0, .870,
                     .320, .095, .017, dark)
    _rounded_frame_x("Sensor_FrontChamferFrame", .395, .408, .870,
                     .320, .095, .017, .292, .070, .020, dark)
    _rounded_prism_x("Sensor_RecessedBlackWindow", .407, .411, 0, .870,
                     .293, .071, .020, rubber)
    _rounded_frame_x("Sensor_WindowInnerSeal", .401, .407, .870,
                     .294, .072, .020, .286, .064, .017, rubber)

    # Large camera on the left when the reference's front face is viewed.
    camera_y = .107
    camera_z = .870
    cylinder("Sensor_CameraBarrel", (.403, camera_y, camera_z),
             .023, .009, rubber, axis="X")
    torus("Sensor_CameraOuterRing", (.397, camera_y, camera_z),
          .0177, .0025, dark, axis="X")
    torus("Sensor_CameraMachinedRing", (.395, camera_y, camera_z),
          .0133, .0012, chrome, axis="X")
    cylinder("Sensor_CameraOpticalGlass", (.3945, camera_y, camera_z),
             .0118, .002, glass, axis="X")
    cylinder("Sensor_CameraPupil", (.3932, camera_y, camera_z),
             .0055, .0005, rubber, vertices=48, axis="X")
    cylinder("Sensor_CameraReflection", (.3928, camera_y + .004, camera_z + .0045),
             .0021, .0004, chrome, vertices=24, axis="X")

    # Twelve small infrared emitters, arranged as in the photographed head.
    for row, z in enumerate((.8585, .8815)):
        for col in range(6):
            y = .049 - col * .029
            stem = "Sensor_IR_%d_%d" % (row + 1, col + 1)
            cylinder(stem + "_Socket", (.404, y, z), .0062, .006,
                     dark, vertices=32, axis="X")
            torus(stem + "_Trim", (.4005, y, z), .0048, .00065,
                  chrome, axis="X", segments=32, minor_segments=8)
            cylinder(stem + "_Lens", (.400, y, z), .0039, .0015,
                     ir_glass, vertices=32, axis="X")
            cylinder(stem + "_Glint", (.3989, y + .001, z + .0011),
                     .0008, .00035, chrome, vertices=16, axis="X")

    # Small fasteners, a side connector, and a generic warning graphic.
    for x in (.446, .645):
        for y in (-.132, .132):
            bolt("Sensor_TopScrew", (x, y, .918),
                 radius=.0032, depth=.0012, axis="Z")
    box("Sensor_SideConnectorMount", (.624, -.164, .859),
        (.047, .010, .039), dark, bevel=.003)
    box("Sensor_SideConnector", (.627, -.184, .855),
        (.043, .034, .035), rubber, bevel=.003)
    box("Sensor_ConnectorCap", (.627, -.202, .855),
        (.033, .005, .027), dark, bevel=.002)
    for x in (.613, .641):
        bolt("Sensor_ConnectorScrew", (x, -.205, .855),
             radius=.0018, depth=.001, axis="Y")
    box("Sensor_WarningSticker", (.489, -.1608, .872),
        (.045, .0012, .027), label, bevel=.0005)
    mesh("Sensor_WarningTriangle",
         [(.472, -.1616, .863), (.490, -.1616, .863),
          (.481, -.1616, .882)], [(0, 1, 2)], yellow)
    mesh("Sensor_WarningLightning",
         [(.482, -.1619, .879), (.478, -.1619, .871),
          (.481, -.1619, .871), (.4795, -.1619, .866),
          (.485, -.1619, .873), (.482, -.1619, .873)],
         [(0, 1, 2, 3, 4, 5)], print_ink)
    for row in range(4):
        box("Sensor_LabelFinePrint", (.501, -.1617, .879 - row * .004),
            (.013 if row != 3 else .009, .0003, .0010),
            print_ink, bevel=0)

    # Warning beacon: flat mounting foot, slender stalk, ribbed socket,
    # then a softly rounded red lens with a slight taper towards the top.
    beacon_x, beacon_y = .610, .035
    cylinder("Beacon_MountingFoot", (beacon_x, beacon_y, .922),
             .028, .008, dark)
    cylinder("Beacon_Stem", (beacon_x, beacon_y, .943),
             .010, .034, rubber)
    _lathe_z("Beacon_LowerTransition", beacon_x, beacon_y,
             [(.957, .014), (.961, .018), (.972, .021),
              (.977, .029), (.980, .031)], rubber)
    cylinder("Beacon_RibbedBase", (beacon_x, beacon_y, 1.000),
             .031, .041, rubber)
    for i in range(6):
        torus("Beacon_BaseRib_%02d" % i,
              (beacon_x, beacon_y, .981 + i * .007),
              .0309, .0011, dark, segments=64, minor_segments=8)
    _lathe_z("Beacon_RedLens", beacon_x, beacon_y,
             [(1.019, .0305), (1.021, .032), (1.025, .0315),
              (1.096, .0279), (1.101, .0270), (1.104, .0247),
              (1.105, .0215)], red)
    torus("Beacon_LensLowerLip", (beacon_x, beacon_y, 1.022),
          .0317, .0013, dark_red)

