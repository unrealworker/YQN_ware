"""Four industrial AGV wheels, in metres with the axle along world Y.

Called by the main reference build; this module never resets, renders or exports
the scene.  Wheel origins and outside faces follow the shared body contract.
"""

import math

from agv_common import *


def _lathe_y(name, center, side, profile, mat, segments=96):
    """Revolve a closed (radius, outward axle offset) profile around Y."""
    cx, cy, cz = center
    verts = []
    for radius, outward in profile:
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            verts.append((cx + radius * math.cos(angle),
                          cy + side * outward,
                          cz + radius * math.sin(angle)))
    faces = []
    for j in range(len(profile)):
        next_j = (j + 1) % len(profile)
        for i in range(segments):
            next_i = (i + 1) % segments
            face = (j * segments + i, next_j * segments + i,
                    next_j * segments + next_i, j * segments + next_i)
            faces.append(face if side > 0 else face[::-1])
    obj = mesh(name, verts, faces, mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def _shoulder_channels(name, center, side, mat):
    """Fine diagonal cuts over each shoulder, joined into one mesh per tire."""
    cx, cy, cz = center
    verts, faces = [], []
    for shoulder in (-1.0, 1.0):
        for i in range(56):
            angle = 2.0 * math.pi * i / 56
            start = len(verts)
            # The strips follow the tire shoulder, just above its surface.
            for axial, radius, skew in ((.018, .15815, 0.0),
                                        (.029, .15615, .017),
                                        (.040, .15115, .034),
                                        (.047, .14315, .048)):
                for edge in (-.006, .006):
                    theta = angle + shoulder * skew + edge
                    verts.append((cx + radius * math.cos(theta),
                                  cy + side * shoulder * axial,
                                  cz + radius * math.sin(theta)))
            for k in range(3):
                a = start + k * 2
                faces.append((a, a + 1, a + 3, a + 2))
    return mesh(name, verts, faces, mat)


def build_wheels():
    """Create four complete wheel assemblies and return their tire objects."""
    rubber = material("Rubber", (.012, .014, .017), roughness=.76)
    chrome = material("Chrome", (.50, .55, .60), roughness=.23, metallic=1.0)
    dark = material("DarkMetal", (.028, .035, .045), roughness=.39, metallic=.8)
    steel = material("Steel", (.16, .18, .22), roughness=.32, metallic=.9)
    recess = material("Wheel_Recess", (.0025, .0035, .005), roughness=.88)
    tire_lettering = material("Tire_Raised_Rubber", (.021, .024, .028),
                             roughness=.81)

    # Rounded rubber profile with two modest grooves on the running surface.
    # The finished rubber extends to Y +/- .458 and Z .004 .. .320.
    tire_profile = [
        (.108, -.046), (.112, -.050), (.131, -.051), (.143, -.047),
        (.151, -.040), (.156, -.029), (.158, -.022),
        (.158, -.0165), (.1558, -.0150), (.1558, -.0125),
        (.158, -.0110), (.158, .0110),
        (.1558, .0125), (.1558, .0150), (.158, .0165),
        (.158, .022), (.156, .029), (.151, .040),
        (.143, .047), (.131, .051), (.112, .050), (.108, .046),
    ]
    # The chrome wheel face has a rolled lip and a recessed dished web.
    rim_profile = [
        (.105, .031), (.111, .033), (.113, .039), (.113, .045),
        (.110, .049), (.106, .047), (.102, .042),
        (.092, .033), (.082, .028), (.074, .028),
        (.057, .034), (.035, .040), (.029, .040),
        (.029, .034), (.055, .028), (.076, .022), (.091, .026),
    ]
    tires = []
    for axle, x in (("Front", -.40), ("Rear", .54)):
        for side_name, side in (("Left", -1.0), ("Right", 1.0)):
            prefix = "Wheel_" + axle + "_" + side_name
            collection(prefix)
            center = (x, side * .407, .162)

            def at(radius=0.0, angle=0.0, outward=0.0):
                return (x + radius * math.cos(angle),
                        center[1] + side * outward,
                        .162 + radius * math.sin(angle))

            tires.append(_lathe_y(prefix + "_RoundedRubber", center, side,
                                 tire_profile, rubber))
            _shoulder_channels(prefix + "_ShoulderSipes", center, side, recess)
            # Two fine molded rings articulate the sidewall and rim seat.
            torus(prefix + "_SidewallMoldRing", at(outward=.0506),
                  .132, .00065, tire_lettering, axis="Y", segments=96,
                  minor_segments=6)
            torus(prefix + "_BeadSeal", at(outward=.050),
                  .1143, .00135, rubber, axis="Y", segments=96,
                  minor_segments=8)

            cylinder(prefix + "_BrakeDrum", at(outward=.006), .103, .040,
                     dark, vertices=64, axis="Y")
            _lathe_y(prefix + "_DishedChromeRim", center, side,
                     rim_profile, chrome)
            torus(prefix + "_PolishedOuterLip", at(outward=.047),
                  .1095, .002, chrome, axis="Y", segments=96,
                  minor_segments=10)
            torus(prefix + "_InnerMachinedRing", at(outward=.041),
                  .1015, .001, steel, axis="Y", segments=96,
                  minor_segments=8)

            # Recessed circular vents and their rolled edges follow the web.
            for i in range(8):
                angle = (i + .5) * 2.0 * math.pi / 8
                cylinder(prefix + "_VentRecess_%02d" % (i + 1),
                         at(.085, angle, .0300), .0082, .0008,
                         recess, vertices=28, axis="Y")
                torus(prefix + "_VentRolledEdge_%02d" % (i + 1),
                      at(.085, angle, .0307), .00835, .00065,
                      steel, axis="Y", segments=28, minor_segments=6)

            # Eight separate lug nuts sit on machined washer seats.
            for i in range(8):
                angle = i * 2.0 * math.pi / 8
                cylinder(prefix + "_LugWasher_%02d" % (i + 1),
                         at(.055, angle, .036), .0062, .0018,
                         dark, vertices=24, axis="Y")
                cylinder(prefix + "_HexLug_%02d" % (i + 1),
                         at(.055, angle, .039), .0046, .0052,
                         chrome, vertices=6, axis="Y")
                cylinder(prefix + "_LugTip_%02d" % (i + 1),
                         at(.055, angle, .0420), .0028, .0008,
                         steel, vertices=16, axis="Y")

            cylinder(prefix + "_HubBase", at(outward=.038), .0350, .009,
                     dark, vertices=64, axis="Y")
            torus(prefix + "_HubRetainingRing", at(outward=.044),
                  .0325, .0015, chrome, axis="Y", segments=64,
                  minor_segments=8)
            cylinder(prefix + "_HubCap", at(outward=.045), .0305, .006,
                     steel, vertices=64, axis="Y")
            cylinder(prefix + "_HubCentre", at(outward=.0485), .018, .0015,
                     dark, vertices=48, axis="Y")
            # A small metal valve with a black cap adds the asymmetric detail.
            valve_angle = math.radians(62)
            cylinder(prefix + "_ValveStem", at(.098, valve_angle, .045),
                     .0020, .007, steel, vertices=12, axis="Y")
            cylinder(prefix + "_ValveCap", at(.098, valve_angle, .049),
                     .0025, .003, rubber, vertices=12, axis="Y")
    return tires
