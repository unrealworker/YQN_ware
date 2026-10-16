# Warehouse refinement V2 implementation plan

**Goal:** Correct cargo proportions, close the roofless warehouse envelope, open and restyle all docks, populate every dock with a waiting box truck, and recover column-conflicted storage by modest rack spacing changes in both scene styles.

**Spec:** User request and screenshot in this conversation; confirmed external box trucks with their rear aligned to each loading door. Both GHS maps remain synchronized.

**Architecture:** Add versioned Blender/FBX assets and a staged registry under `SourceAssets/GHS/RefinementV2`. Build from immutable CAD-derived source data. Back up current maps/registries, apply the shared geometry in live UE with independent existing blue/normal palettes, then reload both maps in a fresh UE process and inspect rendered views.

**Constraints:** Preserve CAD footprint and column coordinates, real rack beam heights, green animated AGV effects, existing lighting and no roof. User authorizes small rack spacing adjustments to recover conflicting storage. Treat 9.6m building and 4.2m doors as existing visualization assumptions. Keep old assets/reports immutable. Use instancing and LODs for repeating assets.

## Tasks

- [x] Checkpoint both maps, registries, content hashes and historical reports before mutation.
- [x] Build proportionate separated carton stacks within unchanged rack frames; verify box aspect ratios and frame dimensions.
- [x] Restore complete rack bays and recover blocked storage through modest layout changes; validate columns, aisle widths, full-size pallets, walls and storage intersections.
- [x] Build a complete exterior wall ring and door headers from the CAD footprint, retaining internal partitions and closing corner gaps; cut intentional door openings only.
- [x] Replace black-backed doors with double-sided detailed half-open shutters, at all 87 CAD dock locations.
- [x] Build/reuse a proportionate box truck, style it for both palettes, and place 87 outside with rear aligned to dock and no inter-truck/wall collisions.
- [x] Import new versioned meshes/materials, update both maps and registries, preserve all unrelated state and save.
- [x] Fresh-load verification and actual UE render review of warehouse exterior, docks, rack cargo and recovered column positions. Maintain compatible verification entrypoints and document actual deviations/assumptions.

## Design decisions

- Use small carton assemblies, not scaled cargo meshes. B's shallow levels receive a single carton tier; A/D1 tall load envelopes receive several distinct tiers with headroom.
- Half-open shutter means approximately 2.1m clear opening under a 4.2m door. Narrow dark seals are acceptable; the broad rear black plate is removed.
- Exterior wall thickness defaults to 0.254m while retaining existing CAD interior partition geometry. All wall top outlines must form closed loops.
- Truck design is a medium rigid box truck, modeled in metres and parked nose outward. Truck dimensions are an explicit visual estimate, consistent across all 87 bays.
- Every displaced/recovered storage identity is recorded; do not silently omit bays or shrink cargo to hide clashes.
