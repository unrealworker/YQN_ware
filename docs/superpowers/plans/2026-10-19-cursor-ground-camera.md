# Absolute cursor ground movement

Superseded: the user rejected this behavior and requested map/grab dragging. See 2026-10-19-map-drag-camera.md for the current implementation; the following is historical verification only.

User confirmed that RMB should move the Pawn to the ground point indicated by the cursor, not grab and drag the map. Preserve Z=0, orbit around the moved Pawn, UniversalCameraPlugin movement/restrictions/lag, existing LMB/zoom/Home, and concurrent truck HUD work.

Capture the actual local player's view-projection matrix and constrained viewport on RMB down. Deproject absolute cursor positions through that fixed matrix and intersect the forward ray with Z=0. This prevents camera movement feeding back into cursor targeting. Reject invalid/horizontal/upward rays. Cancel on release, focus loss, viewport exit/resize, wheel and Home. Keep RMB cursor visible and preserve LMB relative capture.

Scope: native camera/controller and verification only; no map, mesh, material or Blueprint edits. Existing user/HUD work in the shared checkout remains intact.

Verification: new ground-ray regression first failed against the old class (Saved/Logs/GHS_CursorGround_RED.log). Compile using MSVC14.38.33130, run GHS automation including old controls and truck data, then run WarehouseRuntime.CursorGround in a real disposable game viewport across 20 yaw/pitch combinations, including stationary-cursor/no-feedback checks and release handling. Record final results after execution.

Final validation on 2026-10-19: waited for the shared HUD task to finish as the user requested, saved and closed the editor, then linked the final DLL successfully (Saved/Logs/GHS_CursorGround_FinalBuild.log). CursorGround_GHS_Final reports 12 passed, 0 failed; CursorGround_Runtime_Final reports 1 passed, 0 failed across 20 angle combinations in a real 1920x1080 D3D12 viewport. Final independent review confirmed failed projection recapture cancels stale Pan while preserving an existing Orbit gesture. Content hashes match the snapshot taken after HUD completion; evidence is Saved/GHS_CursorGround_ContentPreservation.json.
