# GHS UE5.4 LAN service

Run the bundled Node executable from the delivery folder:

```text
runtime/node.exe server/server.js --config config.json --control-file logs/control.json
```

The launcher supplies a fresh `GHS_CONTROL_TOKEN` environment variable (at least 24 characters). Configuration is read once; stop before changing mode, ports or resolution. Required `executablePath` can be absolute, or relative to the configuration file. Paths containing Chinese characters and spaces are passed as argument-array entries without a shell.

Default configuration: `httpPort:8080`, `streamerPort:8888`, `mode:"shared"`, `showWindow:false`, `width:1920`, `height:1080`, `fps:60`, `qualityProfile:"clear"`, `adaptiveResourceBudget:true`, `minBitrateMbps:12`, `startBitrateMbps:35`, `maxBitrateMbps:60`. Bitrates and frame rate are targets; actual decoded video statistics are available in the browser's lower-left panel and read-only `window.ghsStreamingStats` snapshot. Existing saved mode and dimensions are preserved by the launcher.

The public HTTP server binds all IPv4 interfaces and exposes the player, read-only `/health`, and `POST /api/session`. Player signalling uses `/ws?token=<session>`. UE signalling binds **127.0.0.1** only. Local-subnet firewall scope is configured by the deployment scripts; this service is not a public-internet authentication service. Media uses UDP 50000–50199, with no external STUN/TURN dependency.

The dynamically assigned loopback management HTTP port is written atomically to the control file as `{controlPort,pid,httpPort,streamerPort}`. `GET /status` and `POST /stop` require `Authorization: Bearer <GHS_CONTROL_TOKEN>`. Public port requests cannot reach these endpoints.

Each admitted browser tab has a random session token. Reconnecting the same token replaces only its previous socket and retains its admission order. Disconnects retain their slot for 8 seconds to allow reload/network recovery. The fourth new session evicts the oldest admitted session. Evicted tokens remain refused until this service stops; the page saves an eviction marker and requires an explicit “重新进入” action to obtain a new session. The session list is bounded to 10,000 records per service lifetime.

Shared mode starts one UE immediately. Independent mode starts one UE per admitted session and reaps an evicted/disconnected instance before starting its replacement. Owned, still-running child PIDs are the only `taskkill /PID /T` targets; the Windows launcher additionally places Node and descendants in a dedicated Job Object. UE executable processes must be descendants of the launched application; no global process-name cleanup is used.

The packaged GHS runtime supports a private `-GHSStreamControlDir` file bridge. Node writes bounded, sequenced FPS/bitrate budgets atomically outside the public static root; UE acknowledges them in `metrics.json`. The bridge permits no arbitrary console commands. Dynamic rendering limits affect `t.MaxFPS` only: UE5.4 snapshots `PixelStreaming.WebRTC.Fps` into new RTP senders, so the capture ceiling stays at the configured maximum to permit recovery without reconnecting. This live control requires the GHS runtime module; unrelated UE executables without that module only receive startup flags.

Independent budgets start at configured FPS divided by instance count. After warmup, fresh acknowledged actual-FPS samples permit gradual equal increases; persistent underperformance reduces the common budget and holds it before another probe. GPU frame times are diagnostic only, because they include inter-process contention. Shared mode and a single independent viewer retain the configured target. Runtime files are removed after each owned instance exits.

UE signalled startup has a 120-second deadline. The browser also has a 120-second first-frame deadline and reports the last actual connection stage. First-frame completion uses `requestVideoFrameCallback` where supported. Pixel Streaming input/WebRTC handling is the pinned Epic UE5.4 library; the application does not reimplement the data channel input protocol. Browser resize never changes the UE render resolution.

To rebuild offline, run `node Tools/PixelStreaming/build.js` from the project. Build verifies the SHA-512 of all three vendored npm archives using `dependency-pins.json`, retains licenses, and copies server/player/ws into `Deployment/GHSPixelStreaming`. The only runtime Node dependency is `ws`. The SDP source is wrapped to expose its existing implementation to the unmodified Epic UMD bundle.

Run the meaningful service tests with `node --test Tools/PixelStreaming/tests/*.test.js`. Tests use real local HTTP/WebSocket traffic and real child processes simulating UE signalling. They do **not** substitute for actual WebRTC video/input validation on the packaged UE application.
