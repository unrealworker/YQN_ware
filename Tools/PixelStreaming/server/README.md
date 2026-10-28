# GHS UE5.4 Pixel Streaming service

Start with the bundled runtime:

```text
runtime/node.exe server/server.js --config launcher.config.json --control-file logs/control.json
```

The Windows launcher supplies a fresh `GHS_CONTROL_TOKEN` (at least 24 characters) only through the child environment. Configuration is read once; stop before editing settings. UE and TLS file paths can be absolute or relative to the configuration file. Chinese paths and spaces are supported without shell execution.

## Connections and operator controls

`maxViewers` defaults to **10**, configurable from 1 to 10. Both shared and independent modes count admitted browser sessions. An eleventh browser is refused with an explicit full-capacity message; existing users stay connected. A connection lost to the network holds its place for 8 seconds. Reconnecting the same token replaces only the old socket.

The token-protected management server binds **127.0.0.1** on a dynamic port written to the control file. Its routes are never available on the player port:

- `GET /status`: runtime state, `viewerCount`, `maxViewers`, `viewers`, `instances`, addresses and bounded logs.
- `POST /disconnect`, JSON `{ "playerId": "1" }`: revoke that session, send a terminal disconnect notice, release its independent UE instance and return after cleanup. Requires `Authorization: Bearer <GHS_CONTROL_TOKEN>`.
- `POST /stop`: stop the service and only its owned process tree.

Each viewer row contains `playerId`, optional `displayName`, client `address`, bounded `userAgent`, ISO UTC `connectedAt`, `instanceId`, and `state` (`starting`, `connected`, `reconnecting`, `failed`). `connected` denotes signalling subscription; actual received video/frame rate is reported in the browser. Status and logs contain neither session bearer tokens nor access/TURN secrets.

A manually disconnected browser does not automatically reconnect, including on reload. The user must explicitly choose re-entry; access-code protection, when enabled, requires the code again. This is a connection-disconnect action, not a permanent identity/IP ban.

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

`POST /api/session` creates a random 48-hex bearer token. With `accessProtectionEnabled:false` (the default), it does so without an access code and the player enters automatically. With protection enabled, both LAN and public modes require a valid code first. Explicit non-boolean values such as `"false"`, `0` or `null` are rejected. Public mode still requires a valid public URL and matching TLS arrangement even when the gate is off. Stop and restart the service to apply changes; a valid existing session token still resumes without prompting again.

The access code is not stored in browser storage. Tokens are retained per browser tab for reconnection; unused sessions expire after 12 hours. With protection enabled, LAN, native HTTPS and local proxy modes limit invalid-code attempts per client address to 20 per five minutes. Cloud load balancer mode instead throttles all access-code comparisons, including correct codes, at five per second with an initial burst of ten. Its FIFO queue holds at most twenty requests for at most four seconds; excess or expired requests receive 429 with Retry-After, and disconnect/stop releases pending requests. Records and sessions have hard bounds. Browser POST/WebSocket origins must match the configured public origin (or direct loopback testing), regardless of protection setting. `GET /health` reports `accessRequired` from the protection switch; token-protected operator `/status` includes `accessProtectionEnabled`. Neither endpoint exposes the code. Disabling access-code protection never bypasses session tokens, streamer/control authentication, IP trust boundaries, revocation or viewer limits.

Configured ICE servers are delivered to **both UE and authenticated browsers**. TURN credentials necessarily reach admitted WebRTC clients; use restricted/dedicated TURN credentials, not unrelated account passwords. The packaged server does not itself install or operate a TURN server. Without a configured TURN relay, restrictive client NAT/firewalls may prevent media even when the website opens.

An HTTPS/WebSocket ALB forwards the webpage and signalling, not WebRTC UDP media. A private-only UE server still needs a usable media path (for example, a reachable TURN relay). Successfully loading the HTTPS page does not establish video connectivity.

