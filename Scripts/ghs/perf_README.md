# Warehouse Twin 1080P performance capture

The native driver is disabled unless `-TwinPerf=<label>` is explicitly supplied.
Use an owned standalone game process. It quits that process after recording the
result. It never saves maps, assets, user settings, or project configuration.
Editor binaries additionally require `-game`; Shipping builds omit the driver.

The same driver supports Editor-game and packaged Development. Compare before
and after **within the same build/runtime**, not Editor-game against packaged.
Route version 2 records the executable's build configuration, active RHI,
`-RenderOffscreen` flag and actual viewport window mode. All four fields are
required for version 2 evidence and must match across a comparison.
The frozen baseline must include this driver, but no production optimizations.
Do not capture while building, cooking, compiling shaders, importing assets,
recording screenshots, or running another UE game on the same GPU. Keep laptop
power mode, AC power, display/GPU selection, and background load consistent.

## Run

Root coordinator builds and starts the processes. Example Editor-game command:

```powershell
& 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor.exe' `
  'D:/UEPro/Test/Test.uproject' `
  '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory' `
  -game -RenderOffscreen -Windowed -ForceRes -ResX=1920 -ResY=1080 `
  -Unattended -NoVSync -TwinPerf=BaselineEditor `
  '-TwinPerfOutput=D:/UEPro/Test/Saved/PerformanceP0P1' `
  '-abslog=D:/UEPro/Test/Saved/PerformanceP0P1/BaselineEditor.log'
```

Packaged Development uses the staged game's executable and the same map/options;
omit the `.uproject` argument. `-game` is harmless but unnecessary there. Use the
same `-RenderOffscreen` presentation mode for both sides of a comparison. Run
each side at least three times; startup and first route include naturally cold
business pages, while the second route provides a warm repetition.

Options:

| Option | Meaning |
| --- | --- |
| `-TwinPerf=BaselineDevelopment` | Safe label; required to enable the driver |
| `-TwinPerfOutput=D:/...` | Results root; defaults to this game's `Saved/TwinPerf` |
| `-TwinPerfWarmup=15` | At least 15 seconds after browser readiness |
| `-TwinPerfDuration=90` | At least 90 seconds; repeats a fixed 45-second route |
| `-TwinPerfDuration=1800` | 30-minute soak with the same route |
| `-TwinPerfTrace` | Also writes an Insights trace; compare trace runs separately |

Outputs are `<root>/<label>_<UTC>/run.json`, `frames.csv`, and optionally
`trace.utrace`. The CSV must finish writing before the process exits. A failed
fixture, viewport resize, world loss, or deadline marks the native run failed.
`success` in the native report means the route and CSV writer completed; it is
**not** a 60 FPS result. Run the analyzer to check timing columns and budgets.

The driver temporarily requests uncapped 100% screen percentage, no VSync or
dynamic resolution, GPU CSV timestamps, and no background throttling. It records
the original/effective values and restores originals at exit. It preserves all
other quality settings. GI/reflection CVars are not final post-process settings;
do not infer that Lumen is active from `r.DynamicGlobalIlluminationMethod=1` alone.

## Fixed 45-second route, repeated twice by default

| Seconds | Workload |
| --- | --- |
| 0 | Overview with native selection reset |
| 1 | POI density `all` (the production cap remains 32) |
| 4–12 | Continuous orbit, 45 input pixels/second |
| 12 / 16 | Focus AGV-07 / FORK-01 and open equipment details |
| 20 | Rack-region preset |
| 24 | Aim at deterministic actual HISM rack cargo |
| 26 | Project cargo to screen and use `HandleSceneClick`; require MATERIAL selection |
| 28 / 29 | Close/open the complete panel |
| 30–36 | Devices, orders, inventory, alerts, trace, settings, overview pages |
| 38 / 40 | Overview and all-POI mode |

The route spans repeated two-second updates and 30-second cache intervals. Setup
loads the cargo fixture once before warmup. During capture it avoids screenshots,
per-frame JSON serialization, and file polling. It uses native public HUD/camera
APIs, so this is rendering and application workload evidence, **not OS input
delivery or Pixel Streaming latency testing**. `GHSTwinPerfDriver` and
`GHSTwinPerfAction` CPU scopes plus `TwinPerf:<segment>` bookmarks identify tool
overhead. Segment CSV events use the same names.

## Analyze and compare

```powershell
$perfPython = 'C:/Users/28109/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $perfPython Scripts/ghs/perf_analyze.py summarize 'D:/.../BaselineDevelopment_UTC/run.json'
& $perfPython Scripts/ghs/perf_analyze.py compare `
  'D:/.../BaselineDevelopment_UTC/run.json' 'D:/.../OptimizedDevelopment_UTC/run.json' `
  --output 'D:/.../comparison.json'
& $perfPython Scripts/ghs/perf_test_tools.py
```

