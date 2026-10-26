"""Replay-only blue diffusion, derived from the project's existing AGV rings.

RGB is an unlit colour, not an already-amplified light signal. The material
uses it for both decal Base Color and a restrained emissive contribution so
the rings remain blue against the warehouse's bright grey floor.
"""

REPLAY_RIPPLE_HLSL = r"""
// Three expanding waves retain the established 2 s rhythm and phase offsets.
float2 p = (UV - 0.5) * 2.0;
float r = length(p);
float angle = atan2(p.y, p.x);
float t = T + Phase;
float aa = clamp(fwidth(r), 0.0012, 0.025);
float disk = 1.0 - smoothstep(0.965, 0.995, r);

// The 165 cm decal half-size makes the main wave core about 5.3 cm wide.
// Supporting rings/arcs stay subordinate to the moving diffusion fronts.
float inner = 1.0 - smoothstep(0.006, 0.011 + aa, abs(r - 0.395));
float outer = 1.0 - smoothstep(0.007, 0.012 + aa, abs(r - 0.918));
float arcPatternA = sin(3.0 * (angle - t * 0.22));
float arcPatternB = sin(4.0 * (angle + t * 0.15) + 0.8);
float arcGateA = smoothstep(0.08, 0.08 + max(fwidth(arcPatternA), 0.05), arcPatternA);
float arcGateB = smoothstep(0.22, 0.22 + max(fwidth(arcPatternB), 0.05), arcPatternB);
float arcA = (1.0 - smoothstep(0.009, 0.015 + aa, abs(r - 0.667))) * arcGateA;
float arcB = (1.0 - smoothstep(0.008, 0.014 + aa, abs(r - 0.874))) * arcGateB;

float wave = 0.0;
float waveGradient = 1.0;
[unroll]
for (int i = 0; i < 3; ++i)
{
    float age = frac(t * 0.5 + float(i) / 3.0);
    float waveRadius = 0.36 + 0.58 * age;
    float fade = smoothstep(0.0, 0.07, age) * (1.0 - smoothstep(0.72, 1.0, age));
    float signedDistance = r - waveRadius;
    float coverage = (1.0 - smoothstep(0.016, 0.028 + aa, abs(signedDistance))) * fade;
    if (coverage > wave)
    {
        wave = coverage;
        // Pale inner tail -> theme-blue outer leading edge, matching the route.
        waveGradient = smoothstep(-0.028, 0.014, signedDistance);
    }
}

float geometry = max(0.30 * inner, 0.42 * outer);
geometry = max(geometry, max(0.64 * arcA, 0.50 * arcB));
float alpha = saturate(max(geometry, wave * 0.96)) * disk;
// Identical linear RGB ratios to the route's #8BB9FF -> #356BFA gradient.
float3 tailBlue = saturate(Tint * float3(7.2520595, 3.2997277, 1.0460543));
float3 waveBlue = lerp(tailBlue, Tint, waveGradient);
float3 blue = lerp(Tint, waveBlue, saturate(wave - geometry) / max(wave, 0.001));
return float4(blue, alpha);
"""
