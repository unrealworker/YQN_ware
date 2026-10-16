# Reference-video visual observations

Inspected actual files: `Video_ContactSheet.jpg`; frames at 005, 015, 025, 040, 045, and 070 seconds. Dimensions below are suggested modeling proportions inferred from the imagery, not measured source dimensions.

## Main visual language

- Elevated three-quarter warehouse view, almost orthographic. Dark navy/black floors, cool blue walls, cyan architectural outlines, blue-gray cargo, brightly colored industrial robots. Geometry must read at warehouse scale through silhouette, color blocks, and emission edges.
- This is a stylized industrial digital twin. Floors and robots are opaque; many walls and rack structures are semi-transparent blue so equipment remains visible through them. Do not make all geometry equally transparent.
- Thin cyan rectangular floor grid extends outside the building. Small cyan squares emphasize intersections. Inside, wider muted blue route stripes connect parking slots; directional white arrow ticks are subtle.
- Parking pads are dark slate rectangular/square planes with thin gray borders. Most say `LM` over `14`; AP pads say `AP` over `20` and include a lime-green curved hook/return symbol.

## Robot assets

### Blue pallet stacker / mobile forklift (CDD14-1 through CDD14-4)

Priority P0. Reuse one detailed mesh with instance labels.

- Compact standing vertical body with a low rounded black base and thin warm gray/silver bumper rim; blue/cyan large side panels framed by black uprights.
- Tall narrow black mast/control column rises above the body. A blocky dark sensor head caps it. Upper shoulder/control panel is metallic dark gray with small yellow warning dots. A thin long white vertical strip/light sits on the broad face of the body.
- One side of the chassis carries a blue pallet with cargo immediately in front of/alongside the mast. A loaded instance should read clearly as an actual forklift, with low dark fork tines tucked beneath the pallet.
- Suggested total height 1.65–1.9 m; base footprint about 0.65 x 0.9 m; mast above main blue housing. Loaded package about 0.9–1.1 m square and 0.7–0.9 m tall.
- At 015 s one selected robot uses a translucent/x-ray machinery overlay: pale white vertical guide rails, gray inner mechanisms, cyan light at its base, four cyan corner brackets, and green circular scanning rings beneath. Preserve an opaque normal instance elsewhere for comparison.

### Orange pallet transporter (CBD50-1)

Priority P0. This must be a visually distinct mesh or substantial variation, not just a blue robot recolor.

- Broad orange sloping body with dark black trim and low rounded black chassis; wider and heavier than the blue stacker.
- Rear/top dark gray angled control assembly and tall narrow black sensor/mast. Small red/yellow indicator details; dark wheel recesses at floor level.
- A cargo pallet sits immediately ahead of it. Frame 025 s shows its body turned while the green intended route bends away around a cone.
- Suggested body height 1.15–1.4 m, control mast about 1.75 m, footprint 0.85 x 1.2 m. Use warm saturated orange against cool surroundings.

### White high-rack bin robot (HR-1)

Priority P0 for the dense rack shot.

- Bright white tall rectangular portal/mast assembly. A white top cap spans two upright-looking members; dark/cyan internal lifting mechanism is visible between them.
- Lower white U-shaped cradle projects to the side/back; a thin flat white bin/fork shelf projects outward into an aisle on the opposite side. This asymmetric fork/cradle silhouette is essential.
- Low dark/cyan mechanical base and a small gray lower mast carriage. Surface should be bright white with soft rough metallic response, not transparent blue.
- The robot runs inside rack aisles, partly occluded by translucent rack structures. Suggested total height 2.3–2.8 m, footprint 1.2 x 1.5 m; scale to the racks rather than claiming literal reference dimensions.

### Alarm robot (DN-1)

Priority P1. The orange/black low vehicle is visually obscured by its alert effect in frame 045 s. It should be a low broad industrial base with exposed dark upper mechanisms, not an invented humanoid.

- Render selected body partly translucent orange/amber so the alert remains dominant.
- Red downward triangular status marker above, red underline below white `DN-1` label, status reading approximately `0.00m/s` and `5%`.

