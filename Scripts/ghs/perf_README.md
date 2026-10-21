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
