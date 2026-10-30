# GHS Pixel Streaming

UE5.8.4 PixelStreaming2 + pinned Epic frontend + Node signalling/admission + Windows Forms launcher. Supports LAN and configurable public HTTPS/STUN/TURN deployment. Legacy output: `../../Deployment/GHSPixelStreaming`; portable public delivery: `../../Package_PixelStreaming2_20261030`.

## Build

1. `Scripts/ghs/package_pixel_streaming.ps1` builds TestGame with the UE5.8-compatible MSVC toolchain and cooks the current Zcool warehouse map into `Deployment/GHSPixelStreaming/App/Windows`.
2. `Deployment/GHSPixelStreaming/runtime/node.exe Tools/PixelStreaming/build.js` verifies vendored package SHA512, extracts the pinned dependencies using Windows `tar`, and stages server/player/ws. A clean checkout can use an installed Node.js runtime for this command. Node runtime itself is supplied in deployment, with its license.
3. `Tools/PixelStreaming/launcher/build.ps1` compiles C# and runs launcher checks before emitting the GUI executable.
4. `Deployment/GHSPixelStreaming/runtime/node.exe --test Tools/PixelStreaming/tests/*.test.js` runs protocol, admission, process lifecycle and browser page-policy tests.

Use `Deployment/GHSPixelStreaming/使用说明.md` for operation. Configuration and protocol contract are documented in `server/README.md` and `launcher/README.md`. Browser evidence is under `Saved/PixelStreaming/Browser/20261021`; packaged build and smoke evidence is under `Saved/PixelStreaming/Packaging`.

For a portable public package, set `-Configuration Shipping -ArchiveDirectory <delivery>/App` on the packaging script, build the launcher, then run `node Tools/PixelStreaming/assemble-public.js --output <delivery> --launcher <launcher-output>`. An optional `-BuildProjectFile` supports an isolated build checkout while preserving the open editor. The assembler verifies current UI/data hashes, copies Node and the launcher, adds configuration and Chinese operation notes, and records a SHA256 manifest. It preserves any existing destination launcher configuration.

The assembler also accepts `--engine-root <UE5.8 directory>` (default `D:/UE/UE_5.8`). It verifies the engine version and stages the actual official `vc_redist.x64.exe` and `GameInputRedist.msi` from that engine, records matching SHA256 values, and includes an explicit administrator installation action. UE5.8 no longer ships `UEPrereqSetup_x64.exe`; no legacy prerequisite placeholder is accepted.

The public delivery starts in LAN mode until a real public URL and appropriate TLS/STUN/TURN settings are supplied. Access-code protection is an independent opt-in: `accessProtectionEnabled` defaults to `false`, including when absent from older configurations. Enabling it requires an access code of at least 12 characters for both LAN and public entry. The assembler preserves existing destination configuration and writes the default `false` only for new configuration files. See `deployment/部署说明.md` and `deployment/验收记录.md`. Admission capacity remains 1–10 and is not a guarantee of ten simultaneous GPU-rendered scenes.

## Ownership

The launcher creates Node suspended, assigns a kill-on-close Windows Job, then resumes it. A random control token is passed only in the child environment. Management HTTP binds only to loopback and requires the token. Public player traffic cannot invoke launch/stop or access configuration.

One shared UE starts with service; independent instances start on viewer admission. Admission and release serialize through one queue. A disconnected session has a generation-checked grace timer; a restored socket cannot be removed by an obsolete queued cleanup. The configured limit is 1–10, default 10; excess sessions are rejected without evicting existing viewers. Admin disconnect revokes the selected session and stops automatic reconnection; the user may explicitly authenticate again. The launcher shows connection identity, source, duration and state.

Player admission always requires a server-issued session token. When `accessProtectionEnabled:true`, the session endpoint additionally verifies the configured access code; when false, the page automatically requests a session and enters without the “安全访问仓库” form. A previously saved code does not implicitly enable protection. Disabling this gate does not weaken public Host/Origin checks, TLS validation, IP/proxy trust rules, session revocation or the ten-viewer limit. UE signal sockets bind to loopback, authenticate a per-instance token and validate identity before receiving ICE credentials. Admin control is loopback-only with a separate random bearer token. Public configuration supports native TLS or an explicitly trusted local reverse proxy; only the latter consumes proxy headers. Firewall helpers use program/path-specific rules and do not expose admin or UE signal ports.

## Quality and resource budget

New launch configurations use 1920×1080, fixed target 60 FPS, NVIDIA encoder policy and decoupled capture. The launcher exposes these settings in its main configuration area. A fixed target disables adaptive resource budgeting and preserves real simulation time; the target still depends on available rendering, encoding and network capacity. Existing configurations retain their explicitly saved FPS/bitrate values.

The native UE5.8 setting for capture decoupling is `PixelStreamingDecoupleFramerate`; there is no native `PixelStreamingEncoderAsync` setting. The project implements `PixelStreamingEncoder=NVIDIA/Auto` and `FixedFPS=<target>` compatibility parameters with validation. See `launcher/README.md` for precise mappings and `server/README.md` for the signalling contract.

| Launcher choice | Profile | Min / start / max Mbps |
|---|---|---|
| 流畅优先 | balanced | 1 / 8 / 24 |
| 清晰优先 | clear | 1 / 10 / 35 |
| 超清细节 | ultra | 1 / 16 / 50 |

Loading or saving a configuration never reapplies presets over explicit saved values. With fixed mode disabled, adaptive budgeting waits for warmup and sustained fresh low-FPS telemetry; it does not divide FPS merely by viewer count. FPS 0 means uncapped rendering, with a positive 120 FPS PS2 negotiation ceiling.

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

## UE5.8 migration

The peer-stream comparison sidecar/proxy is removed. Current deliveries use only PixelStreaming2 and its compatible frontend. Delivery manifests record `engine`, `pixelStreamingPlugin`, `sourceCommit` and the actual `sourceDirty` flag. A clean manifest does not substitute for real browser video and input verification.
