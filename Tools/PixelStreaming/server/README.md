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

A manually disconnected browser does not automatically reconnect, including on reload. The user must explicitly choose re-entry; public mode requires the access code again. This is a connection-disconnect action, not a permanent identity/IP ban.

## Public network configuration

| Field | Purpose |
| --- | --- |
| `networkMode` | `lan` or `public` |
| `publicUrl` | Exact player origin, e.g. `https://warehouse.example`; root path only |
| `accessCode` | Public mode requires at least 12 characters |
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

`POST /api/session` exchanges the supplied access code for a random 48-hex bearer token. The access code is not stored in browser storage. Tokens are retained per browser tab for reconnection; unused sessions expire after 12 hours. Native HTTPS and local proxy modes limit invalid-code attempts per client address to 20 per five minutes. Cloud load balancer mode instead throttles all access-code comparisons, including correct codes, at five per second with an initial burst of ten. Its FIFO queue holds at most twenty requests for at most four seconds; excess or expired requests receive 429 with Retry-After, and disconnect/stop releases pending requests. Records and sessions have hard bounds. Browser POST/WebSocket origins must match the configured public origin (or direct loopback testing). A public `GET /health` exposes only basic state/count/auth-needed information.

Configured ICE servers are delivered to **both UE and authenticated browsers**. TURN credentials necessarily reach admitted WebRTC clients; use restricted/dedicated TURN credentials, not unrelated account passwords. The packaged server does not itself install or operate a TURN server. Without a configured TURN relay, restrictive client NAT/firewalls may prevent media even when the website opens.

An HTTPS/WebSocket ALB forwards the webpage and signalling, not WebRTC UDP media. A private-only UE server still needs a usable media path (for example, a reachable TURN relay). Successfully loading the HTTPS page does not establish video connectivity.

UE signalling stays on loopback (default TCP 8888). Each owned UE receives a random per-instance streamer token in its launch URL; upgrades must present that token, and ICE credentials are sent only after matching the owned endpoint identity. Arbitrary website Origins are rejected. The fixed loopback Origin sent by UE5.4 LibWebSockets is explicitly supported. Tokens and TURN/access secrets are redacted from operator logs. UE media uses UDP 50000–50199. Configure the external firewall/NAT with the player TCP port and these media ports. A TURN service has its own listening and relay port ranges. Merely entering a public URL cannot create an external IP, DNS record, port mapping or certificate.

## Rendering and process ownership

Shared mode starts one UE instance. Independent mode starts one per admitted session. Releasing a session reaps its own child before the admission queue continues. Only still-owned PIDs are targeted; the launcher additionally uses a Windows Job Object. No process-name-wide cleanup is used.

The default render target remains 1920×1080 at 60 FPS. FPS and bitrates are **targets**, not simultaneous-user performance guarantees. Independent automatic budgeting initially divides the configured FPS across active UE instances, then probes using acknowledged actual-FPS telemetry. The private sequenced file bridge can only apply bounded FPS/bitrate values. It cannot execute arbitrary console commands. GPU timings remain diagnostic and are not summed as independent render costs.

Startup and first-video-frame deadlines remain 120 seconds. Browser rendering success is detected from an actual decoded video frame, not signalling readiness. Epic's pinned UE5.4 library continues to handle input and WebRTC.

## Build and verification

`node Tools/PixelStreaming/build.js` verifies the SHA-512 of the three vendored dependency archives and builds the player/server delivery. Runtime dependency is `ws`; the Epic library and SDP implementation are pinned with license files.

```text
node --test Tools/PixelStreaming/tests/*.test.js
```

Tests exercise real local HTTP, HTTPS, WS/WSS and owned mock child processes, including ten-person admission, full-capacity refusal, manual disconnect/re-entry, unauthorized management, origin validation, private ICE configuration and the access form. Browser policy tests run the actual application source against an event harness. **They do not establish actual UE video/input, external-network connectivity, or ten-instance performance on the destination server.**

`tests/fixtures/test-localhost-*.pem` is a self-signed test-only TLS identity, never copied into the deployment. Do not use it as a production certificate.
