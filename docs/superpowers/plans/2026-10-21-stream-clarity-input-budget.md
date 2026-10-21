# Pixel stream clarity, framing and resource budget Implementation Plan

> Use parallel agents for camera, player input, runtime control; root integrates service and launcher and validates the packaged browser.

**Goal:** Fix the reported initial framing and browser gestures, improve visual clarity, and distribute available rendering work between independent viewers without restarting their scenes.

**Architecture:** Correct camera startup framing and video containment. Provide Shift+left-drag pan to avoid browser-native right-button gestures. A private per-instance local JSON control/telemetry bridge permits only bounded FPS/bitrate settings; Node computes fair independent-instance budgets. Shared mode retains one renderer at configured FPS. Quality selection is visible in the launcher.

**Tech Stack:** Existing UE5.4 C++, Epic UE5.4 JS player, Node, WinForms.

**Spec:** Current user screenshots and request; no global browser setting changes, preserve current independent/shared choice and local settings.

## Review focus

- Initial camera must frame actual warehouse inside unobscured scene, at initial layout and after reset, without user drag being overwritten.
- Player video and mouse coordinates must agree at wide/tall aspect ratios; avoid double letterboxing.
- Browser/extension gestures cannot be reliably disabled by page code. Shift+left pan must work, and releasing outside/blur must not leave a held mouse button.
- Single independent viewer gets configured FPS cap; 2/3 instances share measured available work fairly; disconnect restores remaining capacity. This is a workload target, not hardware GPU partitioning or guaranteed FPS.
- Bridge accepts only bounded finite known values, no arbitrary console commands or browser-nominated paths. Restart/eviction cleanup still owns only this session's children.
- Quality is native-resolution plus encoding controls; do not claim upscaling was proven without runtime evidence. Do not lower resolution automatically behind the user.

## Tasks

- Camera agent: find startup/reset discrepancy; implement actual-bounds framing and regression checks.
- Player agent: inspect real DOM sizing, fix containment and gesture alternatives; test mapping and cleanup.
- Runtime agent: private budget JSON ticker and telemetry, validation/atomic writes/tests.
- Root: integrate adaptive budget controller, quality controls and safe defaults into server/launcher, preserve config; tests for fair split/recovery/stale metrics.
- Build/package after agent changes; actual first frame, wide/tall viewports, Shift-pan, material selection, quality stats and 1→2→3→1 budget acknowledgment; finalize running deployment and updated docs.
