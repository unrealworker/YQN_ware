"""Animated, texture-free AGV decal shader bodies for Unreal Custom nodes.

Both strings return float4 (HDR emissive RGB, opacity A). Custom inputs:
    UV:    float2, normalized decal texture coordinates (0..1).
    T:     float, seconds from a material Time expression.
    Tint:  float3, linear RGB; suitable for a vector material parameter.
    Phase: float, time offset in seconds, to stagger individual AGVs.

Use a Custom node with CMOT_FLOAT4 output; RGB feeds Emissive Color and A
feeds Opacity. All pattern dimensions are relative to decal half-size.
The decal actor controls physical size and rotation; no mesh or texture is
required by these expressions. Derivatives require pixel-shader evaluation.
"""

__all__ = ["RINGS_HLSL", "RADAR_HLSL", "DEFAULT_TINTS"]

DEFAULT_TINTS = {
    "cyan_green": (0.04, 1.00, 0.58),
    "blue": (0.03, 0.36, 1.00),
    "orange": (1.00, 0.25, 0.025),
}


RINGS_HLSL = r"""
// Three expanding rings: 2.0 s per wave, radii 0.30 -> 0.90.
// Thin stationary rings and two interrupted counter-rotating arcs.
float2 p = (UV - 0.5) * 2.0;
float r = length(p);
float angle = atan2(p.y, p.x);
float t = T + Phase;
float aa = max(fwidth(r), 0.0012);
float disk = 1.0 - smoothstep(0.965, 0.995, r);

float thinInner = 1.0 - smoothstep(0.0025, 0.0025 + aa, abs(r - 0.302));
float thinMiddle = 1.0 - smoothstep(0.0018, 0.0018 + aa, abs(r - 0.525));
float thinOuter = 1.0 - smoothstep(0.0025, 0.0025 + aa, abs(r - 0.918));

// Trigonometric angular masks stay continuous across atan2's wrap seam.
float arcPatternA = sin(3.0 * (angle - t * 0.22));
float arcPatternB = sin(4.0 * (angle + t * 0.15) + 0.8);
float arcGateA = smoothstep(0.08, 0.08 + max(fwidth(arcPatternA), 0.05), arcPatternA);
float arcGateB = smoothstep(0.22, 0.22 + max(fwidth(arcPatternB), 0.05), arcPatternB);
float arcA = (1.0 - smoothstep(0.0040, 0.0040 + aa, abs(r - 0.667))) * arcGateA;
float arcB = (1.0 - smoothstep(0.0030, 0.0030 + aa, abs(r - 0.874))) * arcGateB;

float waves = 0.0;
float waveGlow = 0.0;
[unroll]
for (int i = 0; i < 3; ++i)
{
    float age = frac(t * 0.5 + float(i) / 3.0);
    float waveRadius = 0.30 + 0.60 * age;
    float fade = smoothstep(0.0, 0.09, age) * (1.0 - smoothstep(0.55, 1.0, age));
    float distanceToWave = abs(r - waveRadius);
    waves += (1.0 - smoothstep(0.0040, 0.0040 + aa, distanceToWave)) * fade;
    waveGlow += (1.0 - smoothstep(0.009, 0.030 + aa, distanceToWave)) * fade;
}

float geometry = 0.35 * thinInner + 0.16 * thinMiddle + 0.30 * thinOuter;
geometry += 0.62 * arcA + 0.42 * arcB;
float signal = (geometry + waves * 0.85 + waveGlow * 0.11) * disk;
float alpha = saturate(signal * 0.86);
float3 emission = max(Tint, float3(0.0, 0.0, 0.0)) * signal * 4.0;
return float4(emission, alpha);
"""


RADAR_HLSL = r"""
// 80 degree fan around +V; scan travels -40 -> +40 -> -40 in 2.5 s.
// Positive signed trailing angle follows the current sweep direction.
float2 p = (UV - 0.5) * 2.0;
float r = length(p);
float angle = atan2(p.x, p.y);
float t = T + Phase;
float aa = max(fwidth(r), 0.0012);
float angularAA = max(fwidth(angle), 0.0025);
float halfAngle = 0.698131701;
float fan = 1.0 - smoothstep(halfAngle - angularAA, halfAngle, abs(angle));
float radialMask = smoothstep(0.025, 0.060, r) * (1.0 - smoothstep(0.915, 0.940, r));
float mask = fan * radialMask;

float cycle = t * 2.513274123;
float scanAngle = halfAngle * sin(cycle);
float scanVelocity = cos(cycle);
float direction = (scanVelocity >= 0.0) ? 1.0 : -1.0;
float delta = angle - scanAngle;
float beam = 1.0 - smoothstep(0.0050, 0.0050 + angularAA, abs(delta));
float beamGlow = 1.0 - smoothstep(0.010, 0.065 + angularAA, abs(delta));

float trailingAngle = -delta * direction;
float trail = smoothstep(-angularAA, angularAA, trailingAngle);
trail *= 1.0 - smoothstep(0.015, 0.290, trailingAngle);
// Fade the trailing wedge at turnarounds to avoid an abrupt side swap.
trail *= smoothstep(0.0, 0.30, abs(scanVelocity));

float polarGrid = 0.0;
[unroll]
for (int j = 0; j < 4; ++j)
{
    float gridRadius = 0.26 + float(j) * 0.22;
    polarGrid += 1.0 - smoothstep(0.0015, 0.0015 + aa, abs(r - gridRadius));
}
[unroll]
for (int k = 0; k < 5; ++k)
{
    float spokeAngle = -halfAngle + float(k) * (halfAngle * 0.5);
    polarGrid += 1.0 - smoothstep(0.0015, 0.0015 + angularAA, abs(angle - spokeAngle));
}

float pulseArcs = 0.0;
[unroll]
for (int n = 0; n < 3; ++n)
{
    float age = frac(t / 1.8 + float(n) / 3.0);
    float pulseRadius = 0.10 + age * 0.84;
    float fade = smoothstep(0.0, 0.10, age) * (1.0 - smoothstep(0.58, 1.0, age));
    pulseArcs += (1.0 - smoothstep(0.0030, 0.0030 + aa, abs(r - pulseRadius))) * fade;
}

float distanceFade = 1.0 - 0.45 * saturate(r / 0.94);
float signal = 0.012 + polarGrid * 0.055 + pulseArcs * 0.28;
signal += distanceFade * (beam * 1.05 + beamGlow * 0.16 + trail * 0.24);
signal *= mask;
float alpha = saturate(signal * 0.78);
float3 emission = max(Tint, float3(0.0, 0.0, 0.0)) * signal * 4.2;
return float4(emission, alpha);
"""