The analyzer writes `summary.json` beside the native report. It requires completed
CSV final-header metadata, valid actual GPU timestamps, complete workload markers,
1080P, warmup, and at least 90 measured seconds. It reports mean/P95/P99 frame,
Game, Render and GPU times, frame-budget exceedances, per-segment measurements,
and GPU pass timings where UE supplies them. CPU and GPU work can overlap; their
durations must not be added as a frame-time prediction. GPU pass values near a
segment boundary can reflect delayed query resolution; use Insights for exact
individual hitch attribution.

Version 2 uses complete CSV frame boundaries: exclude the frame containing
`capture_begin`, include the frame containing `capture_end`, then exclude all
GPU-drain frames. CoreTicker dispatches the markers after scene/Slate work, so
the end frame includes any hitch that crossed the route's duration threshold.
Final browser/POI report construction runs on the next tick during drain and
cannot inflate that measured end frame. `sample_window` in the summary records
this policy as `after_begin_through_end`.

Historical version 1 captures retain their original begin-inclusive,
end-exclusive parsing. They can omit the new execution metadata, so they do not
establish the stricter compatibility guarantees of version 2. A version 1 run
cannot be compared with a version 2 run. Rebuild both baseline and optimized
packages with the same version 2 driver before collecting new evidence.

The comparison rejects changes in runtime type, build configuration, RHI,
offscreen/window presentation, engine/hardware, resolution, route, cargo fixture,
duration, warmup, trace mode, or recorded quality CVars. Version 2 summaries and
comparisons reject missing or invalid execution metadata instead of treating
two missing values as evidence of a match.
Negative deltas indicate lower measured cost, not proof of causation. Record
P95/P99 and hitch counts across repeated runs, not just average FPS. Keep every
raw capture. Pixel Streaming additionally needs encoding, transport and browser
presentation measurements in a separate end-to-end acceptance step.

## Current capacity fixtures and diagnostic variants (2026-10-28)

The current warehouse uses full-load `*_Capacity` HISM meshes whose visible
cargo is controlled by `storage-capacity.json`. A pre-capacity benchmark DLL
that only looks up exact mesh names in `rack-slots.json` cannot run this scene:
it fails with `No actual rack cargo fixture`. Rebuild the diagnostic driver;
do not bypass the real material-click assertion or reuse an old scene to make
that assertion pass.

`cargo_fixture_version: 2` supports the current capacity slots and retains the
legacy `rack-slots.json` lookup. For current capacity meshes it validates the
group tag, actual mesh, instance count, complete slot bounds and indices, and
capacity initialization. It chooses actual world-space slot centers filtered
through `IsStorageHitVisible`; hidden cargo is not a valid fixture. The report
records the metadata source, component/instance/mesh, slot count, visible
candidates and capacity state. The fixed action sequence is still
`route_version: 2`: cargo is projected into the viewport and selected through
`HandleSceneClick`, with a required `MATERIAL:` result.

The native variant setup runs once before warmup, outside the timed sample.
It first verifies all **13** unique tagged storage groups against metadata
(the current asset set contains **9,159** instances), and verifies that campus
traffic is ready with four components and 32 fixed instance slots. Mismatched
or missing components fail the run before measurement. This current-scene
validation also applies to the native baseline.

| `-TwinPerfVariant=` | Runtime change in the owned diagnostic process |
| --- | --- |
| `baseline` or omitted/empty | Validate and record the scene; do not alter storage or traffic properties |
| `shadow-auto` | Set the 13 storage groups' `ShadowCacheInvalidationBehavior` to `Auto` |
| `shadow-off` | Disable `CastShadow` on those 13 storage groups |
| `traffic-off` | Disable the campus traffic actor's tick; its existing vehicles remain visible |
| `traffic-hidden` | Disable that actor's tick and hide its vehicles |

Storage variants assign runtime C++ properties and call
`MarkRenderStateDirty`. They do not call editor property setters or
`PostEditChange`, rebuild Blueprint components, change mesh instances, or
change collision settings. The setup reads properties and counts back after
each change. Original values are held by weak object references and restored
on completion/failure; restoration failure prevents a successful run.
`run.json` contains `process_id`, `variant`, `variant_setup` with per-group
before/after values and traffic state, and `variant_restored`.

The former `perf_variants_20261028.py` setup experiment is retired. Its Python
`set_editor_property` path could reconstruct Blueprint-owned components. Do
not use `-ExecCmds="py ...perf_variants_20261028.py"`; native variants need only
`-TwinPerfVariant=...`. Failed experiments belong under `Saved`, not in the
production launch path.

