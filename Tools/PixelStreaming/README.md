# GHS LAN Pixel Streaming

UE5.4 native PixelStreaming + pinned Epic frontend + local Node signalling/admission + Windows Forms launcher. Deployment output: `../../Deployment/GHSPixelStreaming`.

## Build

1. `Scripts/ghs/package_pixel_streaming.ps1` builds TestGame with MSVC14.38.33130 and cooks the current Zcool warehouse map into `Deployment/GHSPixelStreaming/App/Windows`.
2. `Deployment/GHSPixelStreaming/runtime/node.exe Tools/PixelStreaming/build.js` verifies vendored package SHA512, extracts the pinned dependencies using Windows `tar`, and stages server/player/ws. A clean checkout can use an installed Node.js runtime for this command. Node runtime itself is supplied in deployment, with its license.
3. `Tools/PixelStreaming/launcher/build.ps1` compiles C# and runs launcher checks before emitting the GUI executable.
4. `Deployment/GHSPixelStreaming/runtime/node.exe --test Tools/PixelStreaming/tests/*.test.js` runs protocol, admission, process lifecycle and browser page-policy tests.

Use `Deployment/GHSPixelStreaming/使用说明.md` for operation. Configuration and protocol contract are documented in `server/README.md` and `launcher/README.md`. Browser evidence is under `Saved/PixelStreaming/Browser/20261021`; packaged build and smoke evidence is under `Saved/PixelStreaming/Packaging`.

## Ownership

The launcher creates Node suspended, assigns a kill-on-close Windows Job, then resumes it. A random control token is passed only in the child environment. Management HTTP binds only to loopback and requires the token. Public player traffic cannot invoke launch/stop or access configuration.

One shared UE starts with service; independent instances start on viewer admission. Admission and release serialize through one queue. A disconnected session has a generation-checked grace timer; a restored socket cannot be removed by an obsolete queued cleanup. Evicted sessions never auto-rejoin. The fourth session replaces the oldest admitted session, not the most recently refreshed one.

## Quality and resource budget

The launcher writes `qualityProfile` and `adaptiveResourceBudget` alongside the existing FPS, bitrate, resolution, mode and port fields. The default profile is `clear`; the resource-budget switch defaults to `true`.

| Launcher choice | `qualityProfile` | Min / start / max bitrate (Mbps) |
|---|---|---|
| 流畅 | `balanced` | 8 / 20 / 35 |
| 清晰优先 | `clear` | 12 / 35 / 60 |
| 超清细节 | `ultra` | 20 / 50 / 90 |

Loading a legacy config without a quality profile upgrades the old shipped 8 / 20 / 35 defaults to `clear`. Other legacy bitrate values are retained as `custom`. An explicit `balanced` selection survives reopening. Selecting a profile does not change the configured resolution or target FPS. Port conflict checks, the three-session FIFO limit, and owned-process cleanup on Stop or launcher close are unchanged.

With resource budgeting enabled, independent mode starts each instance at configured FPS divided by active instance count: at the default target, 60 / 30 / 20 FPS for one / two / three instances. It then probes a common FPS budget using each instance's actual FPS feedback. Stable instances permit gradual increases; persistently low achieved FPS causes a reduction and a hold period before probing again. GPU frame times can include waits caused by contention between instances, so the controller does not add those timings to estimate total GPU capacity. When only one instance remains, the configured target is restored immediately (60 FPS by default). This is workload control rather than hard GPU partitioning; equal targets do not reserve fixed GPU percentages or guarantee equal observed FPS. Disabling budgeting keeps the configured target for each instance.

Shared mode renders one scene and does not divide its target FPS by viewer count. Additional viewers still consume encoding and network resources. Budgeting does not reduce the configured resolution: 1080p stays 1080p. Users needing sharper text on high-resolution displays can explicitly select 2560×1440 in the launcher; that increases GPU, VRAM and bandwidth requirements. 60 FPS remains a target dependent on hardware, other application load, network and client decoding, not a guarantee.

## Browser interaction

Left drag rotates, **Shift + left drag pans**, the wheel zooms, and the middle mouse button resets the view. Regular right drag still pans, but browser-level mouse gestures can intercept it and display a trail or “无效手势”. Page event cancellation cannot reliably disable browser or extension gestures; Shift + left drag avoids that conflict. The player includes an operation-help control and cancels page context-menu, image-drag, selection and middle-button autoscroll defaults without replacing ordinary HUD clicks. A lost focus or disconnected transport releases an active alternative pan.

The player retains the configured server resolution and centers it with aspect-preserving `contain`; differently proportioned browser windows can have symmetric letterboxing. The player does not resize a shared UE instance to match an individual viewer's window.

## Approved HUD update, 2026-10-21

The scene search uses a browser DOM combobox for Chinese composition, mapped to the actual UE search rectangle through aspect-preserving video geometry. Names, types, IDs and physical rack slots come from the current scene cache, with 50-result pages and validated selection. Client/request identifiers isolate broadcast responses between shared viewers. UE strips raw NUL transport padding produced by the pinned frontend's UTF-8-size/UTF-16-write discrepancy before parsing bounded search JSON; official dependencies remain unchanged.

The launcher is `像素流服务启动器.exe`. It retains WinForms process ownership and configuration while using the approved navy/white/blue interface. Initial and minimum window bounds respect the selected monitor's work area. Loading uses real connection stages, elapsed time and automatic first frame.

Final update validation: UE 96/96, combined web/service 95/95, launcher 29/29, successful packaging, actual 1080p WebRTC, Chinese composition, multi-page material focus and two-viewer query isolation. Detailed evidence and limits: `docs/superpowers/plans/2026-10-21-approved-hud-streaming-ui.md` in the project root.

## Delivery verification

See `Deployment/GHSPixelStreaming/验收记录.md` for dated evidence. The initial deployment verified actual WebRTC frames and interactions in addition to simulated protocol tests; those baseline measurements predate the new quality/resource settings. Three independent instances exceeded this laptop's 60fps rendering budget in that baseline. New configurations default to shared mode, while the current saved user configuration selects independent mode and is preserved. New runtime claims require fresh browser and UE measurements.
