# Adaptive 3x3 truck HUD aggregation

## Follow-up: 2x2 quadrants

The user requested four larger screen regions after reviewing the nine-cell version. The current implementation uses two columns and two rows, with at most four active labels; all animation, selection, dwell and responsive behavior remains applicable. Both the clusterer and compact label measurement now share the same column constant.

- [x] Update production layout and all 11 grid tests to actual quadrant boundaries.
- [x] Update and save the Pencil source and the fourth-board PNG.
- [x] Build Editor and run all 23 GHS automation tests successfully.
- [x] Revalidate actual scenes across five viewport sizes and live resizing, then restore the editor. Full 24, Small 22, UltraWide 23, Portrait 23 and Narrow 22 passed. The independent verifier now rounds logical viewport dimensions to Slate float32 precision before strict quadrant classification.

## Previous nine-cell implementation

User refinement: aggregate trucks within nine equal screen regions; do not let proximity chains join trucks across the screen. The current viewport, rather than a fixed 1920x1080 reference, defines the grid.

- Normalize the existing projected truck anchor by the HUD canvas width and height. Three columns and three rows define cells 0–8.
- Each occupied cell has one active label. More than one truck becomes a count badge; a sole truck retains its compact label. Proximity and badge overlap cannot merge different cells.
- Confirm individual cell changes over 200 ms to suppress boundary chatter. Newly visible trucks enter immediately; removed trucks leave immediately. Canvas resizing rebuilds assignments immediately for the new aspect ratio.
- Keep current 280 ms group transitions, 220 ms detail/list transitions, per-page member selection, viewport clamping and telemetry behavior.
- Grid lines describe the design and tests; they do not add a visible overlay to the product.

## Work and verification

- [x] Replace clusterer and update meaningful tests for cell isolation, per-cell uniqueness, normalized sizes, resizing, boundary dwell and 52 truck identity conservation.
- [x] Update Pencil fourth board, its exported image and docs for the revised behavior. Source save is pending because the minimized Pencil window cannot be restored by the UI tool.
- [x] Build with MSVC 14.38.33130 and run GHS automation: 23 passed, zero failed.
- [x] Run actual warehouse validation at 1920x1080, 960x540, 2560x1080, 800x1200 and 360x800, plus resize an existing game viewport to 1280x960. All five variants passed; screenshots inspected. Telemetry and long-text regressions passed at Full and Small sizes.
- [x] Restore editor and verify the warehouse scene is open with the rebuilt HUD. Final UI observation shows the current PIE preview with separate labels in three occupied screen regions.
