# GHS UE5.8 PixelStreaming2 service

Start with the bundled runtime:

```text
runtime/node.exe server/server.js --config launcher.config.json --control-file logs/control.json
```

The Windows launcher supplies a fresh `GHS_CONTROL_TOKEN` (at least 24 characters) only through the child environment. Configuration is read once; stop before editing settings. UE and TLS file paths can be absolute or relative to the configuration file. Chinese paths and spaces are supported without shell execution.

## Connections and operator controls

`maxViewers` defaults to **5**, configurable from 1 to 5. Older valid values 6–10 migrate to 5. Both shared and independent modes count admitted browser sessions. A sixth browser is refused with an explicit full-capacity message; existing users stay connected. A connection lost to the network holds its place for 8 seconds. Reconnecting the same token replaces only the old socket.

The token-protected management server binds **127.0.0.1** on a dynamic port written to the control file. Its routes are never available on the player port:

- `GET /status`: runtime state, `viewerCount`, `maxViewers`, `viewers`, `instances`, addresses and bounded logs.
- `POST /disconnect`, JSON `{ "playerId": "1" }`: revoke that session, send a terminal disconnect notice, release its independent UE instance and return after cleanup. Requires `Authorization: Bearer <GHS_CONTROL_TOKEN>`.
- `POST /stop`: stop the service and only its owned process tree.

Each viewer row contains `playerId`, optional `displayName`, client `address`, bounded `userAgent`, ISO UTC `connectedAt`, `instanceId`, and `state` (`starting`, `connected`, `reconnecting`, `failed`). `connected` denotes signalling subscription; actual received video/frame rate is reported in the browser. Status and logs contain neither session bearer tokens nor access/TURN secrets.

A manually disconnected browser does not automatically reconnect, including on reload. The user must explicitly choose re-entry; access-code protection, when enabled, requires the code again. This is a connection-disconnect action, not a permanent identity/IP ban.

### Optional pristine warm standby

`warmStandbyEnabled` is a strict boolean, false when absent. In independent mode it maintains at most one pristine spare, counted inside the five-process limit. A spare must authenticate, report fresh PSO=0 metrics for a stable interval, and acknowledge its explicit 5 FPS standby budget before `warmReadyCount` becomes one. Active users retain their configured FPS, capture ceiling, resolution and bitrates. Leasing is one-way: restore the active budget and wait for its new acknowledgement before advertising the streamer. A used instance is destroyed after the ordinary disconnect grace, never recycled into the pool.

Demand launches take priority. Replenishment waits until every connected subscriber has reported a real first displayed frame and remained connected for three seconds. It additionally requires fresh healthy user telemetry, free system memory of at least 8 GiB / 12%, and visible GPU free memory of at least 3 GiB / 20%. The thresholds are conservative spare-admission heuristics, not measured five-user capacity. The GPU check runs asynchronously at most every ten seconds with a three-second timeout; missing/stale GPU data suppresses additional standby while users are active. Sustained resource pressure retires an idle spare instead of lowering active users' budgets. Failed warmup retries back off from 30 to 120 seconds. Service stop cancels the pool and GPU probe.

Operator status adds `warmReadyCount`, `warmStartingCount`, `warmBlockedReason` and per-instance standby state. Browser `ghsStreamingStats.startup` separates page navigation, session, readiness, subscribe, offer/answer, ICE and first displayed frame. `ghsFirstFrame` is an authenticated, bounded, once-per-subscribed-connection report used only to postpone background replenishment; it does not grant routing or change admission limits.

### Bounded UE initialization

An already spawned UE process authenticates its loopback signal socket with its own random token. Its first `endpointId` may arrive after scene/UI initialization, so that one pending socket shares the existing **120-second deadline measured from process launch**. Connecting or reconnecting never extends the deadline. An unknown token/origin is rejected; only one pending identity socket is allowed for an instance, and no ICE credentials or player routing are released before the matching endpoint identity. Ready-instance reconnects retain the ordinary **10-second identity deadline**.

Missing heartbeat replies during this initial wait share the same bounded process deadline; the normal heartbeat resumes after identity. Process exit, administrator removal and service stop immediately close pending sockets. Startup capacity advances only after a valid identity or completed failed-process cleanup, never just a WebSocket connection.

Management instance rows include `startupStage`, `startupElapsedMs` and `identityWaitMs`. `GHS_STARTUP` logs record process start, waiting identity, ready, identity timeout or failure without tokens or raw URLs. The player shows “场景进程已连接，正在完成资源和界面初始化” using its existing progress design. Signalling identity is not proof of a decoded video frame.

## Public network configuration

