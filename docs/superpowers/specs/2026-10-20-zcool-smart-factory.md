# GHS Zcool Smart Factory scene

Create a separate UE 5.4 scene from the current saved `/Game/Maps/GHS_CAD_NormalWarehouse`, retaining its CAD geometry, placed equipment, camera controls and vehicle HUD behavior. Reference: https://www.zcool.com.cn/work/ZNjY0NDI3ODA=.html, Alan's smart factory SaaS. Inspected the actual browser image: near-white architectural models on cool gray grid, soft studio shadows, cobalt blue interaction accents, dark narrow header, white right-hand dashboard, restrained type and line charts.

Target map: `/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`. Theme assets: `/Game/GHSZcoolSmartFactory`. Implement in the existing UE project so all current untracked/binary scene state is available; isolate by new map/assets and narrowly scoped theme activation. Original maps, shared meshes, defaults, and existing Design work must remain intact.

Visuals: ceramic white and pale gray rack/cargo/walls, blue structural accents and location markings, gray fine grid surround, neutral soft lighting, blue/cyan animated AGV decals. Preserve physical thick cutaway walls and all device details. Geometry and actor transforms derive exclusively from latest map, never older rebuild scripts.

User correction: do not create management panels yet. Implement only the three-dimensional scene styling. Preserve the original scene labels, grouping/list pagination/detail panels and camera input, with no new dashboard, header or sidebar. Old map rendering behavior must remain unchanged.

Known source condition: 248 actors; 52 dock trucks, 6 stacker actors, 32 AGVs, 16 manual forklifts. Stacker IDs duplicate (2 unique IDs); preserve original map, assign unique IDs only within the new scene so all six are selectable if feasible. Preserve manual forklift shared mesh paths because discovery relies on them. Retain all tag/attachment data, except explicit new-scene identity repair. No new external data integration or autonomous path scheduling is implied.

Acceptance: original Content hashes unchanged; new map saved and reloaded; actor/instance/transform parity; all device types registered; C++ build and existing GHS automation passing; fresh runtime tests of selection, close, cluster interactions and camera; actual UE render screenshots inspected; leave new map open for user.