These switches are diagnostic controls, not production optimizations. Without
`-TwinPerf=<label>` no variant setup runs, even if a variant parameter is
present. Normal application behavior is unchanged, and Shipping omits this
driver. At documentation time, `traffic-off` and `traffic-hidden` are prepared
but have **not been runtime-validated**. No performance benefit is claimed by
the existence of any switch; results must come from completed matched runs.

## Trace completion and click attribution

Trace capture now calls `FTraceAuxiliary::Start(File, path, channels)` directly,
using `cpu,gpu,frame,bookmark,task,loadtime`. It does not construct a quoted
`Trace.File` console command. The driver checks the start result, then waits
up to five seconds for a file connection whose destination matches the exact
requested path before beginning the measured route.

After the CSV writer finishes, the driver requests `FTraceAuxiliary::Stop`
only if the connected destination still belongs to this run. Stop is
asynchronous: an additional drain stage waits up to five seconds until
`IsConnected()` becomes false, which follows the trace writer's flush and
file close. It then requires an existing, nonempty `.utrace` before reporting
success. Drain frames are outside the route's measured sample. A start,
connection, stop, close, or file failure makes the run fail; a pre-existing or
changed trace destination is not stopped as if it belonged to this run.

Inspect `trace_path`, `trace_destination`, `trace_start_succeeded`,
`trace_connected`, `trace_connected_before_stop`, `trace_stop_succeeded`,
`trace_connection_closed`, `trace_file_exists` and `trace_file_bytes` in the
report. Older runs that claimed `trace_enabled` without a valid trace file do
not establish CPU scope evidence. `GHSTwinScene_PickRay` is an additional CPU
scope for the actual scene-picking traversal; it measures that work without
changing the selection algorithm. Keep traced runs separate from non-traced
timing comparisons.

## Isolated builds while preserving an open user Editor

Do not overwrite a project DLL currently loaded by the user's Editor, stop
that Editor to free the DLL, or save its unsaved map as part of benchmarking.
The current diagnostic workspace is
`Saved/Performance20261028/IsolatedProject/Test.uproject`:

1. Copy the `.uproject`, `Source`, `Config` and required project plugin into a
   dedicated diagnostic directory. Give it independent `Binaries`,
   `Intermediate`, `Saved` and derived-data directories. Copy source again
   only before freezing/building a new diagnostic version, never mid-matrix.
2. Use a `Content` directory junction to the source project's current content
   when disk space requires it. This shares the real map/assets; it is **not**
   a filesystem read-only snapshot. The capture driver must never save them.
   Record the map hash before and after. Do not recursively clean through the
   junction or use it for asset-editing experiments.
3. Build `TestEditor Win64 Development` against the isolated `.uproject` with
   the project's UE 5.4 toolchain (MSVC `14.38.33130`). Freeze one resulting
   DLL hash for the baseline/variant matrix. Do not mix captures from earlier
   DLLs, different source/map states, or pre-capacity fixture code.
4. Launch only owned standalone `-game -RenderOffscreen` processes. Record
   their PID and process start time; wait for that exact process to exit
   before the next run. Never terminate processes just by `UnrealEditor`
   name. Preserve the user's existing Editor and its unsaved scene.

The current helper expects that isolated project to have already been built:

```powershell
& 'D:/UEPro/Test/Scripts/ghs/perf_run_owned_20261028.ps1' `
  -Label BaselineNativeExample -Variant baseline
# After that exact owned process exits:
& 'D:/UEPro/Test/Scripts/ghs/perf_run_owned_20261028.ps1' `
  -Label ShadowAutoNativeExample -Variant shadow-auto
# Collect scope evidence in a separate run:
& 'D:/UEPro/Test/Scripts/ghs/perf_run_owned_20261028.ps1' `
  -Label TraceNativeExample -Variant baseline -Trace
```

The helper uses a 30-second warmup and 90-second route, writes
`launch-<label>.json` with the owned PID/start time, source commit, map hash,
diagnostic DLL hash and exact arguments, and refuses a still-running process
recorded by that helper. Independently check for other GPU work and keep the
desktop unlocked; a locked-session plumbing check is not a performance
baseline. The helper's recorded background-condition label must match the
actual desktop state. If the user's Editor remains open, keep its state
consistent and describe measurements as shared-GPU local diagnostics, not
dedicated-server capacity.

`-DiagnosticTAA` is a separate helper experiment that changes the AA CVar for
that process. It changes rendering quality and is not an equivalent-quality
baseline comparison; the analyzer should report the CVar mismatch. Likewise,
turning shadows off is a cost-isolation experiment, not an accepted visual
configuration. The existing analyzer does not automatically enforce matching
map/DLL hashes or interpret native `variant_setup`; review the launch and
native manifests alongside it. Preserve raw captures and report repeated
baseline variation before attributing a difference to a variant.