| Field | Purpose |
| --- | --- |
| `networkMode` | `lan` or `public` |
| `publicUrl` | Exact player origin, e.g. `https://warehouse.example`; root path only |
| `accessProtectionEnabled` | Strict boolean; defaults to `false`, including when absent in older configuration; independently gates LAN and public sessions |
| `accessCode` | At least 12 characters when protection is enabled; a saved code alone never enables the gate |
| `httpPort` | Player TCP port, also used for native HTTPS; 1–65535 |
| `tlsCertPath`, `tlsKeyPath` | Matching PEM certificate chain and private key for native HTTPS |
| `trustProxy` | Explicit same-machine reverse proxy; mutually exclusive with native TLS |
| `externalTlsTermination` | HTTPS terminated by an external cloud load balancer, HTTP backhaul; defaults to false, exclusive with native TLS and `trustProxy` |
| `stunUrl` | Optional `stun:host:3478` or `stuns:host:5349` |
| `turnUrl` | Optional `turn:host:3478?transport=udp` or `turns:host:5349?transport=tcp` |
| `turnUsername`, `turnPassword` | Required when TURN is configured |

Choose one entry arrangement:

1. **Native HTTPS:** provide the real certificate/key, matching HTTPS public URL and TCP port (typically 443). Node serves HTTPS and WSS directly using TLS 1.2 or later.
2. **Local reverse proxy:** set `trustProxy:true`, configure the public HTTPS origin and let the proxy terminate TLS. The Node player server then listens only on 127.0.0.1. The proxy must preserve the public `Host`, support WebSocket upgrade, and append its client address to `X-Forwarded-For`. Only a loopback peer is trusted; the last forwarded address is used.
3. **External cloud HTTPS load balancer:** set `externalTlsTermination:true` and the exact public HTTPS origin, leaving PEM paths empty and `trustProxy:false`. The HTTP player service listens on server interfaces for remote backhaul. Preserve the public Host and WebSocket Upgrade. Restrict the backend TCP port to the actual load balancer source addresses in both cloud security groups and Windows Firewall. This flag does not trust forwarded client addresses: viewer addresses remain the socket peer. Cloud authentication uses the bounded global throttle described below so failed attempts do not lock out all users sharing an ALB peer. `/health` is suitable for the load balancer health check. The load balancer must own the public certificate and HTTPS listener; this configuration does not create them.
4. **Initial public-IP test:** explicitly use an `http://IP:port` public URL without TLS or proxy. HTTP does not encrypt the access code or signalling; use HTTPS for the finished deployment.

### Optional EIP media mapping

An HTTP/HTTPS load balancer does not carry WebRTC UDP media. Where the UE host has an explicitly configured **1:1 EIP mapping preserving UDP ports 50000–50199**, the operator can create `server/media-address.json` on that deployment:

```json
{ "privateIp": "10.0.0.10", "publicIp": "203.0.113.10" }
```

These are illustrative addresses; replace both with the host's actual interface address and its bound EIP. Restart the service after editing. Public mode reads this optional file; an absent file leaves normal ICE behavior unchanged. The private IPv4 must exist on a local interface, and invalid mappings stop startup rather than advertising an unrelated host. This does not create an EIP, firewall rule, NAT mapping or TURN service.

Only authenticated UE host candidates addressed to that instance's subscribed viewer are supplemented. The native LAN/VPN candidate is retained, and a lower-preference public `srflx` candidate is added only for matching UDP host addresses within 50000–50199, with the same port. Player-supplied candidates, TCP, TURN/relay and other interfaces/ports are not rewritten.

This JSON is deployment-owned, ignored by Git, excluded from builds and forbidden in delivery manifests. The installer preserves its exact existing bytes even if an old manifest incorrectly claimed it, and aborts if it changes during staging. A portable delivery directory containing it is rejected; do not copy a server's EIP configuration into a distributable package.

`POST /api/session` creates a random 48-hex bearer token. With `accessProtectionEnabled:false` (the default), it does so without an access code and the player enters automatically. With protection enabled, both LAN and public modes require a valid code first. Explicit non-boolean values such as `"false"`, `0` or `null` are rejected. Public mode still requires a valid public URL and matching TLS arrangement even when the gate is off. Stop and restart the service to apply changes; a valid existing session token still resumes without prompting again.

The access code is not stored in browser storage. Tokens are retained per browser tab for reconnection; unused sessions expire after 12 hours. With protection enabled, LAN, native HTTPS and local proxy modes limit invalid-code attempts per client address to 20 per five minutes. Cloud load balancer mode instead throttles all access-code comparisons, including correct codes, at five per second with an initial burst of ten. Its FIFO queue holds at most twenty requests for at most four seconds; excess or expired requests receive 429 with Retry-After, and disconnect/stop releases pending requests. Records and sessions have hard bounds. Browser POST/WebSocket origins must match the configured public origin (or direct loopback testing), regardless of protection setting. `GET /health` reports `accessRequired` from the protection switch; token-protected operator `/status` includes `accessProtectionEnabled`. Neither endpoint exposes the code. Disabling access-code protection never bypasses session tokens, streamer/control authentication, IP trust boundaries, revocation or viewer limits.