## Cargo and rack assets

### Blue wireframe cargo on pallets

Priority P0, high instance count.

- Cargo is one near-cubic blue-gray solid volume subdivided visually into a regular box lattice, rather than separate randomly stacked cartons. Its front/top/sides show thin light cyan grid lines, around three columns and two/three levels depending on face/perspective.
- Main faces are muted periwinkle/steel blue; cyan edges are mildly emissive. Tops are lighter; side faces remain readable with blue shading.
- Base is a saturated blue low pallet tray with visible thickness, projecting corners/lips, and darker underside/fork cavities. Slight bevels on the pallet and cargo edges improve silhouette.
- Make a single reusable pallet+cargo asset with separate material slots for face fill, grid edges, and pallet. Instance it in ordered pad rows with occasional empty slots.

### Dense multi-level storage racks

Priority P0 for the warehouse's dominant left block.

- Rectangular large footprint containing many long parallel rack runs and narrow aisles. Tall thin dark-blue uprights, repeated horizontal shelf rails, and diagonal bracing produce a true 3D shelving structure.
- Repeated blue rectangular bins occupy multiple height levels, with a consistent open dark front/recess beneath a pale blue top lip. This repeated box cavity gives the reference its dense rhythm.
- Transparent blue rack envelope and ghosted shelf planes are visible, but the bins are more opaque. Avoid replacing racks with only filled cubes: rack posts, rails, level spacing, bin openings and longitudinal aisle voids are visible.
- Suggested units: 4–5 storage levels, approximately 0.55–0.7 m per level; bin roughly 0.45 x 0.65 x 0.4 m; adjust to the scene composition. Frame 040 s intentionally overlaps many translucent layers.

## Warehouse architecture

- Cutaway outer and internal walls: blue transparent panels around 2.8–3.2 m tall, a thin brighter cyan top/perimeter outline, occasional thicker opaque blue pillars. Rooms are actual spatial volumes and corridors, not outlines floating on one plane.
- Elevator at 005 s is a prominent opaque deep-blue rectangular booth with a flat roof slab, thick front jambs, dark inset side panels, and bright cyan interior. Door opening is about one loaded robot wide. A large glowing white `2` sits on the right outer jamb with small triangular chevrons below. The floor inside is cyan-lit, and white/cool light spills forward onto the corridor floor.
- Blue industrial doorway at 015 s has two narrow blue vertical supports and a wide opaque blue lintel bar. A small amber rectangular beacon sits on top. Adjacent is a gray wall control cabinet: cuboid, inset small dark display, minor face detailing.
- Some wall panels have deep-blue gradient/reflection, and thin twin cyan edges reveal panel thickness. Keep the main walls more substantial than plain single-pixel lines.

## Holograms and dynamic indicators

Priority P0 because these supply the digital-twin appearance even in a still frame.

- Robot labels are white world-space text billboards, with a thin green/red horizontal separator and smaller speed/battery line. IDs observed: CDD14-1, CDD14-2, CDD14-3, CDD14-4, CBD50-1, HR-1, DN-1.
- Normal robots: 2–3 concentric green/cyan partial rings at floor level, short dash divisions, radial white slashes. Selected robots additionally have four cyan corner brackets around the base.
- Routes: flat lime/teal green broad strips following right-angle bends; dashed central/continuation sections, thin bright boundary, and a green destination reticle composed of four L brackets. A downward lime triangle hovers above the target/vehicle.
- Obstacle avoidance at 025 s: actual orange traffic cone with square orange base; translucent green scanning fan/sector extending ahead of orange vehicle, dense thin curved lines, bright green arc at outer radius, softened transparent interior. Route changes around the cone.
- Alarm at 045 s: orange segmented double circular ring, bright orange center pulse, intersecting dashed technical axes, white curved radial ticks. Red callout panel extends upper-right with `错误代码 - 50001`, `车辆故障报警`, and smaller `常见原因`. Thin red border and a leader line tie it to the robot.
- The reference's lower-left Chinese captions are video titles; they are distinct from in-world objects and should not become warehouse mesh assets.

