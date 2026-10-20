# Warehouse twin business UI implementation plan

> For agentic workers: use subagent-driven-development to implement the isolated frontend, scene data and native integration tasks, then verify their combined behavior.

**Goal:** Implement the approved Pencil visual-v4 design in the current Zcool warehouse scene, including responsive business pages, scene selection, readable charts/images and smooth transitions.

**Architecture:** A local, packaged HTML panel hosted by Unreal's Slate WebBrowser renders the seven business sections. A native UMG host paints the scene HUD and POIs, owns the browser bridge and responsive bounds, and connects selection to the existing interpolated camera. A native scene registry discovers actual actors and rack instances without changing saved map geometry.

**Tech stack:** UE 5.4 C++, Slate/UMG/WebBrowser, local HTML/CSS/JavaScript, Unreal automation, Node tests.

**Spec:** Design/GHS_Twin_SaaS_Concept/README.md, business-design-brief.md, business-demo-data.json, visual-demo-data.json and exports/visual-v4. User has authorized development of this approved design.

## Global constraints

- Work in the current checkout: the target map and approved design are untracked and must remain available. Preserve all pre-existing edits; do not reset or replace maps.
- Enable the new UI in the Zcool derived map; retain the original HUD and its regression tests in the original map.
- Show actual scene identities. Inventory/orders/trace and equipment not connected to telemetry must retain explicit demo/unknown provenance.
- Rack meshes contain whole rack instances. Selecting one must not claim an arbitrary stock item as real data.
- All resources are local and staged for packaged builds; no web server or external network is required.
- Browser interaction must not rotate/pan/zoom the scene. Device focus and Home use the existing camera interpolation.
- Use MSVC 14.38.33130. Preserve editor dirty state before a native rebuild/restart.

## Review focus

- Seven useful sections, visible charts, model images, detail/back/search/filter behavior.
- Logical viewport layout at desktop, small window and portrait sizes; no microscopic global scaling.
- POI projection and hit testing agree, selection survives data refresh, selection ids match actual actors.
- Fast page changes cancel stale transitions; resizing and focusing never jump across the screen.
- Fresh C++ build, existing and new automation, actual CEF bridge plus scene runtime screenshots.

## Tasks

- [x] Add and test adaptive panel/scene layout calculations.
- [x] Implement offline frontend and its business data/navigation tests.
- [x] Implement scene registry, geometric picking and data provenance tests.
- [x] Implement native browser host, bridge, scene HUD/POIs and camera focus.
- [x] Integrate controller input and packaged resources.
- [x] Build, run regression/new automation and repair failures.
- [x] Verify actual runtime at multiple sizes and review against taste-skill.
- [x] Document operation, validation and remaining backend integration limits.

Final automated evidence: 65 Unreal automation tests and 17 frontend tests passed. Real CEF screenshots and interaction reports cover 1920×1080, 1366×768, 600×900, animated panel transitions, rapid navigation, actual rack material selection, explicit same-object reselection and live desktop-to-portrait resize. Additional mouse QA found and corrected short-drag release ordering and 150% Windows scaling navigation. See docs/GHS_TwinUI_Implementation.md and Saved/GHS_TwinUI_Runtime_*.json.