Configured ICE servers are delivered to **both UE and authenticated browsers**. TURN credentials necessarily reach admitted WebRTC clients; use restricted/dedicated TURN credentials, not unrelated account passwords. The packaged server does not itself install or operate a TURN server. Without a configured TURN relay, restrictive client NAT/firewalls may prevent media even when the website opens.

An HTTPS/WebSocket ALB forwards the webpage and signalling, not WebRTC UDP media. A private-only UE server still needs a usable media path (for example, a reachable TURN relay). Successfully loading the HTTPS page does not establish video connectivity.

UE signalling stays on loopback (default TCP 8888). Each owned UE receives a random per-instance streamer token in its launch URL; upgrades must present that token, and ICE credentials are sent only after matching the owned endpoint identity. Arbitrary website Origins are rejected. The fixed loopback Origin sent by UE LibWebSockets is explicitly supported. Tokens and TURN/access secrets are redacted from operator logs. UE media uses UDP 50000–50199. Configure the external firewall/NAT with the player TCP port and these media ports. A TURN service has its own listening and relay port ranges. Merely entering a public URL cannot create an external IP, DNS record, port mapping or certificate.

## Rendering and process ownership

Shared mode starts one UE instance. Independent mode starts one per admitted session. UE initialization is queued: only one instance is `starting` at a time; its owned streamer identity must be ready, or its failed process confirmed stopped, before the next `queued` instance starts. This reduces simultaneous initialization spikes without changing existing active viewers. Cancelling a waiting session never launches its UE. The existing eight-second reconnect grace remains. Releasing a session reaps its own child before the admission queue continues. Only still-owned PIDs are targeted; the launcher additionally uses a Windows Job Object. No process-name-wide cleanup is used.

The default is 1920×1080 and a fixed 60 FPS target. `fixedFps:true` is incompatible with `adaptiveResourceBudget:true`. The project-owned `-FixedFPS` alias updates `t.MaxFPS` and `PixelStreaming2.WebRTC.Fps` together, without fixing simulation delta time. With fixed mode off, FPS may be 0 (uncapped rendering) or 15–120. PS2 capture negotiation remains positive (120 for uncapped rendering). Existing explicit frame and bitrate settings survive migration.

`encoderAsync` maps to the native `-PixelStreamingDecoupleFramerate` capture/render decoupling setting. It is not an NVENC asynchronous-encoding switch. `encoder` accepts NVIDIA or Auto; the project-owned `-PixelStreamingEncoder` alias enforces the selected hardware policy. NVIDIA mode validates NVIDIA RHI and NVENC API support and reports a startup failure instead of silently falling back to software.

The bitrate presets are balanced 1/8/24, clear 1/10/35 and ultra 1/16/50 Mbps. WebRTC controls bitrate within that range. Native PS2 encoder quality presets and min/max quality replace obsolete UE5.4 QP/rate-control flags; min quality is balanced/custom 29, clear 37, ultra 45, max 100. No forced target bitrate bypasses congestion control.

Independent budgeting no longer divides FPS solely by viewer count. Finite modes retain the selected cap until warmup and consecutive fresh acknowledged actual-FPS measurements demonstrate pressure, then recover gradually. Uncapped mode stays at 0 even with automatic budgeting enabled; it does not silently introduce a cap. Queued instances do not enter the pressure calculation. The private sequenced file bridge only applies FPS/bitrate values and cannot execute arbitrary commands. GPU timings remain diagnostic and are not summed as independent render costs. No unmeasured CPU affinity, GPU selection, or forced ICE-candidate policy is added.

Startup and first-video-frame deadlines remain 120 seconds. Browser rendering success is detected from an actual decoded video frame, not signalling readiness. Epic's pinned UE5.8 library continues to handle input and WebRTC.

## Build and verification

`node Tools/PixelStreaming/build.js` verifies the SHA-512 of the three vendored dependency archives and builds the player/server delivery. Runtime dependency is `ws`; the Epic library and SDP implementation are pinned with license files.

```text
node --test Tools/PixelStreaming/tests/*.test.js
```

Tests exercise real local HTTP, HTTPS, WS/WSS and owned mock child processes, including ten-person admission, full-capacity refusal, manual disconnect/re-entry, unauthorized management, origin validation, private ICE configuration and the access form. Browser policy tests run the actual application source against an event harness. **They do not establish actual UE video/input, external-network connectivity, or ten-instance performance on the destination server.**

`tests/fixtures/test-localhost-*.pem` is a self-signed test-only TLS identity, never copied into the deployment. Do not use it as a production certificate.

## Removed comparison service

The peer-stream sidecar, reverse proxy and comparison entry have been removed. `/peer-stream/` is no longer a player route. Viewer admission and revocation belong solely to this PixelStreaming2 service.

The public session response separates `fps` (render target; 0 allowed) from `captureFps` (positive PS2 negotiation target; equals positive FPS or 120). The browser must not set WebRTCFPS to zero. Both new and resumed sessions carry the same target.