## Lighting and materials

- Warehouse background stays near black/navy. Broad cool overhead fill lights make the blue cargo tops visible, with gentle shadows and restrained glossy reflections on the floor.
- Floor is dark graphite with moderate roughness; it reflects bright elevator/robot illumination softly. Use stronger localized cool white spill at the elevator and selected robot, rather than making every floor patch equally bright.
- Blue architecture rim emission and cyan package edge emission should remain thin and controlled. Saturated green routes and orange alert dominate only their local areas. Robot surfaces retain realistic metal/plastic shading.
- Rack shot is foggy/ghosted mostly through transparency overlap; avoid heavy global haze that erases the cyan lines and individual bins.
- UI labels must remain readable without excessive bloom. Use emissive materials for rings/grid/elevator digit; modest bloom only.

## Final control-room shot (070 s)

This is a separate modeled interior, not another warehouse bird's-eye view.

- Large, wide room, approximately twice as wide as deep in the visible composition. Camera stands near the rear, aimed at a concave panorama wall. Floor is smooth blue-gray with a broad soft central light pool.
- Main wall display is an extremely wide concave screen, bending inward at both ends, roughly 5.5:1 width/height. Central majority shows the live warehouse; both sides show black analytics dashboards with tiny white text, magenta area/line/bar graphs, and a small colorful pie chart. A thick pale gray architectural frame wraps above, below, and at ends. Use a curved mesh for the screen/frame, not merely a flat billboard, because the curvature defines the room.
- Ceiling has densely spaced long dark gray parallel ribs/slats, with deep black gaps. In perspective these converge strongly toward the display. Model rib depth so dark gaps cast visible shading. There are small cool white rectangular recessed downlights at intervals between/through slats; four or more visible in this crop.
- Side walls are plain large blue-gray panels with dark vertical seams at corners. Thick right end wall/frame beside the display helps establish volume.
- Two white curved operator consoles are separate: smaller at left mid-ground, larger in right foreground. Each is a broad continuous arcuate desktop on a substantial curved opaque front/support panel. Tops gently taper at ends; underside/front recess reads dark gray. Do not use thin tables on stick legs.
- About three small black desktop monitors sit on the right console, on thin short stems with small base feet; left console has multiple similar monitors. Add small low-profile keyboards/mouse pads on desktops.
- White molded bucket chairs with curved backs/seat pans, dark or brass thin splayed legs and stretchers; three visible at each desk. Orient them toward the main display/desk.
- Central floor carries large projected/painted white brand glyphs and Chinese `仙工智能`, placed between the consoles and screen, perspective-aligned to the floor. Treat as texture/decal rather than extruded floating lettering.
- Lighting: cool broad ambient fill, spot/downlight highlights on console tops/chairs/floor, black slat gaps, brighter soft floor center and subdued edges. Screen content is luminous but does not overexpose the white console geometry.

## Prioritized production order

1. P0: Warehouse layout, thick cutaway walls, blue elevator and door portal; establish close matching camera/composition and dark blue lighting.
2. P0: Reusable blue grid cargo+pallet, detailed blue stacker, distinct orange transporter, green rings/routes/labels. These occupy every main shot.
3. P0: Dense shelving module with actual uprights/shelves/bracing and recessed bins, plus white HR robot; fill a large ordered storage block.
4. P0: Control-room curved screen/frame, ribbed ceiling, curved console/chairs/monitors and dedicated interior lighting.
5. P1: Cone/scanning fan, alarm robot/callout/rings, elevator digit, cabinet/beacon, selection x-ray overlay, additional dashboard polish.

All package/rack/robot meshes should be created in Blender as reusable separate objects, with intentional pivots, consistent meter scale, and separate material slots. World-space labels, dynamic route/selection effects, screen dashboard content and floor markings are better authored as UE materials/widgets/decals so they remain readable and editable; architectural screen/frame and consoles themselves must remain modeled geometry.
