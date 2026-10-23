// Private roof material: x=coverage, y=ice tint, z=leading light, w=grid afterglow.
// Progress is the component's smoothstep clock. No time-varying noise or particles.
float3 p = Position - Center;
float along = dot(p, Axis.xyz);
float across = dot(p, float3(-Axis.y, Axis.x, 0.0));
float invExtent = max(Axis.w, 0.000001);
float u = abs(along) * invExtent;
float scan = saturate((Progress - 0.04296875) / 0.8647461);
float front = scan * 1.04;
float distanceToFront = (u - front) / invExtent;
float active = smoothstep(0.0, 0.032, Progress) * (1.0 - smoothstep(0.94, 1.0, Progress));

// A narrow antialiased cut, a wider ice-blue shoulder and a restrained luminous core.
float aa = max(24.0, fwidth(distanceToFront) * 1.15);
float body = lerp(1.0, smoothstep(-aa, aa, distanceToFront), smoothstep(0.0, 0.002, scan));
float shoulder = (1.0 - smoothstep(100.0, 950.0, distanceToFront)) * body * active;
float core = (1.0 - smoothstep(45.0, max(160.0, aa * 1.4), abs(distanceToFront))) * active;

// Short-lived architectural grid follows the scan; derivative AA prevents fine flicker.
float2 q = float2(along / 1400.0, across / 800.0);
float2 cell = abs(frac(q + 0.5) - 0.5);
float2 width = max(fwidth(q), float2(0.002, 0.002));
float2 lines = 1.0 - smoothstep(width * 0.25, width * 1.1, cell);
float grid = max(lines.x, lines.y);
float trail = smoothstep(-1550.0, -950.0, distanceToFront)
            * (1.0 - smoothstep(-120.0, 0.0, distanceToFront)) * active;
float afterglow = grid * trail;
float coverage = max(body, afterglow * 0.58);
float tint = saturate(max(shoulder * 0.85, max(core, afterglow)));
return float4(coverage, tint, core, afterglow * 0.55);