UE signalling stays on loopback (default TCP 8888). Each owned UE receives a random per-instance streamer token in its launch URL; upgrades must present that token, and ICE credentials are sent only after matching the owned endpoint identity. Arbitrary website Origins are rejected. The fixed loopback Origin sent by UE5.4 LibWebSockets is explicitly supported. Tokens and TURN/access secrets are redacted from operator logs. UE media uses UDP 50000–50199. Configure the external firewall/NAT with the player TCP port and these media ports. A TURN service has its own listening and relay port ranges. Merely entering a public URL cannot create an external IP, DNS record, port mapping or certificate.

## Rendering and process ownership

Shared mode starts one UE instance. Independent mode starts one per admitted session. UE initialization is queued: only one instance is `starting` at a time; its owned streamer identity must be ready, or its failed process confirmed stopped, before the next `queued` instance starts. This reduces simultaneous initialization spikes without changing existing active viewers. Cancelling a waiting session never launches its UE. The existing eight-second reconnect grace remains. Releasing a session reaps its own child before the admission queue continues. Only still-owned PIDs are targeted; the launcher additionally uses a Windows Job Object. No process-name-wide cleanup is used.

The default render target is 1920×1080, with `fps:0` meaning **no fixed render or capture frame cap**. It is not a 120/300 FPS substitute. This requires the project's patched UE5.4 PixelStreaming plugin: 0 must be supported by coupled capture and RTP sender parameters. Launch arguments disable VSync, set `t.MaxFPS 0`, keep `PixelStreaming.DecoupleFramerate 0`, and pass `PixelStreamingWebRTCFps=0`. The private runtime bridge and telemetry also preserve 0. Explicit existing FPS/bitrate settings are retained; finite caps remain 15–120.

New service defaults are 1 Mbps minimum, 8 Mbps starting and 24 Mbps maximum. The low minimum allows WebRTC congestion control to reduce traffic when the path cannot carry the starting rate. These values are not forced over an administrator's existing configuration. The encoder remains CBR with its existing NVENC preset; maximum QP is balanced/custom 36, clear 32 and ultra 28, allowing adaptation before frame loss. No fixed encoder target bitrate or disabled frame-dropper flag overrides WebRTC adaptation.

`-GHSLowLatencyPlayout` opts into the project's plugin setting for zero additional playout-delay bounds; remove this argument for A/B comparison. This cannot remove network propagation delay or guarantee a particular browser buffer. Real decoded-video statistics remain necessary to verify improvement.

Independent budgeting no longer divides FPS solely by viewer count. Finite modes retain the selected cap until warmup and consecutive fresh acknowledged actual-FPS measurements demonstrate pressure, then recover gradually. Uncapped mode stays at 0 even with automatic budgeting enabled; it does not silently introduce a cap. Queued instances do not enter the pressure calculation. The private sequenced file bridge only applies FPS/bitrate values and cannot execute arbitrary commands. GPU timings remain diagnostic and are not summed as independent render costs. No unmeasured CPU affinity, GPU selection, or forced ICE-candidate policy is added.

Startup and first-video-frame deadlines remain 120 seconds. Browser rendering success is detected from an actual decoded video frame, not signalling readiness. Epic's pinned UE5.4 library continues to handle input and WebRTC.

## Build and verification

`node Tools/PixelStreaming/build.js` verifies the SHA-512 of the three vendored dependency archives and builds the player/server delivery. Runtime dependency is `ws`; the Epic library and SDP implementation are pinned with license files.

```text
node --test Tools/PixelStreaming/tests/*.test.js
```

Tests exercise real local HTTP, HTTPS, WS/WSS and owned mock child processes, including ten-person admission, full-capacity refusal, manual disconnect/re-entry, unauthorized management, origin validation, private ICE configuration and the access form. Browser policy tests run the actual application source against an event harness. **They do not establish actual UE video/input, external-network connectivity, or ten-instance performance on the destination server.**

`tests/fixtures/test-localhost-*.pem` is a self-signed test-only TLS identity, never copied into the deployment. Do not use it as a production certificate.
