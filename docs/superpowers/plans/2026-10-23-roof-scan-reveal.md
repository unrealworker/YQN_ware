# Roof Scan Reveal Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the component and HUD tasks; root owns material generation, asset application and integrated verification.

**Goal:** Replace the abrupt roof cut with the approved pale-blue, center-out architectural scan reveal.

**Architecture:** A reversible component transition drives private masked material variants. HUD requests manual or fast opening, gates internal interaction until fully open, and fades the POI/labels around the transition. Existing source materials, geometry and scene placements stay intact.

**Tech Stack:** UE 5.4 C++, Unreal Python material authoring, existing CEF HUD.

**Spec:** User-approved proposal in this conversation: 0.8 s manual reveal, 0.5 s navigation reveal; center activation, two smoothly moving scan fronts, ice-blue narrow material band, short architectural afterglow; reverse restoration.

## Global Constraints
- Work in the current master checkout per the user's existing instruction; preserve unrelated dirty files and live editor changes.
- Manual open 0.8 s; fast navigation open 0.5 s; reverse close 0.55 s. Repeated requests do not restart; changing direction preserves the current visible aperture.
- Initial roof remains fully present without an entrance animation. Opening and closing both block interior picking and internal labels until opening completes.
- No actors, particles, physics or permanent translucent roof. Reuse roof geometry and masked materials, preserve source shading and user overrides.
- No Pixel Streaming launch or performance claim; inspect local runtime motion and frame times.

## Review Focus
- Reset while opening clears queued navigation and reverses smoothly.
- Navigation while closing reopens from the visible aperture; latest target wins.
- Repeated click/fast request does not jump or extend unnecessarily.
- Hidden building layer, initial closed state and missing-roof maps remain valid.
- All material slots, roof edges/skylights, POI and label transitions stay synchronized.

## Task 1: Reversible transition/component
- Files: Source/Test/GHSWarehouseRoofComponent.h/.cpp; Source/Test/Tests/GHSWarehouseRoofTests.cpp.
- Interfaces: OpenRoof(bool bFast=false), RestoreRoof(bool bAnimate=true), IsClosing(), IsTransitioning(); GetOpenProgress() remains continuous 0 closed / 1 open.
- [x] Add meaningful timing, reversal, fast-upgrade, finite-delta and tick/material lifecycle tests.
- [x] Implement the state clock, both directions, immediate initialization/teardown restore and idle tick shutdown.

## Task 2: HUD sequencing
- Files: Source/Test/GHSTwinHUDWidget.h/.cpp, affected web settings state and tests if necessary.
- [x] Route QueueInteriorAction through fast opening; manual click remains standard.
- [x] Fade main POI over activation; fade internal labels after full opening. Keep interaction locks, pending navigation and reset rules.
- [x] Report closing state accurately to the settings UI and diagnostics; cover relevant regressions.

## Task 3: Scan material and integration
- Files: Scripts/ghs/apply_roof_dissolve.py; private Content/GHSZcoolSmartFactory/Roof/ScanReveal assets; Scripts/ghs/verify_roof_scan_runtime.py; docs/ghs-campus-interaction.md.
- [x] Replace noisy cut with smooth timed fronts, a narrow blue-white leading line, feathered ice-blue band and short grid afterglow. Permit controlled regeneration of only known generated variants.
- [x] Record source asset hashes and editor/map state, apply generated variants, compile TestEditor with MSVC 14.38.33130.
- [x] Run GHS automation and web checks; capture actual opening/reversal sequences and local frame-time evidence.
- [x] Independently review, restore editor view/state and verify map/source-material preservation. Integrate only owned code/resources into the user-authorized master checkout.

## Added user scope: clean business-page annotations
- [x] Remove technical warehouse/extract metadata from business pages while preserving unverified-data notices, business quantities and identities.
- [x] Update and natively save Pencil components and 21 affected artboards; preserve existing admin/login designs.
- [x] Verify 90 web tests and 9 real CEF checks at desktop/mobile viewport sizes.
- Source design includes pre-existing uncommitted admin/login work; the complete updated design is saved locally and kept outside the scoped code commit.
