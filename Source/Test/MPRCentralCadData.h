// Generated from the original MPR CAD audit. Do not hand-edit surveyed XY.
// Z, carrier count, speed, lift cycle and belt detail are display parameters.
#pragma once
namespace MPRCentralCad
{
struct Worker { double Feet[3]; double Yaw; double Table[3]; };
inline constexpr Worker Workers[] = {
    {{-10637.18077000,-317.34770600,0.00000000},0.0,{-10567.12353600,-282.19858500,103.50000000}},
    {{-10637.18077000,-157.34770600,0.00000000},0.0,{-10567.12353600,-122.19858500,103.50000000}},
    {{-10637.18077000,2.65229400,0.00000000},0.0,{-10567.12353600,37.80141500,103.50000000}},
    {{-10228.14762200,2592.64077500,0.00000000},180.0,{-10300.87353600,2562.80141500,103.50000000}},
    {{-10228.14762200,2750.31528000,0.00000000},180.0,{-10300.87353600,2722.80141500,103.50000000}},
    {{-10228.14762200,2917.84442900,0.00000000},180.0,{-10300.87353600,2882.80141500,103.50000000}},
};
inline constexpr double Center64[3]={-10433.998536,1300.301415,0};
inline constexpr double Center120[3]={-11155.743336,-1636.737051,0};
inline constexpr double Half64=1800,Radius64=54,Half120=367.1,Radius120=44;
inline constexpr const char* SourceSha256="c316aafe183162c5bef636885b59cc1000c3eecf50d8be645490b4716c6af863";
inline constexpr const char* AuditSha256="ff8e4f19c96786a5ea7c787253af0c0cc54704a44faf815446b1e75795f23063";
}
