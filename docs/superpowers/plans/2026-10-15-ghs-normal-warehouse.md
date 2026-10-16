# GHS video-style warehouse implementation plan

**Goal:** Create an independent CAD warehouse matching the bright industrial rendering of `D:/DDDownload/normal_video.mp4`, using the current approved models and layout.

**Design:** Reference frames at 6.44, 9.20, 25.76 and 28.56 seconds establish a light gray studio environment, white/silver frames, blue shelves and pallets, kraft cartons, restrained soft shadows. Video branding/UI are not warehouse geometry. Existing physical dimensions remain display estimates. The user's current request supersedes the earlier blue hologram style for this new scene.

**Architecture:** Clone the saved presentation map. Override component material slots with independent materials under `/Game/GHSNormalWarehouse`, preserving every shared mesh, instance, CAD source ID and the previous scenes. Keep moving decals attached to AGVs, with a new blue physical-color decal style. Use one shadow-casting directional light and one non-realtime ambient cubemap.

**Tech stack:** UE 5.4 Python editor API; Blender's bundled decoder for video analysis; Python/Pillow reference boards. No C++ changes.

- [x] Extract and inspect video keyframes; audit existing scene invariants.
- [x] Hash all existing Content, clone `/Game/Maps/GHS_CAD_NormalWarehouse`, create independent material/FX palette and light environment.
- [x] Render overview, storage, racks and equipment from saved cameras; review against reference and adjust colors/shadows where necessary.
- [x] Fresh-process verification of transforms, CAD lineage, blocked locations, actual bounds, shared assets, persistent materials, FX graphs and lighting. Confirm no old Content hashes changed.
- [x] Deliver new map and real UE rendered previews; attempt editor handoff. Windows was locked, so the live editor was left unchanged; saved map and four captures are ready.

Review focuses: no washed-out white cargo; clear white/blue/kraft hierarchy; grounded objects without local light arrays; all 122 blocked slots remain clear; no source material or old map mutation. New heights, routes or conveyors are outside this restyle.

Final evidence: `Saved/GHS_NormalVerification.json` is successful after a fresh UE reload: 229 actors, 18 HISM groups, 14,116 instances, 40 time-driven Decals, zero overlaps in 9,452 CAD geometry boxes, 598 original Content hashes preserved. `Saved/GHS_Normal_CaptureReport.json` confirms four 2400x1350 UE renders. Independent visual review approved the white/blue/kraft palette. Text labels were polished to blue before final capture. Verification commandlet exit code 0; only existing object-path deprecation warnings.
