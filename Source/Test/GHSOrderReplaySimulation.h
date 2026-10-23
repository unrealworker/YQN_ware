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
struct TrailSegment { Vec A,B; double StartMeters=0,LengthMeters=0; };
/** Visible motion only, with collinear repeated traversals removed at initialization. */
std::vector<TrailSegment> BuildTrailSegments(const Track& Track);
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
