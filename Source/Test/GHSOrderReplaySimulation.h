#pragma once
#include <array>
#include <string>
#include <vector>

namespace GHSReplay
{
constexpr int ForkCount=5,TruckCount=3,CargoCount=10,DeviceCount=8,EntityCount=18;
struct Vec { double X=0,Y=0,Z=0; };
struct Key
{
    double Time=0; Vec Position; double Yaw=0,Lift=0,Door=0;
    bool Visible=true; int Owner=-1; std::string Status;
};
struct Pose
{
    Vec Position; double Yaw=0,Lift=0,Door=0; bool Visible=true; int Owner=-1;
    const std::string* Status=nullptr;
};
struct Track { std::string Id,Name,Kind,Mesh; Vec Scale{1,1,1}; std::vector<Key> Keys; std::vector<Vec> Route; };
struct Event { double Time=0; std::string Id,DeviceId,Kind,Text; };
struct Occurrence { const Event* Source=nullptr; double Time=0; long long Cycle=0; };
struct TrailSegment
{
    Vec A,B; double StartMeters=0,LengthMeters=0,StartShearCm=0,EndShearCm=0,StartHalfWidthCm=9.,EndHalfWidthCm=9.,FlowDeltaMeters=0;
    int LegId=-1; double ProgressStartMeters=0,ProgressDeltaMeters=0;
};
struct TrailDistanceKey { double Time=0,Meters=0; };
struct TrailLeg
{
    int Id=-1; double StartTime=0,EndTime=0,LengthMeters=0;
    std::vector<TrailDistanceKey> DistanceKeys;
};
struct TrailPlan { std::vector<TrailSegment> Segments; std::vector<TrailLeg> Legs; };
struct TrailState
{
    bool Moving=false; int LegId=-1;
    double StartTime=0,EndTime=0,DistanceMeters=0,LengthMeters=0;
};
constexpr double TrailWidthCm=18.,TrailCornerCutCm=80.;
/** Forklift-only cyan, shared by runtime presentation and the device list. */
const char* TrailColor(int DeviceIndex);
/** Visible motion, bounded circular joins, with repeated runs removed. */
std::vector<TrailSegment> BuildTrailSegments(const Track& Track);
/** Precompute disjoint moving legs once; stationary/lift-only/hidden spans are absent. */
TrailPlan BuildTaskTrail(const Track& Track);
/** Absolute-clock, logarithmic lookup; no geometry or instance updates. */
TrailState EvaluateTaskTrail(const TrailPlan& Plan,double Time,double CycleDuration,double PlaybackEndTime=-1.);
/** Stateless evaluation: no accumulation, spawning, physics or process wall clock. */
class Simulation
{
public:
    double CycleDuration=0;
    std::array<Track,EntityCount> Tracks;
    std::vector<Event> Events;
    std::array<Pose,EntityCount> Poses;
    bool Validate(std::string& Error) const;
    void Evaluate(double Time);
    std::vector<Occurrence> EventsIn(double Start,double End,int Limit) const;
    static Pose Sample(const Track& Track,double Time);
};
}
