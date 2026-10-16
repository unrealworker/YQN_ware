# Video Digital Twin Warehouse Implementation Plan

**Goal:** Reconstruct the blue digital-twin warehouse visible in the user's video as a new UE 5.4 map, with Blender-authored equipment and matching lighting.
**Scope:** User explicitly selected warehouse only; exclude the final control room and editorial video captions. Source video duration 75.87 seconds at 1920x1080/30 fps. Key frames 3, 20, 35, 45, 50, 54 and 65 seconds.
**Architecture:** Reusable Blender mesh libraries, UE materials with controlled blue transparency and emission, independently named room/equipment Actors, composed scene cameras and saved visual verification.
**Tech Stack:** Installed Blender 5.2.2, UE 5.4 Python Editor scripting, local Pillow for reference contact sheets. No external downloaded assets or live data service.
**Scale:** Estimated from a 1.2 x 1.0 m pallet; the source does not supply measured dimensions. Facility footprint about 36 x 26 m. A visually matched reconstruction, not surveyed engineering geometry.

## Layout and visual contract

Final coordinates in UE metres: X=-18..18, Y front/back=-13..13, Z up. Overview eye (-35,-42,39), looking toward (0,0,.2), FOV 50. The final pass reflects initial layout positions across X so racks appear on the left of the reference view. Rack block X=4..17, Y=-6..4 has four long rack rows; rear pallet room X=4..17, Y=4..12. Central corridor X=-1..4. Elevator at (1.5,11), front -Y. Empty rooms and the two other pallet grids occupy negative X. Registry records final positions. Walls height 2.8 m, elevator height 3.5 m, blue gate beams with amber lights, roofless cutaway.

PBR dark navy floor, near-black surroundings, faint cyan external grid; broad cool area lights, cyan elevator spill; restrained cyan wall outlines and cargo subdivision edges. Green routing/destination markers, scanner arcs and orange alarm rings. Equipment IDs CDD14-1/2/3/4, CBD50-1, HR-1, DN-1 as world annotations. Visual status only, no invented live connection.

## Files and independent tasks

- [x] Extract and inspect real reference frames; confirm warehouse-only scope.
- [x] `Scripts/video_reference/common.py`: shared Blender helpers, evaluated-copy export and manifests. `.blend` originals remain editable.
- [x] `Scripts/video_reference/build_storage.py`: cargo pallet, detailed repeated rack bay/bins, LM/AP pads, conveyor; `SourceAssets/VideoReference/storage.blend` and `storage.json`.
- [x] `Scripts/video_reference/build_robots.py`: blue pallet stacker, orange transporter, white high-rack robot, alarm chassis and cone; `robots.blend` and `robots.json`.
- [x] `Scripts/video_reference/build_architecture.py`: blue elevator, industrial gate/control cabinet and reusable holographic indicators; `architecture.blend` and `architecture.json`.
- [x] `Scripts/video_reference/build_hud.py`: editable diagnostic panel and Chinese RGBA texture; `hud.blend` and `hud.json`.
- [x] `Scripts/build_video_warehouse.py` plus `finalize_video_warehouse.py`: import libraries, save material assignments, compose `/Game/Maps/VideoDigitalTwinWarehouse` and five reference cameras, registry/report. Preserve earlier maps and assets.
- [x] `Scripts/capture_video_warehouse.py` and `verify_video_warehouse.py`: five real 1920x1080 UE screenshots, saved-asset reload, missing-material checks, bounds, actor categories and source consistency. Blueprint compilation completed with 0 errors, 0 warnings, 0 load failures. Fresh verification passed for 901 actors, 18 imported meshes, 32 rack bays, 7 robots, 1364 scene material slots, 874 registered IDs and 5 cameras. Wall B-only mask and diagnostic texture connection verified. Chinese README documents estimated geometry and static visualization scope.

## Verification

Inspect each Blender library and final UE overview, robot route, rack and alarm shots. Validate meter-to-centimeter conversion, material assignments persisted in fresh UE process, all expected asset types and landmarks, no accidental floor clipping or inverted robot orientation. Scripts must report exceptions; Blender uses `--python-exit-code 1`. Mutations of loaded UE assets occur in the live editor, or import only new assets using a separate process and then load the new map in the live editor. No implementation-mirroring unit tests for geometry generation.
