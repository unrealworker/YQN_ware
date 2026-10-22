#pragma once

// Fixed-cost, engine-independent traffic state. Distances are centimetres.
#include <array>
#include <vector>
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace GHSTraffic
{
constexpr int Capacity=16;
struct Route { double Length=0, MaxSpeed=0; };
struct Vehicle
{
    int Route=0, Kind=0;
    double Distance=0, Speed=0, Cruise=0, Cooldown=0;
    bool Active=false;
};
inline double HalfLength(int Kind) { return Kind==0 ? 750. : 227.; }

struct Simulation
{
    std::array<Vehicle,Capacity> Vehicles{};
    std::vector<Route> Routes;
    uint32_t RandomState=1;
    uint64_t Completed=0, Spawned=0;

    double Random()
    {
        RandomState^=RandomState<<13;RandomState^=RandomState>>17;RandomState^=RandomState<<5;
        return double(RandomState)/4294967296.;
    }
    void Initialize(std::vector<Route> InRoutes,uint32_t Seed)
    {
        Routes=std::move(InRoutes);RandomState=Seed ? Seed : 1;Completed=Spawned=0;
        for(int i=0;i<Capacity;++i)
        {
            Vehicles[i]=Vehicle{};Vehicles[i].Kind=i%4;Vehicles[i].Cooldown=Random()*6;
        }
        if(Routes.empty())return;
        // Two well-spaced vehicles per route make all four corridors alive on
        // entry, with different types and positions on every session.
        for(int i=0;i<std::min(Capacity,int(Routes.size())*2);++i)
        {
            auto& v=Vehicles[i];v.Route=i%int(Routes.size());
            v.Distance=Routes[v.Route].Length*((i/int(Routes.size()) ? .62 : .20)+Random()*.09);
            Activate(v);
        }
    }
    int ActiveCount() const
    {
        int count=0;for(const auto& v:Vehicles)count+=v.Active ? 1 : 0;return count;
    }
    void Activate(Vehicle& V)
    {
        V.Cruise=Routes[V.Route].MaxSpeed*(.78+Random()*.22)*(V.Kind==0 ? .91 : 1.);
        V.Speed=V.Cruise;V.Active=true;V.Cooldown=0;++Spawned;
    }
    void Advance(double Delta)
    {
        if(!std::isfinite(Delta)||Delta<=0||Routes.empty())return;
        // After a debugger pause, avoid a huge traffic jump or unbounded catchup.
        double remaining=std::min(Delta,.25);
        while(remaining>1.e-8)
        {
            const double dt=std::min(remaining,.05);remaining-=dt;
            const auto previous=Vehicles;
            for(auto& v:Vehicles)
            {
                if(!v.Active)
                {
                    v.Cooldown-=dt;
                    if(v.Cooldown>0)continue;
                    v.Route=std::min(int(Routes.size())-1,int(Random()*Routes.size()));
                    bool free=true;int routeCount=0;
                    for(const auto& other:Vehicles)if(other.Active&&other.Route==v.Route)
                    {
                        ++routeCount;
                        if(other.Distance<HalfLength(other.Kind)+HalfLength(v.Kind)+4000)free=false;
                    }
                    if(!free||routeCount>=4){v.Cooldown=1+Random()*2;continue;}
                    v.Distance=0;Activate(v);continue;
                }
                double allowed=Routes[v.Route].Length;
                double target=v.Cruise;
                for(const auto& other:previous)
                {
                    if(!other.Active||other.Route!=v.Route||other.Distance<=v.Distance)continue;
                    const double gap=other.Distance-v.Distance-HalfLength(v.Kind)-HalfLength(other.Kind);
                    allowed=std::min(allowed,other.Distance-HalfLength(v.Kind)-HalfLength(other.Kind)-100);
                    if(gap<600+v.Speed*1.8)target=std::min(target,std::max(0.,other.Speed+(gap-600)/2.));
                }
                v.Speed=std::min(target,v.Speed+350*dt);
                v.Distance=std::max(v.Distance,std::min(allowed,v.Distance+v.Speed*dt));
                if(v.Distance>=Routes[v.Route].Length-1.e-6)
                {
                    v.Active=false;v.Cooldown=4+Random()*12;++Completed;
                }
            }
        }
    }
};
}
